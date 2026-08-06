# S8.4 Phase A — Upload Ownership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every resume and report an owning organization, expose the fraud-screen path on the org plane scoped to what that org uploaded, and make the scoping structural rather than remembered.

**Architecture:** Ownership is a property of the *upload*, not the person — `resumes.org_id` and `reports.org_id`, nullable, `ON DELETE SET NULL`. Candidates stay global and deduplicated. Org-plane reads go through one scoped facade (`app/screening/scope.py`) whose every method takes `org_id` first; a guard test in the `tests/test_route_table_guard.py` family fails the build if an org handler reaches an unscoped read. Resume-farm counterparty identity is stripped by one shared projection used by every org-facing reader.

**Tech Stack:** Python 3.13 · FastAPI 0.138 · SQLAlchemy 2.x + Alembic on SQLite (Postgres-shaped) · Pydantic v2 · pytest.

**Spec:** `docs/superpowers/specs/2026-08-05-s84-ui-integration-surface-design.md` §0.1, §0.2, §0.4, §2.1, §3.

## Global Constraints

- **TDD, fully offline.** `NullLLM` / fakes from `tests/conftest.py`. No network, no API key. `pytest -q` green before merge.
- **Advisory only.** Nothing here auto-rejects, auto-shortlists or hides a candidate.
- **DPDP.** No new `ConsentPurpose` — ownership narrows disclosure, it does not create one. Existing consent gates and audit behaviour are unchanged.
- **Config:** tunables in `config.yaml`, secrets only in `.env` under `DEE_*`. **Phase A adds no config knobs.**
- **DB:** SQLAlchemy + Alembic on SQLite, written Postgres-shaped. SQLite needs `batch_alter_table` to add a column with a foreign key.
- **The admin plane is not touched.** Every existing admin route keeps its current path, behaviour and cross-tenant reach. Any test asserting admin behaviour must still pass unmodified.
- **404, never 403,** for a resource owned by another org — indistinguishable from absent.
- Branch: `s84a-upload-ownership`. Commit after every task.
- **No `Co-Authored-By` trailer in commit messages.**

---

## File Structure

**Created:**
- `alembic/versions/0018_upload_ownership.py` — the two columns.
- `app/screening/__init__.py` — new package (Phase B extends it).
- `app/screening/projection.py` — the single redaction. Pure; no I/O.
- `app/screening/scope.py` — `OrgScopedReads`, the facade. The only door org handlers use.
- `tests/test_upload_ownership.py` — migration + `SET NULL` semantics.
- `tests/test_screening_projection.py` — redaction, pure.
- `tests/test_screening_scope.py` — facade isolation.
- `tests/test_screening_api.py` — the three org routes over HTTP.
- `tests/test_org_scope_guard.py` — the structural guard.
- `tests/test_auth_org_name_taken.py` — the lockout fix.
- `scripts/smoke_s84a.py` — key-less HTTP smoke.
- `TENANCY.md` — root doc, peer of `AUTH.md` / `PORTAL.md`.

**Modified:**
- `app/candidates/models.py` — `ResumeRow.org_id`.
- `app/reports/models.py` — `ReportRow.org_id`.
- `app/candidates/store.py` — `ingest(..., org_id=None)`; `org_owns_candidate`.
- `app/reports/store.py` — `save(..., org_id=None)`; `get_for_org`; `for_candidate_and_org`; Protocol updated.
- `app/schemas/fabrication.py` — `ResumeMatch` identity fields become optional.
- `app/api/routes.py` — three org routes; the signup 409; the verify fork.
- `app/auth/store.py` — `organization_name_exists`.
- `app/auth/service.py` — `RegistrationRefused`, raised distinctly.
- `app/core/services.py` — wire `screening_scope` into `Services`.

---

## Task 1: Ownership columns + migration `0018_upload_ownership`

**Files:**
- Modify: `app/candidates/models.py:57-77` (`ResumeRow`)
- Modify: `app/reports/models.py:26-42` (`ReportRow`)
- Create: `alembic/versions/0018_upload_ownership.py`
- Test: `tests/test_upload_ownership.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ResumeRow.org_id: Mapped[Optional[str]]`, `ReportRow.org_id: Mapped[Optional[str]]`. Both nullable, FK to `organizations.id` with `ondelete="SET NULL"`, both indexed.

**Context you need:** `ON DELETE SET NULL` is the load-bearing choice and the reason this task's test exists. An organization offboarding must **not** destroy a candidate's resume — that is the *person's* data, and the only cascade permitted to delete it is the candidate's own erasure (`resumes.candidate_id → candidates.id ON DELETE CASCADE`, which already exists). A `CASCADE` typo here would be silent until the first org is deleted. SQLite enforces FKs in this repo (`app/core/db.py:32` sets `PRAGMA foreign_keys=ON` per connection), so the test below is real.

- [ ] **Step 1: Write the failing test**

Create `tests/test_upload_ownership.py`:

```python
"""S8.4 Phase A: ownership is a property of the UPLOAD, not the person.

The SET NULL test is the point of this file. An org offboarding must leave the
candidate and their resume intact and merely UNOWNED -- a CASCADE typo would be
silent until the first organization is ever deleted.
"""

from __future__ import annotations

from sqlalchemy import select

from app.candidates.models import ResumeRow
from app.reports.models import ReportRow


def test_resume_and_report_carry_a_nullable_org_id():
    assert ResumeRow.__table__.c.org_id.nullable is True
    assert ReportRow.__table__.c.org_id.nullable is True


def test_org_id_foreign_keys_are_set_null_not_cascade():
    """CASCADE here would delete a person's resume when an org offboards."""
    for table in (ResumeRow.__table__, ReportRow.__table__):
        fk = next(fk for fk in table.c.org_id.foreign_keys)
        assert fk.column.table.name == "organizations"
        assert fk.ondelete == "SET NULL", (
            f"{table.name}.org_id must be SET NULL -- a person's resume does not "
            f"die with the organization that happened to upload it"
        )


def test_deleting_an_org_leaves_the_resume_intact_and_unowned(services):
    """The behaviour the ondelete assertion above is standing in for."""
    from app.candidates.schema import (
        CandidateProfile, ContactInfo, ExtractedStr, ExtractionResult,
    )

    org = services.ledger.create_organization("Acme Staffing")
    outcome = services.candidates.ingest(
        ExtractionResult(
            profile=CandidateProfile(
                full_name=ExtractedStr(value="Priya"),
                contact=ContactInfo(email=ExtractedStr(value="priya@x.io")),
            ),
            method="heuristic",
        ),
        resume_text="priya resume text",
        org_id=org.id,
    )

    with services.candidates._session_factory() as s:
        row = s.get(ResumeRow, outcome.resume_id)
        assert row.org_id == org.id

    # Offboard the organization.
    with services.candidates._session_factory() as s:
        from app.ledger.models import OrganizationRow
        s.delete(s.get(OrganizationRow, org.id))
        s.commit()

    with services.candidates._session_factory() as s:
        row = s.get(ResumeRow, outcome.resume_id)
        assert row is not None, "the person's resume must survive the org"
        assert row.org_id is None, "and must read as unowned"
        assert s.execute(
            select(ResumeRow).where(ResumeRow.candidate_id == outcome.candidate_id)
        ).scalars().first() is not None
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_upload_ownership.py -v`
Expected: FAIL — `AttributeError` / no attribute `org_id` on the table columns.

- [ ] **Step 3: Add the ORM columns**

In `app/candidates/models.py`, inside `class ResumeRow`, after the `text_sha256` column:

```python
    # S8.4: which organization UPLOADED this resume. Nullable -- every
    # pre-S8.4 row and every admin-plane upload is legitimately unowned.
    # SET NULL, never CASCADE: an org offboarding must not destroy a person's
    # resume. The only cascade permitted to delete it is the candidate's own
    # erasure, one column up.
    org_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
```

In `app/reports/models.py`, inside `class ReportRow`, after `candidate_id`:

```python
    # S8.4: which organization COMMISSIONED this evaluation. Same nullable +
    # SET NULL reasoning as resumes.org_id -- and note the contrast with
    # candidate_id directly above, which CASCADES because an attached report
    # is the subject's personal data.
    org_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
```

- [ ] **Step 4: Write the migration**

Create `alembic/versions/0018_upload_ownership.py`:

```python
"""upload ownership: resumes.org_id + reports.org_id (S8.4 Phase A)

Revision ID: 0018_upload_ownership
Revises: 0017_auth_identity
Create Date: 2026-08-06

Nothing in the schema has ever recorded WHICH organization uploaded a resume or
commissioned an evaluation, which was fine while the wedge was operator-run and
is not fine the moment two staffing agencies screen the same candidate.

Ownership is a property of the UPLOAD, not of the person: candidates stay global
and deduplicated (S1.1 identity resolution), so cross-corpus near-duplicate
detection still works, while each upload carries its own owner.

NULLABLE because every existing row is legitimately unowned, and so is every
admin-plane upload. No data migration invents an owner that never existed.

ON DELETE SET NULL, deliberately NOT CASCADE: an organization offboarding must
not destroy a candidate's resume. That resume is the PERSON's data; the only
cascade permitted to delete it is the candidate's own erasure.

batch_alter_table because SQLite cannot ADD COLUMN with a foreign key in place.
On Postgres batch mode is a plain ALTER.
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_upload_ownership"
down_revision = "0017_auth_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("resumes") as batch:
        batch.add_column(sa.Column("org_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_resumes_org_id", "organizations", ["org_id"], ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_resumes_org_id", "resumes", ["org_id"])

    with op.batch_alter_table("reports") as batch:
        batch.add_column(sa.Column("org_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_reports_org_id", "organizations", ["org_id"], ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_reports_org_id", "reports", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_reports_org_id", table_name="reports")
    with op.batch_alter_table("reports") as batch:
        batch.drop_constraint("fk_reports_org_id", type_="foreignkey")
        batch.drop_column("org_id")

    op.drop_index("ix_resumes_org_id", table_name="resumes")
    with op.batch_alter_table("resumes") as batch:
        batch.drop_constraint("fk_resumes_org_id", type_="foreignkey")
        batch.drop_column("org_id")
```

