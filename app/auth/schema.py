"""Auth contracts (S8.2). Pure Pydantic + StrEnum -- no I/O, no ORM.

`Principal` is the single answer to "who is calling?" for all three planes. It
deliberately carries HOW it was established (`via`) as well as who: CSRF
enforcement keys on that field, and an exemption written against "was a header
present?" instead lets a browser carrying a session cookie plus an
attacker-supplied X-Org-Key skip the check entirely.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel


class PrincipalKind(StrEnum):
    CANDIDATE = "candidate"
    ORG = "org"
    ADMIN = "admin"


class PrincipalVia(StrEnum):
    """How the principal was established. SESSION is the stricter one: it is
    cookie-borne, therefore forgeable cross-site, therefore CSRF-checked."""

    SESSION = "session"
    KEY = "key"


class AuthPlane(StrEnum):
    """Which login surface a challenge belongs to.

    Challenges are scoped by plane because one address can legitimately be both
    a candidate and an org user; collapsing them would let activity on one plane
    lock the other out.
    """

    CANDIDATE = "candidate"
    ORG = "org"
    ADMIN = "admin"


class LoginPurpose(StrEnum):
    SIGNUP = "signup"
    LOGIN = "login"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    IDLE_EXPIRED = "idle_expired"
    REVOKED = "revoked"


class OrgUserRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class Principal(BaseModel):
    """Who is calling, and how.

    `org_user_id` / `admin_user_id` being None is what distinguishes a machine
    caller from a named human -- which is the whole point of giving the admin
    plane real operator accounts (PI-8 decision 0.5): a shared secret cannot
    attribute an action to a person.
    """

    kind: PrincipalKind
    via: PrincipalVia
    candidate_id: Optional[str] = None
    org_id: Optional[str] = None
    org_user_id: Optional[str] = None
    admin_user_id: Optional[str] = None
    session_id: Optional[str] = None


class SessionView(BaseModel):
    """A session as its own owner sees it.

    Carries no token and no hash: this is returned to GET /auth/sessions and to
    the DPDP portal, and neither is a place to hand back credentials.
    """

    id: str
    issued_at: datetime
    expires_at: datetime
    last_seen_at: datetime
    status: SessionStatus
    user_agent: Optional[str] = None
    current: bool = False   # is this the session making the request?


class OrgUser(BaseModel):
    id: str
    organization_id: str
    email_hash: str
    role: OrgUserRole = OrgUserRole.MEMBER
    created_at: datetime
    disabled_at: Optional[datetime] = None


class AdminUser(BaseModel):
    """A platform operator. No organization: operators act on the platform, not
    within a tenant, and they are not data principals in the DPDP sense."""

    id: str
    email_hash: str
    label: str = ""
    created_at: datetime
    disabled_at: Optional[datetime] = None
