# S1.3 API + Engine Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the S1.1 extractor + S1.2 candidate store over HTTP — `POST /candidates` (upload → extract → store → auto depth-eval), reports linked to `candidate_id`, candidate read endpoints, and DPDP delete endpoints — with `build_candidate_store` wired into `Services`.

**Architecture:** The candidate store joins the `Services` dataclass (built by `build_candidate_store`, faked with in-memory SQLite in tests). `Report` gains an optional `candidate_id`; both report stores gain `for_candidate` / `delete_for_candidate` so DPDP candidate erasure also removes derived reports. `POST /candidates` orchestrates in the route (extract → ingest → `engine.evaluate` → stamp `report.candidate_id` → save): the LangGraph pipeline is NOT modified — it stays domain-agnostic and candidate-unaware; the API layer owns the linkage. PDF parsing moves from the ingest node's private helper into shared `app/core/pdf.py` so the route and node reuse one function.

**Tech Stack:** FastAPI (existing router/auth patterns), Pydantic v2 request/response models, SQLAlchemy store (S1.2), stdlib-sqlite report store (M1), pypdf, httpx + uvicorn for the smoke.

## Global Constraints

- TDD, fully offline tests; `pytest -q` green before merge (113 tests green today — never fewer; 137 expected after this plan).
- Every LLM step degrades deterministically: offline, `extract_profile` falls back to `method="heuristic"` and the depth-eval runs on rules (NullLLM). No test may require an API key.
- Advisory only: every report keeps `advisory=True`, `human_review_required=True`; nothing auto-rejects.
- DPDP: `DELETE /candidates/{id}` is a hard erase — candidate + resumes (raw text) + extractions (S1.2 cascade) **and** all reports linked to that `candidate_id` (reports contain claims derived from the resume).
- Config: no new settings needed; reuse `max_resume_chars`, `max_pdf_b64_chars`, `candidates_db_url`. Secrets stay in `.env` (`DEE_*`).
- DB: candidate tables are unchanged — **no new Alembic migration**. `reports.db` is stdlib-sqlite (not Alembic-managed); its new `candidate_id` column is added via guarded `ALTER TABLE` in the store constructor.
- All new mutating/reading endpoints sit on the existing key-gated `router` (auth comes free via its `Depends(require_api_key)`); `/healthz` and `/` stay open.
- `POST /evaluate` is untouched — it remains the ad-hoc, store-less evaluation path (its reports simply have `candidate_id=None`).
- Windows venv: run Python as `.resume\Scripts\python.exe`; tests as `.resume\Scripts\python.exe -m pytest -q` from repo root.
- Work on branch `s13-api-wiring` (create from `main` before Task 1).

**Existing interfaces this plan consumes (already on `main`):**

- `app.candidates.extractor.extract_profile(resume_text: str, *, llm: LLMClient, settings: Optional[Settings]) -> ExtractionResult` — never fails; `method` is `"llm"` or `"heuristic"`; applies contact hashes itself.
- `app.candidates.store.CandidateStore` — `ingest(result, resume_text) -> IngestOutcome` (`candidate_id`, `resume_id`, `extraction_id`, `resume_version`, `matched_existing`, `matched_on`, `duplicate_resume`), `get_candidate(id) -> Optional[CandidateSummary]` (`id`, `full_name`, `email_hash`, `phone_hash`, `created_at`, `updated_at`, `resume_count`), `latest_profile(id) -> Optional[CandidateProfile]`, `list_resumes(id) -> list[ResumeSummary]` (`id`, `version`, `text_sha256`, `created_at`), `delete_candidate(id) -> bool`, `delete_resume(id) -> bool`; plus `build_candidate_store(settings) -> CandidateStore` and `MatchedOn = Literal["email_hash", "phone_hash"]`.
- `app.graph.build.EvaluationEngine.evaluate(*, resume_text=None, resume_pdf_b64=None, github_url=None, portfolio_url=None, domain="genai") -> Report` — available as `request.app.state.engine`.
- `app.core.db.Base / make_engine / make_session_factory`; `tests/conftest.py` `settings` fixture + `make_services(...)`.
- Fixture `tests/fixtures/full_profile_resume.txt` (contains an email the heuristic extractor lifts — proven by `scripts/smoke_s12.py`).

---

### Task 1: `Report.candidate_id` + report-store candidate queries

**Files:**
- Modify: `app/schemas/report.py` (add one field to `Report`, ~line 87)
- Modify: `app/services/report_store.py` (Protocol + both stores)
- Test: `tests/test_report_candidate_link.py` (new file)

**Interfaces:**
- Consumes: existing `Report`, `SqliteReportStore`, `InMemoryReportStore`.
- Produces: `Report.candidate_id: Optional[str] = None`; `ReportStore` Protocol gains `for_candidate(candidate_id: str) -> list[Report]` (ascending `created_at`) and `delete_for_candidate(candidate_id: str) -> int` (returns number of reports removed; also removes their outcomes). Both implementations provide them. Tasks 4–6 rely on these exact names.

- [ ] **Step 1: Create the branch**

```powershell
git checkout main; git checkout -b s13-api-wiring
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_report_candidate_link.py`:

