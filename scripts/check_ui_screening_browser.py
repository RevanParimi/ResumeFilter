"""The screening screens, clicked through in a REAL browser over CDP.

`scripts/check_ui_screening_contract.py` proves the API answers what the UI
assumes. This proves the UI actually renders it: React mounts, the bindings
resolve to visible text, the handlers fire, the file picker reaches the
FileReader path, and the client-side process driver runs a batch to completion.

Nothing else in this repo can catch that class of defect. `frontend/` has no
CI, no bundler and no test runner (PI-8 decision 0.1), and the 2026-08-03
session recorded the reason plainly: a DOM dump of one screen never revealed
the comp wrapper — clicking through did.

Two things it watches that no assertion of mine spells out:
  * EVERY console error and uncaught exception, for the whole run. A throw
    inside a React handler is otherwise completely silent.
  * that no candidate NAME appears anywhere in the queue's DOM. The screen
    tells the user in prose that rows hold no names; that has to be true of
    what is rendered, not only of what was fetched.

S8.6: THE PAGE IS NOW LOADED FROM THE API ITSELF, at `/ui/Veritas.dc.html`
with no `?api=`. That is the posture the UI ships in, and this is the only
check anywhere that exercises it — `frontend/api.js` is outside pytest and
outside CI, so its same-origin default is proven here or nowhere.

This replaces a second `http.server` on localhost:5174 whose docstring claimed
*that* was "the posture the UI ships in". It never was, in either direction:
both hosts were localhost, and SameSite ignores the PORT, so the arrangement
was cross-ORIGIN but same-SITE — a Lax cookie was sent, CORS applied, and
`config.yaml`'s shipped `SameSite=None` was exercised by nothing, anywhere.
S8.6 retired that gap from both ends: the UI is same-origin and the shipped
default is now `lax`.

The old localhost-vs-127.0.0.1 trap that cost the 2026-08-02 session an
afternoon is gone with the second server — one origin cannot be cross-site
with itself — but the hostname still matters for a different reason: uvicorn
binds `localhost`, so the page must be fetched as `localhost` too, or it is a
different origin and every call is cross-site again.

Requires Chrome and internet (the dc runtime pulls React from unpkg).

Run from repo root:   python scripts/check_ui_screening_browser.py
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parent.parent
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]
API_PORT = 8096
CDP_PORT = 9422
#: The UI is served BY the API now (S8.6), so there is one origin and no
#: separate UI port.
API_BASE = f"http://localhost:{API_PORT}"
UI_URL = f"{API_BASE}/ui/Veritas.dc.html"
ADMIN = "ui-browser-admin-key"

FIXTURES = ROOT / "tests" / "fixtures"
GENUINE = (FIXTURES / "genuine_genai_resume.txt").read_text(encoding="utf-8")

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))
    print(f"{'OK  ' if ok else 'FAIL'} {name}{(' -- ' + detail) if detail else ''}", flush=True)


def _resume(name: str, email: str) -> str:
    return "\n".join([name, f"Email: {email}"] + GENUINE.splitlines()[1:])


def minimal_pdf(lines: list[str]) -> bytes:
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", r"\(").replace(")", r"\)")

    content = (
        "BT /F1 11 Tf 40 780 Td 14 TL\n"
        + "\n".join(f"({esc(l)}) Tj T*" for l in lines) + "\nET"
    ).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(out))
        out += str(i).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n0000000000 65535 f \n"
    for off in offsets:
        out += ("%010d 00000 n \n" % off).encode()
    out += (b"trailer\n<< /Size " + str(len(objs) + 1).encode() + b" /Root 1 0 R >>\n"
            b"startxref\n" + str(xref).encode() + b"\n%%EOF\n")
    return bytes(out)


def _code_for(mailbox: Path, email: str) -> str:
    if not mailbox.exists():
        raise AssertionError(
            "no email was captured at all — the signup POST never left the "
            "browser, so the form was not filled the way this script assumes")
    for raw in reversed(mailbox.read_text(encoding="utf-8").splitlines()):
        msg = json.loads(raw)
        if msg["to"].strip().lower() == email.strip().lower():
            return re.search(r"\b(\d{6})\b", msg["body"]).group(1)
    raise AssertionError(f"no code was sent to {email}")


class Tab:
    """Just enough CDP: evaluate, wait-for, click-by-text, set a file input."""

    def __init__(self, ws) -> None:
        self.ws = ws
        self._id = 0
        self.console: list[str] = []

    async def send(self, method, params=None):
        self._id += 1
        mine = self._id
        await self.ws.send(json.dumps({"id": mine, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(await self.ws.recv())
            self._note(msg)
            if msg.get("id") == mine:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def _note(self, msg):
        m = msg.get("method")
        if m == "Runtime.consoleAPICalled" and msg["params"]["type"] in ("error", "assert"):
            self.console.append("console." + msg["params"]["type"] + ": " + json.dumps(
                [a.get("value", a.get("description", "?")) for a in msg["params"]["args"]])[:300])
        elif m == "Runtime.exceptionThrown":
            d = msg["params"]["exceptionDetails"]
            self.console.append("uncaught: " + (d.get("exception", {}).get("description")
                                                or d.get("text", "?"))[:300])

    async def js(self, expr, by_value=True):
        r = await self.send("Runtime.evaluate", {
            "expression": expr, "returnByValue": by_value, "awaitPromise": True,
            "userGesture": True,
        })
        res = r.get("result", {})
        if r.get("exceptionDetails"):
            raise RuntimeError("JS threw: " + json.dumps(r["exceptionDetails"])[:400])
        return res.get("value") if by_value else res.get("objectId")

    async def wait(self, expr, timeout=45, label=""):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if await self.js("!!(" + expr + ")"):
                    return True
            except RuntimeError:
                pass
            await asyncio.sleep(0.35)
        print(f"     (timed out waiting for {label or expr})", flush=True)
        return False

    async def text(self):
        return await self.js("document.body.innerText")


# JS helpers injected once; every click goes through them so a failed click is
# a returned false rather than a silent no-op.
# A queue row is the only [role=button] carrying the loudest-signal label.
ROW_SELECTOR = ("[...document.querySelectorAll('[role=button]')]"
                ".filter(e => (e.textContent||'').includes('Loudest signal'))")

HELPERS = """
window.__q = (sel, txt) => [...document.querySelectorAll(sel)]
  .find(e => (e.innerText || e.textContent || '').trim().toLowerCase().includes(txt.toLowerCase()));
