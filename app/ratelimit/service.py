"""RateLimiter (S8.3 Phase A) -- the object every call site talks to.

It is called from the SERVICE layer, never from a route. AuthService's own
docstring gives the reason: "Every gate lives here rather than on a route ... a
rule applied at one entry point and not the other has shipped as a real defect
in S7.1, S7.2 and S7.3." The OTP surface is EIGHT routes across three planes
and exactly TWO service methods.

DUAL SCOPING is the whole design. A rule is evaluated against every scope it
declares, ALL of them are counted, and any single denial denies. Per-email
alone lets an attacker spray one guess across ten thousand addresses; per-IP
alone lets a botnet grind one address. Neither is a bound by itself.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping, Optional

from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.ratelimit.schema import (
    LimitDecision, LimitScope, RateRule, bucket_key, retry_after, window_start,
)
from app.ratelimit.store import RateLimitStore, build_rate_limit_store

log = get_logger(__name__)

_HOUR = 3600


class RateLimited(Exception):
    """A caller exceeded a rule.

    Carries what the HTTP layer needs and nothing that tells an attacker which
    of their assumptions was right -- the rule and scope go to the log, not to
    the response body.
    """

    def __init__(
        self,
        rule: str,
        scope: Optional[LimitScope],
        retry_after_seconds: int,
    ) -> None:
        super().__init__(
            f"rate limited by {rule}/{scope.value if scope else 'unknown'}"
        )
        self.rule = rule
        self.scope = scope
        self.retry_after_seconds = retry_after_seconds


class RateLimiter:
    def __init__(
        self, store: RateLimitStore, *, settings: Settings, metrics=None
    ) -> None:
        self._store = store
        self._settings = settings
        self._metrics = metrics

    def rules_for(self, name: str) -> list[RateRule]:
        """The configured rules under one name.

        KeyError for an unknown name -- a call site naming a rule that does not
        exist must fail loudly rather than silently limiting nothing.
        """
        s = self._settings
        table: dict[str, list[RateRule]] = {
            "login_request": [
                RateRule("login_request", s.rate_limit_login_per_hour_per_email,
                         _HOUR, LimitScope.EMAIL),
                RateRule("login_request", s.rate_limit_login_per_hour_per_ip,
                         _HOUR, LimitScope.IP),
            ],
            "login_verify": [
                RateRule("login_verify", s.rate_limit_verify_per_hour_per_email,
                         _HOUR, LimitScope.EMAIL),
                RateRule("login_verify", s.rate_limit_verify_per_hour_per_ip,
                         _HOUR, LimitScope.IP),
            ],
            "screening_process": [
                RateRule("screening_process", s.rate_limit_process_per_hour_per_org,
                         _HOUR, LimitScope.ORG),
            ],
            "asr_transcribe": [
                RateRule("asr_transcribe", s.rate_limit_asr_per_hour_per_candidate,
                         _HOUR, LimitScope.CANDIDATE),
            ],
            # S8.3 Phase B. ONE rule over BOTH candidate-plane request writes
            # (corrections and grievances). The spec sketched a grievance-only
            # rule; limiting one of two sibling doors is the defect shape this
            # file's own docstring names, so it is named for what it covers.
            "request_submit": [
                RateRule("request_submit",
                         s.rate_limit_request_per_hour_per_candidate,
                         _HOUR, LimitScope.CANDIDATE),
            ],
        }
        return table[name]

    def check(
        self,
        rules: list[RateRule],
        identities: Mapping[LimitScope, Optional[str]],
        *,
        now: datetime,
    ) -> LimitDecision:
        """Count this event against every rule and return the decision.

        EVERY scope is counted before returning, even after one has denied. A
        limiter that stops at the first denial under-reports the attacker who
        tripped it, and leaves the second scope's window looking clean to
        whoever reads the metrics.
        """
        if not self._settings.rate_limit_enabled:
            return LimitDecision(allowed=True, rule=rules[0].name if rules else "")

        denial: Optional[LimitDecision] = None
        for rule in rules:
            identity = identities.get(rule.scope)
            if not identity:
                # No IP is determinable under some ASGI transports. A partial
                # bound is correct; refusing a legitimate caller for a reason
                # they cannot act on is not.
                continue
            opened = window_start(now, rule.window_seconds)
            allowed = self._store.hit(
                bucket_key=bucket_key(
                    rule=rule.name, scope=rule.scope, identity=identity,
                    salt=self._settings.contact_hash_salt,
                ),
                window_start=opened,
                limit=rule.limit,
                expires_at=datetime.fromtimestamp(opened, tz=timezone.utc)
                + timedelta(seconds=rule.window_seconds),
            )
            self._count(rule, allowed)
            if not allowed and denial is None:
                denial = LimitDecision(
                    allowed=False,
                    rule=rule.name,
                    scope=rule.scope,
                    retry_after_seconds=retry_after(now, opened, rule.window_seconds),
                )
        if denial is not None:
            log.info(
                "rate_limited",
                rule=denial.rule,
                scope=denial.scope.value if denial.scope else None,
            )
            return denial
        return LimitDecision(allowed=True, rule=rules[0].name if rules else "")

    def enforce(
        self,
        rules: list[RateRule],
        identities: Mapping[LimitScope, Optional[str]],
        *,
        now: datetime,
    ) -> None:
        """:meth:`check`, raising :class:`RateLimited` on a denial.

        The test is `allowed` and NOTHING ELSE. This previously also required
        `decision.scope is not None`, which made a denial carrying no scope
        pass silently -- a fail-open reachable by any future change to `check`
        that forgot to set one, and silent in exactly the way an unbounded OTP
        endpoint is. `RateLimited` now carries an optional scope instead, so
        the missing information degrades a log line rather than a bound.
        """
        decision = self.check(rules, identities, now=now)
        if not decision.allowed:
            raise RateLimited(
                decision.rule, decision.scope, decision.retry_after_seconds
            )

    def _count(self, rule: RateRule, allowed: bool) -> None:
        if self._metrics is None:
            return
        self._metrics.increment(
            "rate_limit_decisions",
            rule=rule.name,
            scope=rule.scope.value,
            decision="allowed" if allowed else "denied",
        )


def build_rate_limiter(
    settings: Optional[Settings],
    session_factory: sessionmaker,
    *,
    metrics=None,
) -> RateLimiter:
    settings = settings or get_settings()
    return RateLimiter(
        build_rate_limit_store(session_factory), settings=settings, metrics=metrics
    )
