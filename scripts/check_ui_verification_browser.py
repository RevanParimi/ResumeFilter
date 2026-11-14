"""Real candidate contact actions with captured delivery and migrated scratch SQL.

Unavailable/failing delivery is an explicit synthetic provider; CSRF, challenges,
expiry/budget, retries, ownership, reload and session loss use actual HTTP.
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
import sys
import tempfile

from sqlalchemy import create_engine, update

import check_ui_screening_browser as browser
from _smoke import Smoke
from smoke_r3_s1_t2 import contact_marker, latest_code
from app.verification.models import VerificationChallengeRow, VerificationRow


def create_portal_read_browser_app():
    from smoke_r3_s1_t2 import create_smoke_app
    from smoke_r4_s1_t3c import create_portal_read_smoke_app
    return create_portal_read_smoke_app(base_factory=create_smoke_app)


def create_portal_write_browser_app():
    from smoke_r3_s1_t2 import create_smoke_app
    from smoke_r4_s1_t3c import create_portal_write_smoke_app
    return create_portal_write_smoke_app(base_factory=create_smoke_app)


async def candidate_sign_in(tab, mailbox, address):
    assert await tab.js("window.__click('button','Sign out')")
    assert await tab.wait("document.querySelector('input[type=email]') && window.__has('Signed out.')", 20)
    await tab.js("window.__click('button','Candidate'); window.__click('button','Sign in')")
    await tab.js("window.__type('input[type=email]'," + json.dumps(address) + ')')
    assert await tab.js("window.__click('button','Send code')")
    assert await tab.wait("document.querySelectorAll('input[inputmode]').length===6", 20)
    code = browser._code_for(mailbox, address)
    await tab.js("window.__type('input[inputmode]'," + json.dumps(code) + ')')
    assert await tab.js("window.__click('button','Verify and continue')")
    assert await tab.wait("document.querySelector('#contact-destination') && Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='Reload your data' && !b.disabled)", 25)
    return code


async def check_portal_write_workers(tab, scratch, checks, admin, mailbox, email, other_email, cid):
    codes = []
    async def revoke():
        assert await tab.js("(() => { const b=Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='Revoke' && !b.disabled); if(!b)return false; b.click(); return true; })()")
    def grant():
        reply = admin.post(f'/ledger/candidates/{cid}/consent', json={'purpose': 'ledger_read'})
        assert reply.status_code == 200, reply.status_code
        return reply.json()['id']
    async def wait_marker(name):
        async with asyncio.timeout(15):
            while not (scratch / ('portal-write-' + name)).exists():
                await asyncio.sleep(.01)
    def count():
        path = scratch / 'portal-write-operations.jsonl'
        return len(path.read_text().splitlines()) if path.exists() else 0
    grant()
    assert await tab.js("window.__click('button','Consents')")
    assert await tab.wait("window.__has('Revoke') && !window.__has('Loading consents')", 15)
    for name in ('entered', 'release', 'completed'):
        (scratch / ('portal-write-' + name)).unlink(missing_ok=True)
    before = count()
    (scratch / 'portal-write-mode').touch()
    try:
        await revoke()
        await wait_marker('entered')
        checks.check('held revoke gives explicit uncertainty and saved-state recovery',
            await tab.wait("window.__has('Revocation could not be confirmed') && window.__has('An earlier revocation may still finish')", 15))
        await tab.js("window.__click('button','Revoke')")
        checks.check('uncertain revoke requires a read before human retry', count() == before + 1)
        assert await tab.js("window.__click('button','Reload consents')")
        checks.check('snapshot while SQL is held remains active and warns of later settlement',
            await tab.wait("window.__has('Active') && window.__has('An earlier revocation may still finish') && !window.__has('Loading consents')", 15))
        await revoke()
        checks.check('human retry during held work is refused safely',
            await tab.wait("window.__has('Consent changes are temporarily unavailable')", 15) and count() == before + 1)
    finally:
        (scratch / 'portal-write-release').touch()
        if (scratch / 'portal-write-entered').exists():
            await wait_marker('completed')
        (scratch / 'portal-write-mode').unlink(missing_ok=True)
    assert await tab.js("window.__click('button','Reload consents')")
    checks.check('explicit GET recovers the late revoke without replay',
        await tab.wait("window.__has('Revoked') && !window.__has('Active') && !window.__has('Loading consents')", 15)
        and count() == before + 1)

    grant()
    assert await tab.js("window.__click('button','Reload consents')")
    assert await tab.wait("window.__has('Active') && !window.__has('Loading consents')", 15)
    (scratch / 'portal-write-mode').write_text('failure')
    try:
        await revoke()
        checks.check('actual failed worker preserves rows and gives safe manual recovery',
            await tab.wait("window.__has('Revocation could not be confirmed') && window.__has('Active')", 15)
            and not await tab.js("window.__has('internal_error') || window.__has('synthetic-private')"))
    finally:
        (scratch / 'portal-write-mode').unlink(missing_ok=True)
    assert await tab.js("window.__click('button','Reload consents')")
    assert await tab.wait("!window.__has('Loading consents') && window.__has('Active')", 15)

    # Delay native HTTP acknowledgement across real logout/login. Both old
    # success and old failure callbacks must leave the new account untouched.
    for ending in ('success', 'failure'):
        await tab.js("""window.__consentNativePost=window.VeritasAPI.post;
