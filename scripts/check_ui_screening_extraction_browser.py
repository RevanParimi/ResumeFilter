"""Real screening Chrome journey with fake providers and disposable storage.

Reuse file intake, processing, queue, feedback, summary and deletion actions.
Add a second file intake, persisted reload and injected batch-read error/recovery.
Requires Chrome and the existing CDN runtime internet; no live provider calls.
--body-limit also verifies actual ingress 413 rendering and fresh-file recovery.
--pdf-execution verifies actual PDF capacity refusal and recovery/reload.
--auth-code-workers verifies actual auth admission/delayed-mail/manual recovery.
"""

import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

import check_ui_screening_browser as browser


async def main():
    scratch = Path(tempfile.mkdtemp(prefix="r4-s1-t3d-browser-"))
    print(f"Synthetic screening browser evidence: {scratch}", flush=True)
    original_run, original_popen = browser.run, subprocess.Popen
    owned = []
    log = (scratch / "server.log").open("w", encoding="utf-8")
    for attr in ("API_PORT", "CDP_PORT"):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            setattr(browser, attr, sock.getsockname()[1])
    browser.API_BASE = f"http://localhost:{browser.API_PORT}"
    browser.UI_URL = browser.API_BASE + "/ui/Veritas.dc.html"

    def launch(args, **kwargs):
        if "app.main:app" in args:
            args = ["smoke_r3_s1_t2:create_smoke_app" if arg == "app.main:app" else arg for arg in args] + ["--factory"]
            if '--pdf-execution' in sys.argv:
                args = ['smoke_r4_s1_t3d:create_smoke_app' if arg == 'smoke_r3_s1_t2:create_smoke_app' else arg for arg in args]
            if '--auth-code-workers' in sys.argv:
                args = ['smoke_r4_s1_t3a:create_auth_code_smoke_app' if arg == 'smoke_r3_s1_t2:create_smoke_app' else arg for arg in args]
            inherited = kwargs["env"]
            env = {key: value for key, value in inherited.items() if not key.startswith("DEE_")}
            env.update({key: value for key, value in inherited.items() if key in {
                "DEE_CANDIDATES_DB_URL", "DEE_FLYWHEEL_PATH", "DEE_EMAIL_CAPTURE_PATH", "DEE_API_AUTH_KEY"}})
            env.update({
                "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_ENV": "local",
                "DEE_OPENROUTER_API_KEY": "", "DEE_GITHUB_TOKEN": "",
                "DEE_GITHUB_API_BASE": "http://127.0.0.1:9", "DEE_EMAIL_PROVIDER": "capture",
                "DEE_SPEECH_PROVIDER": "local", "DEE_LOGIN_OTP_DEBUG_ECHO": "false",
                "DEE_LOGIN_OTP_STATIC_CODE": "", "DEE_VERIF_OTP_DEBUG_ECHO": "false",
                "DEE_SESSION_COOKIE_SECURE": "false", "DEE_SESSION_COOKIE_SAMESITE": "lax",
                "PYTHONPATH": os.pathsep.join(str(path) for path in (browser.ROOT / "src", browser.ROOT / "scripts", browser.ROOT)),
            })
            if "--body-limit" in sys.argv:
                env["DEE_MAX_REQUEST_BODY_BYTES"] = "64000"
            if '--pdf-execution' in sys.argv:
                env.update(VERITAS_PDF_EXECUTION_SMOKE='true', VERITAS_SQL_SMOKE_EVENTS=str(scratch / 'lifecycle.jsonl'),
                           DEE_PDF_MAX_CONCURRENT_PARSES='1', DEE_PDF_PARSE_TIMEOUT_SECONDS='15')
            if '--auth-code-workers' in sys.argv:
                env.update(VERITAS_SQL_SMOKE_EVENTS=str(scratch / 'lifecycle.jsonl'),
                           DEE_AUTH_CODE_MAX_CONCURRENT_REQUESTS='1', DEE_AUTH_CODE_WAIT_SECONDS='.5')
            kwargs.update(env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT)
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = original_popen(args, **kwargs)
        owned.append(proc)
        return proc

    async def run(tab, mailbox, files, admin):
        if '--auth-code-workers' in sys.argv:
            async def auth_reload(condition):
                await tab.js('window.__authReloadMarker = true')
                await tab.send('Page.reload')
                assert await tab.wait('!window.__authReloadMarker && (' + condition + ')', 30, 'new auth document')
                await tab.js(browser.HELPERS)
            await tab.js(browser.HELPERS)
            assert await tab.wait("document.querySelector('input[type=email]')", 30, 'auth screen')
            (scratch / 'auth-mode').write_text('mail')
            held = asyncio.create_task(asyncio.to_thread(admin.post, '/auth/candidate/signup',
                json={'email': 'held-browser-auth@example.in'}))
            try:
                async with asyncio.timeout(8):
                    while not (scratch / 'auth-entered').exists():
                        await asyncio.sleep(.01)
                assert await tab.js("window.__type('input[type=email]', 'busy-browser-auth@example.in', 0)")
                assert await tab.js("window.__click('button', 'Send code')")
                browser.S.check('actual global auth capacity refusal has useful recovery copy',
                    await tab.wait("window.__has('Code requests are busy. Try again shortly.')", 10, 'auth busy refusal')
                    and await tab.js("document.querySelectorAll('input[inputmode]').length") == 0)
            finally:
                (scratch / 'auth-release').touch()
                assert (await held).status_code == 202
                async with asyncio.timeout(8):
                    while not (scratch / 'auth-completed').exists():
                        await asyncio.sleep(.01)
                (scratch / 'auth-mode').unlink(missing_ok=True)
            for name in ('auth-entered', 'auth-completed', 'auth-release'):
                (scratch / name).unlink(missing_ok=True)
            await auth_reload("[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='Candidate' && b.offsetParent)")
            assert await tab.js("window.__click('button', 'Candidate')")
            email = 'late-browser-auth@example.in'
            (scratch / 'auth-mode').write_text('mail')
            try:
                assert await tab.js(f"window.__type('input[type=email]', '{email}', 0)")
                assert await tab.js("window.__click('button', 'Send code')")
                browser.S.check('real caller timeout permits manual code entry without claiming delivery',
                    await tab.wait("document.querySelectorAll('input[inputmode]').length === 6 && window.__has('Delivery may still be in progress') && window.__has('Requested for') && !window.__has('Sent to')", 10, 'pending code entry')
                    and email not in (mailbox.read_text() if mailbox.exists() else ''))
            finally:
                (scratch / 'auth-release').touch()
                async with asyncio.timeout(8):
                    while not (scratch / 'auth-completed').exists():
                        await asyncio.sleep(.01)
                (scratch / 'auth-mode').unlink(missing_ok=True)
            code = browser._code_for(mailbox, email)
            assert await tab.js(f"window.__type('input[inputmode]', '{code}', 0)")
            assert await tab.js("window.__click('button', 'Verify and continue')")
            browser.S.check('late delivered code signs in after one manually entered verification',
                await tab.wait("window.__has('Sign out')", 25, 'late-code signed-in shell')
                and len([row for row in mailbox.read_text().splitlines() if json.loads(row)['to'] == email]) == 1)
            await auth_reload("document.body.innerText.includes('Sign out')")
            browser.S.check('late-code session survives actual browser reload',
                (await tab.js("fetch('/auth/me', {credentials:'include'}).then(r=>r.json())"))['kind'] == 'candidate')
            assert await tab.js("window.__click('button', 'Sign out')")
            assert await tab.wait("document.querySelector('input[type=email]')", 20, 'signed-out auth screen')
            await auth_reload("[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='Organisation' && b.offsetParent)")
            assert await tab.js("window.__click('button', 'Organisation')")
        await original_run(tab, mailbox, files, admin)
        assert await tab.js("window.__click('button', 'Upload')")
        assert await tab.wait("document.querySelector('input[type=file]')", 20, "new file intake")
        box = await tab.js("document.querySelector('input[type=file]')", by_value=False)
        await tab.send("DOM.setFileInputFiles", {"files": files[:1], "objectId": box})
        assert await tab.wait("window.__has('file ready')", 20, "selected file")
        assert await tab.js("window.__type('input[placeholder*=intake]', 'Router reload intake', 0)")
        assert await tab.js("window.__click('button', 'Register batch and start screening')")
        assert await tab.wait("window.__has('Nothing left to screen')", 60, "new batch screening")
        with browser._org_client(admin) as api:
            batches = api.get("/screening/batches").json()["batches"]
            assert len(batches) == 1 and batches[0]["name"] == "Router reload intake"
            bid = batches[0]["id"]
            browser.S.check("second actual file intake persists one completed batch",
                api.get(f"/screening/batches/{bid}/summary").json()["n_screened"] == 1)
            await tab.js("window.__screeningReloadMarker = true")
            await tab.send("Page.reload")
            assert await tab.wait("!window.__screeningReloadMarker && document.body.innerText.includes('Sign out')", 60, "authenticated new document")
            await tab.js(browser.HELPERS)
            assert await tab.js("window.__click('button', 'Batches')")
            browser.S.check("reloaded batch list renders the persisted intake",
                await tab.wait("window.__has('Router reload intake')", 30, "persisted batch"))
            await tab.js("""
window.__screeningFetch = window.fetch;
window.__failBatchRead = true;
window.fetch = (url, init) => {
 if (window.__failBatchRead && String(url).endsWith('/screening/batches') && (!init || !init.method || init.method === 'GET')) {
  return new Promise(resolve => setTimeout(() => resolve(new Response(JSON.stringify({detail:'Synthetic batch read failure'}), {status:503, headers:{'content-type':'application/json'}})), 100));
 }
 return window.__screeningFetch(url, init);
};
""")
            assert await tab.js("window.__click('button', 'Batches')")
            browser.S.check("batch list renders an injected read failure",
                await tab.wait("window.__has('Synthetic batch read failure')", 20, "batch error"))
            await tab.js("window.fetch = window.__screeningFetch")
            assert await tab.js("window.__click('button', 'Batches')")
            browser.S.check("batch list recovers using saved server state",
                await tab.wait("window.__has('Router reload intake') && !window.__has('Synthetic batch read failure')", 20, "batch recovery")
                and api.get(f"/screening/batches/{bid}").status_code == 200)
            if '--pdf-execution' in sys.argv:
                import base64
                from tests.pdf_helpers import resume_pdf
                pdf = resume_pdf('Python SQL synthetic browser PDF')
                file = scratch / 'capacity-intake.pdf'
                file.write_bytes(base64.b64decode(pdf))
                (scratch / 'pdf-mode').write_text('stall')
                held = asyncio.create_task(asyncio.to_thread(api.post, '/screening/batches',
                    json={'name': 'Held browser PDF', 'items': [{'resume_pdf_b64': pdf}]}))
                try:
                    async with asyncio.timeout(8):
                        while not (scratch / 'pdf-entered').exists():
                            await asyncio.sleep(.02)
                    assert await tab.js("window.__click('button', 'Upload')")
                    assert await tab.wait("document.querySelector('input[type=file]')", 20, 'PDF file intake')
                    box = await tab.js("document.querySelector('input[type=file]')", by_value=False)
                    await tab.send('DOM.setFileInputFiles', {'files': [str(file)], 'objectId': box})
                    assert await tab.wait("window.__has('file ready')", 20, 'PDF selected')
                    assert await tab.js("window.__type('input[placeholder*=intake]', 'PDF capacity recovery', 0)")
                    assert await tab.js("window.__click('button', 'Register batch and start screening')")
                    browser.S.check('actual PDF capacity 503 renders without partial registration',
                        await tab.wait("window.__has('pdf_capacity_exhausted')", 10, 'PDF admission refusal')
                        and all(row['name'] != 'PDF capacity recovery' for row in api.get('/screening/batches').json()['batches']))
                finally:
                    (scratch / 'pdf-release').touch()
                    result = await held
                    (scratch / 'pdf-mode').unlink(missing_ok=True)
                assert result.status_code == 200
                assert await tab.js("window.__click('button', 'Clear')")
                box = await tab.js("document.querySelector('input[type=file]')", by_value=False)
                await tab.send('DOM.setFileInputFiles', {'files': [str(file)], 'objectId': box})
                assert await tab.wait("window.__has('file ready')", 20, 'fresh PDF selection')
                assert await tab.js("window.__click('button', 'Register batch and start screening')")
                assert await tab.wait("window.__has('Nothing left to screen')", 60, 'PDF recovery screening')
                browser.S.check('fresh PDF intake recovers and screens once after capacity returns',
                    len([row for row in api.get('/screening/batches').json()['batches']
                         if row['name'] == 'PDF capacity recovery' and row['counts']['done'] == 1]) == 1)
                await tab.send('Page.reload')
                assert await tab.wait("document.body.innerText.includes('Sign out')", 60, 'PDF recovery reload')
                await tab.js(browser.HELPERS)
                assert await tab.js("window.__click('button', 'Batches')")
                browser.S.check('PDF recovery persists after actual browser reload',
                    await tab.wait("window.__has('PDF capacity recovery')", 30, 'saved PDF recovery'))
            if "--body-limit" in sys.argv:
                oversized = scratch / "aggregate-oversize.txt"
                oversized.write_text("Readable synthetic resume\n" + "x" * 65_000, encoding="utf-8")
                assert await tab.js("window.__click('button', 'Upload')")
                assert await tab.wait("document.querySelector('input[type=file]')", 20, "body-limit file intake")
                box = await tab.js("document.querySelector('input[type=file]')", by_value=False)
                await tab.send("DOM.setFileInputFiles", {"files": [str(oversized)], "objectId": box})
                assert await tab.wait("window.__has('file ready')", 20, "oversized selected file")
                assert await tab.js("window.__type('input[placeholder*=intake]', 'Rejected body intake', 0)")
                assert await tab.js("window.__click('button', 'Register batch and start screening')")
                browser.S.check("actual aggregate 413 renders on the upload screen without a saved batch",
                    await tab.wait("window.__has('request body exceeds max_request_body_bytes=64000')", 20, "body limit refusal")
                    and all(row["name"] != "Rejected body intake" for row in api.get("/screening/batches").json()["batches"]))
                assert await tab.js("window.__click('button', 'Clear')")
                assert await tab.wait("!window.__has('aggregate-oversize.txt') && !window.__has('request body exceeds')", 20, "cleared refused selection")
                box = await tab.js("document.querySelector('input[type=file]')", by_value=False)
                await tab.send("DOM.setFileInputFiles", {"files": files[:1], "objectId": box})
                assert await tab.wait("window.__has('file ready')", 20, "replacement selected file")
                assert await tab.js("window.__type('input[placeholder*=intake]', 'Body limit recovery intake', 0)")
                assert await tab.js("window.__click('button', 'Register batch and start screening')")
                assert await tab.wait("window.__has('Nothing left to screen')", 60, "body limit recovery")
                browser.S.check("fresh valid file recovers after 413 and screens once",
                    len([row for row in api.get("/screening/batches").json()["batches"]
                         if row["name"] == "Body limit recovery intake" and row["counts"]["done"] == 1]) == 1)
                await tab.send("Page.reload")
                assert await tab.wait("document.body.innerText.includes('Sign out')", 60, "body recovery reload")
                await tab.js(browser.HELPERS)
                assert await tab.js("window.__click('button', 'Batches')")
                browser.S.check("recovered body-limit intake persists after actual browser reload",
                    await tab.wait("window.__has('Body limit recovery intake')", 30, "persisted body recovery"))
            browser.S.check("extended screening journey has no console exceptions", not tab.console, "; ".join(tab.console[:2]))

    browser.run, subprocess.Popen = run, launch
    try:
        return await browser.main()
    finally:
        browser.run, subprocess.Popen = original_run, original_popen
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
