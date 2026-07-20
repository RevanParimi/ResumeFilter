"""S3.1 smoke: migrate a scratch DB with Alembic, then run the real ledger flow —
ingest a candidate → org → consent-refused submit → grant → submit → event →
audit trail → revoke blocks → DPDP erasure sweeps the ledger, org survives.

S3.1 is LLM-free; with no API key the candidate-extraction step uses the
heuristic floor, which changes nothing downstream. Run from the repo root:
    python scripts/smoke_s31.py
"""

import asyncio
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.candidates.extractor import extract_profile
from app.candidates.store import CandidateStore
from app.core.config import get_settings
from app.core.db import make_engine, make_session_factory
from app.ledger.store import ConsentError, LedgerStore
from app.services.llm import build_llm

FIXTURE = Path("tests/fixtures/full_profile_resume.txt")
LEDGER_TABLES = {
    "organizations", "consent_grants", "interview_records",
    "evaluation_events", "audit_log",
}


def main() -> int:
    db_path = Path(tempfile.mkdtemp()) / "smoke_s31.db"
    url = "sqlite:///" + db_path.as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    settings = get_settings()
    engine = make_engine(url)
    session_factory = make_session_factory(engine)
    candidates = CandidateStore(session_factory)
    ledger = LedgerStore(
        session_factory,
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
    )
    now = datetime.now(timezone.utc)

    tables_ok = LEDGER_TABLES <= set(inspect(engine).get_table_names())

    text = FIXTURE.read_text(encoding="utf-8")
    result = asyncio.run(extract_profile(text, llm=build_llm(settings), settings=settings))
    ingest = candidates.ingest(result, text)
    print(f"candidate [{result.method}]: {ingest.candidate_id[:8]}")

    org = ledger.create_organization("Acme Talent Pvt Ltd")
    print(f"org: {org.id[:8]} {org.name!r}")

    refused = False
    try:
        ledger.submit_interview_record(
            org_id=org.id, candidate_id=ingest.candidate_id, stage="tech",
            outcome="advanced", interviewed_at=now,
        )
    except ConsentError as exc:
        refused = True
        print(f"submit without consent refused: {exc}")

    grant = ledger.grant_consent(
        candidate_id=ingest.candidate_id, purpose="ledger_write", org_id=org.id
    )
    ttl_days = (grant.expires_at - grant.granted_at).days
    print(f"consent granted: {grant.id[:8]} expires in {ttl_days}d")

    record = ledger.submit_interview_record(
        org_id=org.id, candidate_id=ingest.candidate_id, stage="tech",
        outcome="advanced", interviewed_at=now, summary="solid systems round",
    )
    event = ledger.append_event(record.id, event_type="score",
                                payload={"scale": 5, "value": 4})
    print(f"record: {record.id[:8]} (consent {record.consent_id[:8]}) + event {event.id[:8]}")

    audit_actions = [a.action for a in ledger.audit_for_candidate(ingest.candidate_id)]
    print(f"audit trail: {audit_actions}")

    ledger.revoke_consent(grant.id)
    audit_actions = [a.action for a in ledger.audit_for_candidate(ingest.candidate_id)]
    revoked_blocks = False
    try:
        ledger.submit_interview_record(
            org_id=org.id, candidate_id=ingest.candidate_id, stage="hm",
            outcome="offer", interviewed_at=now,
        )
    except ConsentError:
        revoked_blocks = True
        print("submit after revocation refused")

    retained = len(ledger.records_for_candidate(ingest.candidate_id)) == 1

    erased = candidates.delete_candidate(ingest.candidate_id)
    swept = (
        ledger.records_for_candidate(ingest.candidate_id) == []
        and ledger.events_for_record(record.id) == []
        and ledger.audit_for_candidate(ingest.candidate_id) == []
    )
    org_survives = ledger.get_organization(org.id) is not None

    checks = {
        "ledger tables migrated": tables_ok,
        "submit without consent refused": refused,
        "default consent TTL applied": ttl_days == settings.ledger_consent_default_ttl_days,
        "record links authorizing grant": record.consent_id == grant.id,
        "event lands on record": event.record_id == record.id,
        "mutations audited in order": audit_actions
        == ["consent.grant", "record.submit", "event.append", "consent.revoke"],
        "revocation blocks new submissions": revoked_blocks,
        "pre-revocation record retained until erasure": retained,
        "DPDP erasure sweeps ledger rows": erased and swept,
        "organization survives erasure": org_survives,
    }
    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    if failed:
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