```python
"""Report ⇄ candidate linkage: schema field, store queries, legacy-DB upgrade."""

import sqlite3
from datetime import datetime, timedelta, timezone

from app.schemas.report import Report
from app.services.report_store import (
    InMemoryReportStore,
    OutcomeLabel,
    OutcomeRecord,
    SqliteReportStore,
)


def _store(tmp_path) -> SqliteReportStore:
    return SqliteReportStore(path=(tmp_path / "reports.db").as_posix())


def test_report_candidate_id_defaults_none():
    assert Report().candidate_id is None
    assert Report(candidate_id="cand-1").candidate_id == "cand-1"


def test_sqlite_roundtrip_and_for_candidate_ordering(tmp_path):
    store = _store(tmp_path)
    now = datetime.now(timezone.utc)
    newer = Report(candidate_id="cand-1", created_at=now)
    older = Report(candidate_id="cand-1", created_at=now - timedelta(hours=1))
    other = Report(candidate_id="cand-2")
    unlinked = Report()  # ad-hoc /evaluate report
    for r in (newer, older, other, unlinked):
        store.save(r)

    assert store.get(newer.id).candidate_id == "cand-1"
    listed = store.for_candidate("cand-1")
    assert [r.id for r in listed] == [older.id, newer.id]  # ascending created_at
    assert store.for_candidate("cand-nope") == []


def test_sqlite_delete_for_candidate_cascades_outcomes(tmp_path):
    store = _store(tmp_path)
    linked_a, linked_b, other = (
        Report(candidate_id="cand-1"),
        Report(candidate_id="cand-1"),
        Report(candidate_id="cand-2"),
    )
    for r in (linked_a, linked_b, other):
        store.save(r)
    store.add_outcome(
        OutcomeRecord(report_id=linked_a.id, outcome=OutcomeLabel.INCONCLUSIVE)
    )

    assert store.delete_for_candidate("cand-1") == 2
    assert store.get(linked_a.id) is None
    assert store.outcomes(linked_a.id) == []
    assert store.get(other.id) is not None
    assert store.delete_for_candidate("cand-1") == 0


def test_legacy_reports_db_upgraded_in_place(tmp_path):
    """Opening a pre-S1.3 reports.db must add the candidate_id column, not crash."""
    path = (tmp_path / "legacy.db").as_posix()
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE reports (id TEXT PRIMARY KEY, domain TEXT, created_at TEXT,"
        " depth_band TEXT, body TEXT NOT NULL)"
    )
    old = Report()
    conn.execute(
        "INSERT INTO reports VALUES (?, ?, ?, ?, ?)",
        (old.id, old.domain, old.created_at.isoformat(), old.depth_band.value,
         old.model_dump_json()),
    )
    conn.commit()
    conn.close()

    store = SqliteReportStore(path=path)
    assert store.get(old.id) is not None          # legacy rows still readable
    store.save(Report(candidate_id="cand-9"))     # new column usable
    assert [r.candidate_id for r in store.for_candidate("cand-9")] == ["cand-9"]


def test_inmemory_store_candidate_queries():
    store = InMemoryReportStore()
    linked, other = Report(candidate_id="cand-1"), Report(candidate_id="cand-2")
    store.save(linked)
    store.save(other)
    store.add_outcome(
        OutcomeRecord(report_id=linked.id, outcome=OutcomeLabel.INCONCLUSIVE)
    )
    assert [r.id for r in store.for_candidate("cand-1")] == [linked.id]
    assert store.delete_for_candidate("cand-1") == 1
    assert store.get(linked.id) is None
    assert store.outcomes(linked.id) == []
    assert store.get(other.id) is not None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.resume\Scripts\python.exe -m pytest tests/test_report_candidate_link.py -v`
Expected: FAIL — `Report().candidate_id` raises `AttributeError: 'Report' object has no attribute 'candidate_id'`; the store tests fail with `AttributeError: 'SqliteReportStore' object has no attribute 'for_candidate'` (and the in-memory equivalent).

- [ ] **Step 4: Add the schema field**

In `app/schemas/report.py`, inside `class Report`, directly under the `domain` field (line ~87):

```python
    # PI-1 linkage: which stored candidate this report evaluates. None for
    # ad-hoc POST /evaluate runs that never touched the candidate store.
    candidate_id: Optional[str] = None
```

- [ ] **Step 5: Extend the report stores**

In `app/services/report_store.py`:

**(a)** Add to the `ReportStore` Protocol (after `delete`):

```python
    def for_candidate(self, candidate_id: str) -> list[Report]: ...
    def delete_for_candidate(self, candidate_id: str) -> int: ...
```

**(b)** In `SqliteReportStore.__init__`, replace the `reports` CREATE TABLE statement and add the guarded upgrade + index (keep the `outcomes` DDL as is):

```python
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS reports ("
            " id TEXT PRIMARY KEY, domain TEXT, created_at TEXT,"
            " depth_band TEXT, candidate_id TEXT, body TEXT NOT NULL)"
        )
        # Pre-S1.3 DBs lack candidate_id; this store is stdlib-sqlite (not
        # Alembic-managed), so upgrade in place. Fresh DBs hit the except.
        try:
            self._conn.execute("ALTER TABLE reports ADD COLUMN candidate_id TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reports_candidate ON reports(candidate_id)"
        )
```

**(c)** Replace `SqliteReportStore.save` so the column is populated:

```python
    def save(self, report: Report) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO reports"
                " (id, domain, created_at, depth_band, candidate_id, body)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    report.id,
                    report.domain,
                    report.created_at.isoformat(),
                    report.depth_band.value,
                    report.candidate_id,
                    report.model_dump_json(),
                ),
            )
            self._conn.commit()
```

**(d)** Add to `SqliteReportStore` (after `delete`):

```python
    def for_candidate(self, candidate_id: str) -> list[Report]:
        rows = self._conn.execute(
            "SELECT body FROM reports WHERE candidate_id = ? ORDER BY created_at",
            (candidate_id,),
        ).fetchall()
        return [Report.model_validate_json(r[0]) for r in rows]

    def delete_for_candidate(self, candidate_id: str) -> int:
        """DPDP: erase every report derived from this candidate (+ outcomes)."""
        with self._lock:
            ids = [
                r[0]
                for r in self._conn.execute(
                    "SELECT id FROM reports WHERE candidate_id = ?", (candidate_id,)
                ).fetchall()
            ]
            if ids:
                marks = ",".join("?" * len(ids))
                self._conn.execute(
                    f"DELETE FROM outcomes WHERE report_id IN ({marks})", ids
                )
                self._conn.execute(
                    "DELETE FROM reports WHERE candidate_id = ?", (candidate_id,)
                )
            self._conn.commit()
            return len(ids)
```

