from datetime import datetime, timezone
from app.core.config import Settings
from app.features import default_view, get_feature_registry
from app.features.schema import FeatureContext


def _settings():
    return Settings(_env_file=None, openrouter_api_key="")


def test_default_view_covers_every_registered_feature():
    reg = get_feature_registry()
    view = default_view(reg, settings=_settings())
    assert view.name == "core_v1"
    assert {n for n, _ in view.members} == set(reg.names())
    assert len(reg.names()) >= 25          # seed catalog breadth


def test_consent_flag_matches_source():
    reg = get_feature_registry()
    for spec in reg.specs():
        expect = spec.source.value in ("ledger", "reputation")
        assert spec.requires_consent is expect


def test_manifest_json_roundtrips():
    import json
    reg = get_feature_registry()
    data = json.loads(reg.manifest_json())
    assert len(data) == len(reg.names())
    assert all("dtype" in row and "requires_consent" in row for row in data)


def test_compute_view_on_empty_context_is_well_formed():
    reg = get_feature_registry()
    view = default_view(reg, settings=_settings())
    ctx = FeatureContext(candidate_id="c1", as_of=datetime(2026, 1, 1, tzinfo=timezone.utc))
    fv = reg.compute_view(view, ctx)         # raises if any output violates its spec
    # ledger counts default to 0 (nullable=False); candidate/depth features missing
    assert fv.values["ledger.interview_record_count"] == 0
    assert fv.values["reputation.band"] == "insufficient_data"
    assert "candidate.years_experience" in fv.missing


def test_feat_default_view_setting_present():
    assert _settings().feat_default_view == "core_v1"
