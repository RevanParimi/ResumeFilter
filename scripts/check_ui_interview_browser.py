"""Real candidate text interviews on migrated scratch SQL with fake providers.

Transport failures and saved historical/expiry fixtures are synthetic. Start,
answers, conflicts, finish, ownership, reload and session loss use actual HTTP.
Requires Chrome/internet for the existing CDN runtime; never sends real email/SMS.
"""
import asyncio
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile

from sqlalchemy import create_engine, update

import check_ui_screening_browser as browser
from _smoke import Smoke
from app.interview.models import InterviewSessionRow, InterviewTurnRow
from app.interview.scoring import SCORER_VERSION


async def main():
    scratch = Path(tempfile.mkdtemp(prefix="r3-s3-t2b-browser-"))
    print(f"Synthetic interview browser evidence: {scratch}", flush=True)
    checks = Smoke("R3-S3-T2B candidate interview browser")
    original_run, original_popen = browser.run, subprocess.Popen
    log = (scratch / "server.log").open("w", encoding="utf-8")
    owned, state = [], {}
    for attr in ("API_PORT", "CDP_PORT"):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); setattr(browser, attr, sock.getsockname()[1])
    browser.API_BASE = f"http://localhost:{browser.API_PORT}"
    browser.UI_URL = browser.API_BASE + "/ui/Veritas.dc.html"

    def launch(args, **kwargs):
        if "app.main:app" in args:
            args = ["smoke_r3_s1_t2:create_smoke_app" if a == "app.main:app" else a for a in args] + ["--factory"]
            inherited = kwargs["env"]
            env = {k: v for k, v in inherited.items() if not k.startswith("DEE_")}
            env.update({k: v for k, v in inherited.items() if k in {
                "DEE_CANDIDATES_DB_URL", "DEE_FLYWHEEL_PATH", "DEE_EMAIL_CAPTURE_PATH", "DEE_API_AUTH_KEY"}})
            env.update({
                "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_ENV": "local",
                "DEE_OPENROUTER_API_KEY": "", "DEE_LLM_MAX_RETRIES": "0",
                "DEE_GITHUB_TOKEN": "", "DEE_GITHUB_API_BASE": "http://127.0.0.1:9",
                "DEE_EMAIL_PROVIDER": "capture", "DEE_SPEECH_PROVIDER": "local",
                "DEE_VECTORSTORE_BACKEND": "memory", "DEE_LOGIN_OTP_DEBUG_ECHO": "false",
                "DEE_VERIF_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_STATIC_CODE": "",
                "DEE_SESSION_COOKIE_SECURE": "false", "DEE_SESSION_COOKIE_SAMESITE": "lax",
                "PYTHONPATH": os.pathsep.join(str(p) for p in (browser.ROOT / "src", browser.ROOT / "scripts", browser.ROOT)),
            })
            state["db"] = env["DEE_CANDIDATES_DB_URL"]
            kwargs.update(env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT)
        if os.name == "nt": kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = original_popen(args, **kwargs); owned.append(proc); return proc

    async def run(tab, mailbox, files, admin):
        email = "interview-browser@example.com"
        private = "Synthetic private answer: I compared the baseline and restored the failed parser because tokenization changed."
        def require(response):
            assert response.status_code == 200, response.status_code
            return response.json()
        def resume(name, address):
            return f"{name}\nEmail: {address}\nEXPERIENCE\nEngineer at Acme, 2020 - 2024\nSKILLS\nPython, SQL, Spark"
        cid = require(admin.post("/candidates", json={"evaluate": False,
            "resume_text": resume("Synthetic Interview Candidate", email)}))["candidate_id"]
        key = require(admin.post(f"/candidates/{cid}/auth-key"))["access_key"]
        other_email = "other-interview-browser@example.com"
        other = require(admin.post("/candidates", json={"evaluate": False,
            "resume_text": resume("Synthetic Other Interview", other_email)}))["candidate_id"]
        other_key = require(admin.post(f"/candidates/{other}/auth-key"))["access_key"]
        engine = create_engine(state["db"], hide_parameters=True)
        async def click(label):
            assert await tab.js("window.__click('button'," + json.dumps(label) + ")"), label
        async def login(address):
            await tab.js(browser.HELPERS)
            assert await tab.wait("window.__has('Sign in')", 45)
            await click("Candidate"); await click("Create account")
            assert await tab.js(f"window.__type('input[type=email]',{json.dumps(address)})")
            await click("Create account and send code")
            assert await tab.wait("document.querySelectorAll('input[inputmode]').length === 6", 20)
            code = browser._code_for(mailbox, address)
            await tab.js(f"window.__type('input[inputmode]',{json.dumps(code)})")
            await click("Verify and continue")
            assert await tab.wait("window.__has('Sign out')", 25)
        async def enter():
            await click("Interview")
            assert await tab.wait("window.__q('button','Refresh saved interviews') && !window.__q('button','Refresh saved interviews').disabled", 25)
        async def question_id():
            return await tab.js("document.querySelector('[data-interview-question]')?.getAttribute('data-interview-question')")
        async def session_id():
            return await tab.js("document.querySelector('[data-interview-session]')?.getAttribute('data-interview-session')")
        async def type_answer(value=private):
            assert await tab.js("(() => {const el=document.querySelector('#interview-answer'); if(!el || el.disabled) return false; Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(el,"
                + json.dumps(value) + "); el.dispatchEvent(new Event('input',{bubbles:true})); return true;})()")
        async def refresh():
            await click("Refresh saved interviews")
            assert await tab.wait("!window.__q('button','Refresh saved interviews').disabled", 25)
        async def reload():
            before = await tab.js("performance.timeOrigin")
            await tab.send("Page.reload")
            assert await tab.wait(f"performance.timeOrigin !== {before} && document.readyState === 'complete' && document.querySelector('button')", 60)
            await tab.js(browser.HELPERS)
            assert await tab.wait("window.__has('Sign out')", 25)
            await enter()
        async def install_transport():
            await tab.js("""
window.__nativeFetch=window.fetch; window.__writes=[]; window.__fault=null;
window.fetch=async (url,init)=>{
 if(init?.method==='POST' && url.startsWith('/portal/interviews')) {
  window.__writes.push({url,body:JSON.parse(init.body)});
  const fault=window.__fault; window.__fault=null;
  if(fault==='503') return new Response(JSON.stringify({detail:'synthetic unavailable'}),{status:503,headers:{'Content-Type':'application/json'}});
  if(fault==='malformed') return new Response('{}',{status:200,headers:{'Content-Type':'application/json'}});
  if(fault==='stall') return new Promise(()=>{});
  if(fault==='hold') await new Promise(resolve=>{window.__release=resolve;});
  const response=await window.__nativeFetch(url,init);
  if(fault==='lose') {await response.text(); throw new TypeError('synthetic lost acknowledgement');}
  if(fault==='holdAck') await new Promise(resolve=>{window.__releaseAck=resolve;});
  return response;
 }
 return window.__nativeFetch(url,init);
};
window.__nativePost=window.VeritasAPI.post;
window.VeritasAPI.post=(path,body,opts)=>window.__nativePost(path,body,window.__shortDeadline?{timeoutMs:50}:opts);
""")
        async def recovery_assertion(label):
            checks.check(label, await tab.wait("window.__has('Read-only until saved state is refreshed')", 20)
                and await tab.js("document.querySelector('#interview-answer').disabled")
                and not await tab.js("document.querySelector('[data-interview-assessment]')"))
        try:
            await login(email); await enter()
            checks.check("new candidate sees actual empty interview list and no recorder/sample questions", await tab.js("window.__has('No saved interviews') && !window.__has('Sample data') && !window.__has('Recording')"))
            await install_transport()
            await tab.js("window.__fault='hold'; window.__click('button','Start new interview'); window.__click('button','Start new interview')")
            assert await tab.wait("window.__release", 10)
            checks.check("duplicate start clicks post once without optimistic question", await tab.js("window.__writes.length===1 && !document.querySelector('[data-interview-question]')"))
            await tab.js("window.__release()")
            assert await tab.wait("document.querySelector('#interview-answer') && !document.querySelector('#interview-answer').disabled", 25)
            sid, first = await session_id(), await question_id()
            checks.check("real start returns server question and saved expiry", bool(first) and bool(sid) and await tab.js("window.__has('Expires:') && !window.__has('Session ends in 1:52')"))
            checks.check("other candidate cannot read answer or finish this session", all(r.status_code == 404 for r in [
                admin.get(f"/portal/interviews/{sid}", headers={"X-Candidate-Key": other_key}),
                admin.post(f"/portal/interviews/{sid}/answers", headers={"X-Candidate-Key": other_key}, json={"question_id":first,"text":"foreign"}),
                admin.post(f"/portal/interviews/{sid}/finish", headers={"X-Candidate-Key": other_key}, json={})]))
            await type_answer()
            await tab.js("window.__fault='hold'; window.__release=null; window.__click('button','Submit answer'); window.__click('button','Submit answer')")
            assert await tab.wait("window.__release", 10)
            checks.check("duplicate answer clicks carry exact loaded question/text once", await tab.js("window.__writes.filter(w=>w.url.endsWith('/answers')).length") == 1
                and await tab.js("window.__writes.at(-1).body") == {"question_id": first, "text": private})
            await tab.js("window.__release()")
            assert await tab.wait("document.querySelectorAll('[data-interview-turn]').length===1 && !document.querySelector('#interview-answer').disabled", 25)
            second = await question_id()
            checks.check("answer displays saved transcript and advances to server next question", second != first and await tab.js("document.querySelector('#interview-answer').value===''"))
            await type_answer("unsent reload draft"); await reload()
            checks.check("reload resumes saved next question and transcript with no unsent draft", await question_id() == second
                and await tab.js("document.querySelectorAll('[data-interview-turn]').length===1 && document.querySelector('#interview-answer').value===''")
                and private in await tab.text())
            await install_transport()
            await type_answer("CSRF refused draft")
            await tab.js("window.__csrfCookie=document.cookie.split(';').find(p=>p.trim().startsWith('dee_csrf=')).trim(); document.cookie='dee_csrf=; Max-Age=0; Path=/'")
            await click("Submit answer")
            await recovery_assertion("actual CSRF refusal settles without consuming an answer")
            await tab.js("document.cookie=window.__csrfCookie+'; Path=/; SameSite=Lax'")
            await refresh()
            for fault in ("503", "malformed", "stall"):
                await type_answer("retain uncertain draft")
                await tab.js(f"window.__fault={json.dumps(fault)}; window.__shortDeadline={str(fault=='stall').lower()}")
                await click("Submit answer")
                await recovery_assertion("synthetic " + fault + " settles in read-only recovery")
                checks.check("failed write retains read-only draft: " + fault, await tab.js("document.querySelector('#interview-answer').value") == "retain uncertain draft")
                await tab.js("window.__shortDeadline=false")
                count = await tab.js("window.__writes.length")
                await refresh()
                checks.check("refresh reads without replay: " + fault, await tab.js("window.__writes.length") == count
                    and await tab.js("document.querySelector('#interview-answer').value==='' && !document.querySelector('#interview-answer').disabled"))
            # A second client advances the saved question; the actual stale browser POST must refuse.
            require(admin.post(f"/portal/interviews/{sid}/answers", headers={"X-Candidate-Key": key}, json={"question_id":second,"text":private}))
            await type_answer("stale browser answer"); await click("Submit answer")
            await recovery_assertion("actual stale question returns conflict without consuming a turn")
            await refresh()
            checks.check("stale recovery uses saved current question and clears old draft", await question_id() != second
                and await tab.js("document.querySelectorAll('[data-interview-turn]').length===2 && document.querySelector('#interview-answer').value===''") )
            # Real expiry is a scratch-DB clock fixture; both POST and refreshed read are actual HTTP.
            with engine.begin() as db:
                db.execute(update(InterviewSessionRow).where(InterviewSessionRow.id==sid).values(expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)))
            await type_answer("expired answer"); await click("Submit answer")
            await recovery_assertion("actual expiry during browser answer refuses visibly")
            await refresh()
            checks.check("expired read says expired and offers no writable question", await tab.js("window.__has('This interview expired') && !document.querySelector('#interview-answer') && !window.__has('abandoned')"))
            await click("GenAI")
            await click("Start new interview")
            assert await tab.wait("document.querySelector('#interview-answer') && !document.querySelector('#interview-answer').disabled", 25)
            next_sid = await session_id()
            checks.check("new interview uses the candidate's chosen domain", require(admin.get(f"/portal/interviews/{next_sid}", headers={"X-Candidate-Key":key}))["session"]["domain"] == "genai")
            await type_answer(); await tab.js("window.__fault='lose'"); await click("Submit answer")
            await recovery_assertion("lost actual committed acknowledgement stays uncertain until read")
            count = await tab.js("window.__writes.length")
            await refresh()
            checks.check("saved read recovers committed answer without another POST", await tab.js("window.__writes.length") == count
                and await tab.js("document.querySelectorAll('[data-interview-turn]').length===1 && document.querySelector('#interview-answer').value===''") )
            await click("Finish interview early")
            checks.check("early finish requires confirmation and explains missing coverage", await tab.js("window.__has('Unanswered questions reduce coverage') && !document.querySelector('[data-interview-assessment]')"))
            await click("Confirm finish")
            assert await tab.wait("document.querySelector('[data-interview-assessment]') && !window.__q('button','Refresh saved interviews').disabled", 25)
            result = require(admin.get(f"/portal/interviews/{next_sid}", headers={"X-Candidate-Key":key}))["session"]
            checks.check("completed browser assessment equals saved versioned advisory result", result["status"]=="completed" and result["assessment"]["scorer_version"]==SCORER_VERSION
                and await tab.js("window.__has('Saved scorer version: s73.2') && window.__has('not poor ability') && !document.querySelector('#interview-answer')"))
            shot = await tab.send("Page.captureScreenshot"); (scratch/"saved-assessment.png").write_bytes(base64.b64decode(shot["data"]))
            # Frozen saved historical/mixed/evidence fixtures; no population quality claim.
            historical = {**result["assessment"], "scorer_version":"s73.1", "band":"deep", "overall":.99}
            turn = result["turns"][0]
            with engine.begin() as db:
                db.execute(update(InterviewSessionRow).where(InterviewSessionRow.id==next_sid).values(assessment=historical, scorer_version="s73.1"))
                db.execute(update(InterviewTurnRow).where(InterviewTurnRow.id==turn["id"]).values(scores={**turn["score"],"codes":["limited_content","relevance_unconfirmed"],"insufficient":True}))
            await refresh()
            checks.check("historical saved values stay labeled v1 and cannot compare directly to v2", await tab.js("window.__has('Historical v1 rubric') && window.__has('Saved index 0.99') && window.__has('cannot be compared directly with v2')"))
            checks.check("saved limited evidence and unconfirmed relevance have neutral explanations", await tab.js("window.__has('Limited content evidence') && window.__has('Relevance unconfirmed; excluded') && window.__has('Insufficient evidence; no ability conclusion')"))
            mixed = {**historical, "scorer_version":"mixed/unknown", "band":"insufficient_signal", "overall":0, "confidence":0}
            with engine.begin() as db:
                db.execute(update(InterviewSessionRow).where(InterviewSessionRow.id==next_sid).values(assessment=mixed, scorer_version="mixed/unknown"))
            await refresh()
            checks.check("mixed versions refuse confident blend and do not display a zero ability score", await tab.js("window.__has('No confident blend is available') && window.__has('No ability conclusion') && !window.__has('Saved index 0')"))
            await reload()
            checks.check("reload restores saved completed history and assessment", await tab.js("document.querySelector('[data-interview-assessment]') && window.__has('No confident blend is available')"))
            await tab.js(f"document.querySelector('[data-interview-id=\"{sid}\"]').click()")
            assert await tab.wait("window.__has('This interview expired')", 20)
            checks.check("explicit history selection shows correct expired session", await session_id() == sid)
            await click("Start new interview")
            assert await tab.wait("document.querySelector('#interview-answer') && !document.querySelector('#interview-answer').disabled", 25)
            await install_transport(); await type_answer("private pending account answer")
            await tab.js("window.__fault='holdAck'"); await click("Submit answer")
            assert await tab.wait("window.__releaseAck", 20)
            await click("Overview")
            await tab.js("window.__releaseAck()")
            await enter()
            checks.check("navigation clears unsent input and reads saved progress after a late acknowledgement", await tab.js("document.querySelector('#interview-answer').value==='' && document.querySelectorAll('[data-interview-turn]').length===1"))
            await type_answer("private pending account answer")
            await tab.js("window.__releaseAck=null")
            await tab.js("window.__fault='holdAck'"); await click("Submit answer")
            assert await tab.wait("window.__releaseAck", 20)
            await click("Sign out")
            assert await tab.wait("window.__has('Sign in')", 20)
            await login(other_email); await enter()
            await tab.js("window.__releaseAck()")
            await asyncio.sleep(.5)
            checks.check("new candidate and late old-account response cannot expose transcripts or drafts", await tab.js("window.__has('No saved interviews') && !document.querySelector('[data-interview-session]') && !document.querySelector('#interview-answer')")
                and private not in await tab.text())
            # Actual cookie revocation is triggered by a read, not simulated API errors.
            await tab.js("window.VeritasAPI.post('/auth/logout')")
            await click("Refresh saved interviews")
            checks.check("actual session loss clears interview and returns to sign-in", await tab.wait("window.__has('Your session ended')", 20)
                and not await tab.js("document.querySelector('[data-interview-session]')"))
            checks.check("browser has no console errors or uncaught exceptions", not tab.console, "; ".join(tab.console[:2]))
            logged = (scratch/"server.log").read_text(encoding="utf-8")
            checks.check("app logs omit candidate answer text", private not in logged and "private pending account answer" not in logged)
        finally:
            engine.dispose()

    browser.run, subprocess.Popen = run, launch
    try:
        await browser.main()
        return checks.summary()
    finally:
        browser.run, subprocess.Popen = original_run, original_popen
        for proc in owned:
            if proc.poll() is None: proc.terminate()
            try: proc.wait(timeout=10)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=10)
        log.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