- [ ] **Step 5: Add the `org_id` parameter to `ingest` so the test can run**

In `app/candidates/store.py`, change the `ingest` signature at line 87 and the `ResumeRow` construction at line 116:

```python
    def ingest(
        self,
        result: ExtractionResult,
        resume_text: str,
        *,
        org_id: Optional[str] = None,
    ) -> IngestOutcome:
```

```python
                resume = ResumeRow(
                    candidate_id=cand.id,
                    version=(latest or 0) + 1,
                    raw_text=resume_text,
                    text_sha256=sha,
                    org_id=org_id,
                )
```

Default `None` keeps every existing caller working unchanged — that is deliberate, not laziness: the admin plane genuinely has no owner to supply.

- [ ] **Step 6: Run the ownership tests and the migration guards**

Run: `pytest tests/test_upload_ownership.py tests/test_migrations.py -v`
Expected: PASS. The pre-existing drift / index / FK-ondelete / nullability guards in `tests/test_migrations.py` compare the migrated schema against the ORM metadata and now cover both new columns for free — if the migration and the models disagree, they fail here.

- [ ] **Step 7: Run the full suite**

Run: `pytest -q`
Expected: PASS, count unchanged from baseline plus the 3 new tests. Nothing stamps ownership yet, so no behaviour has changed.

- [ ] **Step 8: Commit**

```bash
git add app/candidates/models.py app/reports/models.py app/candidates/store.py \
        alembic/versions/0018_upload_ownership.py tests/test_upload_ownership.py
git commit -m "feat(s84a): resumes.org_id + reports.org_id, nullable and SET NULL

Ownership is a property of the UPLOAD, not of the person. SET NULL rather
than CASCADE because an org offboarding must not destroy a candidate's
resume -- the only cascade permitted to delete it is the candidate's own
erasure. Schema + ingest parameter only; nothing stamps an owner yet."
```

---

## Task 2: Stamp ownership on the report write path

**Files:**
- Modify: `app/reports/store.py:39-45` (Protocol), `:54-75` (`save`)
- Test: `tests/test_upload_ownership.py` (append)

**Interfaces:**
- Consumes: `ReportRow.org_id` from Task 1.
- Produces: `ReportStore.save(self, report: Report, *, org_id: Optional[str] = None) -> None`.

**Context you need:** `org_id` is a *storage* fact, not part of the `Report` domain contract — it must never appear in the serialized `report.body` that clients receive. So it is a keyword argument on `save`, not a field on `Report`. Note `save` is an upsert; a re-save without `org_id` must not silently un-own an existing report.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_upload_ownership.py`:

```python
def test_report_save_stamps_org_and_keeps_it_out_of_the_body(services):
    from datetime import datetime, timezone
    from app.schemas.report import Report

    org = services.ledger.create_organization("Beta Staffing")
    report = Report(id="rep-1", domain="genai", created_at=datetime.now(timezone.utc))
    services.report_store.save(report, org_id=org.id)

    with services.candidates._session_factory() as s:
        row = s.get(ReportRow, "rep-1")
        assert row.org_id == org.id
        assert "org_id" not in row.body, "ownership is storage, not the report contract"

    assert services.report_store.get("rep-1").model_dump().get("org_id") is None


def test_resaving_without_an_org_does_not_un_own_a_report(services):
    """save() is an upsert; a later save from another path must not orphan it."""
    from datetime import datetime, timezone
    from app.schemas.report import Report

    org = services.ledger.create_organization("Gamma Staffing")
    report = Report(id="rep-2", domain="genai", created_at=datetime.now(timezone.utc))
    services.report_store.save(report, org_id=org.id)
    services.report_store.save(report)  # no org_id supplied

    with services.candidates._session_factory() as s:
        assert s.get(ReportRow, "rep-2").org_id == org.id
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_upload_ownership.py -k "stamps_org or un_own" -v`
Expected: FAIL — `save() got an unexpected keyword argument 'org_id'`.

- [ ] **Step 3: Update the Protocol and `save`**

In `app/reports/store.py`, change the Protocol line 40:

```python
    def save(self, report: Report, *, org_id: Optional[str] = None) -> None: ...
```

And `SqlReportStore.save`:

```python
    def save(self, report: Report, *, org_id: Optional[str] = None) -> None:
        """Upsert. (The old store used ``INSERT OR REPLACE``, which Postgres
        does not have -- the SQL had to be rewritten whatever we did here.)

        ``org_id`` is a STORAGE fact and never enters ``body``: the Report
        contract is what a client receives, and ownership is not part of it.
        Supplying no ``org_id`` on a re-save LEAVES the existing owner alone --
        un-owning a report by forgetting an argument would be a silent
        cross-tenant leak in the making.
        """
        with self._session_factory() as s:
            row = s.get(ReportRow, report.id)
            if row is None:
                row = ReportRow(id=report.id)
                s.add(row)
            row.domain = report.domain
            row.depth_band = report.depth_band.value
            row.candidate_id = report.candidate_id
            if org_id is not None:
                row.org_id = org_id
            row.body = report.model_dump(mode="json")
            row.created_at = as_utc(report.created_at)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                if report.candidate_id is None:
                    raise
                # The only FK on this row is the candidate, so an integrity
                # failure here means the subject was erased mid-flight.
                raise SubjectErasedError(report.candidate_id) from None
```

Note the `IntegrityError` comment is now slightly stale — there are two FKs. Update it:

```python
                # ``org_id`` is SET NULL and cannot fail an insert, so an
                # integrity failure here still means one thing: the subject was
                # erased mid-flight.
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_upload_ownership.py tests/test_report_store.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/reports/store.py tests/test_upload_ownership.py
git commit -m "feat(s84a): stamp org_id on report save, outside the report body

Ownership is storage, not the Report contract, so it is a keyword argument
rather than a schema field. A re-save without org_id leaves the existing
owner alone -- un-owning by forgetting an argument would be a cross-tenant
leak in the making."
```

---

## Task 3: Org-scoped store reads

**Files:**
- Modify: `app/reports/store.py` (Protocol + `SqlReportStore`)
- Modify: `app/candidates/store.py` (append a method)
- Test: `tests/test_screening_scope.py`

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces:
  - `SqlReportStore.get_for_org(self, org_id: str, report_id: str) -> Optional[Report]`
  - `SqlReportStore.for_candidate_and_org(self, org_id: str, candidate_id: str) -> list[Report]`
  - `CandidateStore.org_owns_candidate(self, org_id: str, candidate_id: str) -> bool`

**Context you need:** These are the *only* reads the facade in Task 5 is allowed to use. Each takes `org_id` first. A report with `org_id IS NULL` (pre-S8.4 or admin-uploaded) belongs to **no** org and must not be returned to any of them.

- [ ] **Step 1: Write the failing test**

Create `tests/test_screening_scope.py`:

```python
"""S8.4 Phase A: org-scoped reads. Another org's report is INDISTINGUISHABLE
from one that does not exist -- a 403 would confirm it exists."""

from __future__ import annotations

from datetime import datetime, timezone

from app.candidates.schema import (
    CandidateProfile, ContactInfo, ExtractedStr, ExtractionResult,
)
from app.schemas.report import Report


def _org(services, name):
    return services.ledger.create_organization(name).id


def _upload(services, org_id, *, name="Priya", email="priya@x.io", text="resume text"):
    return services.candidates.ingest(
        ExtractionResult(
            profile=CandidateProfile(
                full_name=ExtractedStr(value=name),
                contact=ContactInfo(email=ExtractedStr(value=email)),
            ),
            method="heuristic",
        ),
        resume_text=text,
        org_id=org_id,
    )


def _report(services, org_id, candidate_id, report_id):
    r = Report(id=report_id, domain="genai", candidate_id=candidate_id,
               created_at=datetime.now(timezone.utc))
    services.report_store.save(r, org_id=org_id)
    return r


def test_get_for_org_returns_only_own_reports(services):
    a, b = _org(services, "Agency A"), _org(services, "Agency B")
    cand = _upload(services, a).candidate_id
    _report(services, a, cand, "rep-a")

    assert services.report_store.get_for_org(a, "rep-a") is not None
    assert services.report_store.get_for_org(b, "rep-a") is None


def test_unowned_reports_belong_to_nobody(services):
    """A pre-S8.4 or admin-uploaded report is unowned, not everyone's."""
    a = _org(services, "Agency A")
    cand = _upload(services, a).candidate_id
    services.report_store.save(
        Report(id="rep-orphan", domain="genai", candidate_id=cand,
               created_at=datetime.now(timezone.utc))
    )
    assert services.report_store.get_for_org(a, "rep-orphan") is None
    assert services.report_store.get("rep-orphan") is not None  # admin still sees it


def test_for_candidate_and_org_filters_by_owner(services):
    a, b = _org(services, "Agency A"), _org(services, "Agency B")
    cand = _upload(services, a).candidate_id
    _report(services, a, cand, "rep-a")
    _report(services, b, cand, "rep-b")

    assert [r.id for r in services.report_store.for_candidate_and_org(a, cand)] == ["rep-a"]
    assert [r.id for r in services.report_store.for_candidate_and_org(b, cand)] == ["rep-b"]


