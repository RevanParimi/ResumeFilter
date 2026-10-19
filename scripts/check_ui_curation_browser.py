"""Real Chrome reviewer journeys. Invoked by smoke_curation_activation.py --browser.

Reuses the existing CDP driver; requires Chrome and internet for shipped CDN assets.
Only synthetic scratch-server records and a fresh browser profile are touched.
"""

import asyncio
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import urllib.request
from datetime import datetime, timedelta, timezone

import websockets

from check_ui_screening_browser import Tab, HELPERS, _chrome
from smoke_curation_input import export
from _smoke import client


async def run_browser(base, scratch, dbpath, admin, cid, checks):
    from smoke_curation_activation import free_port
    port = free_port()
    profile = tempfile.mkdtemp(prefix="curation-browser-")
    chrome = subprocess.Popen([_chrome(), "--headless=new", f"--remote-debugging-port={port}",
        "--no-first-run", "--no-default-browser-check", f"--user-data-dir={profile}",
        "--disable-gpu", "--window-size=1440,1000", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        target = None
        for _ in range(60):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2))
                pages = [t for t in targets if t["type"] == "page"]
                assert all(p["url"] in ("about:blank", "") for p in pages), "unexpected browser target"
                if pages:
                    target = pages[0]["webSocketDebuggerUrl"]
                    break
            except OSError:
                pass
            await asyncio.sleep(0.25)
        assert target, "fresh Chrome did not start"
        async with websockets.connect(target, max_size=40_000_000) as ws:
            tab = Tab(ws)
            await tab.send("Runtime.enable")
            await tab.send("Page.enable")
            await tab.send("Network.enable")
            await tab.send("Page.navigate", {"url": base + "/ui/"})
            assert await tab.wait("document.querySelector('input[type=email]')", 45, "login")
            # The shipped HTML includes a prerendered form. Its presence does
            # not prove that handlers are mounted or startup's /auth/me settled.
            assert await tab.wait("performance.getEntriesByType('resource').some("
                "e => new URL(e.name).pathname === '/auth/me')", 45, "completed sign-in boot")
            await tab.js(HELPERS)
            refused = await tab.js("fetch('/curation/skills/unmapped').then(r=>r.status)")
            checks.check("browser anonymous reviewer refused", refused == 401)
            assert await tab.js("window.__click('button','Operator')")
            assert await tab.wait("window.__has('Operator sign in')", 15, "mounted operator form")
            assert await tab.js("window.__type('input[type=email]', 'reviewer@example.com')")
            await asyncio.sleep(0.2)
            await tab.js("window.__click('button','Send code')")
            assert await tab.wait("document.querySelectorAll('input[inputmode]').length === 6", 20, "OTP")
            mail = json.loads((scratch / "mail.jsonl").read_text(encoding="utf-8").splitlines()[-1])
            code = re.search(r"\b(\d{6})\b", mail["body"]).group(1)
            await tab.js(f"window.__type('input[inputmode]', {json.dumps(code)})")
            await asyncio.sleep(0.2)
            await tab.js("window.__click('button','Verify and continue')")
            assert await tab.wait("window.__has('Operator accounts')", 20, "operator session")
            await tab.js("window.__click('button','Curation queue')")
            assert await tab.wait("window.__has('Shared raw!')", 20, "owned queue")
            checks.check("browser operator sees real owned queue", not await tab.js("window.__has('closest match:')"))
            await tab.js("""
window.__curationWrites=[];
const trackedFetch=window.fetch;
window.fetch=async (url,init)=>{
 const write=url.startsWith('/curation/skills/resolve') && init?.method==='POST';
 if(write) window.__curationWrites.push(JSON.parse(init.body));
 return trackedFetch(url,init);
};
""")

            async def click(text):
                assert await tab.js("window.__click('button', " + json.dumps(text) + ")"), text
                await asyncio.sleep(0.15)

            async def fields(alias, canonical="python", category="language"):
                for label, value in (("Approved alias", alias), ("Canonical ID", canonical), ("Category", category)):
                    assert await tab.js("window.__type(" + json.dumps(f'input[aria-label="{label}"]')
                                        + ", " + json.dumps(value) + ")")
                await asyncio.sleep(0.15)

            async def queue(name):
                assert admin.post(f"/candidates/{cid}/sources/linkedin", json=export([name])).status_code == 200
                await click("Refresh queue")
                assert await tab.wait("window.__has(" + json.dumps(name) + ")", 15, name)

            await click("Review")
            checks.check("review starts with empty approved alias", await tab.js(
                "document.querySelector('input[aria-label=\"Approved alias\"]').value === ''"))
            await click("Approve vocabulary")
            checks.check("browser validation failure leaves review available", await tab.wait(
                "document.querySelector('[role=alert]') && document.querySelector('input[aria-label=\"Approved alias\"]')", 15))
            await fields("Approved browser")
            await click("Approve vocabulary")
            assert await tab.wait("window.__has('Vocabulary approved.') && window.__has('No terms awaiting review.')", 15)
            with sqlite3.connect(dbpath) as db:
                row = db.execute("SELECT alias,admin_user_id FROM curation_aliases WHERE norm_key='approved browser'").fetchone()
                operator = admin.get("/admin/users").json()[0]["id"]
            checks.check("browser promotion persists explicit alias and authenticated operator", row == ("Approved browser", operator))
            checks.check("actual browser decision sent queue revision", await tab.js(
                "window.__curationWrites.length===1 && /^[0-9a-f]{64}$/.test(window.__curationWrites[0].expected_revision)"))
            await tab.send("Page.reload")
            assert await tab.wait("document.body.innerText.includes('Operator accounts')", 30, "reload session")
            await tab.js(HELPERS)
            await click("Curation queue")
            checks.check("browser reload shows server queue state", await tab.wait("window.__has('No terms awaiting review.')", 15))

            await queue("Create browser raw")
            await click("Review")
            await fields("Approved browser skill", "browser_skill", "data")
            await tab.js("(() => { const s=document.querySelector('select[aria-label=\"Curation action\"]'); s.value='create'; s.dispatchEvent(new Event('change',{bubbles:true})); })()")
            await asyncio.sleep(0.15)
            await tab.send("Network.emulateNetworkConditions", {"offline": True,
                "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1})
            await click("Approve vocabulary")
            checks.check("browser network failure preserves the approval draft", await tab.wait(
                "document.querySelector('[role=alert]') && document.querySelector('input[aria-label=\"Approved alias\"]').value === 'Approved browser skill'", 15))
            await tab.send("Network.emulateNetworkConditions", {"offline": False,
                "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1})
            checks.check("uncertain network write disables automatic retry", await tab.js(
                "document.querySelector('input[aria-label=\"Approved alias\"]').disabled && window.__has('decision may have completed')"))
            await click("Refresh queue")
            assert await tab.wait("document.querySelector('input[aria-label=\"Approved alias\"]') && !document.querySelector('input[aria-label=\"Approved alias\"]').disabled", 15)
            await click("Approve vocabulary")
            assert await tab.wait("window.__has('Vocabulary approved.') && window.__has('No terms awaiting review.')", 15)
            signal = admin.post(f"/candidates/{cid}/sources/linkedin", json=export(["Approved browser skill"])).json()
            checks.check("browser create feeds subsequent normalization", signal["skills"][0]["canonical"] == "browser_skill")

            await queue("Conflict browser raw")
            await click("Review")
            await fields("Approved browser")
            await click("Approve vocabulary")
            checks.check("browser alias conflict retains raw queue and review draft", await tab.wait(
                "window.__has('approved alias already exists') && window.__has('Conflict browser raw')"
                " && document.querySelector('input[aria-label=\"Approved alias\"]').value === 'Approved browser'", 15))
            await fields("Approved conflict")
            await click("Approve vocabulary")
            assert await tab.wait("window.__has('Vocabulary approved.') && window.__has('No terms awaiting review.')", 15)

            await queue("Ignore browser raw")
            await click("Ignore")
            assert await tab.wait("window.__has('Term ignored.') && window.__has('No terms awaiting review.')", 15)
            await queue("Ignore browser raw")
            checks.check("browser ignored raw reappears on fresh ingest", await tab.js("window.__has('Ignore browser raw')"))
            await click("Ignore")
            assert await tab.wait("window.__has('No terms awaiting review.')", 15)

            # A second real operator resolves the old incarnation, then fresh
            # capture reuses its text key while Chrome retains the old editor.
            await queue("Stale browser raw")
            await click("Review"); await fields("Stale browser approval")
            email = "second-reviewer@example.com"
            assert admin.post("/admin/users", json={"email": email}).status_code == 200
            with client(base) as other:
                assert other.post("/auth/admin/login", json={"email": email}).status_code == 202
                messages = [json.loads(line) for line in (scratch / "mail.jsonl").read_text(encoding="utf-8").splitlines()]
                message = next(m for m in reversed(messages) if m["to"] == email)
                otp = re.search(r"\b(\d{6})\b", message["body"])[1]
                login = other.post("/auth/admin/verify", json={"email": email, "code": otp})
                assert login.status_code == 200
                other.headers["X-CSRF-Token"] = login.json()["csrf_token"]
                old, = other.get("/curation/skills/unmapped").json()["terms"]
                assert other.post("/curation/skills/resolve", json={"norm_key": old["norm_key"],
                    "action": "ignore", "expected_revision": old["review_revision"]}).status_code == 200
                assert admin.post(f"/candidates/{cid}/sources/linkedin", json=export(["Stale browser raw"])).status_code == 200
            await click("Approve vocabulary")
            checks.check("actual stale reviewer conflict clears editor without consuming replacement", await tab.wait(
                "window.__has('review changed') && window.__has('Stale browser raw') && !document.querySelector('input[aria-label=\"Approved alias\"]')", 15))
            with sqlite3.connect(dbpath) as db:
                checks.check("stale approval persisted no vocabulary and retained fresh raw", db.execute(
                    "SELECT count(*) FROM curation_aliases WHERE norm_key='stale browser approval'").fetchone()[0] == 0
                    and db.execute("SELECT count(*) FROM curation_observations WHERE norm_key='stale browser raw'").fetchone()[0] == 1)
            await click("Review"); await fields("Approved fresh browser"); await click("Approve vocabulary")
            assert await tab.wait("window.__has('No terms awaiting review.')", 15)

            # Synthetic transport faults execute the actual handler/client.
            await queue("Fault browser raw"); await click("Review"); await fields("Approved fault browser")
            await tab.js("window.__nativeFetch=window.fetch; window.__fault=null; const p=window.VeritasAPI.post; window.VeritasAPI.post=(url,b,o)=>p(url,b,window.__fault==='timeout'?{...o,timeoutMs:100}:o); window.fetch=async(url,init)=>{ if(url.startsWith('/curation/skills/resolve') && window.__fault){ const f=window.__fault; window.__fault=null; if(f==='timeout') return new Promise((_r,reject)=>init.signal.addEventListener('abort',()=>reject(new Error('synthetic stall')))); return new Response(JSON.stringify({detail:'Synthetic service refusal'}),{status:503,headers:{'content-type':'application/json'}}); } return window.__nativeFetch(url,init); };")
            await tab.js("const retryFetch=window.fetch; window.__failNextRead=false; window.fetch=async(u,i)=>{if(u.startsWith('/curation/skills/unmapped') && window.__failNextRead){window.__failNextRead=false;return new Response(JSON.stringify({detail:'Synthetic failed recovery read'}),{status:403,headers:{'content-type':'application/json'}});}return retryFetch(u,i);};")
            for fault in ("timeout", "503"):
                await tab.js("window.__fault=" + json.dumps(fault))
                await click("Approve vocabulary")
                checks.check("browser " + fault + " settles read-only draft until refresh", await tab.wait(
                    "window.__has('decision may have completed') && document.querySelector('input[aria-label=\"Approved alias\"]').disabled", 15))
                if fault == "timeout":
                    await tab.js("window.__failNextRead=true")
                    await click("Refresh queue")
                    checks.check("failed recovery read preserves read-only approval draft", await tab.wait(
                        "window.__has('not permitted') && document.querySelector('input[aria-label=\"Approved alias\"]').value==='Approved fault browser' && document.querySelector('input[aria-label=\"Approved alias\"]').disabled", 15))
                await click("Refresh queue")
                assert await tab.wait("!document.querySelector('input[aria-label=\"Approved alias\"]').disabled", 15)
            await click("Approve vocabulary"); assert await tab.wait("window.__has('No terms awaiting review.')", 15)

            # Hold one real mutation before dispatch, leave/re-enter the view,
            # then let the real server save it while a new draft is visible.
            await queue("Late browser raw"); await click("Review"); await fields("Approved late browser")
            await tab.js("const f=window.fetch; window.__holdNext=true; window.fetch=async(u,i)=>{if(u.startsWith('/curation/skills/resolve') && window.__holdNext){window.__holdNext=false; await new Promise(r=>window.__releaseLate=r);} const response=await f(u,i); if(u.startsWith('/curation/skills/resolve')) window.__lateStatus=response.status; return response;};")
            await click("Approve vocabulary"); assert await tab.wait("!!window.__releaseLate", 10)
            await click("Signed-in devices")
            checks.check("navigation removes raw curation editor", not await tab.js("document.querySelector('input[aria-label=\"Approved alias\"]')"))
            await click("Curation queue"); assert await tab.wait("document.querySelector('[data-curation-key=\"late browser raw\"]')", 15)
            await click("Review"); await fields("New view draft")
            await tab.js("window.__releaseLate()")
            assert await tab.wait("window.__lateStatus===200", 15)
            checks.check("late old-view success preserves current editor without success notice", await tab.js(
                "document.querySelector('input[aria-label=\"Approved alias\"]').value==='New view draft' && !window.__has('Vocabulary approved.')"))
            await click("Refresh queue"); assert await tab.wait("window.__has('No terms awaiting review.') && !document.querySelector('input[aria-label=\"Approved alias\"]')", 15)

            names = ["Paging raw " + str(i) for i in range(25)]
            assert admin.post(f"/candidates/{cid}/sources/linkedin", json=export(names)).status_code == 200
            await click("Refresh queue")
            checks.check("browser first page shows actual 20 loaded terms", await tab.wait("document.querySelectorAll('[data-curation-key]').length===20 && window.__has('Loaded 20 terms')", 15))
            await click("Load more terms")
            checks.check("browser next page shows actual 25 without duplicate rows", await tab.wait("document.querySelectorAll('[data-curation-key]').length===25 && window.__has('Loaded 25 terms')", 15))
            for item in admin.get("/curation/skills/unmapped").json()["terms"]:
                assert admin.post("/curation/skills/resolve", json={"norm_key": item["norm_key"],
                    "action": "ignore", "expected_revision": item["review_revision"]}).status_code == 200
            await click("Refresh queue"); assert await tab.wait("window.__has('No terms awaiting review.')", 15)

            await queue("Read fault browser raw")
            await tab.js("const readFetch=window.fetch; window.__readFault=null; window.fetch=async(u,i)=>{if(u.startsWith('/curation/skills/unmapped') && window.__readFault){const f=window.__readFault; window.__readFault=null; return new Response(JSON.stringify(f==='invalid'?{}:{detail:'Synthetic denied read'}),{status:f==='invalid'?200:403,headers:{'content-type':'application/json'}});} return readFetch(u,i);};")
            for fault in ("403", "invalid"):
                await tab.js("window.__readFault=" + json.dumps(fault))
                await click("Refresh queue")
                checks.check("browser refused/invalid read hides cached rows: " + fault, await tab.wait(
                    "document.querySelector('[role=alert]') && document.querySelectorAll('[data-curation-key]').length===0 && !window.__has('No terms awaiting review.') && !window.__has('Loading review queue')", 15))
                await click("Refresh queue")
                assert await tab.wait("document.querySelector('[data-curation-key=\"read fault browser raw\"]')", 15)
            await click("Ignore"); assert await tab.wait("window.__has('No terms awaiting review.')", 15)

            await queue("Expire browser raw")
            await click("Review")
            await fields("Expired approval")
            with sqlite3.connect(dbpath) as db:
                db.execute("UPDATE curation_observations SET created_at=? WHERE norm_key='expire browser raw'",
                    ((datetime.now(timezone.utc) - timedelta(days=31)).isoformat(),))
            await click("Approve vocabulary")
            checks.check("browser stale expiry refuses approval and clears raw editor", await tab.wait(
                "window.__has('Term is no longer available') && window.__has('No terms awaiting review.')"
                " && !document.querySelector('input[aria-label=\"Approved alias\"]')", 15))

            await queue("Erase browser raw")
            await click("Review")
            await fields("Erased approval")
            assert admin.delete(f"/candidates/{cid}").status_code == 200
            await click("Approve vocabulary")
            checks.check("browser stale erasure refuses approval and clears raw editor", await tab.wait(
                "window.__has('Term is no longer available') && window.__has('No terms awaiting review.')"
                " && !document.querySelector('input[aria-label=\"Approved alias\"]')", 15))
            assert admin.delete(f"/admin/users/{operator}").status_code == 200
            await click("Refresh queue")
            checks.check("browser revoked reviewer returns to sign-in", await tab.wait(
                "window.__has('Your session ended.') && document.querySelector('input[type=email]')", 15))
            checks.check("revocation removed raw curation editor and rows", not await tab.js(
                "document.querySelector('[data-curation-key]') || document.querySelector('input[aria-label=\"Approved alias\"]')"))
            # Authenticate different browser planes through real captured API
            # requests, reload the actual UI, and try both shared queue routes.
            for plane in ("org", "candidate"):
                email = "curation-" + plane + "@example.com"
                started = await tab.js("fetch('/auth/" + plane + "/signup',{method:'POST',credentials:'include',headers:{'content-type':'application/json'},body:JSON.stringify("
                    + json.dumps({"email": email, **({"organization_name": "Curation browser tenant"} if plane == "org" else {})})
                    + ")}).then(r=>r.status)")
                assert started == 202
                messages = [json.loads(line) for line in (scratch / "mail.jsonl").read_text(encoding="utf-8").splitlines()]
                message = next(m for m in reversed(messages) if m["to"] == email)
                otp = re.search(r"\b(\d{6})\b", message["body"])[1]
                logged_in = await tab.js("fetch('/auth/" + plane + "/verify',{method:'POST',credentials:'include',headers:{'content-type':'application/json'},body:JSON.stringify("
                    + json.dumps({"email": email, "code": otp}) + ")}).then(r=>r.status)")
                assert logged_in == 200
                await tab.send("Page.reload")
                assert await tab.wait("performance.getEntriesByType('resource').some(e=>new URL(e.name).pathname==='/auth/me')", 40)
                await tab.js(HELPERS)
                statuses = await tab.js("Promise.all([fetch('/curation/skills/unmapped',{credentials:'include'}).then(r=>r.status),window.VeritasAPI.post('/curation/skills/resolve',{norm_key:'synthetic raw',action:'ignore',expected_revision:'0'.repeat(64)}).then(()=>200,e=>e.status)])")
                checks.check(plane + " browser plane cannot read/resolve curation or see cached editor", statuses == [401, 401]
                    and not await tab.js("document.querySelector('[data-curation-key]') || document.querySelector('input[aria-label=\"Approved alias\"]')"))
                await tab.js("window.VeritasAPI.post('/auth/logout',{}).catch(()=>null)")
            with sqlite3.connect(dbpath) as db:
                checks.check("browser refused decisions create no aliases or raw leftovers", db.execute(
                    "SELECT count(*) FROM curation_observations").fetchone()[0] == 0 and db.execute(
                    "SELECT count(*) FROM curation_aliases WHERE norm_key IN ('expired approval','erased approval')").fetchone()[0] == 0)
            await tab.js("true")  # drain queued runtime events
            checks.check("browser has no console errors or uncaught exceptions", not tab.console,
                         " | ".join(tab.console)[:300])
    finally:
        chrome.terminate()
        try:
            chrome.wait(timeout=15)
        except subprocess.TimeoutExpired:
            chrome.kill()
            chrome.wait(timeout=10)


if __name__ == "__main__":
    from smoke_curation_activation import main
    raise SystemExit(main(browser=True))