**(e)** Add to `InMemoryReportStore` (after `delete`):

```python
    def for_candidate(self, candidate_id: str) -> list[Report]:
        linked = [r for r in self._reports.values() if r.candidate_id == candidate_id]
        return sorted(linked, key=lambda r: r.created_at)

    def delete_for_candidate(self, candidate_id: str) -> int:
        ids = [rid for rid, r in self._reports.items() if r.candidate_id == candidate_id]
        for rid in ids:
            self.delete(rid)
        return len(ids)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.resume\Scripts\python.exe -m pytest tests/test_report_candidate_link.py -v`
Expected: 5 passed.

Then the full suite: `.resume\Scripts\python.exe -m pytest -q`
Expected: 118 passed (113 + 5).

- [ ] **Step 7: Commit**

```powershell
git add app/schemas/report.py app/services/report_store.py tests/test_report_candidate_link.py
git commit -m "feat(reports): candidate_id linkage + per-candidate query/delete in report stores"
```

---

### Task 2: Shared PDF helper (`app/core/pdf.py`)

**Files:**
- Create: `app/core/pdf.py`
- Modify: `app/graph/nodes/ingest.py` (use the helper; delete its private copy)
- Test: `tests/test_pdf.py`

**Interfaces:**
- Consumes: pypdf (already a dependency — the ingest node uses it today).
- Produces: `pdf_b64_to_text(b64: str) -> str` (raises on malformed input; returns possibly-empty text). Task 4's route imports this.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pdf.py`:

```python
"""app/core/pdf.py — shared base64-PDF → text helper (route + ingest node)."""

import base64
import io

import pytest
from pypdf import PdfWriter

from app.core.pdf import pdf_b64_to_text


def _blank_pdf_b64() -> str:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return base64.b64encode(buf.getvalue()).decode()


def test_blank_pdf_yields_empty_text():
    assert pdf_b64_to_text(_blank_pdf_b64()).strip() == ""


def test_non_pdf_bytes_raise():
    junk_b64 = base64.b64encode(b"this is not a pdf").decode()
    with pytest.raises(Exception):
        pdf_b64_to_text(junk_b64)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.resume\Scripts\python.exe -m pytest tests/test_pdf.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.pdf'`.

- [ ] **Step 3: Implement the helper and refactor the ingest node**

Create `app/core/pdf.py`:

```python
"""Base64 PDF → plain text. Deterministic and LLM-free.

Shared by the graph's ingest node and the candidate intake route (S1.3), so
resume parsing behaves identically whether a resume enters via POST /evaluate
or POST /candidates. Raises on malformed input — callers decide how to degrade.
"""

from __future__ import annotations

import base64
import io


def pdf_b64_to_text(b64: str) -> str:
    from pypdf import PdfReader  # deferred: pypdf import is not free at startup

    data = base64.b64decode(b64)
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)
```

Replace `app/graph/nodes/ingest.py` in full (the only change: `_parse_pdf` is gone, the helper is imported):

```python
"""ingest — parse the resume to normalized text; capture shared links.

Deterministic and LLM-free. Accepts raw text or a base64 PDF. The optional
github_url / portfolio_url are first-party links the candidate chose to share.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.pdf import pdf_b64_to_text
from app.graph.state import EvaluationState
from app.services import Services


def make_ingest_node(services: Services):
    log = get_logger("node.ingest")

    async def ingest(state: EvaluationState) -> dict:
        text = state.raw_resume_text
        if not text and state.resume_pdf_b64:
            try:
                text = pdf_b64_to_text(state.resume_pdf_b64)
            except Exception as exc:  # malformed PDF: record, don't crash pipeline
                log.warning("pdf_parse_failed", error=str(exc))
                return {"errors": [f"pdf_parse_failed: {exc}"], "resume_text": ""}

        text = (text or "").strip()
        if not text:
            return {"errors": ["empty_resume"], "resume_text": ""}

        log.info("ingested", chars=len(text), has_github=bool(state.github_url))
        return {"resume_text": text}

    return ingest
```

- [ ] **Step 4: Run tests to verify they pass (helper + untouched ingest behavior)**

Run: `.resume\Scripts\python.exe -m pytest tests/test_pdf.py tests/test_ingest.py -v`
Expected: all pass (2 new + existing ingest tests).

Then: `.resume\Scripts\python.exe -m pytest -q`
Expected: 120 passed (118 + 2).

- [ ] **Step 5: Commit**

```powershell
git add app/core/pdf.py app/graph/nodes/ingest.py tests/test_pdf.py
git commit -m "refactor(core): shared pdf_b64_to_text helper for ingest node + candidate intake"
```

---

### Task 3: Wire `CandidateStore` into `Services` (+ test fakes)

**Files:**
- Modify: `app/services/__init__.py`
- Modify: `tests/conftest.py` (`make_services` builds an in-memory candidate store)
- Test: `tests/test_candidates_api.py` (new file, grows through Tasks 4–6)