def test_two_orgs_uploading_one_person_share_the_candidate_row(services):
    """The whole point of ownership-on-the-upload: candidates stay global."""
    a, b = _org(services, "Agency A"), _org(services, "Agency B")
    first = _upload(services, a, text="priya v1")
    second = _upload(services, b, text="priya v2")

    assert first.candidate_id == second.candidate_id, "dedup by email hash still holds"
    assert services.candidates.org_owns_candidate(a, first.candidate_id) is True
    assert services.candidates.org_owns_candidate(b, first.candidate_id) is True


def test_org_owns_candidate_is_false_for_a_stranger(services):
    a, b = _org(services, "Agency A"), _org(services, "Agency B")
    cand = _upload(services, a).candidate_id
    assert services.candidates.org_owns_candidate(b, cand) is False


def test_candidate_erasure_still_takes_owned_reports_with_it(services):
    """Ownership must not weaken the DPDP cascade (spec §7).

    reports.candidate_id CASCADEs and reports.org_id SET NULLs -- adding the
    second FK must not have given the row a reason to survive its subject.
    """
    from app.reports.models import ReportRow

    a = _org(services, "Agency A")
    cand = _upload(services, a).candidate_id
    _report(services, a, cand, "rep-erase")

    assert services.candidates.delete_candidate(cand) is True

    with services.candidates._session_factory() as s:
        assert s.get(ReportRow, "rep-erase") is None, (
            "an owned report must still die with its subject"
        )
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_screening_scope.py -v`
Expected: FAIL — `AttributeError: 'SqlReportStore' object has no attribute 'get_for_org'`.

- [ ] **Step 3: Add the scoped reads to `SqlReportStore`**

In `app/reports/store.py`, add to the `ReportStore` Protocol:

```python
    def get_for_org(self, org_id: str, report_id: str) -> Optional[Report]: ...
    def for_candidate_and_org(
        self, org_id: str, candidate_id: str
    ) -> list[Report]: ...
```

And to `SqlReportStore`:

```python
    def get_for_org(self, org_id: str, report_id: str) -> Optional[Report]:
        """One report, but only if this org commissioned it.

        A report with ``org_id IS NULL`` -- pre-S8.4, or uploaded through the
        admin plane -- belongs to NOBODY, not to everybody. Returning None here
        rather than raising is what lets the route answer 404 instead of 403:
        another org's report must be indistinguishable from one that is absent.
        """
        with self._session_factory() as s:
            row = s.get(ReportRow, report_id)
            if row is None or row.org_id != org_id:
                return None
            return Report.model_validate(row.body)

    def for_candidate_and_org(self, org_id: str, candidate_id: str) -> list[Report]:
        with self._session_factory() as s:
            rows = s.execute(
                select(ReportRow)
                .where(
                    ReportRow.candidate_id == candidate_id,
                    ReportRow.org_id == org_id,
                )
                .order_by(ReportRow.created_at)
            ).scalars().all()
            return [Report.model_validate(r.body) for r in rows]
```

- [ ] **Step 4: Add `org_owns_candidate` to `CandidateStore`**

In `app/candidates/store.py`, after `find_by_email_hash`:

```python
    def org_owns_candidate(self, org_id: str, candidate_id: str) -> bool:
        """Does this org hold at least one upload of this person?

        "My candidates" is DERIVED, never denormalized: there is no
        candidates.org_id, because a candidate is a person and two orgs can
        both have uploaded them. One ownership fact, one home -- nothing to
        drift out of step.
        """
        with self._session_factory() as session:
            return session.execute(
                select(ResumeRow.id)
                .where(
                    ResumeRow.candidate_id == candidate_id,
                    ResumeRow.org_id == org_id,
                )
                .limit(1)
            ).scalars().first() is not None
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_screening_scope.py -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/reports/store.py app/candidates/store.py tests/test_screening_scope.py
git commit -m "feat(s84a): org-scoped store reads

get_for_org / for_candidate_and_org / org_owns_candidate. An unowned report
belongs to nobody rather than to everybody, and a miss returns None so the
route can answer 404 -- a 403 would confirm the report exists."
```

---

## Task 4: The single redacting projection

**Files:**
- Modify: `app/schemas/fabrication.py:100-105` (`ResumeMatch`)
- Create: `app/screening/__init__.py`, `app/screening/projection.py`
- Test: `tests/test_screening_projection.py`

**Interfaces:**
- Consumes: nothing (pure).
- Produces: `app.screening.projection.redact_for_org(report: Report) -> Report`.

**Context you need:** `resume_farm.matches[]` names *other candidates' resumes*, which may belong to another customer. The org plane sees similarity and count, never identity. `ResumeMatch.candidate_id` / `.resume_id` are currently required `str`; they become `Optional[str] = None` so "absent for this reader" is representable honestly rather than faked with empty strings. **The admin path must still populate them** — there is a test for that.

This function is the *only* place the redaction happens; Task 6's routes and Phase B's queue read-model both call it. Two copies would be a bound that holds on one path and lapses on the other, which is the S7.2 `claim_ref` and S7.3 transcript finding a third time.

- [ ] **Step 1: Write the failing test**

Create `tests/test_screening_projection.py`:

```python
"""S8.4 Phase A: the ONE redaction. Similarity and count survive; identity
does not. Both org-facing readers call this same function."""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.fabrication import (
    DuplicationBand, ResumeFarmAssessment, ResumeMatch,
)
from app.schemas.report import Report
from app.screening.projection import redact_for_org


def _report_with_matches() -> Report:
    return Report(
        id="rep-1",
        domain="genai",
        created_at=datetime.now(timezone.utc),
        resume_farm=ResumeFarmAssessment(
            score=0.82,
            confidence=0.7,
            band=DuplicationBand.ELEVATED,
            corpus_size=1200,
            reasoning="two near-duplicates in the corpus",
            matches=[
                ResumeMatch(candidate_id="cand-x", resume_id="res-x", similarity=0.82),
                ResumeMatch(candidate_id="cand-y", resume_id="res-y", similarity=0.61),
            ],
        ),
    )


def test_identity_is_stripped_from_every_match():
    out = redact_for_org(_report_with_matches())
    assert [m.candidate_id for m in out.resume_farm.matches] == [None, None]
    assert [m.resume_id for m in out.resume_farm.matches] == [None, None]


def test_similarity_count_and_the_rest_of_the_signal_survive():
    out = redact_for_org(_report_with_matches())
    assert [m.similarity for m in out.resume_farm.matches] == [0.82, 0.61]
    assert len(out.resume_farm.matches) == 2
    assert out.resume_farm.score == 0.82
    assert out.resume_farm.band == DuplicationBand.ELEVATED
    assert out.resume_farm.corpus_size == 1200
    assert out.resume_farm.reasoning == "two near-duplicates in the corpus"


def test_the_rest_of_the_report_is_untouched():
    """The org sees the FULL report -- verdicts, missing_signals, probes."""
    source = _report_with_matches()
    out = redact_for_org(source)
    assert out.id == source.id
    assert out.verdicts == source.verdicts
    assert out.depth_score == source.depth_score
    assert out.fabrication_risk == source.fabrication_risk


def test_the_input_report_is_not_mutated():
    source = _report_with_matches()
    redact_for_org(source)
    assert source.resume_farm.matches[0].candidate_id == "cand-x", (
        "redaction must not corrupt the admin-plane object it was handed"
    )


def test_a_report_with_no_matches_is_returned_unharmed():
    r = Report(id="rep-2", domain="genai", created_at=datetime.now(timezone.utc))
    out = redact_for_org(r)
    assert out.resume_farm.matches == []
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_screening_projection.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.screening'`.

- [ ] **Step 3: Make the identity fields optional**

In `app/schemas/fabrication.py`, replace `ResumeMatch`:

```python
class ResumeMatch(BaseModel):
    """One stored resume (another candidate's) with estimated content overlap.

    ``candidate_id`` and ``resume_id`` are **None on the org plane** (S8.4
    §3.4): the matched resume may belong to another customer, so an org learns
    THAT a near-duplicate exists and how similar it is, never whose it is. The
    admin plane always populates them.
    """

    candidate_id: Optional[str] = None
    resume_id: Optional[str] = None
    similarity: float = Field(ge=0.0, le=1.0)  # estimated Jaccard over shingles
```

Ensure `Optional` is imported in that module (`from typing import Optional`).

- [ ] **Step 4: Write the projection**

Create `app/screening/__init__.py`:

```python
"""Org-facing screening surface (S8.4).

Phase A ships the tenancy pieces: ``projection`` (the one redaction) and
``scope`` (the one door org handlers read through). Phase B adds the batch
model and the fraud-screen read-model on top.
"""
```

Create `app/screening/projection.py`:

