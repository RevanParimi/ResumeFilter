"""RightsService (S8.3 Phase B) -- request, review, decide, record, disclose.

THE LOAD-BEARING RULE: a correction NEVER rewrites an extraction. An
``extractions`` row is a record of what a document said; rewriting it destroys
the evidence the fraud screen is computed from, and on this product that is not
hypothetical -- the subject of a correction request is exactly the person with
an incentive to edit a claim that got flagged. A resolved correction may touch
the candidate's own identity columns and nothing else (spec §8.2).

Every gate lives HERE rather than on a route, for the reason AuthService's own
docstring gives: a rule applied at one entry point and not the other has
shipped as a real defect in S7.1, S7.2, S7.3 and S8.4 Phase B. Two candidate
doors and two admin doors go through these four methods.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.candidates.store import CandidateStore
from app.core.config import Settings, get_settings
from app.ledger.store import LedgerStore
from app.ratelimit.schema import LimitScope
from app.ratelimit.service import RateLimiter
from app.rights.schema import (
    AUTO_APPLIABLE_FIELDS,
    CorrectionField,
    RequestAlreadyResolved,
    RequestKind,
    RequestRefused,
    RequestStatus,
    RequestView,
    ResolvedBy,
)
from app.rights.store import RightsStore


class RightsService:
    def __init__(
        self,
        store: RightsStore,
        candidates: CandidateStore,
        ledger: LedgerStore,
        *,
        limiter: RateLimiter,
        settings: Settings,
    ) -> None:
        self._store = store
        self._candidates = candidates
        self._ledger = ledger
        # REQUIRED, never Optional-with-a-default. Under a default the tests
        # that construct this service directly would keep passing while running
        # UNLIMITED, which is the entire failure mode (S8.3 Phase A).
        self._limiter = limiter
        self._settings = settings

    # -- the subject's side ---------------------------------------------------

    def submit(
        self,
        candidate_id: str,
        *,
        kind: RequestKind,
        field: Optional[CorrectionField],
        requested_value: str,
        note: str,
        now: datetime,
    ) -> RequestView:
        """File a correction or a grievance.

        THE LIMIT IS CHARGED FIRST, BEFORE VALIDATION, and that ordering is a
        trade-off rather than an oversight. Charging only valid requests would
        leave an endpoint a stuck client can hammer forever with a body that
        never validates -- bounding the successful call is not bounding the
        caller. The cost is that a typo spends one of ten complaints an hour,
        which is the smaller harm; a test pins both halves.
        """
        self._limiter.enforce(
            self._limiter.rules_for("request_submit"),
            {LimitScope.CANDIDATE: candidate_id},
            now=now,
        )

        note = (note or "").strip()
        requested_value = (requested_value or "").strip()
        cap = self._settings.max_request_note_chars
        if len(note) > cap:
            raise RequestRefused(f"note exceeds {cap} characters")
        if len(requested_value) > cap:
            raise RequestRefused(f"requested_value exceeds {cap} characters")

        if kind is RequestKind.GRIEVANCE:
            if not note:
                raise RequestRefused("a grievance needs a note describing it")
            # A grievance is about HANDLING, not about a field. Carrying one
            # would invite an operator to "apply" it.
            field = None
            requested_value = ""
        else:
            if field is None:
                raise RequestRefused("a correction must name a field")
            if field is CorrectionField.OTHER:
                if not note:
                    # `other` can never be auto-applied, so the note IS the
                    # request -- without it the row names a field nobody can
                    # act on.
                    raise RequestRefused(
                        "a correction to 'other' must explain what is wrong"
                    )
            elif not requested_value:
                raise RequestRefused("a correction must say what it should be")

        view = self._store.create(
            candidate_id,
            kind=kind,
            field=field,
            current_value=self._current_value(candidate_id, field),
            requested_value=requested_value,
            note=note,
        )
        self._ledger.audit_request_event(
            candidate_id,
            request_id=view.id,
            action="request.submit",
            actor_type="candidate",
            actor_id=candidate_id,
            details={"kind": kind.value, "field": field.value if field else None},
        )
        return view

    def for_candidate(self, candidate_id: str) -> list[RequestView]:
        return self._store.for_candidate(candidate_id)

    # -- the operator's side --------------------------------------------------

    def list_by_status(
        self, status: Optional[RequestStatus], limit: int
    ) -> list[RequestView]:
        return self._store.list_by_status(status, limit)

    def resolve(
        self,
        request_id: str,
        *,
        status: RequestStatus,
        resolution: str,
        apply: bool,
        resolved_by: ResolvedBy,
        admin_user_id: Optional[str],
        now: datetime,
    ) -> RequestView:
        """Decide one request. NOT rate-limited: the bound exists for the door
        a stuck client loops on, and an operator clearing a backlog of a
        hundred complaints is the behaviour we want.

        Every refusal below is raised BEFORE the store write, so a rejected
        decision leaves the request open for a correct one.
        """
        found = self._store.get(request_id)
        if found is None:
            raise LookupError(f"unknown request: {request_id}")
        view, candidate_id = found

        resolution = (resolution or "").strip()
        if not resolution:
            # DPDP's mechanism is request-review-decide-RECORD-disclose. A
            # decision with no written reason is one the subject cannot act on,
            # which is the one thing a grievance process must never be.
            raise RequestRefused("a decision must carry a written reason")
        if len(resolution) > self._settings.max_request_note_chars:
            raise RequestRefused(
                f"resolution exceeds {self._settings.max_request_note_chars} characters"
            )

        if apply:
            if view.kind is RequestKind.GRIEVANCE:
                raise RequestRefused(
                    "a grievance has nothing to apply -- it is about handling, "
                    "not about a stored value"
                )
            if status is not RequestStatus.RESOLVED:
                raise RequestRefused(
                    "a rejected request cannot also be applied -- the subject "
                    "would read the written value as an approval"
                )
            if view.field not in AUTO_APPLIABLE_FIELDS:
                raise RequestRefused(self._why_not_appliable(view.field))

        if not self._store.resolve(
            request_id,
            status=status,
            resolution=resolution,
            applied=apply,
            resolved_by=resolved_by,
            resolved_by_admin_user_id=admin_user_id,
            now=now,
        ):
            # VERIFIED AFTER THE FACT rather than assumed from the False: the
            # conditional UPDATE also misses when the row is gone entirely,
            # which happens when the subject's erasure CASCADEs mid-decision.
            # Reporting that as "already resolved" would send an operator
            # looking for a decision nobody made (the save()/SubjectErasedError
            # precedent, S8.5).
            if self._store.get(request_id) is None:
                raise LookupError(f"unknown request: {request_id}")
            raise RequestAlreadyResolved(
                "this request already has a decision recorded"
            )

        if apply and not self._candidates.apply_correction(
            candidate_id, full_name=view.requested_value
        ):
            # The candidate was erased between the decision and the write. The
            # request row went with them (CASCADE), so 404 is by then simply
            # true -- the S8.5 posture on a vanished subject.
            raise LookupError(f"unknown request: {request_id}")

        self._ledger.audit_request_event(
            candidate_id,
            request_id=request_id,
            action="request.resolve",
            actor_type="system",
            actor_id=admin_user_id or "platform",
            details={
                "status": status.value,
                "applied": apply,
                "resolved_by": resolved_by.value,
            },
        )
        decided = self._store.get(request_id)
        # Only reachable if the subject erased themselves in the microseconds
        # since the audit write; the same 404 applies.
        if decided is None:  # pragma: no cover - defended, not reachable in tests
            raise LookupError(f"unknown request: {request_id}")
        return decided[0]

    # -- helpers --------------------------------------------------------------

    def _current_value(
        self, candidate_id: str, field: Optional[CorrectionField]
    ) -> str:
        """What the row says RIGHT NOW, frozen into the request.

        Only ``full_name`` has an answer. We hold ``email_hash`` and
        ``phone_hash``, never the address or the number, so echoing a blank is
        honest -- inventing one, or reflecting the requested value back as
        "current", would put a fabricated fact in front of the operator who
        decides.
        """
        if field is not CorrectionField.FULL_NAME:
            return ""
        summary = self._candidates.get_candidate(candidate_id)
        return (summary.full_name or "") if summary else ""

    @staticmethod
    def _why_not_appliable(field: Optional[CorrectionField]) -> str:
        if field is CorrectionField.EMAIL:
            return (
                "an email correction cannot be applied automatically: "
                "email_hash is both a candidate dedup key and the portal login "
                "credential, so changing it can merge two people's records or "
                "move an account's login address. Resolve it by hand, after an "
                "identity check, and record what was done."
            )
        if field is CorrectionField.PHONE:
            return (
                "a phone correction cannot be applied automatically: "
                "phone_hash is a candidate dedup key, so changing it can merge "
                "two people's records. Resolve it by hand and record what was "
                "done."
            )
        return (
            "this correction cannot be applied automatically -- it names no "
            "single stored field. Resolve it by hand and record what was done."
        )


def build_rights_service(
    settings: Optional[Settings] = None,
    *,
    store: RightsStore,
    candidates: CandidateStore,
    ledger: LedgerStore,
    limiter: RateLimiter,
) -> RightsService:
    return RightsService(
        store, candidates, ledger, limiter=limiter,
        settings=settings or get_settings(),
    )
