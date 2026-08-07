"""Run the API and the UI together for local clicking-around.

    python scripts/serve_demo.py

That is the whole command. Everything the browser needs is configured HERE,
in code, rather than pasted into a terminal every time -- a wall of `$env:`
lines is a config file with no home, and the day one of them is forgotten the
symptom is a mysterious 401 rather than an error.

Every setting below exists for a measured reason; none is decoration:

  * CORS is FAIL-CLOSED. With no allowlisted origin the middleware is not
    installed at all, so every browser call dies looking like an auth bug. It
    must match the UI's origin EXACTLY, which is why both ports live here.
  * UI_PORT is 5273, not Vite's 5173. This machine already runs another
    project there, and python's http.server sets SO_REUSEADDR -- which on
    Windows lets a second process bind a port that is already taken. Both
    listen, and which one answers your browser is a coin flip.
  * The DB is a scratch file under TEMP. `data/veritas.db` is TRACKED, so
    demoing against it dirties the working tree.
  * The API key is pinned EMPTY. This repo's .env holds a real one, and
    uploading a resume through the UI would otherwise make billed live calls.
  * Session cookies drop Secure/SameSite=None, which are correct for a
    deployed UI and useless on plain-HTTP localhost. Production refuses to
    BOOT in this configuration (app/core/boot.py), so it cannot leak.

Login codes are captured to a file instead of being emailed, and this script
prints each one as it is issued -- watch this terminal after clicking
"Send code".
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FRONTEND = REPO / "frontend"
API_PORT = 8000          # api.js's DEFAULT_BASE; changing it needs ?api=
UI_PORT = 5273           # NOT 5173 -- see the module docstring
ADMIN_KEY = "demo-admin-key"


def _env(scratch: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "DEE_CANDIDATES_DB_URL": "sqlite:///" + (scratch / "veritas_demo.db").as_posix(),
        "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
        "DEE_VECTORSTORE_BACKEND": "memory",
        "DEE_OPENROUTER_API_KEY": "",
        "DEE_API_AUTH_KEY": ADMIN_KEY,
        "DEE_EMAIL_PROVIDER": "capture",
        "DEE_EMAIL_CAPTURE_PATH": (scratch / "mailbox.jsonl").as_posix(),
        "DEE_SESSION_COOKIE_SECURE": "false",
        "DEE_SESSION_COOKIE_SAMESITE": "lax",
        "DEE_CORS_ALLOWED_ORIGINS": json.dumps([f"http://localhost:{UI_PORT}"]),
        # Echo the sign-in code back to the browser so the UI can fill it in
        # and login is one click. Needs env=local as well (the default here),
        # and prod refuses to BOOT with it -- see app/core/boot.py.
        "DEE_LOGIN_OTP_DEBUG_ECHO": "true",
    })
    return env


def _tail_codes(mailbox: Path, stop: threading.Event) -> None:
    """Print each captured login code as it is issued.

    Reads by line COUNT rather than seeking a byte offset: the file is
    rewritten as JSON lines and a partially-flushed line would otherwise be
    parsed as truncated JSON and kill this thread silently.
    """
    seen = 0
    while not stop.is_set():
        try:
            lines = mailbox.read_text(encoding="utf-8").splitlines()
        except (FileNotFoundError, OSError):
            lines = []
        for raw in lines[seen:]:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            code = "".join(ch for ch in msg.get("body", "") if ch.isdigit())[:6]
            print(f"  [code] {msg.get('to')} -> {code}", flush=True)
        seen = max(seen, len(lines))
        stop.wait(0.5)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api-only", action="store_true", help="skip the static UI server")
    ap.add_argument("--scratch", default="", help="reuse a scratch dir (keeps the DB)")
    args = ap.parse_args()

    scratch = Path(args.scratch) if args.scratch else Path(os.environ.get(
        "TEMP", "/tmp")) / "veritas-demo"
    scratch.mkdir(parents=True, exist_ok=True)
    mailbox = scratch / "mailbox.jsonl"

    print(f"scratch : {scratch}")
    print(f"API     : http://localhost:{API_PORT}")
    if not args.api_only:
        print(f"UI      : http://localhost:{UI_PORT}/Veritas.dc.html   <-- open this")
    print(f"admin   : X-API-Key: {ADMIN_KEY}")
    print("login codes print below as they are issued.\n")

    procs: list[subprocess.Popen] = []
    stop = threading.Event()
    tail = threading.Thread(target=_tail_codes, args=(mailbox, stop), daemon=True)
    tail.start()
    try:
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(API_PORT)],
            cwd=REPO, env=_env(scratch),
        ))
        if not args.api_only:
            # --bind 127.0.0.1 on purpose: without it SO_REUSEADDR lets this
            # bind a port another server already owns (see the docstring).
            procs.append(subprocess.Popen(
                [sys.executable, "-m", "http.server", str(UI_PORT),
                 "--bind", "127.0.0.1"],
                cwd=FRONTEND,
            ))
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
        for p in procs:
            if p.poll() not in (None, 0):
                print(f"\na server exited with {p.returncode}", file=sys.stderr)
                return 1
    except KeyboardInterrupt:
        print("\nstopping...")
    finally:
        stop.set()
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