```python
"""The ONE org-facing redaction (S8.4 Phase A, spec §3.4).

``resume_farm.matches[]`` names other candidates' resumes, which may belong to
another customer. An organization learns THAT a near-duplicate exists and how
similar it is -- never whose it is.

This function is the only place that happens. Every org-facing reader calls it:
the single-report route and Phase B's batch queue read-model. Two copies would
be a bound that holds on one path and lapses on the other, which is the S7.2
``claim_ref`` finding and the S7.3 transcript finding a third time.

Pure: no I/O, no session, no clock. The input report is never mutated -- it is
usually the admin plane's own object.
"""

from __future__ import annotations

from app.schemas.report import Report


def redact_for_org(report: Report) -> Report:
    """Return a copy safe to hand an organization.

    Everything else survives, deliberately: the org sees the FULL report,
    including ``verdicts[]``, ``missing_signals`` and ``probes[]``. Those are
    what convert a score into an action (UI.md §4.B), and withholding them
    would make the numbers less useful without making them more honest.
    """
    farm = report.resume_farm
    if not farm.matches:
        return report.model_copy(deep=True)

    redacted = [
        m.model_copy(update={"candidate_id": None, "resume_id": None})
        for m in farm.matches
    ]
    return report.model_copy(
        deep=True,
        update={"resume_farm": farm.model_copy(update={"matches": redacted})},
    )
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_screening_projection.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Prove the admin path still populates identity**

Append to `tests/test_screening_projection.py`:

```python
def test_admin_plane_still_gets_identity(services, farm_resume_a, farm_resume_b, admin_headers):
    """Widening ResumeMatch to Optional must not silently empty the admin view."""
    from contextlib import contextmanager
    from fastapi.testclient import TestClient
    from app.main import create_app

    with TestClient(create_app(services), raise_server_exceptions=False,
                    headers=admin_headers) as c:
        c.post("/candidates", json={"resume_text": farm_resume_a, "domain": "genai"})
        second = c.post("/candidates",
                        json={"resume_text": farm_resume_b, "domain": "genai"})
        matches = second.json()["resume_farm"]["matches"]
        assert matches, "fixture pair must produce a near-duplicate match"
        assert all(m["candidate_id"] is not None for m in matches)
        assert all(m["resume_id"] is not None for m in matches)
```

Run: `pytest tests/test_screening_projection.py -v`
Expected: PASS (6 tests).

- [ ] **Step 7: Run the full suite**

Run: `pytest -q`
Expected: PASS. Watch specifically for `tests/test_resume_farm*.py` — widening two fields to `Optional` is exactly the kind of change that loosens an assertion somewhere.

- [ ] **Step 8: Commit**

```bash
git add app/schemas/fabrication.py app/screening/ tests/test_screening_projection.py
git commit -m "feat(s84a): one redacting projection for org-facing reports

resume_farm.matches[] keeps similarity and count, loses identity -- the
matched resume may belong to another customer. ResumeMatch identity fields
become Optional so 'absent for this reader' is representable honestly
rather than faked with empty strings; the admin path still populates them
and a test pins that."
```

---

## Task 5: The scoped facade

**Files:**
- Create: `app/screening/scope.py`
- Modify: `app/core/services.py` (wire it into `Services`)
- Test: `tests/test_screening_scope.py` (append)

**Interfaces:**
- Consumes: Task 3's scoped reads, Task 4's `redact_for_org`.
- Produces: `app.screening.scope.OrgScopedReads` with
  - `report(self, org_id: str, report_id: str) -> Optional[Report]`
  - `reports_for_candidate(self, org_id: str, candidate_id: str) -> list[Report]`
  - `owns_candidate(self, org_id: str, candidate_id: str) -> bool`
  and `build_org_scoped_reads(reports, candidates) -> OrgScopedReads`.
  Reachable as `services.screening_scope`.

**Context you need:** This is the *only* object org handlers may read candidates, resumes or reports through. Every method takes `org_id` first — the type signature is the enforcement, and Task 7's guard is the backstop. Both report-returning methods redact before returning, so a handler cannot forget.

Check how `Services` is assembled in `app/core/services.py` before editing; follow the existing cycle-safe construction used for `portal` and `dashboard`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_screening_scope.py`:

```python
def test_facade_report_redacts_and_scopes(services):
    from app.schemas.fabrication import ResumeFarmAssessment, ResumeMatch

    a, b = _org(services, "Agency A"), _org(services, "Agency B")
    cand = _upload(services, a).candidate_id
    r = Report(
        id="rep-f", domain="genai", candidate_id=cand,
        created_at=datetime.now(timezone.utc),
        resume_farm=ResumeFarmAssessment(
            matches=[ResumeMatch(candidate_id="other", resume_id="res", similarity=0.9)],
        ),
    )
    services.report_store.save(r, org_id=a)

    got = services.screening_scope.report(a, "rep-f")
    assert got is not None
    assert got.resume_farm.matches[0].candidate_id is None, "facade must redact"
    assert got.resume_farm.matches[0].similarity == 0.9

    assert services.screening_scope.report(b, "rep-f") is None


def test_facade_reports_for_candidate_redacts_every_element(services):
    from app.schemas.fabrication import ResumeFarmAssessment, ResumeMatch

    a = _org(services, "Agency A")
    cand = _upload(services, a).candidate_id
    for rid in ("rep-1", "rep-2"):
        services.report_store.save(
            Report(id=rid, domain="genai", candidate_id=cand,
                   created_at=datetime.now(timezone.utc),
                   resume_farm=ResumeFarmAssessment(
                       matches=[ResumeMatch(candidate_id="o", resume_id="r",
                                            similarity=0.5)])),
            org_id=a,
        )
    out = services.screening_scope.reports_for_candidate(a, cand)
    assert len(out) == 2
    assert all(m.candidate_id is None for r in out for m in r.resume_farm.matches)


def test_facade_owns_candidate(services):
    a, b = _org(services, "Agency A"), _org(services, "Agency B")
    cand = _upload(services, a).candidate_id
    assert services.screening_scope.owns_candidate(a, cand) is True
    assert services.screening_scope.owns_candidate(b, cand) is False


def test_every_facade_read_takes_org_id_first():
    """The signature IS the enforcement; Task 7's guard is the backstop."""
    import inspect
    from app.screening.scope import OrgScopedReads

    for name in ("report", "reports_for_candidate", "owns_candidate"):
        params = list(inspect.signature(getattr(OrgScopedReads, name)).parameters)
        assert params[:2] == ["self", "org_id"], f"{name} must scope by org first"
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_screening_scope.py -k facade -v`
Expected: FAIL — `ModuleNotFoundError` / `Services` has no attribute `screening_scope`.

- [ ] **Step 3: Write the facade**

Create `app/screening/scope.py`:

```python
"""The ONE door org-plane handlers read people through (S8.4 Phase A, §3.3).

Four consecutive branch reviews -- S7.1 ``start()``, S7.2 ``claim_ref``, S7.3
the audio path, S8.2 the two-challenge lockout -- each found the same shape: a
rule enforced by REMEMBERING to enforce it, forgotten at the second door. A
tenancy rule spread across the org plane is that shape by construction.

So org handlers get no option. Every method here takes ``org_id`` first, there
is no unscoped read on this object, and both report-returning methods redact
before returning so a handler cannot forget. ``tests/test_org_scope_guard.py``
is the backstop that covers routes nobody has written yet.

Owns no tables and holds no state -- pure composition over the two stores, in
the ``app/dashboard/`` style.
"""

from __future__ import annotations

from typing import Optional

from app.candidates.store import CandidateStore
from app.reports.store import ReportStore
from app.schemas.report import Report
from app.screening.projection import redact_for_org


class OrgScopedReads:
    def __init__(self, reports: ReportStore, candidates: CandidateStore) -> None:
        self._reports = reports
        self._candidates = candidates

    def report(self, org_id: str, report_id: str) -> Optional[Report]:
        """One report this org commissioned, redacted. None if it is not theirs.

        None rather than an exception, so the route answers 404: another org's
        report must be indistinguishable from one that does not exist.
        """
        found = self._reports.get_for_org(org_id, report_id)
        return None if found is None else redact_for_org(found)

    def reports_for_candidate(self, org_id: str, candidate_id: str) -> list[Report]:
        """This org's own reports about one person, oldest first, all redacted.

        A person this org has never uploaded yields an EMPTY LIST, not a 404 --
        "you have no reports about them" and "they do not exist" are different
        facts, and only the first is this org's business.
        """
        return [
            redact_for_org(r)
            for r in self._reports.for_candidate_and_org(org_id, candidate_id)
        ]

    def owns_candidate(self, org_id: str, candidate_id: str) -> bool:
        return self._candidates.org_owns_candidate(org_id, candidate_id)


def build_org_scoped_reads(
    reports: ReportStore, candidates: CandidateStore
) -> OrgScopedReads:
    return OrgScopedReads(reports, candidates)
```

- [ ] **Step 4: Wire it into `Services`**

In `app/core/services.py`, add a `screening_scope: OrgScopedReads` field to the `Services` container and construct it alongside `portal`/`dashboard`, passing the already-built `report_store` and `candidates`. Mirror the existing construction order exactly — `screening_scope` depends on both stores and nothing depends on it, so it goes last.

Also update `make_services` in `tests/conftest.py:213-308` so the fixture builds it the same way. If `make_services` constructs `Services(...)` positionally, add the argument in the matching position.

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_screening_scope.py -v`
Expected: PASS (11 tests).

- [ ] **Step 6: Mutation-test the facade and the projection**

Spec §7 asks for this specifically: these two functions are where a silent surviving mutant is a **cross-tenant disclosure**, and S8.2 recorded two mutants surviving a first pass on `AuthService` — one of which proved a load-bearing comment was simply wrong.

Apply each mutation, run `pytest tests/test_screening_scope.py tests/test_screening_projection.py -q`, confirm **RED**, then revert:

| # | Mutation | Must be caught by |
|---|---|---|
| 1 | `OrgScopedReads.report` returns `found` instead of `redact_for_org(found)` | `test_facade_report_redacts_and_scopes` |
| 2 | `reports_for_candidate` returns the list unredacted | `test_facade_reports_for_candidate_redacts_every_element` |
| 3 | `get_for_org` drops the `row.org_id != org_id` check | `test_get_for_org_returns_only_own_reports` |
| 4 | `redact_for_org` clears `candidate_id` but not `resume_id` | `test_identity_is_stripped_from_every_match` |
| 5 | `redact_for_org` returns `report` unchanged when `matches` is non-empty | `test_identity_is_stripped_from_every_match` |

**Any mutant that survives means the test is decorative — fix the test, not the table.**

- [ ] **Step 7: Run the full suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/screening/scope.py app/core/services.py tests/conftest.py \
        tests/test_screening_scope.py
git commit -m "feat(s84a): OrgScopedReads -- the one door org handlers read through

Every method takes org_id first and both report readers redact before
returning, so a handler cannot forget either rule. Owns no tables; pure
composition over the two stores in the app/dashboard/ style."
```

