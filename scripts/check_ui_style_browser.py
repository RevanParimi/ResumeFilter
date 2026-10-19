"""Render v2 report components through the real Chrome screening journey.

Uses the existing browser harness and T1 fake-provider app factory. Synthetic
high-style uploads must render factual component cards without a style card in
the fusion. Requires Chrome/CDN access; UI wording revisions belong to T2.
"""

import asyncio
import os
from pathlib import Path
import subprocess
import tempfile

import check_ui_screening_browser as browser


async def main():
    scratch = Path(tempfile.mkdtemp(prefix="r2-s2-t1-browser-"))
    print(f"Synthetic style browser artifacts: {scratch}")
    polished = (browser.FIXTURES / "style_polished_resume.txt").read_text(encoding="utf-8")
    originals = browser._resume, browser.minimal_pdf, browser.Tab.text, subprocess.Popen
    owned = []
    checked = False
    server_log = (scratch / "server.log").open("w", encoding="utf-8")

    def resume(name, email):
        return polished.replace("Synthetic Taylor", name + "\nEmail: " + email)

    browser._resume = resume
    browser.minimal_pdf = lambda lines: originals[1](resume(lines[0], "kavya.iyer@example.in").splitlines())

    def launch(args, **kwargs):
        if "app.main:app" in args:
            args = ["smoke_r2_s2_t1:create_smoke_app" if a == "app.main:app" else a for a in args]
            args.append("--factory")
            safe_env = {k: v for k, v in kwargs["env"].items() if not k.startswith("DEE_")}
            safe_env.update({k: v for k, v in kwargs["env"].items() if k in {
                "DEE_CANDIDATES_DB_URL", "DEE_FLYWHEEL_PATH", "DEE_EMAIL_CAPTURE_PATH", "DEE_API_AUTH_KEY"}})
            safe_env.update({
                "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_ENV": "local",
                "DEE_OPENROUTER_API_KEY": "", "DEE_LLM_MAX_RETRIES": "0",
                "DEE_GITHUB_TOKEN": "", "DEE_GITHUB_API_BASE": "http://127.0.0.1:9",
                "DEE_EMAIL_PROVIDER": "capture", "DEE_SPEECH_PROVIDER": "local",
                "DEE_VECTORSTORE_BACKEND": "memory", "DEE_LOGIN_OTP_DEBUG_ECHO": "false",
                "DEE_LOGIN_OTP_STATIC_CODE": "", "DEE_SESSION_COOKIE_SECURE": "false",
                "DEE_SESSION_COOKIE_SAMESITE": "lax", "DEE_FR_WEIGHT_AI": "0",
                "PYTHONPATH": os.pathsep.join(str(p) for p in (browser.ROOT / "src", browser.ROOT / "scripts", browser.ROOT)),
            })
            kwargs["env"] = safe_env
            kwargs["cwd"] = scratch
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
            visible = await tab.wait("window.__has('Timeline / structure') && window.__has('Content overlap')", 20,
                                     "factual risk component cards")
            body = await originals[2](tab)
            browser.S.check("v2 report renders factual component cards without a style fusion card", visible and
                            "AI generation" not in body and "Writing-style observations" in body and
                            "likelihood" not in body.lower() and "writing style is excluded" in body.lower())
            (scratch / "rendered-report.txt").write_text(body, encoding="utf-8")
            checked = True
        return body

    browser.Tab.text = report_text
    subprocess.Popen = launch
    try:
        await browser.main()
        browser.S.check("v2 report browser assertion was reached", checked)
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
