"""Question planning: probes first, then profile templates, then domain seeds.
Pure and deterministic -- ordering is asserted because a reviewer reading a
session must be able to tell WHY each question was asked."""

import pytest

from app.candidates.schema import CandidateProfile, ExperienceEntry, SkillItem
from app.domains.base import get_domain, list_domains
from app.interview.questions import NothingToAskError, build_question_plan
from app.interview.schema import QuestionSource
from app.schemas.report import CoherenceVerdict, Report, VerdictStatus


def _profile() -> CandidateProfile:
    return CandidateProfile(
        experience=[ExperienceEntry(employer="Acme Technologies Pvt Ltd",
                                    employer_canonical="Acme Technologies",
                                    title="ML Engineer")],
        skills=[SkillItem(name="PyTorch", canonical="pytorch")],
    )


def _report() -> Report:
    verdicts = [
        CoherenceVerdict(claim_id="cl_flagged", claim_text="fine-tuned a 70B",
                         claim_type="fine_tuning", status=VerdictStatus.INCOHERENT,
                         missing_signals=["gpu hours", "dataset size"],
                         probes=["Which GPUs, and for how many hours?",
                                 "How large was the dataset?"]),
        CoherenceVerdict(claim_id="cl_plain", claim_text="built a RAG app",
                         claim_type="rag", status=VerdictStatus.COHERENT,
                         probes=["Which vector store?"]),
        CoherenceVerdict(claim_id="cl_deferred", claim_text="ran evals",
                         claim_type="evaluation", status=VerdictStatus.DEFER,
                         missing_signals=["metric"], probes=["Which metric moved?"]),
    ]
    return Report(verdicts=verdicts, flagged_claim_ids=["cl_flagged"],
                  deferred_claim_ids=["cl_deferred"])


def test_probes_come_first_and_flagged_before_deferred_before_the_rest():
    plan = build_question_plan(profile=_profile(), report=_report(),
                               domain=None, limit=8, minimum=1)
    probe_texts = [q.text for q in plan if q.source is QuestionSource.PROBE]
    assert probe_texts[0].startswith("Which GPUs")
    assert probe_texts.index("Which metric moved?") < probe_texts.index("Which vector store?")
    assert plan[0].source is QuestionSource.PROBE


def test_a_probe_carries_its_verdicts_missing_signals_as_expected_signals():
    plan = build_question_plan(profile=_profile(), report=_report(),
                               domain=None, limit=8, minimum=1)
    first = plan[0]
    assert first.claim_id == "cl_flagged"
    assert first.expected_signals == ["gpu hours", "dataset size"]


def test_at_most_two_probes_per_verdict():
    verdict = CoherenceVerdict(claim_id="c", claim_text="t", claim_type="rag",
                               probes=["p1", "p2", "p3", "p4"])
    plan = build_question_plan(profile=None, report=Report(verdicts=[verdict]),
                               domain=None, limit=8, minimum=1)
    assert [q.text for q in plan] == ["p1", "p2"]


def test_profile_templates_fill_in_and_name_the_employer_and_skill():
    plan = build_question_plan(profile=_profile(), report=None,
                               domain=None, limit=8, minimum=1)
    assert all(q.source is QuestionSource.PROFILE for q in plan)
    assert "Acme Technologies" in plan[0].text
    assert "ML Engineer" in plan[0].text
    assert "Acme Technologies" in plan[0].expected_signals
    assert any("pytorch" in q.text for q in plan)


def test_domain_seeds_come_last_and_come_from_the_registry():
    plan = build_question_plan(profile=_profile(), report=None,
                               domain=get_domain("genai"), limit=8, minimum=1)
    assert plan[-1].source is QuestionSource.DOMAIN


def test_duplicate_question_text_is_deduped_case_and_space_insensitively():
    verdicts = [CoherenceVerdict(claim_id="a", claim_text="t", claim_type="rag",
                                 probes=["Which vector store?"]),
                CoherenceVerdict(claim_id="b", claim_text="t", claim_type="rag",
                                 probes=["which   VECTOR store?"])]
    plan = build_question_plan(profile=None, report=Report(verdicts=verdicts),
                               domain=None, limit=8, minimum=1)
    assert len(plan) == 1


def test_plan_is_capped_and_sequences_are_1_based_and_contiguous():
    plan = build_question_plan(profile=_profile(), report=_report(),
                               domain=get_domain("genai"), limit=3, minimum=1)
    assert len(plan) == 3
    assert [q.sequence for q in plan] == [1, 2, 3]


def test_too_little_on_file_refuses_rather_than_building_an_empty_interview():
    with pytest.raises(NothingToAskError):
        build_question_plan(profile=CandidateProfile(), report=None,
                            domain=None, limit=8, minimum=3)


def test_a_blank_probe_is_skipped_not_asked():
    verdict = CoherenceVerdict(claim_id="c", claim_text="t", claim_type="rag",
                               probes=["   ", "real question?"])
    plan = build_question_plan(profile=None, report=Report(verdicts=[verdict]),
                               domain=None, limit=8, minimum=1)
    assert [q.text for q in plan] == ["real question?"]


def test_every_registered_domain_answers_the_seed_question_seam():
    for key in list_domains():
        seeds = get_domain(key).interview_seed_questions()
        assert isinstance(seeds, list)
        assert all(isinstance(s, str) and s.strip() for s in seeds)