---

## Task 6: The three org-plane routes

**Files:**
- Modify: `app/api/routes.py` (add three `@org_router` routes near the other org routes)
- Test: `tests/test_screening_api.py`

**Interfaces:**
- Consumes: `services.screening_scope` (Task 5), `require_org` (`app/api/routes.py:148`), `CandidateCreateRequest` / `CandidateCreateResponse` (existing).
- Produces: `POST /screening/candidates`, `GET /screening/reports/{report_id}`, `GET /screening/candidates/{candidate_id}/reports`.

**Context you need:** `require_org` returns `org_id: str`. Paths live under `/screening/*` so they never collide with the admin nouns. The admin routes at `routes.py:309`, `:448` and `:1526` are **not** modified.

`POST /screening/candidates` is the one-off upload and is synchronous like its admin twin — batch is Phase B. Rather than duplicating the ~80-line admin handler, extract its body into a shared helper that takes an optional `org_id`, and have both routes call it. Duplicating it would be the one-rule-two-doors shape in the very sprint that exists to eliminate it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_screening_api.py`:

```python
"""S8.4 Phase A: the org-plane wedge routes. Two agencies, one candidate."""

from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS


@contextmanager
def _client(services):
    with TestClient(create_app(services), raise_server_exceptions=False,
                    headers=ADMIN_HEADERS) as c:
        yield c


def _key(services, name):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def test_org_can_upload_and_read_its_own_report(services, genuine_resume):
    _, key = _key(services, "Agency A")
    with _client(services) as c:
        up = c.post("/screening/candidates", headers={"X-Org-Key": key},
                    json={"resume_text": genuine_resume, "domain": "genai"})
        assert up.status_code == 200, up.text
        body = up.json()
        report_id = body["report"]["id"]

        got = c.get(f"/screening/reports/{report_id}", headers={"X-Org-Key": key})
        assert got.status_code == 200
        assert got.json()["id"] == report_id


def test_another_orgs_report_is_404_not_403(services, genuine_resume):
    _, key_a = _key(services, "Agency A")
    _, key_b = _key(services, "Agency B")
    with _client(services) as c:
        up = c.post("/screening/candidates", headers={"X-Org-Key": key_a},
                    json={"resume_text": genuine_resume, "domain": "genai"})
        report_id = up.json()["report"]["id"]

        theirs = c.get(f"/screening/reports/{report_id}", headers={"X-Org-Key": key_b})
        absent = c.get("/screening/reports/does-not-exist", headers={"X-Org-Key": key_b})

        assert theirs.status_code == 404
        assert absent.status_code == 404
        assert theirs.json() == absent.json(), (
            "a 403 -- or a different body -- would confirm the report exists"
        )


def test_screening_routes_require_an_org_credential(services):
    with _client(services) as c:
        assert c.get("/screening/reports/x").status_code == 401
        assert c.post("/screening/candidates", json={}).status_code == 401


def test_reports_for_a_candidate_are_scoped_to_the_caller(services, genuine_resume):
    _, key_a = _key(services, "Agency A")
    _, key_b = _key(services, "Agency B")
    with _client(services) as c:
        up = c.post("/screening/candidates", headers={"X-Org-Key": key_a},
                    json={"resume_text": genuine_resume, "domain": "genai"})
        cand = up.json()["candidate_id"]

        mine = c.get(f"/screening/candidates/{cand}/reports", headers={"X-Org-Key": key_a})
        theirs = c.get(f"/screening/candidates/{cand}/reports", headers={"X-Org-Key": key_b})

        assert mine.status_code == 200 and len(mine.json()) == 1
        assert theirs.status_code == 200 and theirs.json() == [], (
            "an empty list, not a 404: 'I have no reports on them' is not "
            "'they do not exist'"
        )


def test_the_org_report_is_redacted_but_complete(services, farm_resume_a, farm_resume_b):
    _, key = _key(services, "Agency A")
    with _client(services) as c:
        c.post("/screening/candidates", headers={"X-Org-Key": key},
               json={"resume_text": farm_resume_a, "domain": "genai"})
        second = c.post("/screening/candidates", headers={"X-Org-Key": key},
                        json={"resume_text": farm_resume_b, "domain": "genai"})
        report_id = second.json()["report"]["id"]

        body = c.get(f"/screening/reports/{report_id}",
                     headers={"X-Org-Key": key}).json()
        for m in body["resume_farm"]["matches"]:
            assert m["candidate_id"] is None and m["resume_id"] is None
            assert m["similarity"] > 0
        # The org still gets the full report.
        assert "verdicts" in body and "fabrication_risk" in body


def test_admin_upload_stays_unowned_and_invisible_to_orgs(services, genuine_resume,
                                                          admin_headers):
    org_id, key = _key(services, "Agency A")
    with _client(services) as c:
        up = c.post("/candidates", headers=admin_headers,
                    json={"resume_text": genuine_resume, "domain": "genai"})
        report_id = up.json()["report"]["id"]

        assert c.get(f"/report/{report_id}", headers=admin_headers).status_code == 200
        assert c.get(f"/screening/reports/{report_id}",
                     headers={"X-Org-Key": key}).status_code == 404
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_screening_api.py -v`
Expected: FAIL — 404 on `/screening/candidates` (route does not exist).

- [ ] **Step 3: Extract the ingest handler body into a shared helper**

In `app/api/routes.py`, refactor `create_candidate` (line 309) so its body lives in a module-level coroutine both routes call:

```python
async def _ingest_one(
    req: CandidateCreateRequest, request: Request, *, org_id: Optional[str] = None
) -> CandidateCreateResponse:
    """Upload → extract → store → (auto) depth-eval, for ONE resume.

    Shared by the admin route (no owner) and the org route (owner = caller).
    Kept as one function on purpose: duplicating it would be the
    one-rule-two-doors shape in the sprint that exists to eliminate it.
    """
```

Move the entire existing body of `create_candidate` into it verbatim, with three changes:
- `services.candidates.ingest(result, text)` becomes `services.candidates.ingest(result, text, org_id=org_id)`
- `services.report_store.save(report)` becomes `services.report_store.save(report, org_id=org_id)`
- everything else is unchanged, including the `SubjectErasedError` handling and the `resume_farm` block.

Then the admin route becomes:

```python
@router.post("/candidates", response_model=CandidateCreateResponse)
async def create_candidate(
    req: CandidateCreateRequest, request: Request
) -> CandidateCreateResponse:
    """Admin plane: no owner. Cross-tenant by design -- this is the operator's
    view, and S8.4 deliberately left it alone."""
    return await _ingest_one(req, request)
```

- [ ] **Step 4: Add the three org routes**

Place these beside the other `@org_router` routes:

```python
@org_router.post("/screening/candidates", response_model=CandidateCreateResponse)
async def screening_create_candidate(
    req: CandidateCreateRequest, request: Request, org_id: str = Depends(require_org)
) -> CandidateCreateResponse:
    """The wedge, on the plane that bought it (S8.4 §3.2).

    Synchronous like its admin twin -- this is the one-off upload. Batch is
    Phase B. The resume and its report are stamped with the caller's org.
    """
    return await _ingest_one(req, request, org_id=org_id)


@org_router.get("/screening/reports/{report_id}", response_model=Report)
async def screening_get_report(
    report_id: str, request: Request, org_id: str = Depends(require_org)
) -> Report:
    """404 -- never 403 -- for a report this org did not commission: a 403
    would confirm it exists."""
    found = _services(request).screening_scope.report(org_id, report_id)
    if found is None:
        raise HTTPException(status_code=404, detail="report not found")
    return found


