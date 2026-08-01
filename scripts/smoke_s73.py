"""S7.3 smoke: boot uvicorn on a migrated scratch DB and walk an AI interview
end to end — plan from the candidate's own profile, refuse audio with no ASR
provider, score typed answers, complete, and disclose to an org only under
consent.

The three checks this sprint exists to protect:
  * audio_refused_without_a_provider — with no key the audio channel says so
    (422 speech_unavailable) and the interview runs as a TEXT interview. The
    deterministic fallback, stated out loud rather than degraded silently.
  * assurance_stamped_from_the_live_number — the proxy hook reads S7.1: a
    candidate who self-attests between sessions gets the higher level stamped
    on the NEXT session, and never retroactively on the finished one.
  * org_sees_no_transcript — an org reads bands and dimensions; the candidate's
    own words are theirs alone (spec section 0.1).

No network, no LLM, no API key needed (extraction falls back to heuristics, and
scoring is deterministic without one).

Run from repo root: python scripts/smoke_s73.py
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

PORT = 8073
BASE = f"http://127.0.0.1:{PORT}"
ADMIN = "smoke-admin-key"
EMAIL = "dev@example.com"

RESUME = f"""Dev Kumar
Email: {EMAIL}

EXPERIENCE
Senior Software Engineer at Acme Technologies - Mar 2021 - Jan 2024
Data Engineer at Globex Corp - Jan 2019 - Feb 2021