window.__consentNativeGet=window.VeritasAPI.get; window.__consentReads=0;
window.VeritasAPI.get=(path,...args)=>{if(path==='/portal/consents')window.__consentReads++;return window.__consentNativeGet(path,...args);};
window.VeritasAPI.post=(path,...args)=>{
 const result=window.__consentNativePost(path,...args);
 if(!path.endsWith('/revoke')) return result;
 return result.then(value=>new Promise(resolve=>{window.__releaseConsent=()=>resolve(value);}),
 error=>new Promise((resolve,reject)=>{window.__releaseConsent=()=>reject(error);}));
};""")
        if ending == 'failure':
            (scratch / 'portal-write-mode').write_text('failure')
        try:
            await revoke()
            assert await tab.wait("typeof window.__releaseConsent==='function'", 15)
            (scratch / 'portal-write-mode').unlink(missing_ok=True)
            codes.append(await candidate_sign_in(tab, mailbox, other_email))
            assert await tab.js("window.__click('button','Consents')")
            assert await tab.wait("window.__has('You have not granted') && !window.__has('Loading consents')", 15)
            old_reads = await tab.js('window.__consentReads')
            await tab.js('window.__releaseConsent()')
            checks.check('old native ' + ending + ' callback cannot refill or reload the new account',
                await tab.wait("window.__has('You have not granted') && !window.__has('Revocation could not be confirmed')", 10)
                and await tab.js('window.__consentReads') == old_reads)
        finally:
            (scratch / 'portal-write-mode').unlink(missing_ok=True)
            await tab.js('window.VeritasAPI.post=window.__consentNativePost; window.VeritasAPI.get=window.__consentNativeGet; window.__releaseConsent?.(); delete window.__releaseConsent;')
        codes.append(await candidate_sign_in(tab, mailbox, email))
        grant()
        assert await tab.js("window.__click('button','Consents')")
        assert await tab.wait("window.__has('Active') && !window.__has('Loading consents')", 15)
    before = await tab.js('performance.timeOrigin')
    await tab.send('Page.reload')
    assert await tab.wait(f"performance.timeOrigin !== {before} && document.querySelector('#contact-destination')", 60)
    await tab.js(browser.HELPERS)
    assert await tab.js("window.__click('button','Consents')")
    checks.check('saved consent state survives actual page reload',
        await tab.wait("window.__has('Active') && window.__has('Revoked') && !window.__has('Loading consents')", 15))
    assert await tab.js("window.__click('button','Overview')")
    assert await tab.wait("document.querySelector('#contact-destination')", 15)
    checks.check('worker logs omit private exception details',
        'synthetic-private-portal-smoke-error' not in (scratch / 'server.log').read_text(encoding='utf-8'))
    return codes


async def check_portal_read_workers(tab, scratch, checks, admin, mailbox, email, other_email):
    copy = 'Your saved data is temporarily unavailable'
    async def wait_marker(name):
        async with asyncio.timeout(15):
            while not (scratch / ('portal-read-' + name)).exists():
                await asyncio.sleep(.01)
    def operation_count():
        path = scratch / 'portal-read-operations.jsonl'
        return len(path.read_text().splitlines()) if path.exists() else 0
    for nav, reload_label in [('Overview', 'Reload your data'),
            ('Who accessed it', 'Reload access log'), ('Consents', 'Reload consents')]:
        for name in ('entered', 'release', 'completed'):
            (scratch / ('portal-read-' + name)).unlink(missing_ok=True)
        before = operation_count()
        (scratch / 'portal-read-mode').touch()
        try:
            assert await tab.js('window.__click("button",' + json.dumps(nav) + ')'), 'missing navigation: ' + nav
            await wait_marker('entered')
            checks.check(nav + ': actual held SQL produces visible pending/reload guidance',
                await tab.wait('window.__has(' + json.dumps(copy) + ')', 15)
                and not await tab.js("window.__has('portal_read_pending')"))
            refused = await tab.js("window.VeritasAPI.get('/portal/consents').then(()=>null,e=>e.detail)")
            checks.check(nav + ': pending view retains the shared slot without automatic replay',
                refused == 'portal_read_capacity_exhausted' and operation_count() == before + 1)
        finally:
            (scratch / 'portal-read-release').touch()
            if (scratch / 'portal-read-entered').exists():
                await wait_marker('completed')
            (scratch / 'portal-read-mode').unlink(missing_ok=True)
        assert await tab.js('window.__click("button",' + json.dumps(reload_label) + ')')
        checks.check(nav + ': explicit reload reads saved data and clears the error',
            await tab.wait('!window.__has(' + json.dumps(copy) + ') && Array.from(document.querySelectorAll("button")).some(b=>b.textContent.trim()==='
                + json.dumps(reload_label) + ' && !b.disabled)', 15)
            and operation_count() == before + 2)

    (scratch / 'portal-read-mode').write_text('failure')
    try:
        assert await tab.js("window.__click('button','Reload consents')")
        checks.check('actual worker failure has readable correlated-500 guidance without internal details',
            await tab.wait("window.__has('The request could not be confirmed')", 15)
            and not await tab.js("window.__has('internal_error') || window.__has('synthetic-private')"))
    finally:
        (scratch / 'portal-read-mode').unlink(missing_ok=True)
    assert await tab.js("window.__click('button','Reload consents')")
    checks.check('explicit read recovers from a failed worker',
        await tab.wait("!window.__has('The request could not be confirmed') && Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='Reload consents' && !b.disabled)", 15))

    # Native HTTP supplies the older account's report reference; hold only its
    # delivery to UI, then switch accounts through actual cookie/CSRF login.
    response = admin.post('/candidates', json={'evaluate': True, 'resume_text':
        f'Synthetic Contact Browser\nEmail: {email}\nPhone: +919876543210\nSkills: Python SQL'})
    assert response.status_code == 200
    assert await tab.js("window.__click('button','Overview')")
    count_js = "(() => { const el=Array.from(document.querySelectorAll('div')).find(e=>e.children.length===2 && e.lastElementChild.textContent.trim()==='report references'); return el?.firstElementChild.textContent.trim(); })()"
    assert await tab.wait(count_js + " === '1'", 20)
    await tab.js("""window.__portalNativeGet=window.VeritasAPI.get; window.__portalHoldUsed=false;