@org_router.get(
    "/screening/candidates/{candidate_id}/reports", response_model=list[Report]
)
async def screening_candidate_reports(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> list[Report]:
    """This org's own reports about one person. A person they have never
    uploaded yields an empty list, not a 404."""
    return _services(request).screening_scope.reports_for_candidate(
        org_id, candidate_id
    )
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_screening_api.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: PASS. `tests/test_route_table_guard.py` must still pass — the three new routes depend on `require_org`, which is a sanctioned resolver.

- [ ] **Step 7: Commit**

```bash
git add app/api/routes.py tests/test_screening_api.py
git commit -m "feat(s84a): org-plane screening routes (upload, report, candidate reports)

The wedge reaches the plane that bought it. Another org's report is 404
with a byte-identical body to an absent one. The admin routes are
untouched and keep their cross-tenant reach; the ingest body is shared
rather than duplicated."
```

---

## Task 7: The structural scoping guard

**Files:**
- Create: `tests/test_org_scope_guard.py`

**Interfaces:**
- Consumes: the live FastAPI route table; `app.screening.scope.OrgScopedReads`.
- Produces: nothing importable — this is a build gate.

**Context you need:** Read `tests/test_route_table_guard.py` first; this guard reuses its `_walk` recursion and must reuse its hard-won lesson. **FastAPI 0.138 does not flatten `include_router` into `app.routes`** — it stores an `_IncludedRouter` wrapper, so a naive walk sees 9 routes instead of 63 and the guard passes while inspecting almost nothing. That is the exact failure mode the fail-open admin gate had for eight PIs. Assert a floor, and prove the guard can fail.

The rule: any org-plane handler reading candidates, resumes or reports must do so through `services.screening_scope`, never through `services.report_store` or `services.candidates` directly. Enforced by inspecting each org route's handler source for the forbidden attribute reads.

- [ ] **Step 1: Write the guard, including its own failure proof**

Create `tests/test_org_scope_guard.py`:

```python
"""S8.4 Phase A: the tenancy backstop (spec §3.3).

Type signatures make OrgScopedReads scope by org; this guard makes sure org
handlers actually go THROUGH it. Like tests/test_route_table_guard.py it walks
the live route table, so it covers routes nobody has written yet -- which is
the property that makes a guard worth more than any number of hand-written
per-route tests.

The lesson inherited from that file, and the reason for the floor assertion
below: FastAPI 0.138 stores an ``_IncludedRouter`` wrapper rather than
flattening ``include_router``, so a naive walk sees NINE routes and misses all
of them. A guard that inspects nothing passes everything.
"""

from __future__ import annotations

import inspect
import re

from app.api.routes import require_org
from app.main import create_app
from tests.test_route_table_guard import _resolvers_on, _walk

#: Reads that bypass tenancy scoping. An org handler touching one of these is
#: reading across customers unless it filters by hand -- and "unless it filters
#: by hand" is the whole failure mode this guard exists to prevent.
FORBIDDEN = (
    r"\.report_store\b",
    r"\.candidates\b",
)

#: The sanctioned door.
SANCTIONED = ".screening_scope"


def _org_plane_endpoints(app):
    """Every route that establishes its principal via require_org."""
    for route, inherited in _walk(app.routes):
        if getattr(route, "endpoint", None) is None:
            continue
        if require_org in _resolvers_on(route, inherited):
            yield route


def test_the_walker_actually_finds_the_org_plane(services):
    """Non-vacuity. Without this the guard below can pass having seen nothing."""
    app = create_app(services)
    found = list(_org_plane_endpoints(app))
    assert len(found) >= 20, (
        f"only {len(found)} org-plane routes inspected -- the walker is broken, "
        f"and a guard that inspects nothing passes everything"
    )


def test_no_org_handler_reads_candidates_or_reports_unscoped(services):
    app = create_app(services)
    offenders = []
    for route in _org_plane_endpoints(app):
        source = inspect.getsource(route.endpoint)
        if SANCTIONED in source:
            continue
        for pattern in FORBIDDEN:
            if re.search(pattern, source):
                offenders.append(
                    f"{sorted(route.methods)} {route.path} "
                    f"reads {pattern} directly -- use services.screening_scope"
                )
    assert not offenders, "\n".join(offenders)


def test_the_guard_catches_an_unscoped_handler():
    """Prove the patterns can FAIL something. A guard nobody has seen go red is
    a green light, not a check.

    This pins the DETECTOR against a handler written the wrong way. Step 3 of
    this task additionally proves the guard red against the real route table --
    both matter, because a detector that matches nothing and a walker that
    finds nothing fail identically: silently, and green.
    """
    unscoped_source = (
        "async def bad_handler(request, org_id):\n"
        "    return _services(request).report_store.get('anything')\n"
    )
    assert SANCTIONED not in unscoped_source
    assert any(re.search(p, unscoped_source) for p in FORBIDDEN), (
        "the FORBIDDEN patterns no longer match a genuinely unscoped read"
    )
```

- [ ] **Step 2: Run it**

Run: `pytest tests/test_org_scope_guard.py -v`
Expected: PASS (3 tests). If `test_no_org_handler_reads_candidates_or_reports_unscoped` fails, an existing org route reads a store directly — read the offender before changing the guard. Pre-existing org routes that legitimately read `services.candidates` for non-person data may need an explicit, commented allowlist entry; add one only with a written reason, never to make the test green.

- [ ] **Step 3: Prove it fails on a real regression**

Temporarily change `screening_get_report` to call `_services(request).report_store.get(report_id)` instead of the facade.

Run: `pytest tests/test_org_scope_guard.py -v`
Expected: FAIL, naming `GET /screening/reports/{report_id}`.

Revert the change. Run again. Expected: PASS.

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_org_scope_guard.py
git commit -m "test(s84a): structural guard -- no org handler reads unscoped

Walks the live route table so it covers routes not yet written. Asserts a
floor on what it inspected, because FastAPI 0.138 does not flatten
include_router and a naive walk sees nine routes instead of all of them --
the vacuous-guard failure mode the fail-open admin gate had for eight PIs.
Verified to go red on a deliberately unscoped handler."
```

---

## Task 8: `org_name_taken` — refuse at signup with a 409

**Files:**
- Modify: `app/auth/store.py` (add `organization_name_exists`)
- Modify: `app/api/routes.py:1716-1724` (`auth_org_signup`)
- Test: `tests/test_auth_org_name_taken.py`

**Interfaces:**
- Consumes: `AuthStore`, `OrganizationRow`.
- Produces: `AuthStore.organization_name_exists(self, name: str) -> bool`; `POST /auth/org/signup` → `409 {"detail": "organization_name_taken"}`.

**Context you need:** Today signing up with a taken org name returns 202, sends a real code, and then rejects that **correct** code as `400 invalid_code` — because org creation happens inside `_establish` at *verify* time (`app/auth/service.py:363`) and the route collapses every `ChallengeRefused` into one message (`app/api/routes.py:1703`). The user burns their attempts and cannot onboard.

**The enumeration property being protected is "does this ADDRESS have an account".** Neither new response varies with that: signup for an unknown *address* still returns 202 whether or not the address exists. Only the *organisation name* — a value the caller supplied, and not a secret — changes the answer. A uniqueness constraint already discloses the same fact to anyone who completes a signup.

**Fixture warning — this will waste an hour if you miss it.** The default `services` fixture builds on code defaults, which means `email_provider="null"`, which means **every signup returns `503 email_unavailable`**. Auth tests must use the capture-email fixtures from `tests/test_auth_api.py:20-45` (`capture_path` → `cfg` → `client`). Note `client` attaches the built services as `client.app_services`, which is how you reach `ledger` and `auth` from a test.

- [ ] **Step 1: Write the failing test**

Create `tests/test_auth_org_name_taken.py`:

```python
"""S8.4 Phase A: org signup with a taken name refused at signup, not by
rejecting a correct code at verify (spec §2.1).

The lockout this closes: 202 + a real code that then verifies as
400 invalid_code, burning the attempt counter. "Acme Staffing" is exactly the
name two customers pick.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_services


@pytest.fixture
def capture_path(tmp_path):
    return tmp_path / "mail.jsonl"


@pytest.fixture
def cfg(settings, capture_path):
    """Localhost-shaped, mirroring tests/test_auth_api.py: without capture
    email the provider is 'null' and every signup 503s."""
    return settings.model_copy(update={
        "email_provider": "capture",
        "email_capture_path": str(capture_path),
        "session_cookie_secure": False,
        "session_cookie_samesite": "lax",
    })


@pytest.fixture
def client(cfg, flywheel):
    services = make_services(cfg, flywheel=flywheel)
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        c.app_services = services
        yield c


def _code(capture_path) -> str:
    line = json.loads(capture_path.read_text(encoding="utf-8").splitlines()[-1])
    return re.search(r"\b(\d{6})\b", line["body"]).group(1)


def _sent(capture_path) -> int:
    if not capture_path.exists():
        return 0
    return len(capture_path.read_text(encoding="utf-8").splitlines())


def test_signup_with_a_taken_org_name_is_409_before_any_code_is_sent(
    client, capture_path
):
    client.app_services.ledger.create_organization("Acme Staffing")
    before = _sent(capture_path)

    r = client.post("/auth/org/signup",
                    json={"email": "ops@acme.example",
                          "organization_name": "Acme Staffing"})

    assert r.status_code == 409
    assert r.json()["detail"] == "organization_name_taken"
    assert _sent(capture_path) == before, "no code may be sent for a refused signup"


def test_a_free_org_name_still_returns_202(client):
    r = client.post("/auth/org/signup",
                    json={"email": "ops@new.example",
                          "organization_name": "Brand New Co"})
    assert r.status_code == 202


def test_unknown_and_known_ADDRESSES_are_still_indistinguishable(
    client, capture_path
):
    """The anti-enumeration property is about the ADDRESS, not the org name.

    Register an address by completing a signup, then compare a second signup
    from that KNOWN address against one from an unknown address. Both must be
    identical in status, body and in whether a code was sent.
    """
    assert client.post("/auth/org/signup",
                       json={"email": "known@x.example",
                             "organization_name": "Known Co"}).status_code == 202
    assert client.post("/auth/org/verify",
                       json={"email": "known@x.example",
                             "code": _code(capture_path)}).status_code == 200

    before = _sent(capture_path)
    known = client.post("/auth/org/signup",
                        json={"email": "known@x.example",
                              "organization_name": "Some Free Name"})
    mid = _sent(capture_path)
    unknown = client.post("/auth/org/signup",
                          json={"email": "nobody-at-all@y.example",
                                "organization_name": "Another Free Name"})
    after = _sent(capture_path)

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert mid - before == after - mid, "a code count that differs is the oracle"
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_auth_org_name_taken.py -v`
Expected: FAIL — the first test gets 202, not 409.

- [ ] **Step 3: Add the store lookup**

In `app/auth/store.py`, add to `AuthStore` near `create_org_with_owner`:

```python
    def organization_name_exists(self, name: str) -> bool:
        """Is this organization name already taken?

        Used to refuse a signup BEFORE a code is sent (S8.4 §2.1). This leaks
        nothing: org names are not secret, and the uniqueness constraint
        already discloses the same fact to anyone who completes a signup. The
        property that IS protected -- whether an email address has an account
        -- is untouched, because this never looks at the address.
        """
        with self._session_factory() as session:
            return session.execute(
                select(OrganizationRow.id)
                .where(OrganizationRow.name == name.strip())
                .limit(1)
            ).scalars().first() is not None
```

Ensure `OrganizationRow` and `select` are imported in that module.

- [ ] **Step 4: Refuse at the route**

In `app/api/routes.py`, change `auth_org_signup`:

```python
@auth_router.post("/auth/org/signup", status_code=202)
async def auth_org_signup(req: OrgSignupRequest, request: Request) -> dict:
    """Refuse a taken org name HERE, before a code is ever sent (S8.4 §2.1).

    The old behaviour answered 202, mailed a real code, and then rejected that
    CORRECT code at verify as `invalid_code` -- because org creation happens in
    `_establish`, and every ChallengeRefused collapsed into one message. The
    user burned their attempts and could not onboard.

    This does not re-open the enumeration oracle. What that oracle protects is
    whether an ADDRESS has an account, and this check never looks at the
    address: an unknown address still gets 202 exactly like a known one.
    """
    if not _services(request).auth.organization_name_available(req.organization_name):
        raise HTTPException(status_code=409, detail="organization_name_taken")
    return _request_code(
        request,
        email=req.email,
        plane=AuthPlane.ORG,
        purpose=LoginPurpose.SIGNUP,
        payload={"organization_name": req.organization_name},
    )
```

Add the thin service passthrough in `app/auth/service.py`:

```python
    def organization_name_available(self, name: str) -> bool:
        """True when `name` is free. Routes talk to the service, not the store."""
        return not self._store.organization_name_exists(name)
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_auth_org_name_taken.py tests/test_auth_api.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: PASS. Any existing test asserting "org signup is always 202" that used a duplicate name legitimately changes — read it before editing, and make sure you are not weakening an anti-enumeration assertion about *addresses*.

- [ ] **Step 7: Commit**

```bash
git add app/auth/store.py app/auth/service.py app/api/routes.py \
        tests/test_auth_org_name_taken.py
git commit -m "fix(s84a): refuse a taken org name at signup with 409

Was: 202, a real code mailed, then that CORRECT code rejected at verify as
invalid_code -- attempts burned, onboarding impossible. Org names are not
secret and the uniqueness constraint already discloses this; the protected
property is whether an ADDRESS has an account, which is untouched."
```

---

## Task 9: `org_name_taken` — a distinct refusal at verify

**Files:**
- Modify: `app/auth/service.py:53` (new exception), `:353-370` (`_establish`)
- Modify: `app/api/routes.py:1691-1713` (`_verify`)
- Test: `tests/test_auth_org_name_taken.py` (append)

**Interfaces:**
- Consumes: Task 8.
- Produces: `app.auth.service.RegistrationRefused(AuthError)` with a `.reason: str`; `_verify` maps it to `409`, leaving every genuine code failure as one `400 invalid_code`.

**Context you need:** Task 8 closes the common case but there is a real race — the name can be taken in the window between signup and verify. That path must not resurface as `invalid_code`. Separate *registration* failures from *code* failures: `org_name_taken` and `missing_organization_name` become `RegistrationRefused`; expired / wrong / exhausted stay one indistinguishable `400`.

`no_such_operator` (`service.py:377`) stays a `ChallengeRefused` → `400`: an admin address either is an operator or is not, and distinguishing that *is* an enumeration oracle on a privileged plane.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_auth_org_name_taken.py`:

```python
def test_a_name_taken_during_the_window_is_409_not_invalid_code(
    client, capture_path
):
    """The race Task 8 cannot close: taken between signup and verify.

    This is the ONLY path that still reaches _establish's OrgNameTaken, and it
    is the one that must never resurface as 'your code is wrong'.
    """
    r = client.post("/auth/org/signup",
                    json={"email": "ops@acme.example",
                          "organization_name": "Acme Staffing"})
    assert r.status_code == 202
    code = _code(capture_path)

    # Somebody else registers the name in the window.
    client.app_services.ledger.create_organization("Acme Staffing")

    v = client.post("/auth/org/verify",
                    json={"email": "ops@acme.example", "code": code})
    assert v.status_code == 409, "a CORRECT code must never be reported as wrong"
    assert v.json()["detail"] == "organization_name_taken"


def test_every_genuine_code_failure_is_still_one_invalid_code(
    client, capture_path
):
    client.post("/auth/org/signup",
                json={"email": "ops@fresh.example",
                      "organization_name": "Fresh Co"})
    wrong = client.post("/auth/org/verify",
                        json={"email": "ops@fresh.example", "code": "000000"})
    assert wrong.status_code == 400
    assert wrong.json()["detail"] == "invalid_code"


def test_missing_organization_name_is_a_registration_failure_too(
    client, capture_path
):
    """Rides the same path as org_name_taken and must not read as a bad code.

    Driven through the service because the route schema requires the field --
    this state is reachable only from a machine client or a schema change, and
    it is precisely the kind of path that rots unwatched.
    """
    from datetime import datetime, timezone
    from app.auth.schema import AuthPlane, LoginPurpose

    client.app_services.auth.request_code(
        email="ops@noname.example", plane=AuthPlane.ORG,
        purpose=LoginPurpose.SIGNUP, payload={}, at=datetime.now(timezone.utc),
    )
    v = client.post("/auth/org/verify",
                    json={"email": "ops@noname.example",
                          "code": _code(capture_path)})
    assert v.status_code == 409
    assert v.json()["detail"] == "missing_organization_name"
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_auth_org_name_taken.py -k "window or missing_organization" -v`
Expected: FAIL — 400 `invalid_code` instead of 409.

- [ ] **Step 3: Add the exception**

In `app/auth/service.py`, beside `ChallengeRefused` (line 53):

```python
class RegistrationRefused(AuthError):
    """The code was RIGHT; establishing the principal failed.

    Split out from ChallengeRefused because collapsing the two is what let a
    taken organization name present as a wrong code -- the user typing a
    correct code, being told it was wrong, and burning their attempts.

    The single-message rule exists so a brute-forcer learns nothing about
    CODES. It was never meant to swallow a registration failure.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
```

- [ ] **Step 4: Raise it in `_establish`**

In `app/auth/service.py`, in the `AuthPlane.ORG` branch:

```python
        if plane == AuthPlane.ORG:
            user = self._store.org_user_by_email(email_hash)
            if user is None:
                name = (payload.get("organization_name") or "").strip()
                if not name:
                    raise RegistrationRefused("missing_organization_name")
                try:
                    org_id, user = self._store.create_org_with_owner(
                        name=name, email_hash=email_hash
                    )
                except OrgNameTaken as exc:
                    # Reachable despite the signup-time check (S8.4 §2.1): the
                    # name can be taken in the window between the two calls.
                    raise RegistrationRefused("org_name_taken") from exc
```

Leave `no_such_operator` at line 377 as `ChallengeRefused` — add a comment saying why:

```python
                # Stays a ChallengeRefused -> 400. Distinguishing "not an
                # operator" from "wrong code" IS an enumeration oracle, and on
                # the privileged plane.
```

- [ ] **Step 5: Fork in the route**

In `app/api/routes.py`, in `_verify`:

```python
    except RegistrationRefused as exc:
        # The code was RIGHT. This is a registration failure, and reporting it
        # as invalid_code is what locked users out of their own signup.
        raise HTTPException(status_code=409, detail=exc.reason) from exc
    except ChallengeRefused as exc:
        # ONE status and ONE detail for every CODE failure mode. Distinguishing
        # expired from wrong from exhausted tells a brute-forcer which of their
        # assumptions was right, which is precisely the help not to give.
        raise HTTPException(status_code=400, detail="invalid_code") from exc
```

`RegistrationRefused` must be caught **before** `ChallengeRefused` if it subclasses it — it does not here (both subclass `AuthError`), but keep the order anyway so a later refactor cannot silently re-collapse them. Add `RegistrationRefused` to the import at `app/api/routes.py:24`.

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_auth_org_name_taken.py tests/test_auth_api.py tests/test_auth_service.py -v`
Expected: PASS.

- [ ] **Step 7: Mutation-check the fork**

Temporarily change the `RegistrationRefused` handler to `status_code=400, detail="invalid_code"`.

Run: `pytest tests/test_auth_org_name_taken.py -v`
Expected: FAIL. If it passes, the tests are not pinning the behaviour — fix them before reverting.

Revert. Run again. Expected: PASS.

- [ ] **Step 8: Run the full suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/auth/service.py app/api/routes.py tests/test_auth_org_name_taken.py
git commit -m "fix(s84a): separate registration refusals from code refusals at verify

RegistrationRefused -> 409 closes the signup/verify race Task 8 cannot.
Every genuine code failure -- expired, wrong, exhausted -- stays one
indistinguishable 400 invalid_code. no_such_operator deliberately stays a
400: distinguishing it would be an enumeration oracle on the admin plane.
Verified by mutating the fork and watching the tests go red."
```

---

## Task 10: `TENANCY.md` + the key-less smoke

**Files:**
- Create: `TENANCY.md`
- Create: `scripts/smoke_s84a.py`

**Interfaces:**
- Consumes: everything above.
- Produces: a runnable smoke; no importable API.

**Context you need:** Every sprint here ends with a local smoke run against uvicorn on fixture resumes, not just unit tests — and S8.2's smoke caught a real design bug that 1363 green tests missed, because the org-upload-then-candidate-signup sequence only happens end to end. Model this on `scripts/smoke_s82.py`: key-less, exit non-zero on any failure, print `N/M OK`.

Pin `DEE_OPENROUTER_API_KEY=""` inside the script. S7.3 found a developer with a real key in `.env` was silently shipping junk to a live vendor from a smoke that claimed to prove the no-key path.

- [ ] **Step 1: Write `TENANCY.md`**

Create `TENANCY.md` at the repo root, peer of `AUTH.md` / `PORTAL.md`. Cover, with the reasoning and not just the rules:

- **The model** — ownership is a property of the upload; `resumes.org_id`, `reports.org_id`; nullable; `SET NULL` and why `CASCADE` would be wrong.
- **Why candidates stay global** — S1.1 dedup, and the cross-corpus resume-farm advantage that depends on it.
- **"My candidates" is derived** — no `candidates.org_id`, one home for the ownership fact.
- **What unowned means** — pre-S8.4 rows and admin uploads belong to nobody, not to everybody.
- **The enforcement** — `OrgScopedReads`, the guard, and the four branch reviews that motivated both.
- **404 never 403**, and why.
- **The one redaction** — `resume_farm.matches[]`, in one shared function.
- **What is NOT scoped yet** — `POST /evaluate` and `POST /talent/search` remain admin-only, with the spec §8 reasoning.

- [ ] **Step 2: Write the smoke**

Create `scripts/smoke_s84a.py`. Copy the process/boot/teardown scaffolding from `scripts/smoke_s82.py` verbatim — it already handles uvicorn startup, the capture-email env, readiness polling and cleanup — and replace its check list with the twelve below.

Structure:

```python
#!/usr/bin/env python
"""S8.4 Phase A smoke: two orgs, one deduplicated candidate, over real HTTP.

Key-less by construction. DEE_OPENROUTER_API_KEY is pinned empty because S7.3
found a developer with a real key in .env silently shipping junk to a live
vendor from a smoke that CLAIMED to prove the no-key path.

What a unit test cannot prove and this does: that ownership survives the whole
upload -> extract -> evaluate -> store -> read round trip, on the plane a real
customer uses, with two organizations racing over the same person.
"""

import os

os.environ["DEE_OPENROUTER_API_KEY"] = ""
os.environ["DEE_EMAIL_PROVIDER"] = "capture"
os.environ["DEE_SESSION_COOKIE_SECURE"] = "false"
os.environ["DEE_SESSION_COOKIE_SAMESITE"] = "lax"
# ... plus DEE_EMAIL_CAPTURE_PATH, DEE_API_AUTH_KEY, DEE_CANDIDATES_DB_URL
#     pointing at a temp dir -- see smoke_s82.py

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok), detail))
    print(f"{'OK  ' if ok else 'FAIL'} {name}{(' -- ' + detail) if detail else ''}")


