from datetime import datetime, timezone

from app.features.schema import FeatureVector
from app.features.training_schema import TrainingExample, TrainingLabel

T = datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_label_defaults_are_unobserved_and_not_withheld():
    lab = TrainingLabel()
    assert lab.hired is None and lab.outcome is None
    assert lab.coding_best_percentile is None and lab.event_at is None and lab.lag_days is None
    assert lab.observed is False and lab.withheld is False


def test_example_wraps_a_vector_and_label():
    fv = FeatureVector(candidate_id="c1", as_of=T, view_name="core_v1", view_version=1,
                       values={"candidate.num_skills": 3}, missing=())
    lab = TrainingLabel(hired=True, outcome="hired", event_at=T, lag_days=30.0, observed=True)
    ex = TrainingExample(vector=fv, label=lab)
    assert ex.vector.candidate_id == "c1"
    assert ex.label.hired is True and ex.label.outcome == "hired"
