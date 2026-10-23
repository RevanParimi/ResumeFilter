"""R2-S2-T2: real Chrome reports, scratch migrated SQL, fake providers.

Uses the established CDP/app lifecycle harness. Fixtures use real extraction,
timeline and fingerprint checks; only historical/absent/unknown snapshots are
seeded directly in this disposable store. Requires Chrome and CDN internet.
"""

import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import check_ui_screening_browser as browser
from _smoke import Smoke


async def main():
    scratch = Path(tempfile.mkdtemp(prefix="r2-s2-t2-browser-"))
    print(f"Synthetic review-context artifacts: {scratch}", flush=True)
    original_main_run, original_popen, original_checks = browser.run, subprocess.Popen, browser.S
    browser.S = checks = Smoke("R2-S2-T2 rendered review context / API compatibility")
    owned, state = [], {}
    log = (scratch / "server.log").open("w", encoding="utf-8")
    for attr in ("API_PORT", "CDP_PORT"):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            setattr(browser, attr, sock.getsockname()[1])
    browser.API_BASE = f"http://localhost:{browser.API_PORT}"
    browser.UI_URL = browser.API_BASE + "/ui/Veritas.dc.html"

    def launch(args, **kwargs):
        if "app.main:app" in args:
            args = ["smoke_r2_s2_t1:create_smoke_app" if a == "app.main:app" else a for a in args] + ["--factory"]
            env = {k: v for k, v in kwargs["env"].items() if not k.startswith("DEE_")}
            env.update({k: v for k, v in kwargs["env"].items() if k in {
                "DEE_CANDIDATES_DB_URL", "DEE_FLYWHEEL_PATH", "DEE_EMAIL_CAPTURE_PATH", "DEE_API_AUTH_KEY"}})
            env.update({
                "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_ENV": "local",
                "DEE_OPENROUTER_API_KEY": "", "DEE_LLM_MAX_RETRIES": "0",
                "DEE_GITHUB_TOKEN": "", "DEE_GITHUB_API_BASE": "http://127.0.0.1:9",
                "DEE_EMAIL_PROVIDER": "capture", "DEE_SPEECH_PROVIDER": "local",
                "DEE_VECTORSTORE_BACKEND": "memory", "DEE_LOGIN_OTP_DEBUG_ECHO": "false",
                "DEE_LOGIN_OTP_STATIC_CODE": "", "DEE_SESSION_COOKIE_SECURE": "false",
                "DEE_SESSION_COOKIE_SAMESITE": "lax",
                "PYTHONPATH": os.pathsep.join(str(p) for p in (browser.ROOT / "src", browser.ROOT / "scripts", browser.ROOT)),
            })
            state["url"] = env["DEE_CANDIDATES_DB_URL"]
            (scratch / "scratch-db.txt").write_text(state["url"], encoding="utf-8")
            kwargs.update(env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT)
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = original_popen(args, **kwargs)
        owned.append(proc)
        return proc

    def require(response):
        assert response.status_code == 200, (response.request.url.path, response.status_code)
        return response.json()

    async def run(tab, mailbox, files, admin):
        await tab.js(browser.HELPERS)
        assert await tab.wait("window.__has('Sign in')", 60, "login")
        await tab.js("window.__click('button', 'Create account')")
        assert await tab.wait("document.querySelector('input[placeholder=\"Sampoorna Staffing\"]')", 15)
        email = "review-context@example.com"
        await tab.js("window.__type('input[placeholder=\"Sampoorna Staffing\"]', 'Synthetic Review Context')")
        await tab.js(f"window.__type('input[type=email]', {json.dumps(email)})")
        await tab.js("window.__click('button', 'Create account and send code')")
        assert await tab.wait("document.querySelectorAll('input[inputmode]').length === 6", 30)
        code = browser._code_for(mailbox, email)
        await tab.js(f"window.__type('input[inputmode]', {json.dumps(code)})")
        await tab.js("window.__click('button', 'Verify and continue')")
        checks.check("real org signup and session reach queue", await tab.wait("window.__has('Nothing screened yet')", 30))

        texts = {n: (browser.FIXTURES / f"style_{n}_resume.txt").read_text(encoding="utf-8") for n in ("plain", "polished")}
        def body(text, email):
            return text.replace("Synthetic Taylor", "Synthetic Taylor\nEmail: " + email)

        with browser._org_client(admin) as org:
            require(org.post("/jobs", json={"title": "Synthetic Review Role", "must_have_skills": ["python"]}))
            await tab.js("window.__click('button', 'Roles')")
            checks.check("employer empty board renders an honest state", await tab.wait("window.__has('Nothing to rank yet')", 20))
            await tab.js("window.__click('button', 'Batches')")
            require(admin.post("/candidates", json={"evaluate": False, "resume_text":
                "Synthetic Botanical\nEmail: botanical@example.com\n" + " ".join(f"botanical{i} specimen{i} catalog{i}" for i in range(60))}))

            def batch(name, inputs):
                b = require(org.post("/screening/batches", json={"name": name, "domain": "data_eng",
                    "items": [{"resume_text": text} for text in inputs]}))
                for _ in range(20):
                    if not require(org.post(f'/screening/batches/{b["id"]}/process'))["remaining"]:
                        break
                rows = require(org.get(f'/screening/batches/{b["id"]}/queue'))["rows"]
                assert len(rows) == len(inputs) and all(r["report_id"] for r in rows)
                return b, rows

            clean_batch, clean_rows = batch("Plain and polished truthful", [body(t, "paired@example.com") for t in texts.values()])
            clean_reports = [require(org.get(f'/screening/reports/{r["report_id"]}')) for r in clean_rows]
            plain = next(r for r in clean_reports if r["ai_generation"]["band"] != "likely")
            polished = next(r for r in clean_reports if r["ai_generation"]["band"] == "likely")
            checks.check("paired API reports have identical low factual risk", plain["fabrication_risk"] == polished["fabrication_risk"] and plain["fabrication_risk"]["band"] == "low")
            checks.check("API retains style wire fields with descriptive summary", "likelihood" in polished["ai_generation"] and "Writing-style observations" in polished["summary"] and "likelihood" not in polished["summary"].lower())

            overlap = texts["polished"].replace("Jan 2019 - Dec 2021", "Jan 2021 - Dec 2023")
            for text in (texts["plain"], overlap):
                require(admin.post("/candidates", json={"resume_text": body(text, "reference@example.com"), "evaluate": False}))
            detail_batch, detail_rows = batch("Specific observations and missing coverage", [
                body(text, label + "@example.com").replace("Synthetic Taylor", "Synthetic " + label)
                for label, text in (("overlap", overlap), ("duplicate", texts["plain"]),
                    ("historical", texts["plain"]), ("absent", texts["plain"]), ("unknown", texts["plain"]))
            ] + ["Skills: Python"])
            details = [require(org.get(f'/screening/reports/{r["report_id"]}')) for r in detail_rows]
            profiles = {r["candidate_id"]: require(admin.get(f'/candidates/{r["candidate_id"]}')) for r in details}
            reports = {label: next(r for r in details if profiles[r["candidate_id"]]["full_name"] == "Synthetic " + label)
                       for label in ("overlap", "duplicate", "historical", "absent", "unknown")}
            reports["missing"] = next(r for r in details if r["fabrication_risk"]["band"] == "insufficient_data")
            checks.check("real timeline finding and content matches reach org API", any(f["id"] == "timeline_overlap" for f in reports["overlap"]["cross_field"]["findings"]) and bool(reports["duplicate"]["resume_farm"]["matches"]))
            checks.check("org overlap API withholds matched identities", all(m["candidate_id"] is None and m["resume_id"] is None for m in reports["duplicate"]["resume_farm"]["matches"]))
            private_matches = require(admin.get(f'/report/{reports["duplicate"]["id"]}'))["resume_farm"]["matches"]
            other = require(admin.post("/ledger/orgs", json={"name": "Synthetic Other Reviewer"}))
            denied = admin.get(f'/screening/reports/{polished["id"]}', headers={"X-Org-Key": other["api_key"]})
            checks.check("report explanations retain org ownership refusal", denied.status_code == 404)

            from app.reports.models import ReportRow
            engine = create_engine(state["url"])
            with Session(engine) as session:
                historical = session.get(ReportRow, reports["historical"]["id"])
                old = deepcopy(historical.body)
                old["summary"] = "Synthetic stored historical summary; original wording retained."
                old["fabrication_risk"] = {"score": .72, "confidence": .6, "band": "moderate", "advisory": True,
                    "reasoning": "Historical style-inclusive fusion", "components": [{"id": "ai_generation", "band": "likely", "risk": .75, "confidence": .8, "weight": .8, "flagged": True}]}
                historical.body = old
                absent = session.get(ReportRow, reports["absent"]["id"])
                empty = deepcopy(absent.body)
                for field in ("fabrication_risk", "ai_generation", "cross_field", "resume_farm"):
                    empty[field] = None
                absent.body = empty
                unknown = session.get(ReportRow, reports["unknown"]["id"])
                unsupported = deepcopy(unknown.body)
                unsupported["fabrication_risk"].update(scorer_version=9, score=.99)
                unknown.body = unsupported
                session.commit()

            async def show(b, report, label):
                await tab.js("window.__click('button', 'Batches')")
                assert await tab.wait(f"window.__has({json.dumps(b['name'])})", 20, "batch list")
                await tab.js(f"window.__click('[role=button]', {json.dumps(b['name'])})")
                rows = require(org.get(f'/screening/batches/{b["id"]}/queue'))["rows"]
                index = next(i for i, r in enumerate(rows) if r["report_id"] == report["id"])
                assert await tab.wait(browser.ROW_SELECTOR + f".length === {len(rows)}", 20, "queue rows")
                await tab.js("(" + browser.ROW_SELECTOR + f")[{index}].click()")
                assert await tab.wait("window.__has('Claim by claim')", 20, label)
                text = await tab.text()
                (scratch / f"{label}.txt").write_text(text, encoding="utf-8")
                return text

            ptext = await show(clean_batch, plain, "plain")
            low_ring = await tab.js("({label:document.querySelector('[data-review-index]').getAttribute('aria-label'), background:getComputedStyle(document.querySelector('[data-review-index]')).backgroundImage})")
            qtext = await show(clean_batch, polished, "polished")
            checks.check("plain and polished UI separates style without authorship likelihood", all("Writing-style observations" in t and "writing style is excluded" in t and "likelihood" not in t.lower() and "AI generation" not in t for t in (ptext, qtext)) and "Text observation:" in qtext)
            checks.check("low UI has a numeric index and explained coverage", "low" in ptext.lower() and "Low means few concerns" in ptext and "0.10" in low_ring["label"] and "conic-gradient" in low_ring["background"])
            otext = await show(detail_batch, reports["overlap"], "overlap")
            checks.check("UI renders exact timeline finding with candidate clarification", all(f["detail"] in otext for f in reports["overlap"]["cross_field"]["findings"]) and "concurrent, contract or part-time" in otext)
            dtext = await show(detail_batch, reports["duplicate"], "duplicate")
            checks.check("UI renders corpus matches and template uncertainty without identities", "Content match 1:" in dtext and "estimated text overlap" in dtext and "Shared templates are legitimate" in dtext and all(m["candidate_id"] not in dtext and m["resume_id"] not in dtext for m in private_matches))
            mtext = await show(detail_batch, reports["missing"], "missing")
            missing_ring = await tab.js("({label:document.querySelector('[data-review-index]').getAttribute('aria-label'), background:getComputedStyle(document.querySelector('[data-review-index]')).backgroundImage})")
            checks.check("insufficient coverage is a refusal distinct from low", "Cannot assess factual risk" in mtext and "This is not a low score" in mtext and "insufficient data" in mtext.lower() and missing_ring["label"] == "Review index unavailable" and missing_ring["background"] == "none")
            htext = await show(detail_batch, reports["historical"], "historical")
            checks.check("historical v1 UI preserves original score and identifies style inclusion", "Historical assessment" in htext and "v1" in htext and "0.72" in htext and "included writing style" in htext and old["summary"] in htext)
            atext = await show(detail_batch, reports["absent"], "absent")
            checks.check("absent fields render missing-check and style states", "No factual review assessment" in atext and "No style assessment was recorded" in atext and "Excluded from index: check unavailable" in atext)
            utext = await show(detail_batch, reports["unknown"], "unknown")
            checks.check("unsupported version does not present an interpretable score", "Unsupported scorer version 9" in utext and "unsupported version" in utext.lower() and "0.99" not in utext)
            with Session(engine) as session:
                checks.check("reading historical UI never rewrites its JSON", session.get(ReportRow, reports["historical"]["id"]).body == old)
            engine.dispose()

            before_reload = await tab.js("performance.timeOrigin")
            await tab.send("Page.reload")
            assert await tab.wait(f"performance.timeOrigin !== {before_reload} && document.readyState === 'complete' && document.querySelector('button')", 60, "new report document")
            await tab.js(browser.HELPERS)
            checks.check("reload restores the same authorized saved report",
                await tab.wait("window.__has('Unsupported scorer version 9')", 30)
                and await tab.js("new URLSearchParams(location.hash.slice(1)).get('report')") == reports["unknown"]["id"])
            # Real 404 after erasing only this task's synthetic candidate.
            await show(detail_batch, reports["overlap"], "before-error")
            await tab.js("window.__click('button', 'Back to screening queue')")
            erased = admin.delete(f'/candidates/{reports["overlap"]["candidate_id"]}')
            assert erased.status_code in (200, 204), erased.status_code
            # The rendered queue still holds the old report id until refresh.
            await tab.js(f"window.__click('[role=button]', {json.dumps(reports['overlap']['candidate_id'][:12])})")
            checks.check("real missing-report error renders without stale assessment", await tab.wait("window.__has('not found') || window.__has('no longer')", 20, "report 404") and not await tab.js("window.__has('Claim by claim')"))
            await tab.js("window.__click('button', 'Batches')")
            checks.check("UI recovers to remaining batch after error", await tab.wait(f"window.__has({json.dumps(clean_batch['name'])})", 20))
            await tab.js("window.__click('button', 'Roles')")
            checks.check("real role view explains advisory ranking context", await tab.wait("window.__has('Synthetic Review Role') && window.__has('Match score measures skill and role fit')", 20) and not await tab.js("window.__has('fraud screen')"))
            require(admin.post("/features/materialize", json={}))
            # Re-select through the visible saved role to fetch its new board.
            assert await tab.js("[...document.querySelectorAll('div')].find(e => e.textContent.trim() === 'Synthetic Review Role').click(); true")
            role = require(org.get("/jobs"))[0]
            ranked = require(org.get(f"/jobs/{role['id']}/board"))["match"]["ranked"]
            assert ranked
            checks.check("materialized employer board renders actual candidates", await tab.wait(
                f"!window.__has('Nothing to rank yet') && window.__has({json.dumps(ranked[0]['candidate_id'])}) && window.__has('coverage')", 20))
            await tab.js("window.__click('button', 'Comp intelligence')")
            checks.check("compensation screen renders the wrapped static benchmark", await tab.wait("window.__has('p50') && window.__has('static prior alone')", 20)
                and not await tab.js("window.__has('NaN')"))
            before = await tab.js("performance.timeOrigin")
            await tab.send("Page.reload")
            assert await tab.wait(f"performance.timeOrigin !== {before} && document.readyState === 'complete'", 60)
            await tab.js(browser.HELPERS)
            assert await tab.wait("window.__has('Sign out')", 30)
            assert await tab.js("window.__click('button', 'Comp intelligence')")
            checks.check("new document reload retains employer compensation", await tab.wait("window.__has('p50') && window.__has('static prior alone')", 30))
            await tab.js("""window.__employerFetch = window.fetch;
window.fetch = (url, init) => String(url).endsWith('/board')
  ? Promise.resolve(new Response(JSON.stringify({detail:'synthetic employer read failure'}), {status:503, headers:{'Content-Type':'application/json'}}))
  : window.__employerFetch(url, init);""")
            await tab.js("window.__click('button', 'Roles')")
            assert await tab.js("[...document.querySelectorAll('div')].find(e => e.textContent.trim() === 'Synthetic Review Role').click(); true")
            checks.check("employer board error renders without a stale shortlist", await tab.wait("window.__has('synthetic employer read failure') && !window.__has('coverage')", 20))
            await tab.js("window.fetch = window.__employerFetch")
            assert await tab.js("[...document.querySelectorAll('div')].find(e => e.textContent.trim() === 'Synthetic Review Role').click(); true")
            checks.check("employer board recovers after failed read", await tab.wait("window.__has('coverage') && !window.__has('synthetic employer read failure')", 20))
            await tab.js("""window.fetch = (url, init) => String(url).endsWith('/comp')
  ? Promise.resolve(new Response(JSON.stringify({detail:'synthetic compensation read failure'}), {status:503, headers:{'Content-Type':'application/json'}}))
  : window.__employerFetch(url, init);""")
            await tab.js("window.__click('button', 'Comp intelligence')")
            checks.check("compensation read failure renders explicit missing benchmark without stale band",
                await tab.wait("window.__has('synthetic compensation read failure') && window.__has('benchmark for this requisition did not load')", 20)
                and not await tab.js("window.__has('static prior alone')"))
            await tab.js("window.fetch = window.__employerFetch")
            await tab.js("window.__click('button', 'Roles')")
            await tab.js("window.__click('button', 'Comp intelligence')")
            checks.check("compensation recovers through explicit navigation after read failure",
                await tab.wait("window.__has('p50') && window.__has('static prior alone') && !window.__has('synthetic compensation read failure')", 20))
            await tab.js("window.__click('button', 'Instant check')")
            await tab.js("window.__click('button', 'Evaluate this resume')")
            checks.check("Instant check refuses empty input without a fictional result",
                await tab.wait("window.__has('Paste readable resume text or attach a PDF')", 20)
                and not await tab.js("document.querySelector('[data-review-index]')"))
        checks.check("no browser console errors or uncaught exceptions", not tab.console, "; ".join(tab.console[:3]))

    browser.run, subprocess.Popen = run, launch
    try:
        return await browser.main()
    finally:
        browser.run, subprocess.Popen, browser.S = original_main_run, original_popen, original_checks
        for proc in owned:
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
        log.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