def main() -> int:
    # ... boot uvicorn, wait for /healthz ...
    check("healthz", r.status_code == 200)

    # 1. Org A onboards end to end.
    org_a = signup_and_verify("ops@agency-a.example", "Agency A")
    check("org_a_session", org_a is not None)

    # 2. THE LOCKOUT: Org B tries Org A's name.
    before = captured_count()
    r = post("/auth/org/signup",
             json={"email": "ops@agency-b.example", "organization_name": "Agency A"})
    check("taken_name_409", r.status_code == 409 and
          r.json()["detail"] == "organization_name_taken")
    check("taken_name_sends_no_code", captured_count() == before)

    # 3. Org B onboards under its own name.
    org_b = signup_and_verify("ops@agency-b.example", "Agency B")
    check("org_b_session", org_b is not None)

    # 4. Org A uploads and reads its own report.
    up_a = post("/screening/candidates", session=org_a,
                json={"resume_text": GENUINE, "domain": "genai"})
    rid_a, cand = up_a.json()["report"]["id"], up_a.json()["candidate_id"]
    check("org_a_upload", up_a.status_code == 200)
    check("org_a_reads_own_report",
          get(f"/screening/reports/{rid_a}", session=org_a).status_code == 200)

    # 5. THE ISOLATION: Org B cannot, and cannot tell it exists.
    theirs = get(f"/screening/reports/{rid_a}", session=org_b)
    absent = get("/screening/reports/no-such-report", session=org_b)
    check("cross_org_read_404", theirs.status_code == 404)
    check("404_is_indistinguishable", theirs.text == absent.text)

    # 6. Dedup held: one person, two owners.
    up_b = post("/screening/candidates", session=org_b,
                json={"resume_text": GENUINE_V2, "domain": "genai"})
    check("candidate_deduplicated", up_b.json()["candidate_id"] == cand)
    check("each_org_sees_only_its_own_report",
          len(get(f"/screening/candidates/{cand}/reports", session=org_a).json()) == 1
          and len(get(f"/screening/candidates/{cand}/reports", session=org_b).json()) == 1)

    # 7. The redaction, on a report that really has matches.
    post("/screening/candidates", session=org_a,
         json={"resume_text": FARM_A, "domain": "genai"})
    farm = post("/screening/candidates", session=org_a,
                json={"resume_text": FARM_B, "domain": "genai"})
    matches = get(f"/screening/reports/{farm.json()['report']['id']}",
                  session=org_a).json()["resume_farm"]["matches"]
    check("farm_matches_redacted",
          matches and all(m["candidate_id"] is None and m["similarity"] > 0
                          for m in matches))

    # 8. Admin uploads stay unowned.
    adm = post("/candidates", headers=ADMIN,
               json={"resume_text": OTHER, "domain": "genai"})
    rid_adm = adm.json()["report"]["id"]
    check("admin_still_reads_its_own",
          get(f"/report/{rid_adm}", headers=ADMIN).status_code == 200)
    check("admin_upload_invisible_to_orgs",
          get(f"/screening/reports/{rid_adm}", session=org_a).status_code == 404)

    failed = [n for n, ok, _ in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} OK")
    return 1 if failed else 0