window.VeritasAPI.get=(path,opts)=>{
 if(path!=='/portal/me' || window.__portalHoldUsed) return window.__portalNativeGet(path,opts);
 window.__portalHoldUsed=true;
 return window.__portalNativeGet(path,opts).then(value=>new Promise(resolve=>{window.__releasePortal=()=>resolve(value);}));
};""")
    codes = []
    async def sign_in(address):
        codes.append(await candidate_sign_in(tab, mailbox, address))
        assert await tab.wait("Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='Reload your data' && !b.disabled) && !window.__has("
            + json.dumps(copy) + ')', 25)
    try:
        assert await tab.js("window.__click('button','Reload your data')")
        assert await tab.wait("typeof window.__releasePortal === 'function'", 20)
        await sign_in(other_email)
        assert await tab.wait(count_js + " === '0'", 20)
        await tab.js('window.__releasePortal()')
        checks.check('older native portal reply cannot restore another account report in the current rendered view',
            await tab.wait(count_js + " === '0'", 10)
            and (await tab.js("window.VeritasAPI.get('/portal/me')"))['candidate_id'] != response.json()['candidate_id'])
    finally:
        await tab.js('window.VeritasAPI.get=window.__portalNativeGet; window.__releasePortal?.()')
    await sign_in(email)
    assert await tab.wait(count_js + " === '1'", 20)
    origin = await tab.js('performance.timeOrigin')
    await tab.send('Page.reload')
    assert await tab.wait(f"performance.timeOrigin !== {origin} && document.readyState==='complete' && document.querySelector('#contact-destination')", 60)
    await tab.js(browser.HELPERS)
    checks.check('candidate portal saved report and account survive actual page reload', await tab.wait(count_js + " === '1'", 20))
    logged = (scratch / 'server.log').read_text(encoding='utf-8')
    checks.check('portal account-change logs omit mailbox and delivered login codes',
        other_email not in logged and all(code not in logged for code in codes)
        and 'synthetic-private-portal-smoke-error' not in logged)
    return codes


async def main():
    scratch = Path(tempfile.mkdtemp(prefix="r3-s1-t2-browser-"))
    print(f"Synthetic contact browser evidence: {scratch}", flush=True)
    checks = Smoke("R3-S1-T2 candidate contact browser")
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
            factory = ('check_ui_verification_browser:create_portal_write_browser_app' if '--portal-write-workers' in sys.argv
                else 'check_ui_verification_browser:create_portal_read_browser_app' if '--portal-read-workers' in sys.argv else 'smoke_r3_s1_t2:create_smoke_app')
            args = [factory if a == "app.main:app" else a for a in args] + ["--factory"]
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
            if '--contact-code-workers' in sys.argv:
                env.update(VERITAS_CONTACT_CODE_SMOKE='true', VERITAS_SQL_SMOKE_EVENTS=str(scratch / 'lifecycle.jsonl'),
                    DEE_CONTACT_CODE_MAX_CONCURRENT_REQUESTS='1', DEE_CONTACT_CODE_WAIT_SECONDS='.5',
                    DEE_DB_MIGRATE_ON_BOOT='true')
            if '--portal-read-workers' in sys.argv:
                env.update(VERITAS_SQL_SMOKE_EVENTS=str(scratch / 'lifecycle.jsonl'),
                    DEE_PORTAL_READ_MAX_CONCURRENT_REQUESTS='1', DEE_PORTAL_READ_WAIT_SECONDS='.5',
                    DEE_SESSION_LAST_SEEN_WRITE_SECONDS='3600', DEE_DB_MIGRATE_ON_BOOT='true')
            if '--portal-write-workers' in sys.argv:
                env.update(VERITAS_SQL_SMOKE_EVENTS=str(scratch / 'lifecycle.jsonl'),
                    DEE_PORTAL_WRITE_MAX_CONCURRENT_REQUESTS='1', DEE_PORTAL_WRITE_WAIT_SECONDS='.5',
                    DEE_SESSION_LAST_SEEN_WRITE_SECONDS='3600', DEE_DB_MIGRATE_ON_BOOT='true')
            state["db"] = env["DEE_CANDIDATES_DB_URL"]
            kwargs.update(env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT)
        if os.name == "nt": kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = original_popen(args, **kwargs); owned.append(proc); return proc

    async def run(tab, mailbox, files, admin):
        email = "verify-browser@example.com"
        control = Path(str(mailbox) + ".control")
        codes = []
        def require(response):
            assert response.status_code == 200, response.status_code
            return response.json()
        cid = require(admin.post("/candidates", json={"evaluate": False, "resume_text":
            f"Synthetic Contact Browser\nEmail: {email}\nPhone: +919876543210\nSkills: Python SQL"}))["candidate_id"]
        other_id = require(admin.post("/candidates", json={"evaluate": False, "resume_text":
            "Synthetic Other Contact\nEmail: verify-other@example.com\nSkills: Python"}))["candidate_id"]
        other_key = require(admin.post(f"/candidates/{other_id}/auth-key"))["access_key"]
        engine = create_engine(state["db"])
        def mutate(vid, **values):
            with engine.begin() as session:
                session.execute(update(VerificationChallengeRow).where(
                    VerificationChallengeRow.verification_id == vid).values(**values))
        async def reload():
            before = await tab.js("performance.timeOrigin")
            await tab.send("Page.reload")
            assert await tab.wait(f"performance.timeOrigin !== {before} && document.readyState === 'complete' && document.querySelector('button')", 60, "new candidate document")
            await tab.js(browser.HELPERS)
        async def type_dest(value=email):
            assert await tab.js(f"window.__type('#contact-destination', {json.dumps(value)})")
        async def send():
            assert await tab.js("window.__click('button','Send contact code')")
        async def confirm(value):
            await tab.js(f"window.__type('#contact-code', {json.dumps(value)})")
            assert await tab.js("window.__click('button','Confirm contact code')")
        async def selected_id():
            listed = await tab.js("window.VeritasAPI.get('/portal/verifications')")
            return next(v["id"] for v in reversed(listed["verifications"]) if v["status"] == "pending")
        async def assurance_status(expected):
            # DC inserts spans around text bindings. A descendant :last-child
            # can select the method's inner span, rather than the status chip.
            result = await tab.wait("(() => {const row=document.querySelector('[data-assurance-method=\"otp_email\"]'); return row && row.textContent.replace('Contact-control OTP (email)','').trim().toLowerCase() === "
                + json.dumps(expected) + ";})()", 20, "actual assurance " + expected)
            if not result:
                html = await tab.js("document.querySelector('[data-assurance-method=\"otp_email\"]')?.outerHTML || 'assurance row missing'")
                (scratch / f"assurance-{expected}-failure.html").write_text(html, encoding="utf-8")
            return result

        try:
            await tab.js(browser.HELPERS)
            assert await tab.wait("window.__has('Sign in')", 60)
            assert await tab.js("window.__click('button','Candidate')")
            assert await tab.js("window.__click('button','Create account')")
            await tab.js(f"window.__type('input[type=email]', {json.dumps(email)})")
            assert await tab.js("window.__click('button','Create account and send code')")
            assert await tab.wait("document.querySelectorAll('input[inputmode]').length === 6", 20)
            login_code = browser._code_for(mailbox, email)
            await tab.js(f"window.__type('input[inputmode]', {json.dumps(login_code)})")
            assert await tab.js("window.__click('button','Verify and continue')")
            assert await tab.wait("document.querySelector('#contact-destination')", 25)
            checks.check("actual candidate signup exposes separate contact-control form", await tab.js("window.__has('Verify a contact')")
                and not await tab.js("document.querySelector('[data-review-index]')"))
            await send()
            checks.check("empty destination refuses visibly without sent notice", await tab.wait("window.__has('Enter the contact on your candidate record')", 10)
                and not await tab.js("window.__has('Code sent.')"))
            await tab.js("window.__click('button','Phone contact')"); await type_dest("+919876543210"); await send()
            checks.check("phone unavailable is actual API refusal, not sent success", await tab.wait("window.__has('Phone delivery is unavailable')", 15)
                and not await tab.js("window.__has('Code sent.')"))
            await tab.js("window.__click('button','Email contact')"); await type_dest()
            await tab.js("window.__csrfCookie=document.cookie.split(';').find(p=>p.trim().startsWith('dee_csrf=')).trim(); document.cookie='dee_csrf=; Max-Age=0; Path=/'")
            await send()
            checks.check("actual CSRF failure settles and retains destination", await tab.wait("window.__has('Sign in again to continue')", 15)
                and await tab.js("document.querySelector('#contact-destination').value") == email)
            await tab.js("document.cookie=window.__csrfCookie+'; Path=/; SameSite=Lax'")
            control.write_text("unavailable", encoding="utf-8"); await send()
            checks.check("email unavailable has a visible honest refusal", await tab.wait("window.__has('Email delivery is unavailable')", 15)
                and not await tab.js("window.__has('Code sent.')"))
            control.write_text("failed", encoding="utf-8"); await send()
            checks.check("failed provider produces failed server record and no sent state", await tab.wait("window.__has('The code request failed')", 15)
                and all(v["status"] == "failed" for v in (await tab.js("window.VeritasAPI.get('/portal/verifications')"))["verifications"]))
            control.write_text("ok", encoding="utf-8")
            await tab.js("""
