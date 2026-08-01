"""Deterministic interview question planning (S7.3). Pure: no I/O, no clock.

The primary source is the depth report's OWN probes -- the questions
`probe_generation` already wrote for claims the pipeline could not settle. That
is what makes this an interview about THIS candidate rather than a generic
question bank. A profile-templated bank fills the rest so a candidate with no
report is still interviewable, and a domain may contribute seed openers through
the DomainModel seam (this module never imports a concrete domain).

Ordering is deliberate and asserted by tests: a reviewer reading a session must
be able to see why each question was asked.
"""

from __future__ import annotations

import re
import uuid
from typing import Optional

from app.candidates.schema import CandidateProfile
from app.interview.schema import InterviewQuestion, QuestionSource
from app.schemas.report import Report

_WS = re.compile(r"\s+")

#: Markers a substantive engineering answer tends to contain. Used as the
#: expected_signals of template questions, which have no verdict behind them.
DEPTH_MARKERS: tuple[str, ...] = (
    "fail", "debug", "trade-off", "latency", "cost", "rollback",
)

#: More than two probes from one claim turns the interview into an
#: interrogation about a single line of the resume.
MAX_PROBES_PER_VERDICT = 2

EXPERIENCE_TEMPLATE = (
    "At {employer} you worked as {title}. Describe one specific problem you "
    "solved there: what broke, how you found the cause, and what you changed."
)
SKILL_TEMPLATE = (
    "You list {skill}. Walk through the hardest thing you have done with it: "
    "what you tried first, why it failed, and what you did instead."
)


class NothingToAskError(Exception):
    """Too little is on file to build a meaningful interview. Refusing beats
    conducting an empty one and then scoring the silence."""


def _norm(text: str) -> str:
    return _WS.sub(" ", text or "").strip().casefold()


def _probe_items(report: Optional[Report]) -> list[tuple[str, list[str], Optional[str]]]:
    if report is None:
        return []
    flagged = set(report.flagged_claim_ids)
    deferred = set(report.deferred_claim_ids)

    def rank(verdict) -> int:
        if verdict.claim_id in flagged:
            return 0
        if verdict.claim_id in deferred:
            return 1
        return 2

    items: list[tuple[str, list[str], Optional[str]]] = []
    # sorted() is stable, so within a rank group the report's own order holds.
    for verdict in sorted(report.verdicts, key=rank):
        for probe in verdict.probes[:MAX_PROBES_PER_VERDICT]:
            if probe and probe.strip():
                items.append(
                    (probe.strip(), list(verdict.missing_signals), verdict.claim_id)
                )
    return items


def _profile_items(
    profile: Optional[CandidateProfile],
) -> list[tuple[str, list[str], Optional[str]]]:
    if profile is None:
        return []
    items: list[tuple[str, list[str], Optional[str]]] = []
    for exp in profile.experience:
        employer = exp.employer_canonical or exp.employer
        if not employer:
            continue
        title = exp.title or "an engineer"
        items.append((
            EXPERIENCE_TEMPLATE.format(employer=employer, title=title),
            [employer, *DEPTH_MARKERS],
            None,
        ))
    for skill in profile.skills:
        name = skill.canonical or skill.name
        if not name:
            continue
        items.append((
            SKILL_TEMPLATE.format(skill=name), [name, *DEPTH_MARKERS], None,
        ))
    return items


def build_question_plan(
    *,
    profile: Optional[CandidateProfile],
    report: Optional[Report],
    domain,
    limit: int,
    minimum: int,
) -> list[InterviewQuestion]:
    """Ordered, deduped, capped plan. Raises NothingToAskError below `minimum`.

    `domain` is a DomainModel or None -- typed loosely on purpose so this module
    never imports the domain package's concrete classes.
    """
    seeds = list(domain.interview_seed_questions()) if domain is not None else []
    sourced: list[tuple[str, list[str], Optional[str], QuestionSource]] = [
        *[(t, s, c, QuestionSource.PROBE) for t, s, c in _probe_items(report)],
        *[(t, s, c, QuestionSource.PROFILE) for t, s, c in _profile_items(profile)],
        *[(t, [], None, QuestionSource.DOMAIN) for t in seeds],
    ]

    seen: set[str] = set()
    plan: list[InterviewQuestion] = []
    for text, signals, claim_id, source in sourced:
        key = _norm(text)
        if not key or key in seen:
            continue
        seen.add(key)
        plan.append(
            InterviewQuestion(
                id=f"q_{uuid.uuid4().hex[:10]}",
                sequence=len(plan) + 1,
                text=text,
                source=source,
                expected_signals=[s for s in dict.fromkeys(signals) if s],
                claim_id=claim_id,
            )
        )
        if len(plan) >= limit:
            break

    if len(plan) < minimum:
        raise NothingToAskError(
            f"only {len(plan)} question(s) available; {minimum} required. "
            "Add a resume or run a depth evaluation first."
        )
    return plan