```

Fixture resumes come from `tests/fixtures/` — reuse the same files the `genuine_resume` and `farm_resume_a` / `farm_resume_b` fixtures read (`tests/conftest.py:337-360`). `GENUINE_V2` must be a *different text for the same person* (same email in the contact block) so identity resolution deduplicates while producing a second resume version.

The org-deletion check from the unit tests is deliberately **not** repeated here — there is no HTTP route to delete an organization, and `test_deleting_an_org_leaves_the_resume_intact_and_unowned` already covers it at the layer where it is reachable.

Print `N/N OK` and exit 0; exit 1 naming every failed check.

- [ ] **Step 3: Run the smoke**

Run: `python scripts/smoke_s84a.py`
Expected: every check `OK`, the trailing `N/N OK` line, exit 0. Record the actual N in the commit message and the ROADMAP — a stale count in a commit subject has bitten this repo before (the S6.4 smoke commit says 12/12 for a 10/10 run).

- [ ] **Step 4: Run the regression smokes**

Run each of `scripts/smoke_s13.py`, `smoke_s41.py`, `smoke_s53.py`, `smoke_s64.py`, `smoke_s73.py`, `smoke_s81.py`, `smoke_s82.py`.
Expected: all green, exit 0. `smoke_s82` is the one at risk — it exercises org signup, which Task 8 changed.

- [ ] **Step 5: Run the full suite one final time**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add TENANCY.md scripts/smoke_s84a.py
git commit -m "docs(s84a): TENANCY.md + smoke_s84a (N/N -- use the REAL count)

Two orgs, one deduplicated candidate, proven over HTTP: a taken org name
is refused before any code is sent, neither org can read the other's
report, the 404 is byte-identical to an absent one, farm matches come back
redacted, and admin uploads stay unowned and invisible."
```

---

## Definition of done for Phase A

1. An organization that self-registers can upload a resume and read its fraud report without an operator touching anything.
2. Two organizations screening the same person cannot read each other's reports; the refusal is a 404 with a body identical to a genuinely absent report.
3. The scoping guard fails the build when an org handler reaches an unscoped read, is proven non-vacuous by a floor assertion, and has been watched going red.
4. Signing up with a taken organization name is refused with its own status at signup **and** at verify; every code failure remains one `invalid_code`.
5. Deleting an organization leaves its uploaded resumes and their candidates intact and unowned.
6. The admin plane is behaviourally unchanged and all its tests pass unmodified.
7. `pytest -q` green; `smoke_s84a` all checks OK, exit 0; all seven regression smokes green.
8. `TENANCY.md` written.

## Notes for the reviewer

Three things worth checking hardest, because they are where this sprint's defects would hide:

- **The `SET NULL` vs `CASCADE` choice** on both new FKs. A `CASCADE` typo passes every test except `test_deleting_an_org_leaves_the_resume_intact_and_unowned` and smoke check 12.
- **Whether `redact_for_org` is genuinely the only redaction path.** Grep for `resume_farm` in any org-reachable handler added here.
- **Whether the anti-enumeration property actually survived Task 8.** The question to ask is not "did we add a 409" but "can an attacker now learn whether an *address* has an account". If any signup response varies with the address, that is a Critical.
