"""Actual operator-account Chrome/HTTP/restart with captured login and fake models.

Runs only on a migrated scratch SQLite database. Fault transports are synthetic;
normal account changes, CSRF, role denials and session revocations use real HTTP.
Requires Chrome and CDN internet. Does not touch working data or live providers.
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
    scratch = Path(tempfile.mkdtemp(prefix="r3-s2-t2-browser-"))
    print(f"Synthetic user-admin evidence: {scratch}", flush=True)
    checks = Smoke("R3-S2-T2 operator accounts / HTTP restart")
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
        def require(response, status=200):
            assert response.status_code == status, (response.request.url.path, response.status_code)
            return response.json()
        email_a, email_b = "synthetic-user-a@example.com", "synthetic-user-b@example.com"
        account_a = require(admin.post("/admin/users", json={"email": email_a, "label": "Synthetic Operator A"}))
        disabled = require(admin.post("/admin/users", json={"email": "disabled-fixture@example.com", "label": "Disabled fixture"}))
        engine = create_engine(state["db"])
        try:
            with engine.begin() as conn:
                checks.check("scratch composition is migrated to head", conn.scalar(text("SELECT version_num FROM alembic_version")) == "0029_candidate_login_binding")
                # Fixture-only disabled state; there is no HTTP suspension control.
                conn.execute(text("UPDATE admin_users SET disabled_at=:at WHERE id=:id"), {"at": "2026-10-13 12:00:00", "id": disabled["id"]})
        finally: engine.dispose()

        async def login(email):
            await tab.js(browser.HELPERS)
            assert await tab.wait("window.__has('Sign in')", 60)
            assert await tab.js("window.__click('button','Operator')")
            await tab.js(f"window.__type('input[type=email]', {json.dumps(email)})")
            assert await tab.js("window.__click('button','Send code')")
            assert await tab.wait("document.querySelectorAll('input[inputmode]').length === 6", 20)
            code = browser._code_for(mailbox, email)
            await tab.js(f"window.__type('input[inputmode]', {json.dumps(code)})")
            assert await tab.js("window.__click('button','Verify and continue')")
            assert await tab.wait("document.querySelector('#org-name')", 20)
            assert await tab.js("window.__click('button','Operator accounts')")
            assert await tab.wait("document.querySelector('#operator-email') && !window.__has('Loading operator accounts')", 20)

        async def install():
            await tab.js(browser.HELPERS)
            await tab.js("""