window.__click = (sel, txt) => { const e = window.__q(sel, txt); if (!e) return false; e.click(); return true; };
window.__type = (sel, value, nth) => {
  const els = [...document.querySelectorAll(sel)];
  const el = els[nth || 0];
  if (!el) return false;
  const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  set.call(el, value);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
};
window.__has = (txt) => document.body.innerText.toLowerCase().includes(txt.toLowerCase());
"""


async def run(tab: Tab, mailbox: Path, files: list[str], admin: httpx.Client) -> None:
    await tab.js(HELPERS)

    # ── 1. It boots, and boots to the login screen ──────────────────────────
    ok = await tab.wait("window.__has('Sign in') || window.__has('Send code')", 60, "login screen")
    check("the_app_mounts_and_shows_login", ok, (await tab.text())[:70].replace("\n", " | "))
    if not ok:
        return

    # ── 2. Org self-signup, entirely through the UI ─────────────────────────
    email = "delivery@sampoorna.example"
    await tab.js("window.__click('button', 'Create account')")
    # The organisation-name field only exists in signup mode on the org plane,
    # so waiting for it also proves the mode switch took.
    await tab.wait("document.querySelector('input[placeholder=\"Sampoorna Staffing\"]')",
                   15, "the org-name field")
    await tab.js("window.__type('input[placeholder=\"Sampoorna Staffing\"]', 'Sampoorna Staffing', 0)")
    await tab.js(f"window.__type('input[type=email]', '{email}', 0)")
    await asyncio.sleep(0.2)
    await tab.js("window.__click('button', 'Create account and send code')")
    got_otp = await tab.wait("document.querySelectorAll('input[inputmode]').length === 6",
                             30, "the six OTP boxes")

    code = _code_for(mailbox, email)
    # One box takes all six: the handler distributes anything longer than a
    # character, which is how a pasted code works.
    await tab.js(f"window.__type('input[inputmode]', '{code}', 0)")
    await asyncio.sleep(0.3)
    await tab.js("window.__click('button', 'Verify and continue')")
    landed = await tab.wait("window.__has('Screening queue')", 30, "the queue")
    check("signup_verify_and_landing_on_the_queue", got_otp and landed,
          f"otp_screen={got_otp} landed={landed}")

    # ── 3. The first screen a new customer ever sees ────────────────────────
    empty = await tab.wait("window.__has('Nothing screened yet')", 20, "the empty state")
    check("a_brand_new_org_sees_an_empty_queue_not_an_error", empty,
          "renders 'Nothing screened yet'")

    # ── 4. Upload: the real file picker, through the real FileReader ────────
    await tab.js("window.__click('button', 'Upload')")
    await tab.wait("window.__has('Drop the resumes you already have')", 20, "the upload screen")
    box = await tab.js("document.querySelector('input[type=file]')", by_value=False)
    if box:
        await tab.send("DOM.setFileInputFiles", {"files": files, "objectId": box})
    await asyncio.sleep(0.6)
    listed = await tab.js("window.__has('files ready') || window.__has('file ready')")
    check("the_file_picker_lists_what_was_chosen", bool(box) and bool(listed),
          f"input_found={bool(box)} listed={bool(listed)}")

    await tab.js("window.__type('input[placeholder*=\\\"intake\\\"]', 'Wipro DE — August intake', 0)")
    await asyncio.sleep(0.2)

    # LATCH the driver's banner before starting it, instead of polling for it.
    # "Screening from this browser" exists only WHILE work is in flight, and
    # with three fixture resumes under NullLLM that window is short -- S8.6
    # made it shorter still, because a same-origin call skips the CORS
    # preflight round trip. A 0.35s poll missed it once in two runs here, which
    # is a check that fails at random: worse than a weaker one, because the
    # next person cannot tell a flake from a regression. The MutationObserver
    # cannot miss it -- it fires on the render that shows the text.
    await tab.js("""
        window.__sawDriver = false;
        window.__driverWatch = new MutationObserver(() => {
          if (document.body.innerText.includes('Screening from this browser')) {
            window.__sawDriver = true;
          }
        });
        window.__driverWatch.observe(document.body, {
          subtree: true, childList: true, characterData: true,
        });
        true
    """)
    await tab.js("window.__click('button', 'Register batch and start screening')")

    # ── 5. The driver runs, in the browser, to completion ───────────────────
    started = await tab.wait("window.__sawDriver", 30, "the driver to start")
    finished = await tab.wait("window.__has('Nothing left to screen')", 180, "the driver to finish")
    check("the_process_driver_runs_in_the_browser_and_finishes", started and finished,
          f"started={started} finished={finished}")

    # ── 6. What the queue actually renders ──────────────────────────────────
    # innerText applies CSS text-transform, so every text assertion here is
    # case-insensitive: the queue's column labels are uppercased in CSS and a
    # case-sensitive check reads them as absent.
    body = (await tab.text()).lower()
    rows = await tab.js(ROW_SELECTOR + ".length")
    check("the_queue_renders_a_row_per_resume_with_its_reason",
          rows == len(files)
          and ("fabrication risk" in body or "insufficient signal" in body)
          and "loudest signal" in body,
          f"{rows} rows for {len(files)} files")

    leaked = [n for n in ("priya nandakumar", "arjun rao", "kavya iyer") if n in body]
    check("no_candidate_name_is_rendered_on_the_queue", not leaked, f"leaked={leaked}")

    # The header's band counts must be the WHOLE batch's, from /summary — so
    # they are read back through a SEPARATE machine credential rather than by
    # trusting what the screen says about itself.
    api = _org_client(admin)
    bid = api.get("/screening/batches").json()["batches"][0]["id"]
    bands = api.get(f"/screening/batches/{bid}/summary").json()["by_risk_band"]
    shown = {}
    for label in ("elevated", "moderate", "low", "insufficient"):
        m = re.search(r"(\d+)\s*\n?\s*" + label, body)
        shown[label] = int(m.group(1)) if m else None
    expected = {
        "elevated": bands.get("elevated", 0), "moderate": bands.get("moderate", 0),
        "low": bands.get("low", 0), "insufficient": bands.get("insufficient_data", 0),
    }
    check("the_header_counts_match_the_summary_endpoint", shown == expected,
          f"shown={shown} api={expected}")

    # ── 7. Drill in to the report ───────────────────────────────────────────
    await tab.js(ROW_SELECTOR + "[0].click()")
    opened = await tab.wait("window.__has('What drove it')", 30, "the report")
    report_body = (await tab.text()).lower()
    named = any(n in report_body for n in ("priya nandakumar", "arjun rao", "kavya iyer",
                                           "name not extracted"))
    check("the_report_opens_and_names_the_person_the_queue_would_not", opened and named,
          f"opened={opened} named={named}")
    check("the_report_shows_claim_level_reasoning", "claim by claim" in report_body
          and ("missing signals" in report_body or "nothing to reason about" in report_body))
    # ── 7b. THE LOOP CLOSES, by clicking (S8.5) ─────────────────────────────
    # The four buttons this file used to assert were ABSENT. They are back
    # because POST /screening/reports/{id}/outcome landed on the org plane,
    # and the check inverted with them: a screen that says an action exists
    # has to perform it.
    check("the_four_outcome_buttons_are_present_and_the_prose_no_longer_apologises",
          bool(await tab.js("!!window.__q('button', 'Verified genuine')"))
          and bool(await tab.js("!!window.__q('button', 'Verified fabricated')"))
          and bool(await tab.js("!!window.__q('button', 'Candidate clarified')"))
          and bool(await tab.js("!!window.__q('button', 'Inconclusive')"))
          and "operator action today" not in report_body,
          "the section acts instead of explaining itself")

    # Type into the notes field the way a person does, so the React onInput
    # handler runs: setting .value directly would never fire it, and the note
    # would post as "" while this check still went green.
    await tab.js(
        "(() => { const i = [...document.querySelectorAll('input')]"
        ".find(x => (x.placeholder || '').startsWith('What did you find out'));"
        " if (!i) return false;"
        " const set = Object.getOwnPropertyDescriptor("
        "   window.HTMLInputElement.prototype, 'value').set;"
        " set.call(i, 'Called the listed manager; no such team.');"
        " i.dispatchEvent(new Event('input', { bubbles: true })); return true; })()"
    )
    await tab.js("window.__click('button', 'Verified fabricated')")
    recorded = await tab.wait("window.__has('judgement recorded')", 25,
                              "the recorded judgement")
    # Read back through the SEPARATE machine credential, and sweep the whole
    # batch rather than guessing which report the click opened: "exactly one
    # judgement exists anywhere in this batch" is both stronger than naming a
    # report id and free of any assumption about row ordering.
    queue_rows = api.get(f"/screening/batches/{bid}/queue").json()["rows"]
    stored = [
        o
        for r in queue_rows if r.get("report_id")
        for o in api.get(
            f"/screening/reports/{r['report_id']}/outcomes"
        ).json()["outcomes"]
    ]
    check("clicking_an_outcome_records_it_and_the_history_renders",
          bool(recorded) and len(stored) == 1
          and stored[0]["outcome"] == "verified_fabricated"
          and stored[0]["notes"].startswith("Called the listed manager")
          and stored[0]["recorded_by"] == "organization",
          f"rendered={bool(recorded)} stored={[(o['outcome'], o['notes'][:24]) for o in stored]}")

    # The note must be cleared after a SUCCESS -- leaving one person's sentence
    # in the box is how it ends up filed against the next candidate.
    still_typed = await tab.js(
        "(() => { const i = [...document.querySelectorAll('input')]"
        ".find(x => (x.placeholder || '').startsWith('What did you find out'));"
        " return i ? i.value : null; })()"
    )
    check("the_notes_box_is_cleared_after_a_successful_record",
          still_typed == "", f"value={still_typed!r}")

    # Two clicks in one synchronous block must leave ONE judgement, because
    # this list is append-only and a double-record is permanent.
    #
    # STATE ITS REACH HONESTLY: this does NOT discriminate between the
    # instance-field guard the handler uses and a `state.outcomeBusy` one. That
    # was the assumption when this check was written, and it was probed and
    # found FALSE -- planting the state-based guard leaves this green, because
    # React flushes discrete events synchronously and the second click already
    # sees the first click's state. So this is a regression pin on the
    # BEHAVIOUR ("one intent, one judgement"), not evidence for the guard's
    # spelling. A check whose reach is overstated is what stops somebody adding
    # the one that would have caught the next bug.
    await tab.js(
        "(() => { const b = [...document.querySelectorAll('button')]"
        ".filter(x => /^(Inconclusive|Candidate clarified)$/.test("
        "  (x.innerText || '').trim()));"
        " b.forEach(x => x.click()); return b.length; })()"
    )
    await tab.wait("window.__has('judgements, oldest first')", 25,
                   "the second judgement")
    swept = [
        o
        for r in queue_rows if r.get("report_id")
        for o in api.get(
            f"/screening/reports/{r['report_id']}/outcomes"
        ).json()["outcomes"]
    ]
    check("two_clicks_in_one_tick_record_exactly_one_judgement",
          len(swept) == 2,
          f"{len(swept)} total after 1 deliberate + 2 same-tick clicks: "
          f"{[o['outcome'] for o in swept]}")

    # ── 8. Summary and batches ──────────────────────────────────────────────
    await tab.js("window.__click('button', 'Batch summary')")
    sum_ok = await tab.wait("window.__has('of those screened')", 25, "the summary")
    sum_body = (await tab.text()).lower()
    check("the_summary_renders_bands_and_signals_from_the_api", sum_ok
          and "loudest" in sum_body
          and not any(n in sum_body for n in ("priya", "arjun", "kavya")),
          "counts and enum members only")

    await tab.js("window.__click('button', 'Batches')")
    # Wait for a ROW, not for the heading: the heading is static markup and
    # matches before the fetch resolves, which made this check race the load.
    list_ok = await tab.wait("window.__has('Your batches')", 25, "the batches screen")
    named_batch = await tab.wait("window.__has('Wipro DE')", 25, "the batch row")
    check("the_batches_screen_lists_the_batch_that_was_just_uploaded",
          list_ok and bool(named_batch),
          f"listed={list_ok} named={bool(named_batch)} "
          f"untitled={bool(await tab.js('window.__has(\"Untitled batch\")'))} "
          f"api_name={api.get('/screening/batches').json()['batches'][0]['name']!r}")

    # ── 9. Delete: two steps, and it really deletes ─────────────────────────
    await tab.js("window.__click('button', 'Delete')")
    armed = await tab.wait("window.__has('Keep it')", 15, "the delete confirmation")
    await tab.js("window.__click('button', 'Delete batch')")
    emptied = await tab.wait("window.__has('No batches yet')", 25, "the emptied list")
    gone = api.get(f"/screening/batches/{bid}").status_code
    check("delete_is_two_step_and_removes_the_batch_server_side",
          armed and emptied and gone == 404,
          f"armed={armed} emptied={emptied} api_after={gone}")

    # ── 10. Nothing threw, the whole way through ────────────────────────────
    check("no_console_errors_or_uncaught_exceptions", not tab.console,
          "; ".join(tab.console[:3]) if tab.console else "clean")


def _chrome() -> str:
    for path in CHROME_CANDIDATES:
        if os.path.exists(path):
            return path
    raise SystemExit("no Chrome found; this check needs one")


async def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    mailbox = scratch / "mailbox.jsonl"
    url = "sqlite:///" + (scratch / "ui_browser.db").as_posix()

    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    uploads = scratch / "uploads"
    uploads.mkdir()
    (uploads / "priya_nandakumar.txt").write_text(
        _resume("Priya Nandakumar", "priya.n@example.in"), encoding="utf-8")
    (uploads / "arjun_rao.txt").write_text(
        _resume("Arjun Rao", "arjun.rao@example.in"), encoding="utf-8")
    (uploads / "kavya_iyer.pdf").write_bytes(minimal_pdf([
        "Kavya Iyer", "Email: kavya.iyer@example.in", "Senior Data Engineer, Pune",
        "Owned the Airflow migration for a 400-table warehouse ingest.",
    ]))
    files = [str(p) for p in sorted(uploads.iterdir())]

    env = os.environ.copy()
    env.update({
        "DEE_CANDIDATES_DB_URL": url,
        "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
        "DEE_VECTORSTORE_BACKEND": "memory",
        "DEE_OPENROUTER_API_KEY": "",
        "DEE_API_AUTH_KEY": ADMIN,
        "DEE_EMAIL_PROVIDER": "capture",
        "DEE_EMAIL_CAPTURE_PATH": mailbox.as_posix(),
        # No DEE_CORS_ALLOWED_ORIGINS: there is no cross-origin caller left.
        # Leaving it EMPTY is part of what this check now proves -- CORS is
        # fail-closed, so if any of these calls were still cross-origin the
        # browser would block them and the run would fail loudly.
        "DEE_SESSION_COOKIE_SECURE": "false",
        # The SHIPPED default since S8.6, not a test-only convenience. Set
        # explicitly anyway, so this file states the posture it is exercising.
        "DEE_SESSION_COOKIE_SAMESITE": "lax",
    })

    api_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "localhost",
         "--port", str(API_PORT)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    profile = tempfile.mkdtemp()
    chrome = subprocess.Popen([
        _chrome(), "--headless=new", f"--remote-debugging-port={CDP_PORT}",
        "--no-first-run", "--no-default-browser-check", f"--user-data-dir={profile}",
        "--disable-gpu", "--window-size=1440,1000", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    api = httpx.Client(base_url=API_BASE, timeout=60,
                       headers={"X-API-Key": ADMIN})
    try:
        for _ in range(80):
            try:
                if api.get("/healthz").status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.5)
        else:
            print("API never became healthy")
            return 1
        check("the_api_is_up_and_is_also_the_ui_host", True)

        ws_url, tabs = None, []
        for _ in range(60):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json"))
                pages = [t for t in tabs if t["type"] == "page"]
                if pages:
                    ws_url = pages[0]["webSocketDebuggerUrl"]
                    break
            except Exception:
                pass
            time.sleep(0.5)
        # Refuse to drive anything but the throwaway browser this script
        # launched. A debugging port that already had somebody's tabs on it is
        # somebody else's browser, and this script clicks buttons.
        stray = [t for t in tabs if t["type"] == "page" and t["url"] not in ("about:blank", "")]
        if not ws_url or stray:
            print(f"refusing to attach: unexpected targets on {CDP_PORT}: "
                  f"{[t['url'][:60] for t in stray]}")
            return 1

        async with websockets.connect(ws_url, max_size=40_000_000) as ws:
            tab = Tab(ws)
            await tab.send("Runtime.enable")
            await tab.send("Page.enable")
            await tab.send("DOM.enable")
            # NO ?api=. The whole point is that api.js's same-origin default
            # resolves to the page's own origin -- pass the override here and
            # the default would never be exercised at all.
            await tab.send("Page.navigate", {"url": UI_URL})
            await asyncio.sleep(2)
            await run(tab, mailbox, files, api)
    finally:
        for p in (chrome, api_proc):
            p.terminate()
        api.close()

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"\n{passed}/{len(CHECKS)} OK")
    return 0 if passed == len(CHECKS) else 1


def _org_client(admin: httpx.Client) -> httpx.Client:
    """A machine client scoped to the organisation the BROWSER just created.

    The browser holds the only session; this reads the same data through
    `X-Org-Key` so the screen's numbers can be checked against the API's
    without borrowing the browser's cookie.
    """
    orgs = admin.get("/ledger/orgs").json()
    org_id = orgs[-1]["id"] if orgs else None
    key = admin.post(f"/ledger/orgs/{org_id}/api-key").json()["api_key"]
    return httpx.Client(base_url=API_BASE, timeout=60, headers={"X-Org-Key": key})


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