SKILLS
Python, PyTorch, Spark, Kubernetes
"""

ANSWER = (
    "I rebuilt the nightly ingestion path at Acme myself. The PyTorch training "
    "job kept failing on 8 GPUs after a tokenizer change, I traced it through "
    "the checkpoint logs, and I cut p99 latency from 900 ms to 220 ms while "
    "dropping cost by 40 percent. I rolled it out behind a flag."
)
AUDIO_B64 = "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQQ=="   # valid base64, not audio


def _wait_healthy(c) -> bool:
    for _ in range(60):
        try:
            if c.get("/healthz").status_code == 200:
                return True
        except httpx.TransportError:
            time.sleep(0.5)
    return False


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s73.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    env = os.environ.copy()
    env.update({
        "DEE_CANDIDATES_DB_URL": url,
        "DEE_REPORT_DB_PATH": (scratch / "reports.db").as_posix(),
        "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
        "DEE_VECTORSTORE_BACKEND": "memory",
        "DEE_API_AUTH_KEY": ADMIN,
        # Pinned EMPTY on purpose. This smoke's whole claim is that the no-key
        # path works end to end, and a developer with a real key in .env would
        # otherwise send junk audio to a live vendor and get `speech_failed`
        # instead of the `speech_unavailable` this exercises. The live ASR path
        # is verified separately and recorded in MODELS.md.
        "DEE_OPENROUTER_API_KEY": "",
    })
    admin_h = {"X-API-Key": ADMIN}
    checks: dict[str, bool] = {}

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], env=env
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(60, connect=5)) as c:
            if not _wait_healthy(c):
                print("server did not become healthy")
                return 1

            # 1. candidate + key; nothing interviewed yet
            cid = c.post("/candidates", headers=admin_h,
                         json={"resume_text": RESUME, "evaluate": False}
                         ).json()["candidate_id"]
            key = c.post(f"/candidates/{cid}/auth-key",
                         headers=admin_h).json()["access_key"]
            ch = {"X-Candidate-Key": key}
            checks["no_interviews_yet"] = (
                c.get("/portal/interviews", headers=ch).json()["interviews"] == []
            )

            # 2. start -> a plan built from the candidate's own profile
            started = c.post("/portal/interviews", json={}, headers=ch)
            body = started.json()
            sid = body["session"]["id"]
            first = body["next_question"]
            checks["interview_starts_with_a_question"] = (
                started.status_code == 200
                and first is not None
                and len(body["session"]["questions"]) >= 3
                and body["session"]["assurance_level_at_start"] == 0
            )

            # 3. a second start while one is live is refused
            checks["one_live_session_only"] = (
                c.post("/portal/interviews", json={}, headers=ch).status_code == 409
            )

            def answer(question_id, **payload):
                return c.post(f"/portal/interviews/{sid}/answers",
                              json={"question_id": question_id, **payload},
                              headers=ch)

            # 4. THE fallback check: no ASR provider -> the audio channel says so
            audio = answer(first["id"], audio_b64=AUDIO_B64, mime="audio/wav")
            checks["audio_refused_without_a_provider"] = (
                audio.status_code == 422
                and "speech_unavailable" in audio.json()["detail"]
            )

            # 5. ...and nothing was recorded, so a retry costs nothing
            checks["refused_audio_recorded_no_turn"] = (
                c.get(f"/portal/interviews/{sid}", headers=ch)
                .json()["session"]["turns"] == []
            )

            # 6. a typed answer scores and advances
            first_answer = answer(first["id"], text=ANSWER)
            fa = first_answer.json()
            checks["text_answer_is_scored"] = (
                first_answer.status_code == 200
                and len(fa["session"]["turns"]) == 1
                and bool(fa["session"]["turns"][0]["score"]["dimensions"])
                and fa["next_question"]["sequence"] == 2
            )

            # 7. an answer naming the wrong question is refused
            following = fa["next_question"]
            checks["wrong_question_id_is_409"] = (
                answer(first["id"], text=ANSWER).status_code == 409
            )

            # 8. an oversize answer is refused
            checks["oversize_answer_refused"] = (
                answer(following["id"], text="x " * 20_000).status_code == 422
            )

            # 9. finish the interview -> an advisory assessment
            while following is not None:
                out = answer(following["id"], text=ANSWER).json()
                following = out["next_question"]
            session = out["session"]
            assessment = session["assessment"]
            checks["session_completes_with_an_advisory_assessment"] = (
                session["status"] == "completed"
                and assessment is not None
                and assessment["advisory"] is True
                and assessment["human_review_required"] is True
                and assessment["coverage"] == 1.0
                and bool(assessment["band"])
            )

            # 10. the proxy signal read the assurance level and capped itself
            proxy = assessment["proxy"]
            ids = {f["id"] for f in proxy["findings"]}
            checks["proxy_reads_identity_assurance"] = (
                "identity_assurance_none" in ids
                and proxy["assurance_level_at_start"] == 0
                and proxy["band"] in ("low", "moderate", "elevated")
                and all(f["severity"] != "hard" for f in proxy["findings"])
            )

            # 11. THE hook check: self-attest, then a NEW session stamps level 1
            c.post("/portal/verifications", json={"method": "self_attested"},
                   headers=ch)
            second = c.post("/portal/interviews", json={}, headers=ch).json()
            checks["assurance_stamped_from_the_live_number"] = (
                second["session"]["assurance_level_at_start"] == 1
                # and the finished session was NOT retroactively rewritten
                and c.get(f"/portal/interviews/{sid}", headers=ch)
                .json()["session"]["assurance_level_at_start"] == 0
            )

            # 12. org disclosure is consent-gated on the NEW purpose
            org = c.post("/ledger/orgs", headers=admin_h,
                         json={"name": "Globex Talent"}).json()
            org_id, org_key = org["org"]["id"], org["api_key"]
            org_h = {"X-Org-Key": org_key}
            path = f"/interview/candidates/{cid}/assessments"
            checks["org_403_without_consent"] = (
                c.get(path, headers=org_h).status_code == 403
            )

            gid = c.post(f"/ledger/candidates/{cid}/consent", headers=admin_h,
                         json={"purpose": "interview_read", "org_id": org_id}
                         ).json()["id"]
            granted = c.get(path, headers=org_h)
            checks["org_200_with_consent"] = (
                granted.status_code == 200
                and granted.json()["attempts"] == 1        # only the COMPLETED one
                and bool(granted.json()["assessments"][0]["dimensions"])
            )

            # 13. THE disclosure line: numbers for the org, words for the candidate
            checks["org_sees_no_transcript"] = (
                ANSWER not in granted.text
                and "transcript" not in granted.text
                and ANSWER in c.get(f"/portal/interviews/{sid}", headers=ch).text
            )

            c.post(f"/ledger/consent/{gid}/revoke", headers=admin_h)
            checks["org_403_after_revoke"] = (
                c.get(path, headers=org_h).status_code == 403
            )

            # 14. the portal shows the interviews + their retention window
            me = c.get("/portal/me", headers=ch).json()
            windows = {w["data_class"]: w for w in me["retention"]["windows"]}
            checks["portal_lists_interviews_and_retention"] = (
                len(me["interviews"]) == 2
                and ANSWER not in str(me["interviews"])     # summaries only
                and windows["interviews"]["ttl_days"] == 1095
                and me["retention"]["sweep_active"] is False
            )

            # 15. the org's query is in the candidate's own access log, by name
            log = c.get("/portal/access-log", headers=ch).json()
            queries = [e for e in log if e["action"] == "interview.query"]
            checks["access_log_shows_the_org_query"] = (
                bool(queries) and queries[0]["actor_name"] == "Globex Talent"
            )

            # 16. DPDP erasure sweeps the interviews with the candidate
            c.delete("/portal/me", headers=ch)
            checks["org_404_after_erase"] = (
                c.get(path, headers=org_h).status_code == 404
            )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    ok_count = sum(checks.values())
    for name, passed in checks.items():
        print(f"  [{'OK' if passed else 'XX'}] {name}")
    print(f"{ok_count}/{len(checks)} checks OK")
    return 0 if ok_count == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
