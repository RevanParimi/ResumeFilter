"""Advisory proxy-risk signals for an interview (S7.3). Pure: no I/O, no clock
(every rate comes from the turns' own asked_at/answered_at).

What this is NOT: voice biometrics. Comparing voiceprints across sessions would
require storing a voice embedding -- exactly the artifact class S7.1 made
structurally impossible -- and would need its own consent purpose and its own
legal review. The roadmap asked for "proxy-detection hooks reading
IdentityAssurance", and that is precisely what this is: the assurance level held
when the session STARTED, plus behaviour visible in the timing and wording of
the answers.

Nothing here can confirm a proxy, so ProxyBand stops at `elevated` and no
finding may be `hard`. Escalation needs TWO soft findings -- the S2.4 AND-gate,
so one noisy signal cannot brand anyone.
"""

from __future__ import annotations

from typing import Sequence

from app.core.config import Settings
from app.fabrication import ai_text
from app.interview.schema import (
    AnswerChannel, InterviewTurn, ProxyBand, ProxyFinding, ProxyRisk,
)
from app.verification.schema import AssuranceLevel, IdentityAssurance

ASSURANCE_NONE = "identity_assurance_none"
ASSURANCE_LOW = "identity_assurance_low"
RATE_IMPLAUSIBLE = "answer_rate_implausible"
TYPED_RATE_IMPLAUSIBLE = "typed_answer_rate_implausible"
AI_STYLE = "answer_style_ai_generated"
TEXT_ONLY = "text_channel_only"


def _elapsed_seconds(turn: InterviewTurn) -> float:
    delta = (turn.answered_at - turn.asked_at).total_seconds()
    return max(delta, 1.0)   # never divide by zero; sub-second is already extreme


def assess_proxy_risk(
    *,
    assurance: IdentityAssurance,
    turns: Sequence[InterviewTurn],
    settings: Settings,
) -> ProxyRisk:
    findings: list[ProxyFinding] = []

    level = int(assurance.level) if assurance is not None else 0
    if level <= int(AssuranceLevel.NONE):
        findings.append(ProxyFinding(
            id=ASSURANCE_NONE, severity="soft",
            message="nothing verifies who is taking this interview",
            detail={"assurance_level": level},
        ))
    elif level == int(AssuranceLevel.SELF_ATTESTED):
        findings.append(ProxyFinding(
            id=ASSURANCE_LOW, severity="info",
            message="identity is self-attested only",
            detail={"assurance_level": level},
        ))

    audio = [t for t in turns if t.channel is AnswerChannel.AUDIO]
    text = [t for t in turns if t.channel is AnswerChannel.TEXT]

    fast_audio = [
        t for t in audio
        if t.word_count / _elapsed_seconds(t) > settings.interview_max_words_per_second
    ]
    if fast_audio:
        findings.append(ProxyFinding(
            id=RATE_IMPLAUSIBLE, severity="soft",
            message="one or more answers arrived faster than they could be spoken",
            detail={"turns": len(fast_audio)},
        ))

    fast_text = [
        t for t in text
        if t.word_count / _elapsed_seconds(t)
        > settings.interview_max_typed_words_per_second
    ]
    if fast_text:
        findings.append(ProxyFinding(
            id=TYPED_RATE_IMPLAUSIBLE, severity="soft",
            message="one or more typed answers arrived faster than they could be typed",
            detail={"turns": len(fast_text)},
        ))

    if turns:
        joined = "\n".join(t.transcript for t in turns if t.transcript)
        style = ai_text.assess_deterministic(joined)
        # The same conservatism ai_text.band_for applies to resumes: at least
        # two independent tells before the word "generated" is used at all.
        if len(style.signals) >= 2 and style.likelihood >= settings.ai_likely_threshold:
            findings.append(ProxyFinding(
                id=AI_STYLE, severity="soft",
                message="answer wording carries several machine-generated tells",
                detail={"tells": len(style.signals)},
            ))

    if turns and not audio:
        findings.append(ProxyFinding(
            id=TEXT_ONLY, severity="info",
            message="every answer was typed; voice-based proxy signals are unavailable",
            detail={"turns": len(text)},
        ))

    soft = sum(1 for f in findings if f.severity == "soft")
    band = (
        ProxyBand.ELEVATED if soft >= 2
        else ProxyBand.MODERATE if soft == 1
        else ProxyBand.LOW
    )
    return ProxyRisk(band=band, findings=findings, assurance_level_at_start=level)