window.__nativeFetch=window.fetch; window.__contactPosts=0; window.__hold=true;
window.fetch=async (url,init)=>{
 if(init && init.method==='POST' && url==='/portal/verifications') {
  window.__contactPosts++;
  if(window.__hold) {window.__hold=false; await new Promise(resolve=>{window.__release=resolve;});}
 }
 return window.__nativeFetch(url,init);
};
""")
            await tab.js("window.__click('button','Send contact code'); window.__click('button','Working')")
            assert await tab.wait("window.__release", 10)
            checks.check("duplicate clicks send once with no pre-response sent notice", await tab.js("window.__contactPosts") == 1
                and not await tab.js("window.__has('Code sent.')"))
            await tab.js("window.__release()")
            assert await tab.wait("window.__has('Code sent.') && document.querySelector('#contact-code')", 20)
            first_id = await selected_id(); otp = latest_code(mailbox, email); codes.append(otp)
            checks.check("captured delivered code and actual pending record drive form", bool(otp)
                and await tab.js(f"document.querySelector('[data-contact-record=\"{first_id}\"]') !== null"))
            await confirm("000000" if otp != "000000" else "111111")
            checks.check("wrong code is a visible refusal and plaintext input is cleared", await tab.wait("window.__has('incorrect code')", 15)
                and await tab.js("document.querySelector('#contact-code').value") == "")
            foreign = admin.post(f"/portal/verifications/{first_id}/confirm", headers={"X-Candidate-Key": other_key}, json={"code": otp})
            checks.check("another candidate cannot confirm the delivered code", foreign.status_code == 404)
            await reload()
            assert await tab.wait(f"document.querySelector('[data-contact-record=\"{first_id}\"]')", 25)
            checks.check("reload restores persisted pending status without storing inputs", await tab.js("document.querySelector('#contact-destination').value") == "")
            await tab.js(f"document.querySelector('[data-contact-record=\"{first_id}\"] button').click()")
            assert await tab.wait("document.querySelector('#contact-code')", 10)
            mutate(first_id, expires_at=datetime.now(timezone.utc)-timedelta(seconds=1))
            await confirm(otp)
            checks.check("expired delivered code refuses and stops offering confirmation", await tab.wait("window.__has('challenge expired') && !document.querySelector('#contact-code')", 15))
            await type_dest(); await send()
            assert await tab.wait("window.__has('Code sent.')", 15)
            exhausted_id = await selected_id(); exhausted_code = latest_code(mailbox, email); codes.append(exhausted_code)
            mutate(exhausted_id, attempts=5)
            await confirm(exhausted_code)
            checks.check("exhausted correct code cannot verify and status becomes failed", await tab.wait("window.__has('too many attempts')", 15)
                and next(v for v in (await tab.js("window.VeritasAPI.get('/portal/verifications')"))["verifications"] if v["id"] == exhausted_id)["status"] == "failed")
            await send(); assert await tab.wait("window.__has('Code sent.')", 15)
            final_id = await selected_id(); final_code = latest_code(mailbox, email); codes.append(final_code)
            await confirm(final_code)
            checks.check("real confirmation shows advisory contact success and saved status", await tab.wait("window.__has('Contact verified. This proves contact control, not employment.')", 15)
                and (await tab.js("window.VeritasAPI.get('/portal/verifications')"))["assurance"]["level"] == 2
                and await assurance_status("held"))
            await tab.js("document.querySelector('#contact-destination').scrollIntoView({block:'center'})")
            shot = await tab.send("Page.captureScreenshot")
            (scratch / "verified-contact.png").write_bytes(base64.b64decode(shot["data"]))
            await reload()
            checks.check("reload retains actual verified record without exposing a risk score", await tab.wait(f"document.querySelector('[data-contact-record=\"{final_id}\"]')", 20)
                and not await tab.js("document.querySelector('[data-review-index]')") and await assurance_status("held"))
            with engine.begin() as session:
                session.execute(update(VerificationRow).where(VerificationRow.id == final_id)
                    .values(expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)))
            await reload()
            checks.check("lapsed outcome reads expired without a false held/low assurance", await assurance_status("expired")
                and (await tab.js("window.VeritasAPI.get('/portal/verifications')"))["assurance"]["level"] == 0)
            if '--contact-code-workers' in sys.argv:
                async def worker_finished():
                    async with asyncio.timeout(10):
                        while not contact_marker(mailbox, 'completed').exists():
                            await asyncio.sleep(.01)
                def reset_worker():
                    for name in ('entered', 'release', 'completed'):
                        contact_marker(mailbox, name).unlink(missing_ok=True)
                reset_worker()
                control.write_text('held')
                held = asyncio.create_task(asyncio.to_thread(admin.post, '/portal/verifications',
                    headers={'X-Candidate-Key': other_key}, json={'method': 'otp_email', 'destination': 'verify-other@example.com'}))
                try:
                    async with asyncio.timeout(10):
                        while not contact_marker(mailbox, 'entered').exists():
                            await asyncio.sleep(.01)
                    await type_dest(); await send()
                    checks.check('actual shared contact capacity refusal retains destination and makes no sent claim',
                        await tab.wait("window.__has('Contact code requests are busy') && !window.__has('Code sent.')", 10)
                        and await tab.js("document.querySelector('#contact-destination').value") == email
                        and not await tab.js("document.querySelector('#contact-code')"))
                finally:
                    contact_marker(mailbox, 'release').touch()
                    assert (await held).status_code in {200, 504}
                    await worker_finished()
                    control.write_text('ok')
                reset_worker()
                def deliveries():
                    return [json.loads(row) for row in mailbox.read_text().splitlines()
                        if json.loads(row)['to'] == email and json.loads(row)['subject'] == 'Verify your Veritas contact']
                before = len(deliveries())
                control.write_text('held')
                try:
                    await send()
                    checks.check('actual caller wait shows uncertain outcome without sent notice or automatic code entry',
                        await tab.wait("window.__has('A code can arrive later. Refresh contact status') && !window.__has('Code sent.')", 10)
                        and not await tab.js("document.querySelector('#contact-code')") and len(deliveries()) == before)
                finally:
                    contact_marker(mailbox, 'release').touch()
                    await worker_finished()
                    control.write_text('ok')
                await tab.js("window.__click('button', 'Refresh contact status')")
                late_id = await selected_id()
                assert await tab.wait(f"document.querySelector('[data-contact-record=\"{late_id}\"] button')", 15)
                await tab.js(f"document.querySelector('[data-contact-record=\"{late_id}\"] button').click()")
                late_code = latest_code(mailbox, email); codes.append(late_code)
                await confirm(late_code)
                checks.check('late delivered code confirms through own refreshed saved record without resending',
                    await tab.wait("window.__has('Contact verified. This proves contact control, not employment.')", 15)
                    and len(deliveries()) == before + 1)
                await reload()
                checks.check('late contact completion survives actual browser reload',
                    await tab.wait(f"document.querySelector('[data-contact-record=\"{late_id}\"]')", 20)
                    and await assurance_status('held'))
            if '--portal-read-workers' in sys.argv:
                codes.extend(await check_portal_read_workers(tab, scratch, checks, admin, mailbox, email, 'verify-other@example.com'))
            if '--portal-write-workers' in sys.argv:
                codes.extend(await check_portal_write_workers(tab, scratch, checks, admin, mailbox, email, 'verify-other@example.com', cid))
            await type_dest(); await send(); assert await tab.wait("document.querySelector('#contact-code')", 15)
            ending_code = latest_code(mailbox, email); codes.append(ending_code)
            await tab.js("window.VeritasAPI.post('/auth/logout')")
            await confirm(ending_code)
            checks.check("actual session expiry clears code/destination and returns to sign-in", await tab.wait("window.__has('Your session ended')", 15)
                and not await tab.js("document.querySelector('#contact-destination') || document.querySelector('#contact-code')"))
            checks.check("browser console has no errors or uncaught exceptions", not tab.console, "; ".join(tab.console[:2]))
            logged = (scratch / "server.log").read_text(encoding="utf-8")
            checks.check("actual app logs omit raw destination and delivered codes", all(v not in logged for v in [email, *codes]))
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
