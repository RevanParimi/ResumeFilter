"""Reuse the real screening browser journey with a synthetic GitHub outage.

Requires Chrome/CDN access; provider calls use the T3 MockTransport factory.
All uploads, login capture, Chrome profile and migrated storage are disposable.
"""

import asyncio
import os
from pathlib import Path
import subprocess
import tempfile

import check_ui_screening_browser as browser


async def main():
    scratch = Path(tempfile.mkdtemp(prefix="r2-s1-t3-browser-"))
    (scratch / "github-mode.txt").write_text("404", encoding="utf-8")
    (scratch / "claim-mode.txt").write_text("rules", encoding="utf-8")
    print(f"Synthetic GitHub browser artifacts: {scratch}")
    originals = browser._resume, browser.minimal_pdf, browser.Tab.text, subprocess.Popen
    owned = []
    checked = False
    server_log = (scratch / "server.log").open("w", encoding="utf-8")
    # The existing upload screen defaults to data_eng; this line is also
    # recognizable in genai if that UI default changes.
    linked_claim = "Built a retrieval augmented generation pipeline for support. https://github.com/alice/project"

    browser._resume = lambda name, email: originals[0](name, email) + "\n" + linked_claim + "\n"
    browser.minimal_pdf = lambda lines: originals[1]([*lines, linked_claim])

    def launch(args, **kwargs):
        if "app.main:app" in args:
            args = ["smoke_r2_s1_t3:create_smoke_app" if a == "app.main:app" else a for a in args]
            args.append("--factory")
            kwargs["env"] = {**kwargs["env"], "R2_GITHUB_SMOKE_DIR": str(scratch),
                "PYTHONPATH": os.pathsep.join(str(p) for p in (browser.ROOT / "src", browser.ROOT / "scripts", browser.ROOT))}
            kwargs["stdout"], kwargs["stderr"] = server_log, subprocess.STDOUT
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = originals[3](args, **kwargs)
        owned.append(proc)
        return proc

    async def report_text(tab):
        nonlocal checked
        body = await originals[2](tab)
        if not checked and "claim by claim" in body.lower():
            visible = await tab.wait("window.__has('not found or inaccessible (HTTP 404)')", 20,
                                     "the GitHub unavailable context")
            body = await originals[2](tab)
            browser.S.check("report renders GitHub outage without claiming repository absence", visible and
                "does not exist" not in body.lower() and "synthetic-upstream-private-detail" not in body)
            checked = True
        return body

    browser.Tab.text = report_text
    subprocess.Popen = launch
    try:
        await browser.main()
        browser.S.check("GitHub report browser assertion was reached", checked)
        calls = scratch / "github-calls.txt"
        browser.S.check("browser uploads reached the fake GitHub repository client", calls.exists() and
                        calls.read_text(encoding="utf-8").splitlines().count("/repos/alice/project") == 3)
        return browser.S.summary()
    finally:
        browser._resume, browser.minimal_pdf, browser.Tab.text, subprocess.Popen = originals
        for proc in owned:
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
        server_log.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
