"""Regression tests for the S7.3 whole-branch review.

Both findings are this codebase's recurring shapes, caught for the third sprint
running:

  A. A bound applied on one path and not the other (S7.2's `claim_ref`): the
     text channel capped answers at `interview_max_answer_chars`; the AUDIO
     channel stored whatever the provider returned, unbounded.
  B. A stored row that cannot be parsed bricking a candidate's own DPDP access
     forever (S7.2's `METHOD_LEVEL` KeyError): one malformed `assessment` JSON
     and every later read of /portal/me 500s.
"""

import base64
from datetime import datetime, timezone

from app.candidates.schema import (
    CandidateProfile, DateRange, ExperienceEntry, ExtractionResult, SkillItem,
)
from app.interview.models import InterviewSessionRow
from app.services.speech import Transcript
from tests.conftest import FakeSpeech, make_services

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
AUDIO_B64 = base64.b64encode(b"not-really-audio-but-valid-base64").decode()


def _ingest(services) -> str:
    profile = CandidateProfile(
        experience=[ExperienceEntry(employer="Acme Technologies",
                                    employer_canonical="Acme", title="ML Engineer",
                                    dates=DateRange(start="2021-03", end="2024-01"))],
        skills=[SkillItem(name="PyTorch", canonical="pytorch"),
                SkillItem(name="Spark", canonical="apache_spark")],
    )
    return services.candidates.ingest(
        ExtractionResult(profile=profile, method="heuristic"), "resume").candidate_id


class BerserkSpeech(FakeSpeech):
    """A provider that returns far more text than any answer should contain --
    a compromised vendor, a stuck decoder, or simply an hour-long recording."""

    async def atranscribe(self, *, audio_b64: str, mime: str) -> Transcript:
        self.calls.append((audio_b64, mime))
        return Transcript(text="word " * 400_000, model="berserk")


async def test_an_asr_transcript_is_bounded_like_a_typed_answer(settings):
    """FINDING A. The text channel refuses past interview_max_answer_chars, so
    the audio channel must not quietly store 2MB into the one Text column on
    the table."""
    services = make_services(settings, speech=BerserkSpeech(settings=settings))
    cid = _ingest(services)
    session = services.interview.start(cid, at=NOW)

    session, _ = await services.interview.answer(
        cid, session.id, question_id=session.questions[0].id,
        audio_b64=AUDIO_B64, mime="audio/wav", at=NOW,
    )
    stored = session.turns[0].transcript
    assert len(stored) <= settings.interview_max_answer_chars
    assert session.turns[0].score.codes  # the truncation is disclosed, not silent
    assert "transcript_truncated" in session.turns[0].score.codes


async def test_a_normal_transcript_is_not_truncated_or_flagged(settings):
    answer = "I rebuilt the ingestion path at Acme myself after the tokenizer change"
    services = make_services(settings, speech=FakeSpeech(text=answer,
                                                         settings=settings))
    cid = _ingest(services)
    session = services.interview.start(cid, at=NOW)
    session, _ = await services.interview.answer(
        cid, session.id, question_id=session.questions[0].id,
        audio_b64=AUDIO_B64, mime="audio/wav", at=NOW,
    )
    assert session.turns[0].transcript == answer
    assert "transcript_truncated" not in session.turns[0].score.codes


def test_an_unparseable_stored_assessment_never_bricks_the_portal(settings):
    """FINDING B. A row that cannot be parsed must degrade to "no assessment",
    never to a 500 on the candidate's own DPDP access -- the exact failure S7.2
    closed in compute_assurance, in its S7.3 clothing."""
    services = make_services(settings)
    cid = _ingest(services)
    session = services.interview.start(cid, at=NOW)

    # Simulate a future scorer writing a shape this code cannot read.
    with services.candidates._session_factory() as db:
        row = db.get(InterviewSessionRow, session.id)
        row.assessment = {"band": "deep"}          # missing required fields
        db.commit()

    my_data = services.portal.my_data(cid)          # must not raise
    assert len(my_data.interviews) == 1
    assert my_data.interviews[0].band.value == "insufficient_signal"

    reread = services.interview.get(cid, session.id, at=NOW)
    assert reread.assessment is None                # degraded, not fatal
    assert services.interview.list_for_candidate(cid, at=NOW)
