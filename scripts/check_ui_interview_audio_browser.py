"""Real candidate microphone answers on migrated scratch SQL with fake providers.

Chrome uses a synthetic microphone; ASR refusals/delays and oversize chunks are
explicit fixtures. Recording and answer/conflict/reload/actor paths use real APIs.
Requires Chrome/internet for the existing CDN runtime; never sends real email/SMS.
"""
import asyncio
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import check_ui_screening_browser as browser
from _smoke import Smoke
from app.interview.scoring import SCORER_VERSION
from smoke_r3_s3_t3 import ANSWER


async def main(*, after_completion=None):
    scratch = Path(tempfile.mkdtemp(prefix="r3-s3-t3-browser-"))
    print(f"Synthetic interview browser evidence: {scratch}", flush=True)
    checks = Smoke("R3-S3-T3 candidate microphone browser")
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
            args = ["smoke_r3_s3_t3:create_smoke_app" if a == "app.main:app" else a for a in args] + ["--factory"]
            inherited = kwargs["env"]
            env = {k: v for k, v in inherited.items() if not k.startswith("DEE_")}
            env.update({k: v for k, v in inherited.items() if k in {
                "DEE_CANDIDATES_DB_URL", "DEE_FLYWHEEL_PATH", "DEE_EMAIL_CAPTURE_PATH", "DEE_API_AUTH_KEY"}})
            env.update({
                "DEE_INTERVIEW_MAX_AUDIO_B64_CHARS": "250000", "DEE_CONFIG_FILE": str(scratch / "no-config.yaml"), "DEE_ENV": "local",
                "DEE_OPENROUTER_API_KEY": "", "DEE_LLM_MAX_RETRIES": "0",
                "DEE_GITHUB_TOKEN": "", "DEE_GITHUB_API_BASE": "http://127.0.0.1:9",
                "DEE_EMAIL_PROVIDER": "capture", "DEE_SPEECH_PROVIDER": "local",
                "DEE_VECTORSTORE_BACKEND": "memory", "DEE_LOGIN_OTP_DEBUG_ECHO": "false",
                "DEE_VERIF_OTP_DEBUG_ECHO": "false", "DEE_LOGIN_OTP_STATIC_CODE": "",
                "DEE_SESSION_COOKIE_SECURE": "false", "DEE_SESSION_COOKIE_SAMESITE": "lax",
                "PYTHONPATH": os.pathsep.join(str(p) for p in (browser.ROOT / "src", browser.ROOT / "scripts", browser.ROOT)),
            })
            state["control"] = Path(env["DEE_EMAIL_CAPTURE_PATH"] + ".speech-control")
            kwargs.update(env=env, cwd=scratch, stdout=log, stderr=subprocess.STDOUT)
        if "--headless=new" in args: args = [*args, "--use-fake-device-for-media-stream"]
        if os.name == "nt": kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = original_popen(args, **kwargs); owned.append(proc)
        if "smoke_r3_s3_t3:create_smoke_app" in args:
            state.update(app=proc, args=args, kwargs=kwargs)
        return proc

    def restart():
        proc = state["app"]
        proc.terminate()
        try: proc.wait(timeout=10)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=10)
        state["app"] = launch(state["args"], **state["kwargs"])
        from _smoke import client, wait_healthy
        with client(browser.API_BASE) as http:
            assert wait_healthy(http), "owned scratch app failed to restart"

    async def run(tab, mailbox, files, admin):
        control = state["control"]
        address = "microphone-browser@example.com"
        def require(response):
            assert response.status_code == 200, response.status_code
            return response.json()
        def resume(email):
            return f"Synthetic Microphone Candidate\nEmail: {email}\nEXPERIENCE\nEngineer at Acme, 2020 - 2024\nSKILLS\nPython, SQL, Spark"
        cid = require(admin.post("/candidates",json={"evaluate":False,"resume_text":resume(address)}))["candidate_id"]
        key = require(admin.post(f"/candidates/{cid}/auth-key"))["access_key"]
        other_email = "microphone-other@example.com"
        other = require(admin.post("/candidates",json={"evaluate":False,"resume_text":resume(other_email)}))["candidate_id"]
        other_key = require(admin.post(f"/candidates/{other}/auth-key"))["access_key"]
        async def click(label):
            assert await tab.js("window.__click('button',"+json.dumps(label)+")"), label
        async def login(email):
            await tab.js(browser.HELPERS)
            assert await tab.wait("window.__has('Sign in')",45)
            await click("Candidate"); await click("Create account")
            await tab.js(f"window.__type('input[type=email]',{json.dumps(email)})")
            await click("Create account and send code")
            assert await tab.wait("document.querySelectorAll('input[inputmode]').length === 6",20)
            code = browser._code_for(mailbox,email)
            await tab.js(f"window.__type('input[inputmode]',{json.dumps(code)})")
            await click("Verify and continue")
            assert await tab.wait("window.__has('Sign out')",25)
        async def enter():
            await click("Interview")
            assert await tab.wait("window.__q('button','Refresh saved interviews') && !window.__q('button','Refresh saved interviews').disabled",25)
        async def refresh():
            await click("Refresh saved interviews")
            assert await tab.wait("!window.__q('button','Refresh saved interviews').disabled",25)
        async def writable():
            assert await tab.wait("document.querySelector('#interview-answer') && !document.querySelector('#interview-answer').disabled",25)
        async def sid():
            return await tab.js("document.querySelector('[data-interview-session]')?.getAttribute('data-interview-session')")
        async def qid():
            return await tab.js("document.querySelector('[data-interview-question]')?.getAttribute('data-interview-question')")
        async def paste(text):
            assert await tab.js("(() => {const e=document.querySelector('#interview-answer'); if(!e) return false; Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(e,"+json.dumps(text)+"); e.dispatchEvent(new Event('input',{bubbles:true})); return true;})()")
        async def record():
            await click("Voice answer"); await click("Record voice answer")
            assert await tab.wait("document.querySelector('[data-interview-recording=recording]')",15)
            await asyncio.sleep(.8)
        async def stop():
            await click("Stop recording")
            assert await tab.wait("document.querySelector('[data-interview-recording=ready]')",15)
        async def install():
            await tab.js("""
window.__streams=[]; window.__recorders=[]; window.__audioPosts=0; window.__lastAudio=null;
window.__gum=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
navigator.mediaDevices.getUserMedia=async constraints=>{
 const stream=await window.__gum(constraints); window.__streams.push(stream);
 if(window.__holdPermission) {window.__holdPermission=false; await new Promise(resolve=>{window.__releasePermission=resolve;});}
 return stream;
};
window.__Recorder=window.MediaRecorder;
window.MediaRecorder=class extends window.__Recorder { constructor(...args){super(...args); window.__recorders.push(this);} };
window.__fetch=window.fetch;
window.fetch=async (url,init)=>{
 if(init?.method==='POST' && url.endsWith('/answers') && JSON.parse(init.body).audio_b64) {
  const p=JSON.parse(init.body); window.__audioPosts++;
  const bytes=Uint8Array.from(atob(p.audio_b64),c=>c.charCodeAt(0));
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(b=>b.toString(16).padStart(2,'0')).join('');
  window.__lastAudio={mime:p.mime,question_id:p.question_id,chars:p.audio_b64.length,digest,keys:Object.keys(p).sort()};
  const response=await window.__fetch(url,init);
  if(window.__loseAck) {window.__loseAck=false; await response.text(); throw new TypeError('synthetic lost acknowledgement');}
  return response;
 }
 return window.__fetch(url,init);
};
window.__post=window.VeritasAPI.post;
window.VeritasAPI.post=(path,body,opts)=>window.__post(path,body,window.__shortDeadline?{timeoutMs:250}:opts);
window.__allStopped=()=>window.__streams.every(s=>s.getTracks().every(t=>t.readyState==='ended'));
""")
        def events():
            path = Path(str(control)+".jsonl")
            return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        async def wait_provider(event, before):
            for _ in range(100):
                if sum(e["event"]==event for e in events()) > before: return
                await asyncio.sleep(.05)
            raise AssertionError("provider did not reach "+event)

        await login(address); await enter(); await click("Start new interview"); await writable()
        session_id, first = await sid(), await qid()
        await install()
        await paste("Keep my typed fallback draft")
        await tab.send("Browser.setPermission",{"permission":{"name":"microphone"},"setting":"denied","origin":browser.API_BASE})
        await click("Voice answer"); await click("Record voice answer")
        checks.check("actual browser permission denial is recoverable with no request or saved turn", await tab.wait("window.__has('Microphone permission was denied')",15)
            and await tab.js("window.__audioPosts===0") and not events())
        await click("Type answer")
        checks.check("permission refusal preserves typed fallback and current question", await tab.js("document.querySelector('#interview-answer').value")=="Keep my typed fallback draft" and await qid()==first)
        await tab.send("Browser.setPermission",{"permission":{"name":"microphone"},"setting":"granted","origin":browser.API_BASE})
        await record()
        checks.check("real fake-device MediaRecorder shows recording and only audio tracks", await tab.js("window.__streams.at(-1).getAudioTracks().length===1 && window.__streams.at(-1).getVideoTracks().length===0 && window.__audioPosts===0"))
        shot=await tab.send("Page.captureScreenshot"); (scratch/"recording.png").write_bytes(base64.b64decode(shot["data"]))
        await stop()
        checks.check("stopping releases actual tracks and retains an unsent local clip", await tab.js("window.__allStopped() && window.__audioPosts===0 && !window.__q('button','Submit voice answer').disabled"))
        await click("Discard recording")
        checks.check("discard consumes no question or provider call", await tab.wait("document.querySelector('[data-interview-recording=idle]')",10) and await qid()==first and not events())
        await record(); await click("Type answer")
        checks.check("switching to text stops capture and preserves the typed draft", await tab.js("window.__allStopped() && document.querySelector('#interview-answer').value==='Keep my typed fallback draft'"))
        await click("Voice answer")
        await tab.js("window.__supported=window.MediaRecorder.isTypeSupported; window.MediaRecorder.isTypeSupported=()=>false")
        await click("Record voice answer")
        checks.check("unsupported browser recording format offers typed fallback", await tab.wait("window.__has('Microphone recording is unavailable')",10))
        await tab.js("window.MediaRecorder.isTypeSupported=window.__supported")
        await record()
        await tab.js("window.__recorders.at(-1).dispatchEvent(new BlobEvent('dataavailable',{data:new Blob([new Uint8Array(5000001)],{type:'audio/webm'})}))")
        checks.check("oversize chunk stops real device, discards clip and never uploads", await tab.wait("window.__has('Recording exceeded 5 MB')",10) and await tab.js("window.__allStopped() && window.__audioPosts===0"))
        for mode in ("failed","unavailable","empty"):
            control.write_text(mode); await record(); await stop(); await click("Submit voice answer")
            checks.check("actual fake-ASR refusal is visible with no saved answer: "+mode,
                await tab.wait("window.__has('No answer was saved') && window.__has('Read-only until saved state is refreshed')",20)
                and not await tab.js("document.querySelector('[data-interview-turn]')")
                and not require(admin.get(f"/portal/interviews/{session_id}",headers={"X-Candidate-Key":key}))["session"]["turns"])
            await refresh(); await writable()
            checks.check("ASR refusal recovery restores text on the same question: "+mode, await qid()==first)
        control.write_text("delay"); await record(); await stop()
        started = sum(e["event"]=="start" for e in events()); failed = sum(e["event"]=="failed" for e in events())
        await tab.js("window.__shortDeadline=true"); await click("Submit voice answer"); await wait_provider("start",started)
        checks.check("actual delayed ASR reaches client deadline without false transcript/success", await tab.wait("window.__has('could not be confirmed') && window.__has('Read-only until saved state is refreshed')",15)
            and not await tab.js("document.querySelector('[data-interview-turn]')"))
        control.write_text("failed"); await wait_provider("failed",failed); await tab.js("window.__shortDeadline=false")
        before = await tab.js("window.__audioPosts"); await refresh(); await writable()
        checks.check("timeout read restores unchanged question without replay", await qid()==first and await tab.js("window.__audioPosts")==before)
        control.write_text("ok"); await record(); await stop(); await tab.js("window.__loseAck=true")
        await tab.js("window.__click('button','Submit voice answer'); window.__click('button','Submit voice answer')")
        assert await tab.wait("window.__has('Read-only until saved state is refreshed')",20)
        checks.check("duplicate submit and lost committed acknowledgement remain uncertain", await tab.js("window.__audioPosts")==before+1)
        await refresh(); await writable()
        body = require(admin.get(f"/portal/interviews/{session_id}",headers={"X-Candidate-Key":key}))
        turn = body["session"]["turns"][0]
        metadata = await tab.js("window.__lastAudio")
        checks.check("real encoded browser bytes reach API; saved digest/transcript recover without replay", turn["channel"]=="audio" and turn["transcript"]==ANSWER
            and turn["audio_digest"]==metadata["digest"] and metadata["chars"]>0 and metadata["keys"]==["audio_b64","mime","question_id"]
            and metadata["question_id"]==first and await tab.js("window.__audioPosts")==before+1
            and ANSWER in await tab.text())
        foreign = admin.post(f"/portal/interviews/{session_id}/answers",headers={"X-Candidate-Key":other_key},json={"question_id":await qid(),"audio_b64":"AAAA","mime":"audio/webm"})
        checks.check("another candidate cannot submit audio to this session", foreign.status_code==404)
        # Freeze a local clip while a second client answers the same saved question.
        current = await qid(); await record(); await stop()
        require(admin.post(f"/portal/interviews/{session_id}/answers",headers={"X-Candidate-Key":key},json={"question_id":current,"text":"A second client answered this question."}))
        await click("Submit voice answer")
        checks.check("stale recorded question refuses instead of rebinding clip", await tab.wait("window.__has('Saved interview state changed or expired')",15))
        await refresh(); await writable()
        control.write_text("long"); await record(); await stop(); await click("Submit voice answer")
        checks.check("saved truncated transcript is disclosed in actual browser", await tab.wait("window.__has('Saved transcript was truncated')",25))
        await writable(); control.write_text("ok"); await record(); await stop(); await click("Submit voice answer")
        assert await tab.wait("document.querySelector('[data-interview-assessment]')",25)
        done = require(admin.get(f"/portal/interviews/{session_id}",headers={"X-Candidate-Key":key}))["session"]
        checks.check("last voice answer completes with saved advisory content assessment", done["status"]=="completed"
            and done["assessment"]["scorer_version"]==SCORER_VERSION and done["assessment"]["human_review_required"]
            and await tab.js("window.__has('Advisory only') && !document.querySelector('[data-interview-recording]')"))
        shot=await tab.send("Page.captureScreenshot"); (scratch/"audio-completed.png").write_bytes(base64.b64decode(shot["data"]))
        if after_completion:
            await after_completion(tab, admin, checks, cid=cid, key=key, scratch=scratch, restart=restart)
            await install()  # A combined journey may reload the actual page.
        await click("Start new interview"); await writable(); await click("Voice answer")
        await tab.js("window.__holdPermission=true"); await click("Record voice answer")
        assert await tab.wait("window.__releasePermission",15)
        await click("Overview"); await tab.js("window.__releasePermission()")
        checks.check("late permission after navigation closes real stream without restoring capture", await tab.wait("window.__allStopped()",10) and not await tab.js("document.querySelector('[data-interview-recording]')"))
        await enter(); await record(); await click("Overview")
        checks.check("navigation during recording releases actual tracks", await tab.js("window.__allStopped()"))
        await enter(); await record()
        before_origin=await tab.js("performance.timeOrigin"); await tab.send("Page.reload")
        assert await tab.wait(f"performance.timeOrigin !== {before_origin} && document.readyState==='complete' && document.querySelector('button')",60)
        await tab.js(browser.HELPERS); assert await tab.wait("window.__has('Sign out')",25); await enter(); await writable()
        checks.check("reload during recording resumes saved question with no local clip", await tab.js("document.querySelector('#interview-answer').value==='' && !document.querySelector('[data-interview-recording]')"))
        await install(); await record(); await click("Sign out")
        checks.check("signout during recording releases actual tracks", await tab.wait("window.__has('Sign in')",15) and await tab.js("window.__allStopped()"))
        await login(other_email); await enter()
        checks.check("new account has no previous candidate's transcript or clip", await tab.js("window.__has('No saved interviews') && !document.querySelector('[data-interview-session]')") and ANSWER not in await tab.text())
        checks.check("browser has no console errors or uncaught exceptions", not tab.console,"; ".join(tab.console[:2]))
        logs=(scratch/"server.log").read_text(encoding="utf-8")
        checks.check("actual app logs omit transcript and private provider error", ANSWER not in logs and "synthetic-private-provider-secret" not in logs)

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