window.__nativeFetch=window.__nativeFetch || window.fetch;
window.__userWrites=0; window.__userFault=null; window.__userHold=false;
window.fetch=async (url,init)=>{
 if(url.startsWith('/admin/users') && init && ['POST','DELETE'].includes(init.method)) {
  window.__userWrites++;
  const fault=window.__userFault; window.__userFault=null;
  if(fault==='403' || fault==='503') return new Response(JSON.stringify({detail:'Synthetic service refusal'}), {status:Number(fault),headers:{'content-type':'application/json'}});
  if(fault==='timeout') return new Promise((_r,reject)=>init.signal.addEventListener('abort',()=>reject(new Error('synthetic stalled transport'))));
  if(window.__userHold) {window.__userHold=false; await new Promise(resolve=>{window.__userRelease=resolve;});}
 }
 return window.__nativeFetch(url,init);
};
""")

        async def refresh():
            assert await tab.js("window.__click('button','Refresh operator accounts')")
            assert await tab.wait("!window.__has('Loading operator accounts')", 15)

        async def arm(uid):
            assert await tab.wait(f"document.querySelector('[data-operator-record=\"{uid}\"] button')", 15)
            await tab.js(f"document.querySelector('[data-operator-record=\"{uid}\"] button').click()")
            assert await tab.wait("window.__has('Confirm operator deletion')", 10)

        await login(email_a); await install()
        checks.check("actual list shows enabled/disabled platform role without sample emails or last seen",
            await tab.wait("document.querySelectorAll('[data-operator-record]').length === 2", 15)
            and await tab.js("window.__has('Operator · Enabled') && window.__has('Operator · Disabled') && !window.__has('Sample data') && !window.__has('ops@veritas.in')")
            and not await tab.js("document.querySelector('select')"))
        await tab.js("window.__type('#operator-filter','no-such-operator')")
        checks.check("actual empty filter state has no fabricated rows", await tab.wait("window.__has('No operator accounts found') && document.querySelectorAll('[data-operator-record]').length === 0", 10))
        await tab.js("window.__type('#operator-filter','')")
        assert await tab.js("window.__click('button','Create operator')")
        checks.check("invalid email refuses locally without mutation", await tab.wait("window.__has('Enter a valid sign-in email')", 10) and await tab.js("window.__userWrites") == 0)
        await tab.js(f"window.__type('#operator-email', {json.dumps(email_b)}); window.__type('#operator-label','Synthetic Operator B'); window.__userHold=true")
        await tab.js("window.__click('button','Create operator'); window.__click('button','Create operator'); void 0;")
        assert await tab.wait("window.__userRelease", 10)
        checks.check("duplicate click sends one request without optimistic success", await tab.js("window.__userWrites") == 1 and not await tab.js("window.__has('Operator account created.')"))
        await tab.js("window.__userRelease()")
        assert await tab.wait("window.__has('Operator account created.') && document.querySelectorAll('[data-operator-record]').length === 3", 20)
        account_b = next(u for u in require(admin.get("/admin/users")) if u["label"] == "Synthetic Operator B")
        checks.check("browser creation persists actual label and clears transient email", await tab.js("document.querySelector('#operator-email').value") == "" and account_b["disabled_at"] is None)
        actor_b = browser.httpx.Client(base_url=browser.API_BASE, timeout=20)
        try:
            require(actor_b.post("/auth/admin/login", json={"email": email_b}), 202)
            require(actor_b.post("/auth/admin/verify", json={"email": email_b, "code": browser._code_for(mailbox, email_b)}))
            csrf_b = actor_b.cookies.get("dee_csrf")
            checks.check("new operator can authenticate and has full existing operator role", actor_b.get("/admin/users").status_code == 200)
            await tab.js(f"window.__type('#operator-email', {json.dumps(email_b)})")
            assert await tab.js("window.__click('button','Create operator')")
            checks.check("actual duplicate conflict retains input and reports no success", await tab.wait("window.__has('operator already exists')", 15) and not await tab.js("window.__has('Operator account created.')") and len(require(admin.get('/admin/users'))) == 3)
            await tab.js("window.__type('#operator-email','csrf-refused@example.com'); window.__savedCsrf=document.cookie.split(';').find(p=>p.trim().startsWith('dee_csrf=')).trim(); document.cookie='dee_csrf=; Max-Age=0; Path=/'")
            assert await tab.js("window.__click('button','Create operator')")
            checks.check("actual CSRF refusal saves nothing and retains email", await tab.wait("window.__has('Sign in again to continue')", 15) and len(require(admin.get('/admin/users'))) == 3)
            await tab.js("document.cookie=window.__savedCsrf+'; Path=/; SameSite=Lax'; window.__userFault='403'")
            assert await tab.js("window.__click('button','Create operator')")
            checks.check("synthetic policy refusal uses operator denial copy", await tab.wait("window.__has('not permitted to administer operator accounts')", 15) and not await tab.js("window.__has('This candidate has not shared')"))
            await tab.js("window.__userFault='503'")
            assert await tab.js("window.__click('button','Create operator')")
            checks.check("service failure settles with possible-commit recovery advice", await tab.wait("window.__has('Refresh operator accounts before retrying')", 15))
            await tab.js("window.__originalPost=window.VeritasAPI.post; window.VeritasAPI.post=(p,b,o)=>window.__originalPost(p,b,o ? {timeoutMs:30}:undefined); window.__userFault='timeout'")
            assert await tab.js("window.__click('button','Create operator')")
            checks.check("stalled request deadline settles retaining draft", await tab.wait("window.__has('Request timed out')", 10) and await tab.js("document.querySelector('#operator-email').value") == "csrf-refused@example.com")
            await tab.js("window.VeritasAPI.post=window.__originalPost")
            await refresh()
            # An external deletion makes the rendered confirmation stale.
            stale = require(admin.post('/admin/users', json={'email':'stale-fixture@example.com','label':'Stale fixture'}))
            await refresh(); await arm(stale['id'])
            require(admin.delete('/admin/users/' + stale['id']))
            assert await tab.js("window.__click('button','Confirm operator deletion')")
            checks.check("stale target deletion reports actual 404 without fake success", await tab.wait("window.__has('operator not found')", 15) and not await tab.js("window.__has('Operator account deleted.')"))
            await refresh()
            for i in range(20): require(admin.post('/admin/users', json={'email':f'page-{i}@example.com','label':f'Page Operator {i:02d}'}))
            await refresh()
            checks.check("actual 23-account list paginates locally", await tab.wait("document.querySelectorAll('[data-operator-record]').length === 20", 15))
            assert await tab.js("window.__click('button','Next operator accounts')")
            checks.check("next page renders remaining actual rows", await tab.wait("document.querySelectorAll('[data-operator-record]').length === 3", 10))
            await tab.js("window.__type('#operator-filter','Synthetic Operator B')")
            checks.check("filter resets page and targets actual label", await tab.wait("document.querySelectorAll('[data-operator-record]').length === 1", 10))
            await arm(account_b['id'])
            checks.check("confirmation states session cascade, self-lockout and last-operator recovery", await tab.js("window.__has('All its sessions are revoked') && window.__has('your own account') && window.__has('last operator') && window.__has('machine admin key')"))
            before = await tab.js("window.__userWrites")
            assert await tab.js("window.__click('button','Keep operator')")
            checks.check("cancelling deletion sends no mutation", await tab.js("window.__userWrites") == before and actor_b.get('/admin/users').status_code == 200)
            await arm(account_b['id'])
            assert await tab.js("window.__click('button','Confirm operator deletion')")
            checks.check("confirmed target deletion revokes its session and preserves actor A", await tab.wait("window.__has('Operator account deleted.') && document.querySelectorAll('[data-operator-record]').length === 0", 15) and actor_b.get('/admin/users').status_code == 401 and account_a['id'] in [u['id'] for u in require(admin.get('/admin/users'))])
        finally: actor_b.close()

        await tab.js("window.__type('#operator-filter',''); window.__type('#operator-email','private-draft@example.com')")
        assert await tab.js("window.__click('button','Organisations')")
        assert await tab.wait("document.querySelector('#org-name')", 10)
        assert await tab.js("window.__click('button','Operator accounts')")
        checks.check("navigation clears unsaved email and confirmation", await tab.wait("document.querySelector('#operator-email')", 15) and await tab.js("document.querySelector('#operator-email').value") == "" and not await tab.js("window.__has('Confirm operator deletion')"))
        origin = await tab.js("performance.timeOrigin")
        await tab.send('Page.reload')
        assert await tab.wait(f"performance.timeOrigin !== {origin} && document.readyState === 'complete' && document.querySelector('#org-name')", 60)
        await install(); assert await tab.js("window.__click('button','Operator accounts')")
        checks.check("document reload reads persisted operator roles/status without drafts", await tab.wait("document.querySelectorAll('[data-operator-record]').length === 20 && window.__has('Operator · Disabled')", 15) and await tab.js("document.querySelector('#operator-email').value") == "")
        stop(state['server']); state['server'] = launch(state['args'], **state['kwargs'])
        assert wait_healthy(admin), 'restarted scratch app failed'
        await refresh()
        checks.check("backend restart preserves accounts/status and current session", await tab.wait("document.querySelectorAll('[data-operator-record]').length === 20", 15) and len(require(admin.get('/admin/users'))) == 22 and next(u for u in require(admin.get('/admin/users')) if u['id'] == disabled['id'])['disabled_at'] is not None)
        org = require(admin.post('/ledger/orgs', json={'name':'Denied User Admin Org'}))
        with browser.httpx.Client(base_url=browser.API_BASE, headers={'X-Org-Key':org['api_key']}) as other:
            checks.check("org plane cannot list/create/delete platform operators", other.get('/admin/users').status_code == 401 and other.post('/admin/users', json={'email':'denied@example.com'}).status_code == 401 and other.delete('/admin/users/' + account_a['id']).status_code == 401)
        cid = require(admin.post('/candidates', json={'resume_text':'Synthetic Denied Operator\nEmail: denied-operator@example.com\nSkills: Python','evaluate':False}))['candidate_id']
        candidate_key = require(admin.post(f'/candidates/{cid}/auth-key'))['access_key']
        with browser.httpx.Client(base_url=browser.API_BASE, headers={'X-Candidate-Key':candidate_key}) as candidate:
            checks.check("candidate plane cannot list or delete operators", candidate.get('/admin/users').status_code == 401 and candidate.delete('/admin/users/' + account_a['id']).status_code == 401)
        await tab.js("window.VeritasAPI.post('/auth/logout')")
        assert await tab.js("window.__click('button','Refresh operator accounts')")
        checks.check("real expired session clears privileged rows and draft", await tab.wait("window.__has('Your session ended')", 15) and not await tab.js("document.querySelector('#operator-email') || document.querySelector('[data-operator-record]')"))
        await login(email_a); await install()
        await tab.js("window.__type('#operator-filter','Synthetic Operator A')")
        await arm(account_a['id'])
        assert await tab.js("window.__click('button','Confirm operator deletion')")
        checks.check("self deletion actually ends sign-in and removes account", await tab.wait("window.__has('Your session ended')", 15) and account_a['id'] not in [u['id'] for u in require(admin.get('/admin/users'))])
        # Sign in on the organization plane in the same actual browser.
        assert await tab.js("window.__click('button','Organisation')")
        assert await tab.js("window.__click('button','Create account')")
        assert await tab.js("window.__type('input[type=email]','denied-browser@example.com'); window.__type('input[placeholder=\"Sampoorna Staffing\"]','Denied Browser Org')")
        assert await tab.js("window.__click('button','Create account and send code')")
        assert await tab.wait("document.querySelectorAll('input[inputmode]').length === 6", 20)
        code = browser._code_for(mailbox, 'denied-browser@example.com')
        await tab.js(f"window.__type('input[inputmode]', {json.dumps(code)})")
        assert await tab.js("window.__click('button','Verify and continue')")
        assert await tab.wait("window.__has('Screening queue')", 20)
        checks.check("organization browser has no operator administration navigation", not await tab.js("Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='Operator accounts')"))
        status = await tab.js("window.fetch('/admin/users',{credentials:'include'}).then(r=>r.status)")
        checks.check("actual wrong-plane browser request is denied", status == 401)
        checks.check("browser console has no exceptions", not tab.console, '; '.join(tab.console[:2]))

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