**Interfaces:**
- Consumes: `CandidateStore`, `build_candidate_store` (S1.2); `Base`/`make_engine`/`make_session_factory` (`app/core/db.py`).
- Produces: `Services.candidates: CandidateStore` (field name `candidates`); `build_default_services` populates it via `build_candidate_store(settings)`; `tests.conftest.make_candidate_store() -> CandidateStore` (in-memory SQLite, `create_all` — tests only; production schema stays Alembic's job) and a `candidates=` keyword on `make_services`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_candidates_api.py`:

```python
"""Candidate API surface (S1.3) — offline: NullLLM ⇒ heuristic extraction,
rule-driven depth-eval. TestClient over injected in-memory services."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.candidates.store import CandidateStore
from app.main import create_app
from tests.conftest import make_services

RESUME = """Asha Rao
Email: asha.rao@example.com | Phone: +91 98765 43210

EXPERIENCE
- Senior ML Engineer, Acme AI (2021 - Present)
- Fine-tuned transformer models and built production RAG pipelines.

SKILLS
Python, PyTorch, LangChain
"""


@pytest.fixture
def api(settings, flywheel):
    """TestClient wired to fully offline services (NullLLM, in-memory stores)."""
    services = make_services(settings, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, services


# ── services wiring ───────────────────────────────────────────────────────────
def test_services_bundle_has_working_candidate_store(services):
    assert isinstance(services.candidates, CandidateStore)
    # Live schema behind it (create_all in the test fake), not a stub.
    assert services.candidates.get_candidate("no-such-id") is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.resume\Scripts\python.exe -m pytest tests/test_candidates_api.py -v`
Expected: FAIL — `AttributeError: 'Services' object has no attribute 'candidates'` (dataclass) or `TypeError: Services.__init__() ... 'candidates'`.

- [ ] **Step 3: Implement the wiring**

Replace `app/services/__init__.py` in full:

```python
"""Service container — the dependency bundle nodes close over.

Node factories receive a :class:`Services` instance (never global singletons),
so tests inject fakes (FakeLLM, InMemoryVectorStore, InMemoryFlywheel) trivially.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.candidates.store import CandidateStore, build_candidate_store
from app.core.config import Settings, get_settings
from app.services.flywheel import Flywheel, build_flywheel
from app.services.github import GitHubClient, GitHubService
from app.services.llm import LLMClient, build_llm
from app.services.report_store import ReportStore, build_report_store
from app.services.vectorstore import VectorStore, build_vectorstore


@dataclass
class Services:
    settings: Settings
    llm: LLMClient
    vectorstore: VectorStore
    github: GitHubService
    flywheel: Flywheel
    report_store: ReportStore
    candidates: CandidateStore


def build_default_services(settings: Optional[Settings] = None) -> Services:
    settings = settings or get_settings()
    return Services(
        settings=settings,
        llm=build_llm(settings),
        vectorstore=build_vectorstore(settings),
        github=GitHubClient(settings),
        flywheel=build_flywheel(settings),
        report_store=build_report_store(settings),
        candidates=build_candidate_store(settings),
    )


__all__ = ["Services", "build_default_services"]
```

In `tests/conftest.py`, add imports (top of file, with the other `app.` imports):

```python
from app.candidates.store import CandidateStore
from app.core.db import Base, make_engine, make_session_factory
```

Add a factory above `make_services`:

```python
def make_candidate_store() -> CandidateStore:
    """In-memory candidate store for tests. create_all is a TEST convenience;
    real deployments migrate via Alembic (S1.2 decision)."""
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return CandidateStore(make_session_factory(engine))
```

And extend `make_services`:

```python
def make_services(
    settings: Settings,
    *,
    llm: LLMClient | None = None,
    github: FakeGitHub | None = None,
    flywheel: InMemoryFlywheel | None = None,
    candidates: CandidateStore | None = None,
) -> Services:
    return Services(
        settings=settings,
        llm=llm or NullLLM(settings),
        vectorstore=InMemoryVectorStore(),
        github=github or FakeGitHub(),
        flywheel=flywheel or InMemoryFlywheel(),
        report_store=InMemoryReportStore(),
        candidates=candidates or make_candidate_store(),
    )
```

(`CandidateStore` is imported in `conftest.py`; `Base.metadata` already knows the candidate tables because `app.candidates.store` imports `app.candidates.models`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.resume\Scripts\python.exe -m pytest tests/test_candidates_api.py -q; .resume\Scripts\python.exe -m pytest -q`
Expected: 121 passed (120 + 1) — the whole existing suite must stay green (every `Services(...)` construction site is covered by `make_services`).

- [ ] **Step 5: Commit**

```powershell
git add app/services/__init__.py tests/conftest.py tests/test_candidates_api.py
git commit -m "feat(services): wire CandidateStore into Services bundle + test fakes"
```

---

### Task 4: `POST /candidates` — upload → extract → store → auto depth-eval

**Files:**
- Modify: `app/api/routes.py`
- Test: `tests/test_candidates_api.py` (append)

**Interfaces:**
- Consumes: `extract_profile` (S1.1), `services.candidates.ingest` (S1.2), `request.app.state.engine.evaluate` (existing), `pdf_b64_to_text` (Task 2), `Report.candidate_id` + `report_store.save` (Task 1).
- Produces: `POST /candidates` returning `CandidateCreateResponse` — fields `candidate_id: str`, `resume_id: str`, `resume_version: int`, `matched_existing: bool`, `matched_on: Optional[MatchedOn]`, `duplicate_resume: bool`, `extraction_method: str` (`"llm"`/`"heuristic"`), `report: Optional[Report]`. Tasks 5–6 and the smoke consume this shape.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_candidates_api.py`:

```python
# ── POST /candidates ──────────────────────────────────────────────────────────
def test_create_candidate_ingests_and_links_report(api):
    client, services = api
    resp = client.post("/candidates", json={"resume_text": RESUME})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["candidate_id"] and body["resume_id"]
    assert body["resume_version"] == 1
    assert body["matched_existing"] is False
    assert body["extraction_method"] == "heuristic"  # NullLLM abstains offline
    # Auto depth-eval ran, stayed advisory, and is linked to the candidate.
    assert body["report"] is not None
    assert body["report"]["candidate_id"] == body["candidate_id"]
    assert body["report"]["advisory"] is True
    assert body["report"]["human_review_required"] is True
    # Persisted through BOTH stores, not just echoed on the wire.
    assert services.candidates.get_candidate(body["candidate_id"]) is not None
    stored = services.report_store.get(body["report"]["id"])
    assert stored is not None and stored.candidate_id == body["candidate_id"]


def test_linked_report_retrievable_via_report_endpoint(api):
    client, _ = api
    body = client.post("/candidates", json={"resume_text": RESUME}).json()
    got = client.get(f"/report/{body['report']['id']}")
    assert got.status_code == 200
    assert got.json()["candidate_id"] == body["candidate_id"]


def test_same_text_is_duplicate_resume_same_candidate(api):
    client, _ = api
    first = client.post("/candidates", json={"resume_text": RESUME}).json()
    again = client.post("/candidates", json={"resume_text": RESUME}).json()
    assert again["candidate_id"] == first["candidate_id"]
    assert again["duplicate_resume"] is True
    assert again["resume_version"] == 1


def test_updated_text_matches_identity_as_new_version(api):
    client, _ = api
    first = client.post("/candidates", json={"resume_text": RESUME}).json()
    second = client.post(
        "/candidates", json={"resume_text": RESUME + "\n- AWS certified (2026)."}
    ).json()
    assert second["candidate_id"] == first["candidate_id"]
    assert second["matched_existing"] is True
    assert second["matched_on"] == "email_hash"
    assert second["resume_version"] == 2


def test_evaluate_false_skips_depth_eval(api):
    client, services = api
    body = client.post(
        "/candidates", json={"resume_text": RESUME, "evaluate": False}
    ).json()
    assert body["report"] is None
    assert services.report_store.for_candidate(body["candidate_id"]) == []
    # Ingestion still happened.
    assert services.candidates.get_candidate(body["candidate_id"]) is not None


def test_candidates_oversize_resume_422(api):
    client, services = api
    too_big = "x" * (services.settings.max_resume_chars + 1)
    resp = client.post("/candidates", json={"resume_text": too_big})
    assert resp.status_code == 422
    assert "max_resume_chars" in resp.text


def test_candidates_unknown_domain_422(api):
    client, _ = api
    resp = client.post(
        "/candidates", json={"resume_text": RESUME, "domain": "astrology"}
    )
    assert resp.status_code == 422
    assert "genai" in resp.text


def test_candidates_requires_a_source_422(api):
    client, _ = api
    assert client.post("/candidates", json={}).status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.resume\Scripts\python.exe -m pytest tests/test_candidates_api.py -v`
Expected: the wiring test passes; all 8 new tests FAIL. With no route registered FastAPI returns 404 everywhere, so the happy-path tests fail on `assert 404 == 200` and the error-path tests fail on `assert 404 == 422`.

- [ ] **Step 3: Implement the route**

In `app/api/routes.py`:

**(a)** Extend the imports:

```python
from datetime import datetime

from app.candidates.extractor import extract_profile
from app.candidates.schema import CandidateProfile
from app.candidates.store import MatchedOn, ResumeSummary
from app.core.pdf import pdf_b64_to_text
```

(`ResumeSummary` and `CandidateProfile`/`datetime` are used by Task 5's endpoints; adding them now avoids re-touching the import block — if your linter objects to briefly-unused imports, add them in Task 5 instead.)

**(b)** Add after the `evaluate` endpoint (keep `/evaluate` untouched):

```python
class CandidateCreateRequest(BaseModel):
    """Exactly one of resume_text / resume_pdf_b64 is required."""

    resume_text: str | None = None
    resume_pdf_b64: str | None = None
    domain: str = "genai"
    # Auto depth-eval is the default (S1.3 mandate); clients doing bulk import
    # can opt out and evaluate later.
    evaluate: bool = True

    @model_validator(mode="after")
    def _need_one_source(self) -> "CandidateCreateRequest":
        if not (self.resume_text or self.resume_pdf_b64):
            raise ValueError("Provide resume_text or resume_pdf_b64.")
        return self


class CandidateCreateResponse(BaseModel):
    """What one upload did (S1.2 IngestOutcome) + the advisory report, if run."""

    candidate_id: str
    resume_id: str
    resume_version: int
    matched_existing: bool
    matched_on: Optional[MatchedOn] = None
    duplicate_resume: bool
    extraction_method: str  # "llm" | "heuristic"
    report: Optional[Report] = None


@router.post("/candidates", response_model=CandidateCreateResponse)
async def create_candidate(
    req: CandidateCreateRequest, request: Request
) -> CandidateCreateResponse:
    """Upload → extract → store → (auto) depth-eval. The graph stays
    candidate-unaware: the API stamps report.candidate_id after evaluation."""
    services = _services(request)

    caps = services.settings
    if req.resume_text and len(req.resume_text) > caps.max_resume_chars:
        raise HTTPException(
            status_code=422,
            detail=f"resume_text exceeds max_resume_chars={caps.max_resume_chars}",
        )
    if req.resume_pdf_b64 and len(req.resume_pdf_b64) > caps.max_pdf_b64_chars:
        raise HTTPException(
            status_code=422,
            detail=f"resume_pdf_b64 exceeds max_pdf_b64_chars={caps.max_pdf_b64_chars}",
        )
    try:
        get_domain(req.domain)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    text = req.resume_text
    if not text and req.resume_pdf_b64:
        try:
            text = pdf_b64_to_text(req.resume_pdf_b64)
        except Exception as exc:
            raise HTTPException(
                status_code=422, detail=f"pdf_parse_failed: {exc}"
            ) from exc
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="empty_resume")

    result = await extract_profile(text, llm=services.llm, settings=services.settings)
    outcome = services.candidates.ingest(result, text)

    report: Optional[Report] = None
    if req.evaluate:
        report = await request.app.state.engine.evaluate(
            resume_text=text, domain=req.domain
        )
        report.candidate_id = outcome.candidate_id
        services.report_store.save(report)

    return CandidateCreateResponse(
        candidate_id=outcome.candidate_id,
        resume_id=outcome.resume_id,
        resume_version=outcome.resume_version,
        matched_existing=outcome.matched_existing,
        matched_on=outcome.matched_on,
        duplicate_resume=outcome.duplicate_resume,
        extraction_method=result.method,
        report=report,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.resume\Scripts\python.exe -m pytest tests/test_candidates_api.py -v`
Expected: 9 passed (1 wiring + 8 new).

Then: `.resume\Scripts\python.exe -m pytest -q`
Expected: 129 passed (121 + 8).

- [ ] **Step 5: Commit**

```powershell
git add app/api/routes.py tests/test_candidates_api.py
git commit -m "feat(api): POST /candidates - upload, extract, store, auto depth-eval"
```

---

### Task 5: Candidate read endpoints

**Files:**
- Modify: `app/api/routes.py`
- Test: `tests/test_candidates_api.py` (append)

**Interfaces:**
- Consumes: `services.candidates.get_candidate` / `latest_profile` / `list_resumes`; `services.report_store.for_candidate` (Task 1); `ResumeSummary`, `CandidateProfile` (imported in Task 4).
- Produces: `GET /candidates/{candidate_id}` → `CandidateDetail` (`id`, `full_name`, `email_hash`, `phone_hash`, `created_at`, `updated_at`, `resume_count`, `latest_profile: Optional[CandidateProfile]`); `GET /candidates/{candidate_id}/resumes` → `CandidateResumesResponse` (`candidate_id`, `resumes: list[ResumeSummary]`); `GET /candidates/{candidate_id}/reports` → `list[Report]` (ascending `created_at`). All 404 on unknown candidate.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_candidates_api.py`:

```python
# ── candidate reads ───────────────────────────────────────────────────────────
def test_candidate_detail_includes_latest_profile(api):
    client, _ = api
    cid = client.post(
        "/candidates", json={"resume_text": RESUME, "evaluate": False}
    ).json()["candidate_id"]
    resp = client.get(f"/candidates/{cid}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["id"] == cid
    assert detail["resume_count"] == 1
    assert detail["email_hash"]
    assert detail["latest_profile"] is not None
    assert detail["latest_profile"]["contact"]["email_hash"] == detail["email_hash"]


def test_candidate_detail_404(api):
    client, _ = api
    assert client.get("/candidates/no-such-id").status_code == 404


def test_list_candidate_resumes(api):
    client, _ = api
    cid = client.post(
        "/candidates", json={"resume_text": RESUME, "evaluate": False}
    ).json()["candidate_id"]
    client.post(
        "/candidates",
        json={"resume_text": RESUME + "\n- New project shipped.", "evaluate": False},
    )
    resp = client.get(f"/candidates/{cid}/resumes")
    assert resp.status_code == 200
    body = resp.json()
    assert body["candidate_id"] == cid
    assert [r["version"] for r in body["resumes"]] == [1, 2]
    assert client.get("/candidates/no-such-id/resumes").status_code == 404


def test_list_candidate_reports(api):
    client, _ = api
    first = client.post("/candidates", json={"resume_text": RESUME}).json()
    cid = first["candidate_id"]
    resp = client.get(f"/candidates/{cid}/reports")
    assert resp.status_code == 200
    reports = resp.json()
    assert len(reports) == 1
    assert reports[0]["id"] == first["report"]["id"]
    assert reports[0]["candidate_id"] == cid
    assert client.get("/candidates/no-such-id/reports").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.resume\Scripts\python.exe -m pytest tests/test_candidates_api.py -v`
Expected: previous 9 pass; `test_candidate_detail_includes_latest_profile`, `test_list_candidate_resumes`, and `test_list_candidate_reports` FAIL with `assert 404 == 200` (routes missing). `test_candidate_detail_404` passes trivially now (404 either way); it earns its keep after Step 3 by proving the 404 is a lookup miss, not a missing route.

- [ ] **Step 3: Implement the endpoints**

Add to `app/api/routes.py` after `create_candidate`:

```python
class CandidateDetail(BaseModel):
    """Store summary + the newest extracted profile (hashes only — no raw PII)."""

    id: str
    full_name: Optional[str] = None
    email_hash: Optional[str] = None
    phone_hash: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    resume_count: int = 0
    latest_profile: Optional[CandidateProfile] = None


class CandidateResumesResponse(BaseModel):
    candidate_id: str
    resumes: list[ResumeSummary]


@router.get("/candidates/{candidate_id}", response_model=CandidateDetail)
async def get_candidate(candidate_id: str, request: Request) -> CandidateDetail:
    services = _services(request)
    summary = services.candidates.get_candidate(candidate_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    return CandidateDetail(
        **summary.model_dump(),
        latest_profile=services.candidates.latest_profile(candidate_id),
    )


@router.get("/candidates/{candidate_id}/resumes", response_model=CandidateResumesResponse)
async def list_candidate_resumes(
    candidate_id: str, request: Request
) -> CandidateResumesResponse:
    services = _services(request)
    if services.candidates.get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    return CandidateResumesResponse(
        candidate_id=candidate_id,
        resumes=services.candidates.list_resumes(candidate_id),
    )


@router.get("/candidates/{candidate_id}/reports", response_model=list[Report])
async def list_candidate_reports(candidate_id: str, request: Request) -> list[Report]:
    services = _services(request)
    if services.candidates.get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    return services.report_store.for_candidate(candidate_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.resume\Scripts\python.exe -m pytest tests/test_candidates_api.py -v`
Expected: 13 passed.

Then: `.resume\Scripts\python.exe -m pytest -q`
Expected: 133 passed (129 + 4).

- [ ] **Step 5: Commit**

```powershell
git add app/api/routes.py tests/test_candidates_api.py
git commit -m "feat(api): candidate detail, resume list, and per-candidate report list"
```

---

### Task 6: DPDP delete endpoints + root endpoint listing

**Files:**
- Modify: `app/api/routes.py`
- Modify: `app/main.py` (root `/` endpoints list)
- Test: `tests/test_candidates_api.py` (append)

**Interfaces:**
- Consumes: `services.candidates.delete_candidate` / `delete_resume` / `list_resumes` (S1.2); `services.report_store.delete_for_candidate` (Task 1).
- Produces: `DELETE /candidates/{candidate_id}` → `{"candidate_id", "deleted": true, "reports_deleted": int}` (erases candidate cascade + linked reports); `DELETE /candidates/{candidate_id}/resumes/{resume_id}` → `{"resume_id", "deleted": true}` (ownership-checked; candidate row survives). Both 404 on unknown ids.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_candidates_api.py`:

```python
# ── DPDP deletes ──────────────────────────────────────────────────────────────
RESUME_B = """Ravi Kumar
Email: ravi.kumar@example.com

SKILLS
Java, Spring
"""


def test_delete_candidate_erases_store_and_reports(api):
    client, services = api
    body = client.post("/candidates", json={"resume_text": RESUME}).json()
    cid, report_id = body["candidate_id"], body["report"]["id"]

    resp = client.delete(f"/candidates/{cid}")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["deleted"] is True
    assert payload["reports_deleted"] == 1
    # Everything derived from the resume is gone (DPDP erasure).
    assert client.get(f"/candidates/{cid}").status_code == 404
    assert client.get(f"/report/{report_id}").status_code == 404
    assert services.candidates.get_candidate(cid) is None


def test_delete_missing_candidate_404(api):
    client, _ = api
    assert client.delete("/candidates/no-such-id").status_code == 404


def test_delete_one_resume_keeps_candidate(api):
    client, _ = api
    client.post("/candidates", json={"resume_text": RESUME, "evaluate": False})
    second = client.post(
        "/candidates",
        json={"resume_text": RESUME + "\n- Extra line.", "evaluate": False},
    ).json()
    cid = second["candidate_id"]

    resp = client.delete(f"/candidates/{cid}/resumes/{second['resume_id']}")
    assert resp.status_code == 200 and resp.json()["deleted"] is True
    versions = [
        r["version"] for r in client.get(f"/candidates/{cid}/resumes").json()["resumes"]
    ]
    assert versions == [1]
    assert client.get(f"/candidates/{cid}").status_code == 200


def test_delete_resume_of_another_candidate_404(api):
    client, _ = api
    a = client.post("/candidates", json={"resume_text": RESUME, "evaluate": False}).json()
    b = client.post("/candidates", json={"resume_text": RESUME_B, "evaluate": False}).json()
    assert a["candidate_id"] != b["candidate_id"]  # distinct contacts ⇒ distinct people
    # A's resume under B's candidate id must not delete anything.
    resp = client.delete(f"/candidates/{b['candidate_id']}/resumes/{a['resume_id']}")
    assert resp.status_code == 404
    assert client.get(f"/candidates/{a['candidate_id']}/resumes").json()["resumes"] != []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.resume\Scripts\python.exe -m pytest tests/test_candidates_api.py -v`
Expected: previous 13 pass; `test_delete_candidate_erases_store_and_reports` and `test_delete_one_resume_keeps_candidate` FAIL with `assert 405 == 200` (no DELETE handler ⇒ FastAPI 405 on an existing GET path). The two 404 tests may pass trivially pre-implementation — the failing pair drives the code.

- [ ] **Step 3: Implement the delete endpoints**

Add to `app/api/routes.py` after `list_candidate_reports`:

```python
@router.delete("/candidates/{candidate_id}")
async def delete_candidate(candidate_id: str, request: Request) -> dict:
    """DPDP erasure: candidate + resumes (raw text) + extractions + all reports
    derived from them. Hard delete — there is nothing to un-delete."""
    services = _services(request)
    if services.candidates.get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    reports_deleted = services.report_store.delete_for_candidate(candidate_id)
    services.candidates.delete_candidate(candidate_id)
    return {
        "candidate_id": candidate_id,
        "deleted": True,
        "reports_deleted": reports_deleted,
    }


@router.delete("/candidates/{candidate_id}/resumes/{resume_id}")
async def delete_candidate_resume(
    candidate_id: str, resume_id: str, request: Request
) -> dict:
    """DPDP erasure of ONE resume version (+ its extractions). The candidate
    row and other versions stay; ownership is checked so one candidate's URL
    can never erase another's data."""
    services = _services(request)
    if services.candidates.get_candidate(candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    owned = {r.id for r in services.candidates.list_resumes(candidate_id)}
    if resume_id not in owned:
        raise HTTPException(status_code=404, detail="resume not found for candidate")
    services.candidates.delete_resume(resume_id)
    return {"resume_id": resume_id, "deleted": True}
```

In `app/main.py`, replace the `"endpoints"` list in the root handler:

```python
            "endpoints": [
                "POST /evaluate",
                "POST /candidates",
                "GET /candidates/{id}",
                "GET /candidates/{id}/resumes",
                "GET /candidates/{id}/reports",
                "DELETE /candidates/{id}",
                "DELETE /candidates/{id}/resumes/{resume_id}",
                "GET /report/{id}",
                "POST /report/{id}/outcome",
                "GET /report/{id}/outcomes",
                "GET /domains",
                "GET /healthz",
            ],
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.resume\Scripts\python.exe -m pytest tests/test_candidates_api.py -v`
Expected: 17 passed.

Then: `.resume\Scripts\python.exe -m pytest -q`
Expected: 137 passed (133 + 4).

- [ ] **Step 5: Commit**

```powershell
git add app/api/routes.py app/main.py tests/test_candidates_api.py
git commit -m "feat(api): DPDP delete endpoints for candidates and resume versions"
```

---

### Task 7: Smoke script (uvicorn + HTTP) + roadmap close-out

**Files:**
- Create: `scripts/smoke_s13.py`
- Modify: `docs/ROADMAP.md` (status board `[~]`→`[x]` for S1.3, current state, session log)

**Interfaces:**
- Consumes: the full HTTP surface built above; Alembic env (S1.2); fixture `tests/fixtures/full_profile_resume.txt`.
- Produces: `python scripts/smoke_s13.py` exiting 0 with `SMOKE OK` — with a live key (LLM extraction) AND key-less (heuristic floor). This is the per-sprint uvicorn smoke the conventions require.

- [ ] **Step 1: Write the smoke script**

Create `scripts/smoke_s13.py`:

```python
"""S1.3 smoke: the real HTTP surface end to end.

Migrates a scratch candidate DB with Alembic, boots uvicorn with env-overridden
store paths, then drives: POST /candidates (auto depth-eval) → identity match on
re-upload → candidate/resume/report reads → DPDP resume + candidate deletes →
verifies linked reports are erased. Works with a live key (LLM extraction) and
without one (heuristic floor + rule-driven eval). Run from the repo root:
    python scripts/smoke_s13.py
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

FIXTURE = Path("tests/fixtures/full_profile_resume.txt")
PORT = 8013
BASE = f"http://127.0.0.1:{PORT}"


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s13.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    env = os.environ.copy()
    env.update(
        {
            "DEE_CANDIDATES_DB_URL": url,
            "DEE_REPORT_DB_PATH": (scratch / "reports.db").as_posix(),
            "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
            # Chroma init can hang on some machines; the smoke stays bounded.
            "DEE_VECTORSTORE_BACKEND": "memory",
        }
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        env=env,
    )
    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(180, connect=5)) as c:
            for _ in range(60):
                try:
                    if c.get("/healthz").status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.5)
            else:
                print("FAIL server never became healthy")
                return 1

            text = FIXTURE.read_text(encoding="utf-8")
            first = c.post("/candidates", json={"resume_text": text}).json()
            cid = first["candidate_id"]
            print(
                f"POST /candidates #1 [{first['extraction_method']}]: "
                f"candidate={cid[:8]} v{first['resume_version']} "
                f"report={first['report']['id']}"
            )

            second = c.post(
                "/candidates",
                json={"resume_text": text + "\n\nUpdate: AWS certification added."},
            ).json()
            print(
                f"POST /candidates #2: matched={second['matched_existing']} "
                f"on={second['matched_on']} v{second['resume_version']}"
            )

            detail = c.get(f"/candidates/{cid}").json()
            resumes = c.get(f"/candidates/{cid}/resumes").json()
            reports = c.get(f"/candidates/{cid}/reports").json()

            del_resume = c.delete(
                f"/candidates/{cid}/resumes/{second['resume_id']}"
            )
            del_cand = c.delete(f"/candidates/{cid}")
            report_after = c.get(f"/report/{first['report']['id']}")
            cand_after = c.get(f"/candidates/{cid}")

        checks = {
            "upload created candidate + advisory report": bool(cid)
            and first["report"]["advisory"] is True
            and first["report"]["human_review_required"] is True,
            "report linked to candidate": first["report"]["candidate_id"] == cid,
            "re-upload matched identity": second["candidate_id"] == cid
            and second["matched_existing"] is True,
            "re-upload became resume v2": second["resume_version"] == 2,
            "detail exposes latest profile": detail["latest_profile"] is not None,
            "two resume versions listed": [
                r["version"] for r in resumes["resumes"]
            ] == [1, 2],
            "both reports listed for candidate": len(reports) == 2,
            "DPDP resume delete ok": del_resume.status_code == 200,
            "DPDP candidate delete erased reports": del_cand.status_code == 200
            and del_cand.json()["reports_deleted"] == 2,
            "linked report 404 after erasure": report_after.status_code == 404,
            "candidate 404 after erasure": cand_after.status_code == 404,
        }
        failed = [name for name, ok in checks.items() if not ok]
        for name, ok in checks.items():
            print(f"  {'OK  ' if ok else 'FAIL'} {name}")
        if failed:
            return 1
        print("\nSMOKE OK")
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=15)


if __name__ == "__main__":
    sys.exit(main())
```

Note: `reports_deleted == 2` because BOTH uploads auto-evaluate (the second is a new resume version of the same candidate, so its report also carries `cid`). If it comes back 1, the second POST's report linkage broke — investigate, don't loosen the check.

- [ ] **Step 2: Run the smoke offline (deterministic floor)**

Run (PowerShell, repo root):

```powershell
$env:DEE_OPENROUTER_API_KEY = ""; .resume\Scripts\python.exe scripts/smoke_s13.py
```

Expected: `[heuristic]` on the first POST line, all checks `OK`, exit 0 with `SMOKE OK`.
Afterwards clear the override so later shells aren't key-less: `Remove-Item Env:DEE_OPENROUTER_API_KEY`.

- [ ] **Step 3: Run the smoke live (if a key is configured in .env)**

Run: `.resume\Scripts\python.exe scripts/smoke_s13.py`
Expected: `[llm]` extraction (or `[heuristic]` if no key), all checks `OK`, `SMOKE OK`. The live run takes longer — two full depth-evals go through OpenRouter.

- [ ] **Step 4: Full suite one last time**

Run: `.resume\Scripts\python.exe -m pytest -q`
Expected: 137 passed, 0 failed.

- [ ] **Step 5: Update `docs/ROADMAP.md`**

- Status board: `[~] S1.3` → `[x] S1.3`, `[ ] S1.4` → `[~] S1.4`.
- "Current state": current sprint → S1.4 (India normalization); next action → write S1.4 plan (skill taxonomy, degree/CGPA normalizer, institution + employer canonicalization, city/notice-period); last-session line summarizing S1.3 (branch, endpoints added, `Services.candidates`, `Report.candidate_id`, test count 137, smoke result).
- Session log: append a dated S1.3 entry.

- [ ] **Step 6: Commit**

```powershell
git add scripts/smoke_s13.py docs/ROADMAP.md
git commit -m "chore: S1.3 smoke script + roadmap close-out"
```

---

## Execution notes

- Run everything from the repo root; the venv is `.resume\Scripts\python.exe` (Windows).
- The LangGraph pipeline, domains, and `/evaluate` are intentionally untouched — if a task seems to need a graph change, stop and re-read the architecture note.
- Each `POST /candidates` with `evaluate=true` runs a full depth-eval (LLM calls when a key is present). Tests always run offline (NullLLM); only the optional live smoke spends tokens.
- Merge flow (matches S1.1/S1.2): after all tasks green, merge `s13-api-wiring` into `main` per superpowers:finishing-a-development-branch.
