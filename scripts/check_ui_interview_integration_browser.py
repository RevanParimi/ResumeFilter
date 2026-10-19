"""Combined text/audio/summary/restart journey, extending real microphone checks.

Synthetic microphone and fake ASR only; employer summary is the actual HTTP API,
not a claimed employer interview UI. Owns only the child processes it starts.
"""
import asyncio
import base64
import json

import check_ui_interview_audio_browser as audio
import check_ui_screening_browser as browser
from smoke_r3_s3_t3 import ANSWER


async def combined(tab, admin, checks, *, cid, key, scratch, restart):
    def require(response):
        assert response.status_code == 200, (response.request.url.path, response.status_code)
        return response.json()

    async def click(label):
        assert await tab.js("window.__click('button'," + json.dumps(label) + ")"), label

    async def writable():
        assert await tab.wait("document.querySelector('#interview-answer') && !document.querySelector('#interview-answer').disabled", 25)

    async def reload():
        before = await tab.js("performance.timeOrigin")
        await tab.send("Page.reload")
        assert await tab.wait(f"performance.timeOrigin !== {before} && document.readyState==='complete' && document.querySelector('button')", 45)
        await tab.js(browser.HELPERS)
        assert await tab.wait("window.__has('Sign out')", 25)
        await click("Interview")
        assert await tab.wait("window.__q('button','Refresh saved interviews') && !window.__q('button','Refresh saved interviews').disabled", 25)

    async def paste(value):
        assert await tab.js("(() => {const e=document.querySelector('#interview-answer'); if(!e) return false; Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(e," + json.dumps(value) + "); e.dispatchEvent(new Event('input',{bubbles:true})); return true;})()")

    async def detail(sid):
        return require(admin.get(f"/portal/interviews/{sid}", headers={"X-Candidate-Key": key}))

    await click("Start new interview"); await writable()
    sid = await tab.js("document.querySelector('[data-interview-session]').getAttribute('data-interview-session')")
    repeated = "I Python 123 retrieval " * 20
    await paste(repeated); await click("Submit answer"); await writable()
    first = await detail(sid)
    checks.check("combined browser typed repetition saves progress without eligible evidence",
        len(first["session"]["turns"]) == 1 and first["session"]["turns"][0]["channel"] == "text"
        and first["session"]["turns"][0]["score"]["insufficient"])
    await reload(); await writable()
    checks.check("combined reload resumes exact next question and saved typed evidence",
        await tab.js("document.querySelector('[data-interview-question]').getAttribute('data-interview-question')") == first["next_question"]["id"]
        and repeated.strip() in await tab.text())
    await click("Voice answer"); await click("Record voice answer")
    assert await tab.wait("document.querySelector('[data-interview-recording=recording]')", 15)
    await asyncio.sleep(.8)
    await click("Stop recording")
    assert await tab.wait("document.querySelector('[data-interview-recording=ready]')", 15)
    await click("Submit voice answer")
    assert await tab.wait("document.querySelectorAll('[data-interview-turn]').length===2 && !window.__q('button','Refresh saved interviews').disabled", 25)
    saved = await detail(sid)
    checks.check("same browser interview saves real microphone bytes and both channels",
        [t["channel"] for t in saved["session"]["turns"]] == ["text", "audio"]
        and saved["session"]["turns"][1]["transcript"] == ANSWER
        and bool(saved["session"]["turns"][1]["audio_digest"]))

    # Real process stop/start with the same migrated scratch storage and cookie.
    await asyncio.to_thread(restart)
    await reload(); await writable()
    checks.check("browser reload after actual app restart preserves exact mixed-channel state",
        await detail(sid) == saved and ANSWER in await tab.text()
        and await tab.js("document.querySelector('#interview-answer').value==='' && !document.querySelector('[data-interview-recording]')"))
    await click("Finish interview early")
    assert await tab.wait("window.__has('Unanswered questions reduce coverage')", 10)
    await click("Confirm finish")
    assert await tab.wait("document.querySelector('[data-interview-assessment]') && !window.__q('button','Refresh saved interviews').disabled", 25)
    done = await detail(sid)
    assessment = done["session"]["assessment"]
    checks.check("combined completion is persisted advisory v2 with evidence explanations",
        done["next_question"] is None and assessment["scorer_version"] == "s73.2"
        and assessment["advisory"] and assessment["human_review_required"]
        and await tab.js("window.__has('Saved scorer version: s73.2') && window.__has('not poor ability') && window.__has('answered fraction, not evidence quality')"))
    checks.check("known repeated-keyword answer cannot create a strong aggregate",
        assessment["band"] not in {"deep", "solid"}
        and assessment["confidence"] == round(sum(t["score"]["evidence_confidence"] for t in saved["session"]["turns"]
            if not t["score"]["insufficient"] and "relevance_unconfirmed" not in t["score"]["codes"]) / assessment["questions_planned"], 4))
    shot = await tab.send("Page.captureScreenshot")
    (scratch / "combined-text-audio-assessment.png").write_bytes(base64.b64decode(shot["data"]))

    org = require(admin.post("/ledger/orgs", json={"name": "Combined interview employer"}))
    other_org = require(admin.post("/ledger/orgs", json={"name": "Unconsented interview employer"}))
    path = f"/interview/candidates/{cid}/assessments"
    def employer(org_key):
        # No candidate/admin headers: exercise the employer authentication plane.
        from _smoke import client
        with client(browser.API_BASE, headers={"X-Org-Key": org_key}) as reader:
            return reader.get(path)
    checks.check("employer summary denies before consent", employer(org["api_key"]).status_code == 403)
    grant = require(admin.post(f"/ledger/candidates/{cid}/consent", json={"purpose": "interview_read", "org_id": org["org"]["id"]}))
    response = employer(org["api_key"])
    summaries = require(response)["assessments"]
    summary = next(s for s in summaries if s["id"] == sid)
    checks.check("employer sees exact combined saved assessment without transcript or media",
        all(summary[field] == assessment[field] for field in ("band", "overall", "dimensions", "confidence", "scorer_version", "questions_planned", "questions_answered", "advisory"))
        and all(value not in response.text for value in
        (ANSWER, repeated.strip(), "transcript", '"turns"', "audio_digest", "audio_b64")))
    checks.check("another employer cannot consume this consent", employer(other_org["api_key"]).status_code == 403)
    await asyncio.to_thread(restart)
    await reload()
    checks.check("completed browser assessment and employer permission survive real restart",
        await detail(sid) == done and employer(org["api_key"]).status_code == 200
        and await tab.js("document.querySelector('[data-interview-assessment]') && window.__has('Saved scorer version: s73.2')"))
    require(admin.post(f"/ledger/consent/{grant['id']}/revoke"))
    checks.check("current revocation immediately hides persisted mixed-channel summary",
        employer(org["api_key"]).status_code == 403)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(audio.main(after_completion=combined)))
