"""Combined Chrome org/account/guarded-curation journey for R3-S2-Q.

Called by smoke_r3_s2_q.py --browser on its migrated scratch app. Uses captured
sign-in and fake providers; Chrome/CDN internet is required. Never uses working
data. HTTP restart and denials are real, with no synthetic transport in this run.
"""
import asyncio
import base64
import json
import os
import subprocess
import tempfile
import urllib.request

import websockets

from _smoke import client
from check_ui_screening_browser import Tab, HELPERS, _chrome, _code_for
from smoke_curation_activation import free_port
from smoke_curation_input import export


async def run_browser(base, scratch, admin, checks, restart_app):
    port = free_port()
    profile = tempfile.mkdtemp(prefix="r3-s2-q-chrome-")
    chrome = subprocess.Popen([_chrome(), "--headless=new", f"--remote-debugging-port={port}",
        "--no-first-run", "--no-default-browser-check", f"--user-data-dir={profile}",
        "--disable-gpu", "--window-size=1440,1000", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    codes, keys = [], []
    email_a, email_b = "combined-browser-a@example.com", "combined-browser-b@example.com"

    def require(response, status=200):
        assert response.status_code == status, (response.request.url.path, response.status_code)
        return response.json()

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
        with client(base) as actor_b:
            account_a = require(admin.post("/admin/users", json={"email": email_a, "label": "Combined Browser A"}))
            cid = require(admin.post("/candidates", json={"evaluate": False,
                "resume_text": "Combined Browser Candidate\nEmail: combined-candidate@example.com\nSkills: Python SQL"}))["candidate_id"]
            async with websockets.connect(target, max_size=40_000_000) as ws:
                tab = Tab(ws)
                for domain in ("Runtime", "Page", "Network"):
                    await tab.send(domain + ".enable")
                await tab.send("Page.navigate", {"url": base + "/ui/"})
                assert await tab.wait("performance.getEntriesByType('resource').some(e=>new URL(e.name).pathname==='/auth/me') && document.querySelector('input[type=email]')", 60)
                await tab.js(HELPERS)

                async def click(label):
                    assert await tab.js("window.__click('button'," + json.dumps(label) + ")"), label
                    await asyncio.sleep(0.15)

                async def type_field(selector, value):
                    assert await tab.js("window.__type(" + json.dumps(selector) + "," + json.dumps(value) + ")"), selector
                    await asyncio.sleep(0.15)

                async def screen(label, selector):
                    await click(label)
                    assert await tab.wait(selector, 20), label

                async def capture(raw):
                    require(admin.post(f"/candidates/{cid}/sources/linkedin", json=export([raw])))
                    await click("Refresh queue")
                    assert await tab.wait("window.__has(" + json.dumps(raw) + ")", 20), raw

                async def vocabulary(alias, canonical="python", category="language"):
                    for label, value in (("Approved alias", alias), ("Canonical ID", canonical), ("Category", category)):
                        await type_field(f'input[aria-label="{label}"]', value)

                await click("Operator")
                assert await tab.wait("window.__has('Operator sign in')", 15)
                await type_field("input[type=email]", email_a)
                await click("Send code")
                assert await tab.wait("document.querySelectorAll('input[inputmode]').length === 6", 20)
                code = _code_for(scratch / "mail.jsonl", email_a); codes.append(code)
                await type_field("input[inputmode]", code)
                await click("Verify and continue")
                assert await tab.wait("document.querySelector('#org-name') && !window.__has('Loading organisations')", 20)
                checks.check("combined browser starts from actual existing org rows", await tab.js("document.querySelectorAll('[data-org-record]').length") == 2)

                name = "Combined Browser Agency"
                await type_field("#org-name", name)
                await click("Create organisation")
                assert await tab.wait("document.querySelector('#org-key') && window.__has('Organisation created.')", 20)
                org = next(o for o in require(admin.get("/ledger/orgs")) if o["name"] == name)
                oid = org["id"]
                first = await tab.js("document.querySelector('#org-key').value"); keys.append(first)
                checks.check("combined create displays concealed one-time key from actual response", bool(first)
                    and await tab.js("document.querySelector('#org-key').type") == "password")
                await type_field("#org-weight", "2.5")
                await click("Save reliability")
                assert await tab.wait("window.__has('Saved reliability 2.5')", 15)
                await click("Rotate organisation key")
                await click("Confirm key rotation")
                assert await tab.wait("document.querySelector('#org-key') && window.__has('Organisation key rotated')", 15)
                rotated = await tab.js("document.querySelector('#org-key').value"); keys.append(rotated)
                with client(base) as stranger:
                    checks.check("combined browser rotation revokes old key", stranger.get("/screening/batches", headers={"X-Org-Key": first}).status_code == 401
                        and stranger.get("/screening/batches", headers={"X-Org-Key": rotated}).status_code == 200)

                await screen("Operator accounts", "document.querySelector('#operator-email') && !window.__has('Loading operator accounts')")
                checks.check("org to account navigation clears one-time key", not await tab.js("document.querySelector('#org-key')"))
                await type_field("#operator-email", email_b)
                await type_field("#operator-label", "Combined Browser B")
                await click("Create operator")
                assert await tab.wait("window.__has('Operator account created.')", 20)
                account_b = next(u for u in require(admin.get("/admin/users")) if u["label"] == "Combined Browser B")
                require(actor_b.post("/auth/admin/login", json={"email": email_b}), 202)
                code = _code_for(scratch / "mail.jsonl", email_b); codes.append(code)
                verified = require(actor_b.post("/auth/admin/verify", json={"email": email_b, "code": code}))
                actor_b.headers["X-CSRF-Token"] = verified["csrf_token"]
                checks.check("browser-created account really signs in and reads all operator screens",
                    all(actor_b.get(p).status_code == 200 for p in ("/ledger/orgs", "/admin/users", "/curation/skills/unmapped")))

                await screen("Curation queue", "window.__has('No terms awaiting review.')")
                await capture("Combined map raw")
                await click("Review"); await vocabulary("Combined approved alias")
                await click("Approve vocabulary")
                checks.check("combined browser maps explicit vocabulary and reloads empty queue", await tab.wait("window.__has('Vocabulary approved.') && window.__has('No terms awaiting review.')", 20))
                await capture("Combined create raw")
                await click("Review"); await vocabulary("Combined approved tool", "combined_tool", "data")
                await tab.js("(()=>{const s=document.querySelector('select[aria-label=\"Curation action\"]'); s.value='create'; s.dispatchEvent(new Event('change',{bubbles:true}));})()")
                await click("Approve vocabulary")
                assert await tab.wait("window.__has('Vocabulary approved.') && window.__has('No terms awaiting review.')", 20)
                await capture("Combined ignored raw")
                old, = require(actor_b.get("/curation/skills/unmapped"))["terms"]
                await click("Ignore")
                assert await tab.wait("window.__has('Term ignored.') && window.__has('No terms awaiting review.')", 20)
                await capture("Combined ignored raw")
                stale = actor_b.post("/curation/skills/resolve", json={"norm_key": old["norm_key"],
                    "expected_revision": old["review_revision"], "action": "map", "alias": "Combined stale alias",
                    "canonical": "python", "category": "language"})
                checks.check("second browser-created reviewer cannot consume reappeared raw", stale.status_code == 409
                    and require(actor_b.get("/curation/skills/unmapped"))["terms"][0]["review_revision"] != old["review_revision"])
                await click("Review"); await vocabulary("Unsaved private vocabulary")
                await screen("Operator accounts", "document.querySelector('#operator-email')")
                await type_field("#operator-email", "unsaved-private@example.com")
                await screen("Curation queue", "window.__has('Combined ignored raw')")
                checks.check("account/curation navigation clears raw editor and unsaved account input",
                    not await tab.js("document.querySelector('input[aria-label=\"Approved alias\"]')"))
                await click("Ignore")
                assert await tab.wait("window.__has('No terms awaiting review.')", 20)

                restart_app()
                origin = await tab.js("performance.timeOrigin")
                await tab.send("Page.reload")
                assert await tab.wait(f"performance.timeOrigin !== {origin} && document.readyState==='complete' && document.querySelector('#org-name')", 60)
                await tab.js(HELPERS)
                assert await tab.wait(f"document.querySelector('[data-org-record=\"{oid}\"] button')", 15)
                await tab.js(f"document.querySelector('[data-org-record=\"{oid}\"] button').click()")
                checks.check("combined browser reload after backend restart preserves org settings without key",
                    await tab.wait("window.__has('Saved reliability 2.5')", 15) and not await tab.js("document.querySelector('#org-key')"))
                await screen("Operator accounts", "document.querySelector('#operator-email') && !window.__has('Loading operator accounts')")
                checks.check("restart preserves browser-created operator and clears unsaved input", await tab.js(
                    f"!!document.querySelector('[data-operator-record=\"{account_b['id']}\"]') && document.querySelector('#operator-email').value===''"))
                await screen("Curation queue", "window.__has('No terms awaiting review.')")
                signal = require(admin.post(f"/candidates/{cid}/sources/linkedin",
                    json=export(["Combined approved alias", "Combined approved tool", "Python"])))
                checks.check("combined restart reloads approved overlay with static precedence", [s["canonical"] for s in signal["skills"]] == ["python", "combined_tool", "python"])
                shot = await tab.send("Page.captureScreenshot")
                (scratch / "combined-curation.png").write_bytes(base64.b64decode(shot["data"]))

                await screen("Operator accounts", "document.querySelector('#operator-email') && !window.__has('Loading operator accounts')")
                await tab.js(f"document.querySelector('[data-operator-record=\"{account_b['id']}\"] button').click()")
                assert await tab.wait("window.__has('Confirm operator deletion')", 10)
                await click("Confirm operator deletion")
                checks.check("browser account deletion revokes all three operator surfaces", await tab.wait("window.__has('Operator account deleted.')", 15)
                    and all(actor_b.get(p).status_code == 401 for p in ("/ledger/orgs", "/admin/users", "/curation/skills/unmapped")))
                await screen("Organisations", "document.querySelector('#org-name') && !window.__has('Loading organisations')")
                await tab.js(f"document.querySelector('[data-org-record=\"{oid}\"] button').click()")
                assert await tab.wait("document.querySelector('#org-weight')", 10)
                await click("Offboard organisation"); await click("Confirm offboarding")
                with client(base) as stranger:
                    checks.check("combined browser offboarding revokes target key and preserves other orgs", await tab.wait("window.__has('Organisation offboarded.')", 15)
                        and stranger.get("/screening/batches", headers={"X-Org-Key": rotated}).status_code == 401
                        and len(require(admin.get("/ledger/orgs"))) == 2)
                await screen("Curation queue", "window.__has('No terms awaiting review.')")
                await capture("Combined revoked raw")
                await click("Review"); await vocabulary("Combined revoked draft")
                require(admin.delete(f"/admin/users/{account_a['id']}"))
                await click("Refresh queue")
                checks.check("combined revocation clears raw queue/draft and returns to sign-in", await tab.wait("window.__has('Your session ended') && document.querySelector('input[type=email]')", 15)
                    and not await tab.js("document.querySelector('[data-curation-key]') || document.querySelector('#operator-email') || document.querySelector('#org-key') || document.querySelector('input[aria-label=\"Approved alias\"]')"))
                require(admin.delete(f"/candidates/{cid}"))

                for plane in ("org", "candidate"):
                    email = f"combined-denied-{plane}@example.com"
                    body = {"email": email, **({"organization_name": "Combined denied browser org"} if plane == "org" else {})}
                    status = await tab.js("fetch('/auth/" + plane + "/signup',{method:'POST',credentials:'include',headers:{'content-type':'application/json'},body:JSON.stringify(" + json.dumps(body) + ")}).then(r=>r.status)")
                    assert status == 202
                    code = _code_for(scratch / "mail.jsonl", email); codes.append(code)
                    assert await tab.js("fetch('/auth/" + plane + "/verify',{method:'POST',credentials:'include',headers:{'content-type':'application/json'},body:JSON.stringify(" + json.dumps({"email": email, "code": code}) + ")}).then(r=>r.status)") == 200
                    origin = await tab.js("performance.timeOrigin")
                    await tab.send("Page.reload")
                    assert await tab.wait(f"performance.timeOrigin !== {origin} && performance.getEntriesByType('resource').some(e=>new URL(e.name).pathname==='/auth/me')", 60)
                    await tab.js(HELPERS)
                    assert await tab.wait("window.__has('Screening queue')" if plane == "org" else "window.__has('Everything Veritas holds about you')", 20)
                    statuses = await tab.js("Promise.all(['/ledger/orgs','/admin/users','/curation/skills/unmapped'].map(p=>fetch(p,{credentials:'include'}).then(r=>r.status)))")
                    checks.check(plane + " browser cannot read any operator surface or render privileged cached state", statuses == [401, 401, 401]
                        and not await tab.js("document.querySelector('[data-org-record]') || document.querySelector('[data-operator-record]') || document.querySelector('[data-curation-key]') || document.querySelector('input[aria-label=\"Approved alias\"]')"))
                    await tab.js("window.VeritasAPI.post('/auth/logout',{}).catch(()=>null)")
                denied_org = next(o for o in require(admin.get("/ledger/orgs")) if o["name"] == "Combined denied browser org")
                require(admin.delete(f"/ledger/orgs/{denied_org['id']}"))
                await tab.js("true")
                checks.check("combined browser has no console exceptions", not tab.console, " | ".join(tab.console[:2]))
                logged = (scratch / "server.log").read_text(encoding="utf-8")
                checks.check("combined HTTP logs omit one-time credentials and operator emails", all(value not in logged for value in [*codes, *keys, email_a, email_b]))
    finally:
        chrome.terminate()
        try: chrome.wait(timeout=15)
        except subprocess.TimeoutExpired: chrome.kill(); chrome.wait(timeout=10)
