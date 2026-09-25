"""Real Chrome queue/reload/fresh-upload journey on the smoke's scratch app.

Invoked by smoke_r1_s1_t3b_d3b2b2.py --browser. Authentication setup uses real
HTTP/capture email; the queue and upload actions use the rendered browser UI.
The existing frontend runtime requires internet CDN assets.
"""

import asyncio
import base64
import json
import os
import socket
import subprocess

import httpx
import websockets

from check_ui_screening_browser import Tab, HELPERS, _chrome, _code_for


async def check_browser(base, admin, scratch, checks):
    with httpx.Client(base_url=base, timeout=30) as user:
        email = "unresolved-browser@example.com"
        assert user.post("/auth/org/signup", json={
            "email": email, "organization_name": "Synthetic browser agency"}).status_code == 202
        code = _code_for(scratch / "mailbox.jsonl", email)
        assert user.post("/auth/org/verify", json={"email": email, "code": code}).status_code == 200
        user.headers["X-CSRF-Token"] = user.cookies.get("dee_csrf")
        content = "Synthetic browser engineer\nEmail: browser-subject@example.com\nSkills: Python"
        subject = user.post("/screening/candidates", json={
            "resume_text": content, "evaluate": False})
        assert subject.status_code == 200
        registered = user.post("/screening/batches", json={"name": "Needs fresh upload", "domain": "genai",
                              "items": [{"resume_text": content}]})
        assert registered.status_code == 200
        assert admin.delete(f"/candidates/{subject.json()['candidate_id']}").status_code == 200

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        chrome = subprocess.Popen([
            _chrome(), "--headless=new", f"--remote-debugging-port={port}",
            "--no-first-run", "--no-default-browser-check", "--disable-gpu",
            f"--user-data-dir={scratch / 'chrome-profile'}", "--window-size=1440,1000", "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            async with httpx.AsyncClient() as cdp:
                pages = []
                for _ in range(60):
                    try:
                        pages = (await cdp.get(f"http://127.0.0.1:{port}/json")).json()
                        if any(p["type"] == "page" for p in pages):
                            break
                    except httpx.TransportError:
                        pass
                    await asyncio.sleep(0.25)
            pages = [p for p in pages if p["type"] == "page"]
            assert pages and all(p["url"] in ("about:blank", "") for p in pages)
            async with websockets.connect(pages[0]["webSocketDebuggerUrl"], max_size=40_000_000) as ws:
                tab = Tab(ws)
                await tab.send("Runtime.enable")
                await tab.send("Page.enable")
                await tab.send("DOM.enable")
                await tab.send("Network.enable")
                for cookie in user.cookies.jar:
                    await tab.send("Network.setCookie", {"name": cookie.name, "value": cookie.value,
                                                         "url": base, "path": "/"})
                await tab.send("Page.navigate", {"url": base + "/ui/Veritas.dc.html"})
                reason = "document.body.innerText.includes('Upload this resume again')"
                assert await tab.wait(reason, 50, "fresh-upload instruction")
                checks.check("browser renders actionable paused queue", True)
                await tab.send("Page.reload")
                assert await tab.wait(reason, 30, "paused queue after reload")
                checks.check("browser reload preserves refusal", True)
                shot = await tab.send("Page.captureScreenshot", {"format": "png"})
                (scratch / "paused-queue.png").write_bytes(base64.b64decode(shot["data"]))
                await tab.js(HELPERS)
                assert await tab.js("window.__click('button', 'Upload')")
                assert await tab.wait("document.querySelector('input[type=file]')", 20, "upload picker")
                upload = scratch / "fresh-resume.txt"
                upload.write_text(content, encoding="utf-8")
                picker = await tab.js("document.querySelector('input[type=file]')", by_value=False)
                await tab.send("DOM.setFileInputFiles", {"files": [str(upload)], "objectId": picker})
                assert await tab.wait("window.__has('file ready')", 15, "selected file")
                assert await tab.js("window.__click('button', 'Register batch and start screening')")
                assert await tab.wait("window.__has('Nothing left to screen')", 60, "fresh upload processing")
                batches = user.get("/screening/batches").json()["batches"]
                assert len(batches) == 2 and sum(b["counts"]["done"] for b in batches) == 1
                checks.check("browser fresh upload completes while original remains paused", True)
                assert not tab.console, tab.console
                checks.check("browser has no console errors or uncaught exceptions", True)
        finally:
            chrome.terminate()
            try:
                chrome.wait(timeout=15)
            except subprocess.TimeoutExpired:
                chrome.kill()
                chrome.wait(timeout=10)
