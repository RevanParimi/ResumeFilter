"""Evaluation, feedback and contact over real Chrome and migrated scratch SQL.

Reuses the screening harness for OTP, browser startup and CDP. Timeout/network/
503 cases inject transport failures in this throwaway browser; success, PDF,
CSRF, expiry, ownership, outcomes and erasure use actual application HTTP.
Requires Chrome and internet for the existing CDN runtime assets.
"""
import asyncio
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile

import httpx

import check_ui_screening_browser as browser
from _smoke import Smoke
from smoke_r3_s1_t2 import latest_code


async def main():
    scratch = Path(tempfile.mkdtemp(prefix="r3-s1-t1-browser-"))
    print(f"Synthetic browser evidence: {scratch}", flush=True)
    checks = Smoke("R3-S1 evaluation / feedback / captured contact")
    original_run, original_popen = browser.run, subprocess.Popen
    owned = []
    log = (scratch / "server.log").open("w", encoding="utf-8")
    for attr in ("API_PORT", "CDP_PORT"):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            setattr(browser, attr, sock.getsockname()[1])
    browser.API_BASE = f"http://localhost:{browser.API_PORT}"
    browser.UI_URL = browser.API_BASE + "/ui/Veritas.dc.html"
    state = {}

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
                "DEE_VERIF_OTP_DEBUG_ECHO": "false",
                "DEE_LOGIN_OTP_STATIC_CODE": "", "DEE_SESSION_COOKIE_SECURE": "false",
                "DEE_LOGIN_OTP_COOLDOWN_SECONDS": "0",
                "DEE_SESSION_COOKIE_SAMESITE": "lax",
                "PYTHONPATH": os.pathsep.join(str(p) for p in (browser.ROOT / "src", browser.ROOT / "scripts", browser.ROOT)),
            })
            state["db"] = env["DEE_CANDIDATES_DB_URL"]
            kwargs.update(env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT)
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = original_popen(args, **kwargs)
        owned.append(proc)
        return proc

    async def run(tab, mailbox, files, admin):
        await tab.js(browser.HELPERS)
        assert await tab.wait("window.__has('Sign in')", 60, "login")

        async def shared_shell(plane):
            me = await tab.js("fetch('/auth/me', {credentials:'include'}).then(r => r.json())")
            if plane == "Candidate":
                portal = await tab.js("fetch('/portal/me', {credentials:'include'}).then(r => r.json())")
                name = (portal.get("profile") or {}).get("full_name")
                identity = (name.get("value") if isinstance(name, dict) else name) or "Your data"
            else:
                identity = "Operator" if plane == "Operator" else "Org " + me["organization_id"][:8]
            checks.check(plane + " shell renders its live identity and current-plane navigation",
                await tab.wait(f"window.__has({json.dumps(identity)})", 20)
                and await tab.js("!!document.querySelector('input[placeholder=\"Search candidates\"]')") == (plane == "Organisation")
                and "Sample data" not in await tab.text())
            assert await tab.js("window.__click('button', 'Light mode')")
            checks.check(plane + " shared theme control switches and restores through bound callbacks",
                await tab.wait("window.__has('Dark mode')", 10))
            assert await tab.js("window.__click('button', 'Dark mode')")
            assert await tab.wait("window.__has('Light mode')", 10)

        async def login(plane, email, signup=False):
            await tab.js(browser.HELPERS)
            assert await tab.js(f"window.__click('button', {json.dumps(plane)})")
            if signup:
                assert await tab.js("window.__click('button', 'Create account')")
                if plane == "Organisation":
                    await tab.js("window.__type('input[placeholder=\"Sampoorna Staffing\"]', 'Synthetic Instant Reviewer')")
            await tab.js(f"window.__type('input[type=email]', {json.dumps(email)})")
            assert await tab.js("window.__click('button', " + json.dumps("Create account and send code" if signup else "Send code") + ")")
            assert await tab.wait("document.querySelectorAll('input[inputmode]').length === 6", 20, "OTP")
            if plane == "Candidate" and signup:
                assert await tab.js("window.__click('a', 'Send another code')")
                checks.check("candidate resend keeps uniform acceptance copy", await tab.wait(
                    "window.__has('If that address is registered, another code is on its way.')", 20))
            code = browser._code_for(mailbox, email)
            if plane == "Candidate" and signup:
                wrong = str((int(code[0]) + 1) % 10) + code[1:]
                await tab.js(f"window.__type('input[inputmode]', {json.dumps(wrong)})")
                assert await tab.js("window.__click('button', 'Verify and continue')")
                checks.check("candidate wrong code refuses and clears digits before recovery", await tab.wait(
                    "window.__has('That code did not work') && [...document.querySelectorAll('input[inputmode]')].every(e => !e.value)", 20))
            await tab.js(f"window.__type('input[inputmode]', {json.dumps(code)})")
            assert await tab.js("window.__click('button', 'Verify and continue')")
            assert await tab.wait("window.__has('Sign out')", 25, "authenticated shell")
            await shared_shell(plane)

        async def install_transport():
            await tab.js("""
window.__paste = text => {
 const el = document.querySelector('#instant-resume');
 Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(el, text);
 el.dispatchEvent(new Event('input', {bubbles:true}));
};
window.__posts = [];
window.__nativeFetch = window.__nativeFetch || window.fetch;
window.__fault=null; window.__hold=false;
window.fetch = async (url, init) => {
 if (init && init.method === 'POST' && url.endsWith('/outcome') && window.__loseOutcomeAck) {
  window.__loseOutcomeAck=false;
  const response=await window.__nativeFetch(url, init);
  window.__savedOutcomeAck=response.ok;
  return new Promise((_r, reject) => init.signal.addEventListener('abort', () => reject(new Error('synthetic lost acknowledgement'))));
 }
 if (init && init.method === 'POST' && ['/evaluate','/screening/candidates'].includes(url)) {
  window.__posts.push({path:url, body:JSON.parse(init.body)});
  window.__lastReport=null;
  const fault = window.__fault; window.__fault = null;
  if (fault === 'timeout') return new Promise((_r, reject) => init.signal.addEventListener('abort', () => reject(new Error('synthetic stalled transport'))));
  if (fault === 'network') throw new Error('synthetic transport offline');
  if (fault === '503') return new Response(JSON.stringify({detail:'Service unavailable'}), {status:503, headers:{'content-type':'application/json'}});
  if (window.__hold) { window.__hold=false; await new Promise(resolve => { window.__release=resolve; }); }
  const response=await window.__nativeFetch(url, init);
  if (response.ok) { const result=await response.clone().json(); window.__lastReport=result.report || result; }
  return response;
 }
 return window.__nativeFetch(url, init);
};
""")

        async def reload():
            before = await tab.js("performance.timeOrigin")
            await tab.send("Page.reload")
            assert await tab.wait(f"performance.timeOrigin !== {before} && document.readyState === 'complete' && document.querySelector('button')", 60, "new document mounted")
            await tab.js(browser.HELPERS)
            await install_transport()

        async def paste(text):
            await tab.js("window.__paste(" + json.dumps(text) + ")")

        async def evaluate(button="Evaluate this resume"):
            assert await tab.js(f"window.__click('button', {json.dumps(button)})")

        async def report_ref():
            assert await tab.wait("window.__has('Claim by claim') && window.__has('Saved report:')", 30, "saved report")
            return await tab.js("new URLSearchParams(location.hash.slice(1)).get('report')")

        async def back():
            assert await tab.js("window.__click('button', 'Back to Instant check')")
            assert await tab.wait("document.querySelector('#instant-resume')", 15)

        await login("Organisation", "instant-org@example.com", signup=True)
        assert await tab.js("window.__click('button', 'Instant check')")
        assert await tab.wait("document.querySelector('#instant-resume')", 15)
        await install_transport()
        checks.check("org retention is explicit and screen has no sample-result notice",
            "saves a candidate, resume and report" in await tab.text() and "Sample data" not in await tab.text())
        await evaluate()
        checks.check("empty input refuses visibly without sending", await tab.wait("window.__has('Paste readable resume')", 10)
            and await tab.js("window.__posts.length") == 0)
        text = (browser.FIXTURES / "style_polished_resume.txt").read_text(encoding="utf-8")
        text = text.replace("Synthetic Taylor", "Synthetic Instant\nEmail: instant-candidate@example.com")
        await paste(text)
        # Real CSRF refusal, with the input retained and no success.
        await tab.js("window.__csrfCookie=document.cookie.split(';').find(p=>p.trim().startsWith('dee_csrf=')).trim(); document.cookie='dee_csrf=; Max-Age=0; Path=/'")
        await evaluate()
        checks.check("actual 403 settles without losing pasted input", await tab.wait("window.__has('Sign in again to continue')", 15)
            and await tab.js("document.querySelector('#instant-resume').value") == text
            and not await tab.js("window.__has('Saved report:')"))
        await tab.js("document.cookie=window.__csrfCookie+'; Path=/; SameSite=Lax'")
        await tab.js("window.__hold=true")
        await tab.js("window.__click('button','Retry evaluation'); window.__click('button','Evaluating')")
        assert await tab.wait("window.__release", 15)
        checks.check("duplicate clicks send one request and show real server-wait state",
            await tab.js("window.__posts.length") == 2 and "Waiting for the server assessment" in await tab.text()
            and await tab.js("[...document.querySelectorAll('button')].find(e=>e.textContent.includes('Evaluating')).disabled"))
        await tab.js("window.__release()")
        rid = await report_ref()
        actual = await tab.js(f"window.VeritasAPI.get('/screening/reports/{rid}')")
        rendered = await tab.text()
        checks.check("real report ID, summary and factual/style advisory presentation match server",
            actual["id"] == rid and actual["summary"] in rendered and rid in rendered
            and "Writing-style observations" in rendered and "writing style is excluded" in rendered)
        (scratch / "org-report.txt").write_text(rendered, encoding="utf-8")
        shot = await tab.send("Page.captureScreenshot")
        (scratch / "org-report.png").write_bytes(base64.b64decode(shot["data"]))
        other = admin.post("/ledger/orgs", json={"name": "Synthetic Other Instant Reviewer"}).json()
        denied = admin.get(f"/screening/reports/{rid}", headers={"X-Org-Key": other["api_key"]})
        checks.check("another organisation cannot read Instant check report", denied.status_code == 404)
        # Actual outcome write and read through the screen.
        assert await tab.js("window.__click('button', 'Verified genuine')")
        checks.check("review feedback is saved through the org route", await tab.wait("window.__has('One judgement recorded')", 15)
            and len((await tab.js(f"window.VeritasAPI.get('/screening/reports/{rid}/outcomes')"))["outcomes"]) == 1)
        await tab.js("window.__type('input[placeholder=\"What did you find out, and how?\"]', 'Synthetic follow-up notes'); window.__feedbackPost=window.VeritasAPI.post; window.VeritasAPI.post=(p,b,o)=>window.__feedbackPost(p,b,p.endsWith('/outcome') ? {timeoutMs:2000} : o); window.__loseOutcomeAck=true")
        assert await tab.js("window.__click('button', 'Inconclusive')")
        checks.check("lost feedback acknowledgement settles visibly and retains notes",
            await tab.wait("window.__has('Reload saved feedback before recording again')", 15)
            and await tab.js("document.querySelector('input[placeholder=\"What did you find out, and how?\"]').value") == "Synthetic follow-up notes"
            and await tab.js("window.__savedOutcomeAck") is True)
        checks.check("lost acknowledgement may already have saved the actual second judgement",
            len((await tab.js(f"window.VeritasAPI.get('/screening/reports/{rid}/outcomes')"))["outcomes"]) == 2)
        assert await tab.js("window.__click('button', 'Reload saved feedback')")
        checks.check("feedback recovery reads saved judgements without recording again",
            await tab.wait("window.__has('2 judgements, oldest first')", 15)
            and len((await tab.js(f"window.VeritasAPI.get('/screening/reports/{rid}/outcomes')"))["outcomes"]) == 2)
        await tab.js("window.VeritasAPI.post=window.__feedbackPost")
        await reload()
        checks.check("reload fetches the same authorized report without another upload", await report_ref() == rid)
        await install_transport()
        await back()
        checks.check("resume input is not persisted through reload", await tab.js("document.querySelector('#instant-resume').value") == "")
        # Real corrupt PDF refusal followed by a valid file-picker retry.
        invalid = scratch / "invalid.pdf"; invalid.write_bytes(b"%PDF-not-a-readable-document")
        valid = scratch / "valid.pdf"; valid.write_bytes(browser.minimal_pdf(text.splitlines()))
        async def choose(file):
            root = await tab.send("DOM.getDocument", {"depth": -1})
            node = await tab.send("DOM.querySelector", {"nodeId": root["root"]["nodeId"], "selector": "#instant-pdf"})
            await tab.send("DOM.setFileInputFiles", {"nodeId": node["nodeId"], "files": [str(file)]})
        await choose(invalid); await evaluate()
        checks.check("real unreadable PDF refuses visibly and retains selection", await tab.wait("window.__has('pdf_parse_failed')", 20)
            and "invalid.pdf" in await tab.text())
        await choose(valid)
        assert await tab.js("window.__click('button', 'GenAI')")
        await evaluate()
        pdf_id = await report_ref()
        checks.check("PDF retry returns a different real saved report in selected domain",
            pdf_id != rid and (await tab.js(f"window.VeritasAPI.get('/screening/reports/{pdf_id}')"))["domain"] == "genai")
        await back(); await paste(text)
        # Transport faults are explicitly synthetic, not live-provider evidence.
        await tab.js("window.__originalPost=window.VeritasAPI.post; window.VeritasAPI.post=(p,b,o)=>window.__originalPost(p,b,o ? {timeoutMs:30}:undefined); window.__fault='timeout'")
        await evaluate()
        checks.check("stalled transport timeout settles and warns about ambiguous save", await tab.wait("window.__has('Request timed out')", 10)
            and "may create another saved evaluation" in await tab.text()
            and await tab.js("document.querySelector('#instant-resume').value") == text)
        await tab.js("window.VeritasAPI.post=window.__originalPost; window.__fault='network'")
        await evaluate("Retry evaluation")
        checks.check("network failure settles with explicit retry", await tab.wait("window.__has('Could not reach the API')", 10))
        await tab.js("window.__fault='503'"); await evaluate("Retry evaluation")
        checks.check("service failure does not show a report or invented progress", await tab.wait("window.__has('Service unavailable')", 10)
            and not await tab.js("window.__has('Saved report:')"))
        await tab.js("window.__hold=true"); await evaluate("Retry evaluation")
        assert await tab.wait("window.__release", 10)
        assert await tab.js("window.__click('button', 'Signed-in devices')")
        await tab.js("window.__release()")
        assert await tab.wait("window.__lastReport && window.__lastReport.id", 30, "response completed while away")
        await asyncio.sleep(.25)
        checks.check("late success does not switch away from devices", not await tab.js("window.__has('Claim by claim')"))
        assert await tab.js("window.__click('button', 'Instant check')")
        assert await tab.wait("window.__has('Open saved report')", 30)
        checks.check("late completion leaves navigation alone and keeps a report reference",
            await tab.js("document.querySelector('#instant-resume') !== null"))
        assert await tab.js("window.__click('button', 'Open saved report')")
        saved = await report_ref()
        saved_report = admin.get(f"/report/{saved}").json()
        assert admin.delete(f'/candidates/{saved_report["candidate_id"]}').status_code == 200
        await reload()
        checks.check("erased report reload gives actual 404 and read-only recovery", await tab.wait("window.__has('report not found')", 20)
            and await tab.js("window.__has('Reload saved report')"))
        await back(); await paste(text)
        # Revoke the browser session on the server without notifying the UI;
        # its next evaluation must get a real 401 from the expired cookie.
        await tab.js("window.VeritasAPI.post('/auth/logout')")
        # Hold an actual expired-session 401 until a new account signs in.
        await tab.js("""
window.__before401Fetch=window.fetch; window.__hold401=true;
window.fetch=async (url,init)=>{
 const response=await window.__before401Fetch(url,init);
 if(url==='/auth/me' && window.__hold401) {
  window.__hold401=false; window.__delayed401Status=response.status;
  return new Promise(resolve=>{window.__release401=()=>resolve(response);});
 }
 return response;
};
window.VeritasAPI.get('/auth/me').catch(err=>{window.__old401Kind=err.kind;});
void 0;
""")
        assert await tab.wait("window.__release401", 10, "actual old-session response held")
        await evaluate()
        checks.check("real session expiry sends user to sign-in and clears report URL", await tab.wait("window.__has('Your session ended')", 15)
            and await tab.js("location.hash") == "")
        # Operator's ad-hoc path and outcome route.
        assert admin.post("/admin/users", json={"email": "instant-operator@example.com", "label": "Synthetic Instant Operator"}).status_code == 200
        await login("Operator", "instant-operator@example.com")
        await tab.js("window.__release401()")
        checks.check("actual old-session 401 cannot sign out the new operator account",
            await tab.wait("window.__old401Kind === 'session_lost'", 10)
            and await tab.js("window.__delayed401Status") == 401
            and await tab.js("window.__has('Sign out')"))
        assert await tab.js("window.__click('button', 'Instant check')")
        await install_transport(); await paste(text)
        await tab.js("window.__type('#instant-github', 'https://github.com/synthetic/instant')")
        await evaluate()
        operator_id = await report_ref()
        checks.check("operator uses ad-hoc route and saves a candidate-free report",
            await tab.js("window.__posts[0].path") == "/evaluate"
            and admin.get(f"/report/{operator_id}").json()["candidate_id"] is None)
        assert await tab.js("window.__click('button', 'Verified genuine')")
        checks.check("operator feedback uses admin report routes", await tab.wait("window.__has('One judgement recorded')", 15)
            and len(admin.get(f"/report/{operator_id}/outcomes").json()["outcomes"]) == 1)
        await reload()
        checks.check("operator report reload retains actual ID", await report_ref() == operator_id)
        assert await tab.js("window.__click('button', 'Sign out')")
        assert await tab.wait("window.__has('Sign in')", 15)
        await login("Candidate", "instant-candidate@example.com", signup=True)
        checks.check("candidate has no evaluation action", not await tab.js("window.__has('Instant check')"))
        with httpx.Client(base_url=browser.API_BASE, headers={"User-Agent": "Synthetic sibling device"}) as sibling:
            email = "instant-candidate@example.com"
            assert sibling.post("/auth/candidate/login", json={"email": email}).status_code == 202
            assert sibling.post("/auth/candidate/verify", json={
                "email": email, "code": browser._code_for(mailbox, email)}).status_code == 200
            assert await tab.js("window.__click('button', 'Signed-in devices')")
            checks.check("candidate devices show the saved sibling and current session", await tab.wait(
                "window.__has('Synthetic sibling device') && window.__has('This device')", 20))
            assert await tab.js("window.__click('button', 'Revoke')")
            checks.check("browser revokes sibling while retaining the current session", await tab.wait(
                "!window.__has('Synthetic sibling device') && window.__has('This device')", 20)
                and sibling.get("/auth/me").status_code == 401
                and (await tab.js("window.VeritasAPI.get('/auth/me')"))["kind"] == "candidate")
        assert await tab.js("window.__click('button', 'Overview')")
        # Continue in the same app/browser composition, using the separately
        # proved login subject rather than treating resume contact hints as proof.
        email = "instant-candidate@example.com"
        assert await tab.wait("document.querySelector('#contact-destination')", 20)
        await tab.js(f"window.__type('#contact-destination', {json.dumps(email)})")
        control = Path(str(mailbox) + ".control")
        control.write_text("failed", encoding="utf-8")
        assert await tab.js("window.__click('button', 'Send contact code')")
        checks.check("combined journey refuses failed contact delivery without sent success",
            await tab.wait("window.__has('The code request failed')", 15)
            and not await tab.js("window.__has('Code sent.')")
            and await tab.js("document.querySelector('#contact-destination').value") == email)
        control.write_text("ok", encoding="utf-8")
        assert await tab.js("window.__click('button', 'Send contact code')")
        assert await tab.wait("window.__has('Code sent.') && document.querySelector('#contact-code')", 15)
        contact_code = latest_code(mailbox, email)
        await tab.js(f"window.__type('#contact-code', {json.dumps(contact_code)})")
        assert await tab.js("window.__click('button', 'Confirm contact code')")
        assert await tab.wait("window.__has('Contact verified. This proves contact control, not employment.')", 15)
        contact = await tab.js("window.VeritasAPI.get('/portal/verifications')")
        verified_id = next(v["id"] for v in contact["verifications"] if v["status"] == "verified")
        checks.check("combined journey confirms delivered contact with advisory assurance",
            contact["assurance"]["level"] == 2 and contact["assurance"]["advisory"]
            and not await tab.js("document.querySelector('#contact-code')"))
        await reload()
        checks.check("combined journey reloads contact outcome and clears transient input",
            await tab.wait(f"document.querySelector('[data-contact-record=\"{verified_id}\"]')", 20)
            and await tab.js("document.querySelector('#contact-destination').value") == ""
            and (await tab.js("window.VeritasAPI.get('/portal/verifications')"))["assurance"]["level"] == 2)
        checks.check("combined app logs omit destination and delivered contact code",
            all(value not in (scratch / "server.log").read_text(encoding="utf-8")
                for value in (email, contact_code)))
        # T3H reuses this actual candidate session for portal/consent/erasure.
        def portal_response(response, status=200):
            assert response.status_code == status, (response.request.url.path, response.status_code)
            return response.json()
        subject = (await tab.js("window.VeritasAPI.get('/portal/me')"))["candidate_id"]
        organization = portal_response(admin.post("/ledger/orgs", json={"name": "Synthetic Portal Browser"}))
        oid = organization["org"]["id"]
        grant = await tab.js("window.VeritasAPI.post('/portal/consents'," + json.dumps({
            "purpose": "ledger_read", "org_id": oid}) + ")")
        assert grant["candidate_id"] == subject
        ledger_path = f"/ledger/candidates/{subject}/records"
        org_headers = {"X-Org-Key": organization["api_key"]}
        portal_response(admin.get(ledger_path, headers=org_headers))
        assert await tab.js("window.__click('button', 'Consents')")
        checks.check("portal browser renders its own active consent", await tab.wait(
            f"window.__has({json.dumps(oid)}) && [...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='Revoke')", 20))
        assert await tab.js("window.__click('button', 'Revoke')")
        checks.check("portal browser revoke persists before the next employer read", await tab.wait(
            "window.__has('Revoked') && ![...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='Revoke')", 20)
            and admin.get(ledger_path, headers=org_headers).status_code == 403)
        assert await tab.js("window.__click('button', 'Who accessed it')")
        checks.check("portal browser shows allowed and refused access with the actor", await tab.wait(
            "window.__has('Synthetic Portal Browser') && window.__has('record.query') && window.__has('Allowed') && window.__has('Refused')", 20))
        await reload()
        assert await tab.wait("window.__has('Sign out')", 20)
        assert await tab.js("window.__click('button', 'Consents')")
        checks.check("new document reload retains revoked portal consent", await tab.wait("window.__has('Revoked')", 20)
            and (await tab.js("window.VeritasAPI.get('/portal/consents')"))[0]["grant"]["id"] == grant["id"])
        await tab.js("""window.__portalFetch = window.fetch;
window.fetch = (url, init) => String(url).endsWith('/portal/me')
 ? Promise.resolve(new Response(JSON.stringify({detail:'synthetic portal read failure'}), {status:503, headers:{'Content-Type':'application/json'}}))
 : window.__portalFetch(url, init);""")
        assert await tab.js("window.__click('button', 'Overview')")
        checks.check("portal browser renders failed access-view read", await tab.wait("window.__has('synthetic portal read failure')", 20))
        await tab.js("window.fetch = window.__portalFetch")
        assert await tab.js("window.__click('button', 'Consents')")
        assert await tab.js("window.__click('button', 'Overview')")
        checks.check("portal browser recovers from failed access-view read", await tab.wait(
            "window.__has('Everything Veritas holds about you') && !window.__has('synthetic portal read failure') && document.querySelector('#contact-destination')", 20))
        survivor = portal_response(admin.post("/candidates", json={"evaluate": False, "resume_text":
            "Synthetic Portal Survivor\nEmail: portal-survivor@example.in\nSKILLS\nSQL"}))["candidate_id"]
        survivor_key = portal_response(admin.post(f"/candidates/{survivor}/auth-key"))["access_key"]
        own_key = portal_response(admin.post(f"/candidates/{subject}/auth-key"))["access_key"]
        assert await tab.js("window.__click('button', 'Delete everything')")
        assert await tab.js("window.__type('input[placeholder=\"DELETE\"]', 'DELETE')")
        assert await tab.wait("document.querySelector('input[placeholder=\"DELETE\"]').parentElement.querySelector('button')", 10)
        assert await tab.js("document.querySelector('input[placeholder=\"DELETE\"]').parentElement.querySelector('button').click(); true")
        checks.check("portal browser erasure ends the session and preserves another subject", await tab.wait(
            "window.__has('Your data has been deleted') && document.querySelector('input[type=email]')", 20)
            and admin.get("/portal/me", headers={"X-Candidate-Key": own_key}).status_code == 401
            and portal_response(admin.get("/portal/me", headers={"X-Candidate-Key": survivor_key}))["candidate_id"] == survivor)
        checks.check("browser journeys have no console exceptions", not tab.console, "; ".join(tab.console[:2]))
        (scratch / "database-url.txt").write_text(state["db"], encoding="utf-8")

    browser.run = run
    subprocess.Popen = launch
    try:
        await browser.main()
        return checks.summary()
    finally:
        browser.run, subprocess.Popen = original_run, original_popen
        for proc in owned:
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait(timeout=10)
        log.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
