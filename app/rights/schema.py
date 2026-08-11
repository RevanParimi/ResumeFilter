"""DPDP rights contracts (S8.3 Phase B). Pure Pydantic + StrEnum -- no I/O.

A correction is a REVIEWED REQUEST, never a self-service edit (spec 0.3). On a
fraud-screening platform, giving the subject a write path onto the data the risk
score is computed from is giving them an edit box over the evidence -- and the
subject of a correction request is exactly the person with an incentive to edit
a claim that got flagged. DPDP permits the fiduciary to verify before
correcting; what must exist is the MECHANISM -- request, review, decide, record,
disclose -- and it exists here for all four fields. Auto-apply is a convenience
for the one field where it is safe, and the refusal names its own reason.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel


class RequestKind(StrEnum):
    CORRECTION = "correction"
    GRIEVANCE = "grievance"


class RequestStatus(StrEnum):
    """What the OPERATOR decided.

    Whether stored data actually changed is ``applied``, a separate column:
    false for every grievance, false for a resolved `email` correction handled
    out of band, true only when a value was written.
    """

    OPEN = "open"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class CorrectionField(StrEnum):
    FULL_NAME = "full_name"
    EMAIL = "email"
    PHONE = "phone"
    OTHER = "other"


class ResolvedBy(StrEnum):
    """WHO decided, as a kind rather than an identity.

    The S8.5 ``recorded_by`` argument one table over: the shared admin key has
    no human behind it, so a null ``resolved_by_admin_user_id`` on its own
    would conflate "an operator used the machine credential" with "the admin
    who decided this has since been deleted".
    """

    OPERATOR_KEY = "operator_key"
    ADMIN_USER = "admin_user"


#: The ONLY field a resolution may write automatically. `full_name` is a plain
#: column with no identity semantics. `email`/`phone` are hashed into the dedup
#: keys `_resolve_candidate` matches on and `email_hash` is the portal login
#: credential, so changing either is an identity operation that can collide two
#: candidate rows or move an account's login address. `other` is free text
#: nobody can map to a column.
AUTO_APPLIABLE_FIELDS: frozenset[CorrectionField] = frozenset(
    {CorrectionField.FULL_NAME}
)


class RequestRefused(Exception):
    """The request or the resolution is not permissible.

    Carries the reason, because a refusal a subject (or an operator) cannot act
    on is not a mechanism.
    """


class RequestAlreadyResolved(RequestRefused):
    """A second decision on a request that already has one.

    Its own type, not a message: the HTTP layer answers 409 here and 422 for
    every other refusal, and choosing between them by matching on message text
    is a translation that breaks the first time somebody rewords a sentence.
    """


class RequestView(BaseModel):
    """One request as its subject sees it -- and as the operator lists it.

    ONE shape for both planes: the operator's view of a person's complaint
    should not be able to drift from what that person is shown.

    ``resolved_by`` names the KIND of decider and never the person: "a platform
    operator decided this" is what the subject is owed; an admin's identity is
    not theirs to have.
    """

    id: str
    kind: RequestKind
    status: RequestStatus
    applied: bool = False
    field: Optional[CorrectionField] = None
    #: What the row said WHEN THE REQUEST WAS FILED. The operator reviews the
    #: pair the subject actually saw, not whatever the row says by the time
    #: somebody gets to it.
    current_value: str = ""
    requested_value: str = ""
    note: str = ""
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolution: str = ""
    resolved_by: Optional[ResolvedBy] = None


class GrievanceContact(BaseModel):
    """The published grievance mechanism.

    DPDP requires it to be PUBLISHED, so ``GET /grievance`` is in
    ``PUBLIC_PATHS``: a contact reachable only after login is not reachable by
    someone whose complaint is that they cannot log in.
    """

    name: str = ""
    email: str = ""
    phone: str = ""
    response_days: int = 30
