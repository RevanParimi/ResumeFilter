"""Real operator org management, HTTP ownership/restart and synthetic Chrome.

Uses migrated scratch SQLite, captured login and fake model/evidence providers.
Transport timeout/503/held acknowledgments are synthetic; all normal operations,
CSRF, wrong-plane denials, key invalidation and persistence use actual HTTP.
Requires Chrome and CDN internet. Never uses working data or live providers.
"""
import asyncio
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile

from sqlalchemy import create_engine, text

import check_ui_screening_browser as browser
from _smoke import Smoke, wait_healthy


async def main():
    scratch = Path(tempfile.mkdtemp(prefix="r3-s2-t1-browser-"))
    print(f"Synthetic org-admin evidence: {scratch}", flush=True)
    checks = Smoke("R3-S2-T1 operator organisations / HTTP restart")
    original_run, original_popen = browser.run, subprocess.Popen
    owned, state = [], {}
    log = (scratch / "server.log").open("w", encoding="utf-8")
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
                "DEE_OPENROUTER_API_KEY": "", "DEE_LLM_MAX_RETRIES": "0", "DEE_GITHUB_TOKEN": "",
                "DEE_GITHUB_API_BASE": "http://127.0.0.1:9", "DEE_EMAIL_PROVIDER": "capture",
                "DEE_SPEECH_PROVIDER": "local", "DEE_VECTORSTORE_BACKEND": "memory",
                "DEE_LOGIN_OTP_DEBUG_ECHO": "false", "DEE_VERIF_OTP_DEBUG_ECHO": "false",
                "DEE_LOGIN_OTP_STATIC_CODE": "", "DEE_SESSION_COOKIE_SECURE": "false",
                "DEE_SESSION_COOKIE_SAMESITE": "lax",
                "PYTHONPATH": os.pathsep.join(str(p) for p in (browser.ROOT / "src", browser.ROOT / "scripts", browser.ROOT)),
            })
            kwargs.update(env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT)
            state.update(db=env["DEE_CANDIDATES_DB_URL"], args=args, kwargs=kwargs)
        if os.name == "nt": kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = original_popen(args, **kwargs)
        owned.append(proc)
        if "--factory" in args: state["server"] = proc
        return proc

    def stop(proc):
        if proc.poll() is None: proc.terminate()
        try: proc.wait(timeout=15)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=10)

    async def run(tab, mailbox, files, admin):
        keys = []
        def require(response, status=200):
            assert response.status_code == status, (response.request.url.path, response.status_code)
            return response.json()
        operator_email = "synthetic-org-operator@example.com"
        require(admin.post("/admin/users", json={"email": operator_email, "label": "Synthetic Org Operator"}))
        engine = create_engine(state["db"])
        try:
            with engine.connect() as conn:
                checks.check("actual scratch composition is migrated to head",
                    conn.scalar(text("SELECT version_num FROM alembic_version")) == "0029_candidate_login_binding")
        finally: engine.dispose()

        async def login():
            await tab.js(browser.HELPERS)
            assert await tab.wait("window.__has('Sign in')", 60)
            assert await tab.js("window.__click('button', 'Operator')")
            await tab.js(f"window.__type('input[type=email]', {json.dumps(operator_email)})")
            assert await tab.js("window.__click('button', 'Send code')")
            assert await tab.wait("document.querySelectorAll('input[inputmode]').length === 6", 20)
            code = browser._code_for(mailbox, operator_email)
            await tab.js(f"window.__type('input[inputmode]', {json.dumps(code)})")
            assert await tab.js("window.__click('button', 'Verify and continue')")
            assert await tab.wait("document.querySelector('#org-name')", 20)

        async def install():
            await tab.js(browser.HELPERS)
            await tab.js("""
window.__nativeFetch=window.__nativeFetch || window.fetch;
window.__orgPosts=0; window.__orgFault=null; window.__orgHold=false;
window.fetch=async (url,init)=>{
 if(url.startsWith('/ledger/orgs') && init && ['POST','DELETE'].includes(init.method)) {
  window.__orgPosts++;
  const fault=window.__orgFault; window.__orgFault=null;
  if(fault==='403') return new Response(JSON.stringify({detail:'Synthetic policy refusal'}), {status:403,headers:{'content-type':'application/json'}});
  if(fault==='503') return new Response(JSON.stringify({detail:'Synthetic service unavailable'}), {status:503,headers:{'content-type':'application/json'}});
  if(fault==='timeout') return new Promise((_r,reject)=>init.signal.addEventListener('abort',()=>reject(new Error('synthetic stalled transport'))));
  if(window.__orgHold) {window.__orgHold=false; await new Promise(resolve=>{window.__orgRelease=resolve;});}
 }
 return window.__nativeFetch(url,init);
};
""")

        async def reload():
            before = await tab.js("performance.timeOrigin")
            await tab.send("Page.reload")
            assert await tab.wait(f"performance.timeOrigin !== {before} && document.readyState === 'complete' && document.querySelector('#org-name')", 60)
            await install()

        async def inspect(oid):
            assert await tab.wait(f"document.querySelector('[data-org-record=\"{oid}\"] button')", 15)
            await tab.js(f"document.querySelector('[data-org-record=\"{oid}\"] button').click()")
            assert await tab.wait("document.querySelector('#org-weight')", 10)

        await login(); await install()
        checks.check("operator landing uses actual empty list without sample counts",
            await tab.wait("window.__has('No organisations found')", 15)
            and not await tab.js("window.__has('Sample data')")
            and await tab.js("document.querySelectorAll('[data-org-record]').length") == 0)
        assert await tab.js("window.__click('button', 'Create organisation')")
        checks.check("blank name refuses locally without sending",
            await tab.wait("window.__has('Enter an organisation name')", 10)
            and await tab.js("window.__orgPosts") == 0)
        name = "Synthetic Browser Agency A"
        await tab.js(f"window.__type('#org-name', {json.dumps(name)}); window.__orgHold=true")
        await tab.js("window.__click('button','Create organisation'); window.__click('button','Create organisation')")
        assert await tab.wait("window.__orgRelease", 10)
        checks.check("duplicate create sends one request without optimistic success",
            await tab.js("window.__orgPosts") == 1 and not await tab.js("window.__has('Organisation created.')"))
        await tab.js("window.__orgRelease()")
        assert await tab.wait("document.querySelector('#org-key') && window.__has('Organisation created.')", 20)
        org_a = next(o for o in require(admin.get("/ledger/orgs")) if o["name"] == name)
        first_key = await tab.js("document.querySelector('#org-key').value"); keys.append(first_key)
        checks.check("actual create returns a concealed one-time key and saved row",
            bool(first_key) and await tab.js("document.querySelector('#org-key').type") == "password"
            and await tab.wait(f"document.querySelector('[data-org-record=\"{org_a['id']}\"]')", 15))
        assert await tab.js("window.__click('button', 'Reveal API key')")
        checks.check("reveal is explicit and key stays out of URL/browser storage",
            await tab.js("document.querySelector('#org-key').type") == "text"
            and not await tab.js(f"location.href.includes({json.dumps(first_key)}) || JSON.stringify(localStorage).includes({json.dumps(first_key)}) || JSON.stringify(sessionStorage).includes({json.dumps(first_key)})"))
        await tab.js(f"window.__type('#org-name', {json.dumps(name)})")
        assert await tab.js("window.__click('button', 'Create organisation')")
        checks.check("real duplicate-name conflict settles and retains name without fake success",
            await tab.wait("document.querySelector('[role=alert]') && !document.querySelector('#org-key')", 15)
            and await tab.js("document.querySelector('#org-name').value") == name
            and len(require(admin.get("/ledger/orgs"))) == 1)
        await tab.js("window.__type('#org-name','Synthetic CSRF Refusal'); window.__savedCsrf=document.cookie.split(';').find(p=>p.trim().startsWith('dee_csrf=')).trim(); document.cookie='dee_csrf=; Max-Age=0; Path=/'")
        assert await tab.js("window.__click('button', 'Create organisation')")
        checks.check("actual CSRF refusal saves nothing and keeps input",
            await tab.wait("window.__has('Sign in again to continue')", 15)
            and await tab.js("document.querySelector('#org-name').value") == "Synthetic CSRF Refusal"
            and len(require(admin.get("/ledger/orgs"))) == 1)
        await tab.js("document.cookie=window.__savedCsrf+'; Path=/; SameSite=Lax'")
        await inspect(org_a["id"])
        await tab.js("window.__type('#org-weight','-1')")
        before = await tab.js("window.__orgPosts")
        assert await tab.js("window.__click('button','Save reliability')")
        checks.check("negative reliability refuses without a mutation",
            await tab.wait("window.__has('Enter a finite reliability multiplier')", 10)
            and await tab.js("window.__orgPosts") == before)
        await tab.js("window.__type('#org-weight','1.75')")
        assert await tab.js("window.__click('button','Save reliability')")
        checks.check("reliability update uses the actual selected server record",
            await tab.wait("window.__has('Reliability saved.') && window.__has('Saved reliability 1.75')", 15)
            and next(o for o in require(admin.get("/ledger/orgs")) if o["id"] == org_a["id"])["reliability_weight"] == 1.75)
        await tab.js("window.__orgFault='403'")
        assert await tab.js("window.__click('button','Save reliability')")
        checks.check("non-CSRF policy refusal is an admin denial rather than candidate consent copy",
            await tab.wait("window.__has('not permitted to administer organisations')", 15)
            and not await tab.js("window.__has('This candidate has not shared')"))
        await tab.js("window.__orgFault='503'")
        assert await tab.js("window.__click('button','Save reliability')")
        checks.check("service failure settles with explicit refresh advice",
            await tab.wait("window.__has('Refresh organisations before retrying')", 15))
        await tab.js("window.__originalPost=window.VeritasAPI.post; window.VeritasAPI.post=(p,b,o)=>window.__originalPost(p,b,o ? {timeoutMs:30}:undefined); window.__orgFault='timeout'")
        assert await tab.js("window.__click('button','Save reliability')")
        checks.check("stalled mutation deadline retains weight and warns about a possible commit",
            await tab.wait("window.__has('Request timed out')", 10)
            and await tab.js("document.querySelector('#org-weight').value") == "1.75")
        await tab.js("window.VeritasAPI.post=window.__originalPost")
        before = await tab.js("window.__orgPosts")
        assert await tab.js("window.__click('button','Rotate organisation key')")
        assert await tab.js("window.__click('button','Keep organisation unchanged')")
        checks.check("rotation cancellation sends nothing", await tab.js("window.__orgPosts") == before)
        assert await tab.js("window.__click('button','Rotate organisation key')")
        assert await tab.js("window.__click('button','Confirm key rotation')")
        assert await tab.wait("document.querySelector('#org-key') && window.__has('Organisation key rotated')", 15)
        rotated = await tab.js("document.querySelector('#org-key').value"); keys.append(rotated)
        with browser.httpx.Client(base_url=browser.API_BASE, headers={"X-Org-Key": first_key}) as old_actor, browser.httpx.Client(base_url=browser.API_BASE, headers={"X-Org-Key": rotated}) as new_actor:
            checks.check("confirmed rotation invalidates old key and enables returned key",
                old_actor.get("/screening/batches").status_code == 401 and new_actor.get("/screening/batches").status_code == 200)
        org_b = require(admin.post("/ledger/orgs", json={"name": "Synthetic Browser Agency B"}))
        keys.append(org_b["api_key"])
        for i in range(23): require(admin.post("/ledger/orgs", json={"name": f"Synthetic Page Org {i:02d}"}))
        assert await tab.js("window.__click('button','Refresh organisations')")
        checks.check("actual list paginates 25 rows locally and clears displayed key",
            await tab.wait("document.querySelectorAll('[data-org-record]').length === 20", 20)
            and not await tab.js("document.querySelector('#org-key')"))
        assert await tab.js("window.__click('button','Next organisations')")
        checks.check("second page contains the remaining actual rows",
            await tab.wait("document.querySelectorAll('[data-org-record]').length === 5", 10))
        await tab.js(f"window.__type('#org-filter', {json.dumps(name)})")
        checks.check("filter resets paging and exposes only the matching server row",
            await tab.wait("document.querySelectorAll('[data-org-record]').length === 1", 10))
        await inspect(org_a["id"])
        assert await tab.js("window.__click('button','Offboard organisation')")
        before = len(require(admin.get("/ledger/orgs")))
        assert await tab.js("window.__click('button','Keep organisation unchanged')")
        checks.check("offboarding requires a second deliberate action", len(require(admin.get("/ledger/orgs"))) == before)
        assert await tab.js("window.__click('button','Offboard organisation')")
        assert await tab.js("window.__click('button','Confirm offboarding')")
        assert await tab.wait("window.__has('Organisation offboarded.')", 15)
        with browser.httpx.Client(base_url=browser.API_BASE, headers={"X-Org-Key": rotated}) as erased, browser.httpx.Client(base_url=browser.API_BASE, headers={"X-Org-Key": org_b["api_key"]}) as other:
            checks.check("offboarding removes only its target and revokes that org's credential",
                erased.get("/screening/batches").status_code == 401 and other.get("/screening/batches").status_code == 200
                and org_a["id"] not in [o["id"] for o in require(admin.get("/ledger/orgs"))])
            checks.check("wrong-plane org cannot list or mutate admin state",
                other.get("/ledger/orgs").status_code == 401
                and other.post(f'/ledger/orgs/{org_b["org"]["id"]}/reliability', json={"weight": 0}).status_code == 401)
        cid = require(admin.post("/candidates", json={"resume_text": "Synthetic Denied Candidate\nEmail: denied-org-admin@example.com\nSkills: Python", "evaluate": False}))["candidate_id"]
        candidate_key = require(admin.post(f"/candidates/{cid}/auth-key"))["access_key"]
        with browser.httpx.Client(base_url=browser.API_BASE, headers={"X-Candidate-Key": candidate_key}) as candidate:
            checks.check("candidate plane cannot list or offboard organisations",
                candidate.get("/ledger/orgs").status_code == 401 and candidate.delete(f'/ledger/orgs/{org_b["org"]["id"]}').status_code == 401)
        await tab.js("window.__type('#org-filter','Synthetic Browser Agency B')")
        await inspect(org_b["org"]["id"])
        await tab.js("window.__type('#org-weight','2.25')")
        assert await tab.js("window.__click('button','Save reliability')")
        checks.check("second org reliability is saved before restart",
            await tab.wait("window.__has('Saved reliability 2.25')", 15))
        await reload()
        checks.check("document reload restores server rows with no retained key/draft",
            await tab.wait("document.querySelectorAll('[data-org-record]').length === 20", 15)
            and not await tab.js("document.querySelector('#org-key')")
            and await tab.js("document.querySelector('#org-name').value") == "")
        stop(state["server"])
        state["server"] = launch(state["args"], **state["kwargs"])
        assert wait_healthy(admin), "restarted scratch app failed"
        assert await tab.js("window.__click('button','Refresh organisations')")
        with browser.httpx.Client(base_url=browser.API_BASE, headers={"X-Org-Key": org_b["api_key"]}) as other:
            checks.check("backend restart preserves org state, reliability, operator session and second org key",
                await tab.wait("document.querySelectorAll('[data-org-record]').length === 20 && !window.__has('Loading organisations')", 15)
                and len(require(admin.get("/ledger/orgs"))) == 24
                and next(o for o in require(admin.get("/ledger/orgs")) if o["id"] == org_b["org"]["id"])["reliability_weight"] == 2.25
                and other.get("/screening/batches").status_code == 200)
        shot = await tab.send("Page.captureScreenshot")
        (scratch / "org-list.png").write_bytes(base64.b64decode(shot["data"]))
        await tab.js("window.VeritasAPI.post('/auth/logout')")
        assert await tab.js("window.__click('button','Refresh organisations')")
        checks.check("real session expiry clears operator rows/keys and requires sign-in",
            await tab.wait("window.__has('Your session ended')", 15)
            and not await tab.js("document.querySelector('#org-name') || document.querySelector('#org-key')"))
        checks.check("console has no exceptions", not tab.console, "; ".join(tab.console[:2]))
        logged = (scratch / "server.log").read_text(encoding="utf-8")
        checks.check("actual server logs omit generated org keys", all(key not in logged for key in keys))

    browser.run, subprocess.Popen = run, launch
    try:
        await browser.main()
        return checks.summary()
    finally:
        browser.run, subprocess.Popen = original_run, original_popen
        for proc in owned: stop(proc)
        log.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
