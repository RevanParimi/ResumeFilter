# S2.4 — Unified fabrication_risk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fuse the three PI-2 fabrication assessments (`ai_generation` ⊕ `cross_field` ⊕ `resume_farm`) into one unified advisory `fabrication_risk` assessment, computed in the calibration stage (scoring node) and surfaced on the Report + flywheel — still advisory, never auto-reject, depth evaluation untouched.

**Architecture:** A new pure, deterministic module `app/fabrication/risk.py` maps each subsystem's *band* to a component risk value, fuses evaluable components with a 70/30 weighted-mean/max blend, and bands the result conservatively. The scoring node (where calibration already runs) calls it and writes `state.fabrication_risk`; the report node attaches it to `Report.fabrication_risk`, adds a summary note on the two upper bands, and logs one flywheel record. No LLM, no migration, no new tables.

**Tech Stack:** Python 3.12, Pydantic v2, LangGraph, pytest (offline, NullLLM/fakes from `tests/conftest.py`), uvicorn + httpx for the smoke.

**Branch:** `s24-fabrication-risk` (create from `main` before Task 1: `git checkout -b s24-fabrication-risk`)

**Test count:** 312 green today → ~345 expected.

## Global Constraints

- Advisory only — fabrication_risk never changes `VerdictStatus`, `depth_score`, `depth_band`, or produces an auto-reject. Every assessment carries `advisory: true` and reviewer copy saying "never a rejection signal".
- Conservative by construction — ELEVATED requires ≥ 2 components at their top band; fusion over a single subsystem never asserts (coverage confidence 0.45 < `fr_min_confidence` 0.50 ⇒ INSUFFICIENT_DATA).
- Deterministic, offline — no LLM anywhere in S2.4; all tests run with NullLLM.
- Tunables in `config.yaml` (`fr_*` keys, no `DEE_` prefix in YAML); band→risk mapping and the 70/30 blend are **code constants** (like S2.2's severity escalations — change deliberately).
- Absent/insufficient subsystem signals are **excluded** from fusion, never counted as evidence of risk.
- Commit messages: plain conventional commits, **no Co-Authored-By trailer**.
- `pytest -q` must be green at every commit.

## File Structure

- Create: `app/fabrication/risk.py` — band→risk mapping, `build_components`, `fuse_components`, `band_for_risk`, `assess_fabrication_risk`. One responsibility: pure fusion math.
- Modify: `app/schemas/fabrication.py` — add `FabricationRiskBand`, `RiskComponent`, `FabricationRiskAssessment`.
- Modify: `app/core/config.py` + `config.yaml` — `fr_*` knobs.
- Modify: `app/graph/state.py` — `fabrication_risk` field (written once, by scoring).
- Modify: `app/graph/nodes/scoring.py` — compute fusion after `aggregate_depth`.
- Modify: `app/graph/nodes/report.py` — attach field, summary note, flywheel record.
- Modify: `app/schemas/report.py` — `Report.fabrication_risk: Optional[...]`.
- Create: `scripts/smoke_s24.py` — uvicorn smoke on fixtures.
- Modify: `FABRICATION.md` — S2.4 section + tables.
- Tests: `tests/test_fabrication_risk_schema.py`, `tests/test_fabrication_risk.py`, `tests/test_scoring_fabrication_risk.py`, `tests/test_report_fabrication_risk.py`, `tests/test_fabrication_risk_integration.py`.

---

### Task 1: S2.4 contracts — FabricationRiskBand / RiskComponent / FabricationRiskAssessment

**Files:**
- Modify: `app/schemas/fabrication.py` (append at end of file)
- Test: `tests/test_fabrication_risk_schema.py`

**Interfaces:**
- Consumes: nothing new (extends the existing fabrication contracts module).
- Produces: `FabricationRiskBand` (StrEnum: `INSUFFICIENT_DATA/LOW/MODERATE/ELEVATED`), `RiskComponent {id: str, band: str, risk: float, confidence: float, weight: float, flagged: bool}`, `FabricationRiskAssessment {score, confidence, band, components: list[RiskComponent], reasoning, advisory=True}`. Later tasks import all three from `app.schemas.fabrication`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fabrication_risk_schema.py`:

```python
"""S2.4 contracts: unified fabrication-risk band + assessment schema."""

import pytest
from pydantic import ValidationError

from app.schemas.fabrication import (
    FabricationRiskAssessment,
    FabricationRiskBand,
    RiskComponent,
)


def test_band_values():
    assert FabricationRiskBand.INSUFFICIENT_DATA == "insufficient_data"
    assert FabricationRiskBand.LOW == "low"
    assert FabricationRiskBand.MODERATE == "moderate"
    assert FabricationRiskBand.ELEVATED == "elevated"


def test_component_bounds():
    c = RiskComponent(id="resume_farm", band="near_duplicate", risk=0.8, confidence=0.7, weight=0.7)
    assert c.flagged is False  # default
    with pytest.raises(ValidationError):
        RiskComponent(id="x", band="b", risk=1.2, confidence=0.5, weight=0.5)
    with pytest.raises(ValidationError):
        RiskComponent(id="x", band="b", risk=0.5, confidence=0.5, weight=-0.1)


def test_assessment_defaults_are_conservative():
    a = FabricationRiskAssessment()
    assert a.band is FabricationRiskBand.INSUFFICIENT_DATA
    assert a.score == 0.0 and a.confidence == 0.0
    assert a.components == []
    assert a.advisory is True


def test_assessment_round_trips_json():
    a = FabricationRiskAssessment(
        score=0.55,
        confidence=0.75,
        band=FabricationRiskBand.MODERATE,
        components=[RiskComponent(id="cross_field", band="major_issues", risk=0.75, confidence=0.75, weight=0.75, flagged=True)],
        reasoning="r",
    )
    again = FabricationRiskAssessment.model_validate_json(a.model_dump_json())
    assert again == a


def test_score_and_confidence_bounded():
    with pytest.raises(ValidationError):
        FabricationRiskAssessment(score=1.5)
    with pytest.raises(ValidationError):
        FabricationRiskAssessment(confidence=-0.1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_fabrication_risk_schema.py -q`
Expected: FAIL — `ImportError: cannot import name 'FabricationRiskBand'`

- [ ] **Step 3: Implement — append to `app/schemas/fabrication.py`**

```python
class FabricationRiskBand(StrEnum):
    """S2.4 — conservative advisory bands. INSUFFICIENT_DATA when we can't say."""

    INSUFFICIENT_DATA = "insufficient_data"
    LOW = "low"
    MODERATE = "moderate"
    ELEVATED = "elevated"


class RiskComponent(BaseModel):
    """One subsystem's contribution to the unified fabrication risk."""

    id: str          # "ai_generation" | "cross_field" | "resume_farm"
    band: str        # the component's own band value at fusion time
    risk: float = Field(ge=0.0, le=1.0)        # band-mapped component risk
    confidence: float = Field(ge=0.0, le=1.0)  # component's own confidence
    weight: float = Field(ge=0.0)              # config weight x confidence
    flagged: bool = False                      # component sits at its top band


class FabricationRiskAssessment(BaseModel):
    """S2.4 — unified advisory fusion of ai_generation + cross_field + resume_farm.

    Computed in the calibration stage (scoring node). ADVISORY ONLY: never
    changes verdicts, depth scores, or bands, and never a rejection signal."""

    score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    band: FabricationRiskBand = FabricationRiskBand.INSUFFICIENT_DATA
    components: list[RiskComponent] = Field(default_factory=list)
    reasoning: str = ""
    advisory: bool = True  # mirrors Report: never a rejection signal
```

Also update the module docstring's sprint list at the top of `app/schemas/fabrication.py`: add the line `S2.4 — unified fabrication risk: advisory fusion of the three signals above.`

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fabrication_risk_schema.py -q` → all pass.
Run: `pytest -q` → 312 + 5 pass, no regressions.

- [ ] **Step 5: Commit**

```bash
git add app/schemas/fabrication.py tests/test_fabrication_risk_schema.py
git commit -m "feat(fabrication): S2.4 contracts - FabricationRiskBand, RiskComponent, FabricationRiskAssessment"
```

---

### Task 2: Config knobs (`fr_*`) + component construction

**Files:**
- Create: `app/fabrication/risk.py`
- Modify: `app/core/config.py` (after the `rf_*` block, ~line 165)
- Modify: `config.yaml` (after the S2.3 block, ~line 89)
- Test: `tests/test_fabrication_risk.py`

**Interfaces:**
- Consumes: `AIGenerationAssessment`, `CrossFieldAssessment`, `ResumeFarmAssessment`, `RiskComponent` and band enums from `app.schemas.fabrication`; `Settings` from `app.core.config`.
- Produces: `Settings` fields `fr_moderate_threshold: float = 0.30`, `fr_elevated_threshold: float = 0.60`, `fr_min_confidence: float = 0.50`, `fr_weight_ai: float = 1.0`, `fr_weight_cross_field: float = 1.0`, `fr_weight_farm: float = 1.0`; and `build_components(ai, cross_field, resume_farm, *, settings=None) -> list[RiskComponent]` in `app.fabrication.risk`. Task 3 builds fusion/banding on top of these exact names.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fabrication_risk.py`:

```python
"""S2.4 fusion math: component construction, fusion, banding — pure and offline."""

from app.fabrication.risk import build_components
from app.schemas.fabrication import (
    AIGenerationAssessment,
    AILikelihoodBand,
    ConsistencyBand,
    CrossFieldAssessment,
    DuplicationBand,
    ResumeFarmAssessment,
)


def _ai(band: AILikelihoodBand, conf: float = 0.75) -> AIGenerationAssessment:
    return AIGenerationAssessment(likelihood=0.6, confidence=conf, band=band)


def _xf(band: ConsistencyBand, conf: float = 0.75) -> CrossFieldAssessment:
    return CrossFieldAssessment(score=0.5, confidence=conf, band=band)


def _rf(band: DuplicationBand, conf: float = 0.70) -> ResumeFarmAssessment:
    return ResumeFarmAssessment(score=0.85, confidence=conf, band=band, corpus_size=3)


def test_settings_expose_fr_knobs(settings):
    assert settings.fr_moderate_threshold == 0.30
    assert settings.fr_elevated_threshold == 0.60
    assert settings.fr_min_confidence == 0.50
    assert settings.fr_weight_ai == 1.0
    assert settings.fr_weight_cross_field == 1.0
    assert settings.fr_weight_farm == 1.0


def test_one_component_per_evaluable_assessment(settings):
    comps = build_components(
        _ai(AILikelihoodBand.POSSIBLE), _xf(ConsistencyBand.CONSISTENT),
        _rf(DuplicationBand.NEAR_DUPLICATE), settings=settings,
    )
    assert [c.id for c in comps] == ["ai_generation", "cross_field", "resume_farm"]


def test_none_and_insufficient_are_excluded(settings):
    comps = build_components(
        None, _xf(ConsistencyBand.INSUFFICIENT_DATA),
        _rf(DuplicationBand.UNIQUE), settings=settings,
    )
    assert [c.id for c in comps] == ["resume_farm"]
    assert build_components(None, None, None, settings=settings) == []


def test_component_risk_band_mapping(settings):
    comps = build_components(
        _ai(AILikelihoodBand.LIKELY), _xf(ConsistencyBand.MINOR_ISSUES),
        _rf(DuplicationBand.NEAR_DUPLICATE), settings=settings,
    )
    by_id = {c.id: c for c in comps}
    assert by_id["ai_generation"].risk == 0.75
    assert by_id["cross_field"].risk == 0.40
    assert by_id["resume_farm"].risk == 0.80


def test_flagged_only_at_top_band(settings):
    comps = build_components(
        _ai(AILikelihoodBand.POSSIBLE), _xf(ConsistencyBand.MAJOR_ISSUES),
        _rf(DuplicationBand.SIMILAR), settings=settings,
    )
    by_id = {c.id: c for c in comps}
    assert by_id["ai_generation"].flagged is False
    assert by_id["cross_field"].flagged is True
    assert by_id["resume_farm"].flagged is False


def test_weight_is_config_weight_times_confidence(settings):
    comps = build_components(_ai(AILikelihoodBand.UNLIKELY, conf=0.8), None, None, settings=settings)
    assert comps[0].weight == 0.8  # fr_weight_ai (1.0) x confidence
    assert comps[0].band == "unlikely"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fabrication_risk.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.fabrication.risk'`

- [ ] **Step 3: Implement**

Add to `app/core/config.py` after the `rf_max_matches` field:

```python
    # --- Fabrication defense (PI-2, S2.4): unified fabrication risk -------------
    # Deterministic fusion of ai_generation + cross_field + resume_farm bands,
    # computed in the calibration stage. ADVISORY: never changes verdicts or
    # depth, never a rejection signal. ELEVATED additionally requires >= 2
    # components at their top band; fusion never asserts on a single subsystem.
    fr_moderate_threshold: float = Field(default=0.30, ge=0.0, le=1.0)
    fr_elevated_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    fr_min_confidence: float = Field(default=0.50, ge=0.0, le=1.0)
    fr_weight_ai: float = Field(default=1.0, ge=0.0)
    fr_weight_cross_field: float = Field(default=1.0, ge=0.0)
    fr_weight_farm: float = Field(default=1.0, ge=0.0)
```

Add to `config.yaml` after the S2.3 block:

```yaml
# --- Fabrication defense (PI-2) — S2.4 unified fabrication risk ----------------
# Deterministic fusion of the three fabrication signals into one advisory band,
# computed in the calibration stage. Never changes verdicts or depth scores;
# "elevated" additionally requires >=2 subsystems at their top band.
fr_moderate_threshold: 0.30      # fused score >= this -> band "moderate"
fr_elevated_threshold: 0.60      # fused score >= this (AND >=2 flags) -> "elevated"
fr_min_confidence: 0.50          # below this -> "insufficient_data", never assert
fr_weight_ai: 1.0                # per-subsystem fusion weights (x component confidence)
fr_weight_cross_field: 1.0
fr_weight_farm: 1.0
```

Create `app/fabrication/risk.py`:

```python
"""S2.4 — unified fabrication risk: fuse ai_generation + cross_field + resume_farm.

Pure functions, no I/O, no LLM. ADVISORY ONLY: the fused band is reviewer
context computed in the calibration stage — it never changes a verdict, the
depth score, or the depth band, and it is never a rejection signal.

Conservative by construction: absent/insufficient subsystem signals are
excluded from fusion (absence of signal is not evidence of risk); ELEVATED
requires >= 2 components at their top band; fusion over a single subsystem
never clears the confidence floor, so it never asserts.
"""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.schemas.fabrication import (
    AIGenerationAssessment,
    AILikelihoodBand,
    ConsistencyBand,
    CrossFieldAssessment,
    DuplicationBand,
    FabricationRiskAssessment,
    FabricationRiskBand,
    ResumeFarmAssessment,
    RiskComponent,
)

# Band -> component risk. Insufficient bands are absent on purpose: they are
# excluded from fusion entirely. Code constants, not config — change deliberately.
_AI_RISK = {
    AILikelihoodBand.UNLIKELY: 0.10,
    AILikelihoodBand.POSSIBLE: 0.45,
    AILikelihoodBand.LIKELY: 0.75,
}
_XF_RISK = {
    ConsistencyBand.CONSISTENT: 0.10,
    ConsistencyBand.MINOR_ISSUES: 0.40,
    ConsistencyBand.MAJOR_ISSUES: 0.75,
}
_RF_RISK = {
    DuplicationBand.UNIQUE: 0.10,
    DuplicationBand.SIMILAR: 0.45,
    DuplicationBand.NEAR_DUPLICATE: 0.80,
}

# A pure weighted mean lets clean subsystems dilute one strong signal; a pure
# max ignores corroboration. The 70/30 blend keeps a single strong signal
# visible (MODERATE) while ELEVATED still needs corroborating components.
_MEAN_WEIGHT = 0.7
_MAX_WEIGHT = 0.3


def build_components(
    ai: AIGenerationAssessment | None,
    cross_field: CrossFieldAssessment | None,
    resume_farm: ResumeFarmAssessment | None,
    *,
    settings: Settings | None = None,
) -> list[RiskComponent]:
    """One RiskComponent per assessment that has data; insufficient bands are
    excluded entirely — absence of signal is not evidence of risk."""
    s = settings or get_settings()
    out: list[RiskComponent] = []
    if ai is not None and ai.band in _AI_RISK:
        out.append(
            RiskComponent(
                id="ai_generation",
                band=ai.band.value,
                risk=_AI_RISK[ai.band],
                confidence=ai.confidence,
                weight=s.fr_weight_ai * ai.confidence,
                flagged=ai.band is AILikelihoodBand.LIKELY,
            )
        )
    if cross_field is not None and cross_field.band in _XF_RISK:
        out.append(
            RiskComponent(
                id="cross_field",
                band=cross_field.band.value,
                risk=_XF_RISK[cross_field.band],
                confidence=cross_field.confidence,
                weight=s.fr_weight_cross_field * cross_field.confidence,
                flagged=cross_field.band is ConsistencyBand.MAJOR_ISSUES,
            )
        )
    if resume_farm is not None and resume_farm.band in _RF_RISK:
        out.append(
            RiskComponent(
                id="resume_farm",
                band=resume_farm.band.value,
                risk=_RF_RISK[resume_farm.band],
                confidence=resume_farm.confidence,
                weight=s.fr_weight_farm * resume_farm.confidence,
                flagged=resume_farm.band is DuplicationBand.NEAR_DUPLICATE,
            )
        )
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fabrication_risk.py -q` → all pass.
Run: `pytest -q` → no regressions.

- [ ] **Step 5: Commit**

```bash
git add app/fabrication/risk.py app/core/config.py config.yaml tests/test_fabrication_risk.py
git commit -m "feat(fabrication): fr_* config knobs + risk component construction (S2.4)"
```

---

### Task 3: Fusion + conservative banding + `assess_fabrication_risk`

**Files:**
- Modify: `app/fabrication/risk.py` (append)
- Test: `tests/test_fabrication_risk.py` (append)

**Interfaces:**
- Consumes: Task 2's `build_components` and constants; `Settings.fr_*`.
- Produces: `fuse_components(components: list[RiskComponent]) -> tuple[float, float]` (score, confidence); `band_for_risk(score: float, confidence: float, flagged_count: int, *, settings=None) -> FabricationRiskBand`; `assess_fabrication_risk(ai, cross_field, resume_farm, *, settings=None) -> FabricationRiskAssessment`. Task 4's scoring node calls `assess_fabrication_risk` with exactly this signature.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fabrication_risk.py`:

```python
from app.fabrication.risk import assess_fabrication_risk, band_for_risk, fuse_components
from app.schemas.fabrication import FabricationRiskBand


def test_fuse_empty_is_zero():
    assert fuse_components([]) == (0.0, 0.0)


def test_fuse_blends_weighted_mean_and_max(settings):
    comps = build_components(
        _ai(AILikelihoodBand.LIKELY, conf=0.8), _xf(ConsistencyBand.MAJOR_ISSUES, conf=0.8),
        _rf(DuplicationBand.NEAR_DUPLICATE, conf=0.8), settings=settings,
    )
    score, confidence = fuse_components(comps)
    # equal weights: mean = (0.75+0.75+0.80)/3; score = 0.7*mean + 0.3*0.80
    assert abs(score - (0.7 * (0.75 + 0.75 + 0.80) / 3 + 0.3 * 0.80)) < 1e-9
    assert confidence == 0.75  # min(0.9, 0.30 + 0.15*3)


def test_confidence_follows_coverage(settings):
    two = build_components(
        _ai(AILikelihoodBand.UNLIKELY), _xf(ConsistencyBand.CONSISTENT), None, settings=settings,
    )
    assert fuse_components(two)[1] == 0.60
    one = build_components(_ai(AILikelihoodBand.UNLIKELY), None, None, settings=settings)
    assert fuse_components(one)[1] == 0.45


def test_band_never_asserts_below_min_confidence(settings):
    assert band_for_risk(0.9, 0.45, 3, settings=settings) is FabricationRiskBand.INSUFFICIENT_DATA


def test_band_elevated_needs_two_flags(settings):
    assert band_for_risk(0.70, 0.75, 2, settings=settings) is FabricationRiskBand.ELEVATED
    # structural cap: one flag alone can never be ELEVATED, however high the score
    assert band_for_risk(0.78, 0.75, 1, settings=settings) is FabricationRiskBand.MODERATE


def test_band_thresholds(settings):
    assert band_for_risk(0.10, 0.75, 0, settings=settings) is FabricationRiskBand.LOW
    assert band_for_risk(0.30, 0.75, 0, settings=settings) is FabricationRiskBand.MODERATE
    assert band_for_risk(0.29, 0.75, 0, settings=settings) is FabricationRiskBand.LOW


def test_assess_all_clean_is_low(settings):
    a = assess_fabrication_risk(
        _ai(AILikelihoodBand.UNLIKELY), _xf(ConsistencyBand.CONSISTENT),
        _rf(DuplicationBand.UNIQUE), settings=settings,
    )
    assert a.band is FabricationRiskBand.LOW
    assert a.advisory is True
    assert len(a.components) == 3
    assert "never" in a.reasoning  # advisory copy present


def test_assess_single_near_duplicate_caps_at_moderate(settings):
    a = assess_fabrication_risk(
        _ai(AILikelihoodBand.UNLIKELY), _xf(ConsistencyBand.CONSISTENT),
        _rf(DuplicationBand.NEAR_DUPLICATE, conf=0.9), settings=settings,
    )
    assert a.band is FabricationRiskBand.MODERATE


def test_assess_corroborated_flags_reach_elevated(settings):
    a = assess_fabrication_risk(
        _ai(AILikelihoodBand.LIKELY, conf=0.8), _xf(ConsistencyBand.MAJOR_ISSUES, conf=0.8),
        _rf(DuplicationBand.NEAR_DUPLICATE, conf=0.8), settings=settings,
    )
    assert a.band is FabricationRiskBand.ELEVATED
    assert sum(1 for c in a.components if c.flagged) == 3


def test_assess_soft_signals_accumulate(settings):
    # No single subsystem flags loudly, but three soft signals together matter.
    a = assess_fabrication_risk(
        _ai(AILikelihoodBand.POSSIBLE), _xf(ConsistencyBand.MINOR_ISSUES),
        _rf(DuplicationBand.SIMILAR), settings=settings,
    )
    assert a.band is FabricationRiskBand.MODERATE


def test_assess_no_components_is_insufficient(settings):
    a = assess_fabrication_risk(None, None, None, settings=settings)
    assert a.band is FabricationRiskBand.INSUFFICIENT_DATA
    assert a.components == [] and a.score == 0.0 and a.confidence == 0.0


def test_assess_single_subsystem_never_asserts(settings):
    a = assess_fabrication_risk(None, _xf(ConsistencyBand.MAJOR_ISSUES, conf=0.9), None, settings=settings)
    assert a.band is FabricationRiskBand.INSUFFICIENT_DATA  # confidence 0.45 < 0.50


def test_assess_is_deterministic(settings):
    args = (_ai(AILikelihoodBand.POSSIBLE), _xf(ConsistencyBand.MAJOR_ISSUES), _rf(DuplicationBand.SIMILAR))
    assert assess_fabrication_risk(*args, settings=settings) == assess_fabrication_risk(*args, settings=settings)
```

Sanity math for `test_assess_soft_signals_accumulate` (all confidences 0.75/0.75/0.70, weights = confidences): mean = (0.45·0.75 + 0.40·0.75 + 0.45·0.70) / (0.75+0.75+0.70) = 0.9525/2.20 ≈ 0.433; score = 0.7·0.433 + 0.3·0.45 ≈ 0.438 ≥ 0.30 ⇒ MODERATE. For `test_assess_single_near_duplicate_caps_at_moderate`: mean = (0.10·0.75 + 0.10·0.75 + 0.80·0.9)/2.40 = 0.87/2.40 = 0.3625; score = 0.254 + 0.24 = 0.494 ⇒ MODERATE (and the flagged<2 gate would cap it anyway).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fabrication_risk.py -q`
Expected: FAIL — `ImportError: cannot import name 'fuse_components'`

- [ ] **Step 3: Implement — append to `app/fabrication/risk.py`**

```python
def fuse_components(components: list[RiskComponent]) -> tuple[float, float]:
    """(score, confidence). Score blends the weighted mean with the max
    component risk (70/30); confidence follows coverage, same shape as
    S2.1/S2.2: min(0.9, 0.30 + 0.15 * evaluated). One component -> 0.45,
    which sits below fr_min_confidence — single-subsystem fusion never asserts."""
    if not components:
        return 0.0, 0.0
    total_weight = sum(c.weight for c in components)
    if total_weight > 0:
        mean = sum(c.risk * c.weight for c in components) / total_weight
    else:  # defensive: evaluable components with zero confidence
        mean = sum(c.risk for c in components) / len(components)
    score = _MEAN_WEIGHT * mean + _MAX_WEIGHT * max(c.risk for c in components)
    confidence = min(0.9, 0.30 + 0.15 * len(components))
    return score, confidence


def band_for_risk(
    score: float,
    confidence: float,
    flagged_count: int,
    *,
    settings: Settings | None = None,
) -> FabricationRiskBand:
    """Conservative banding: never assert under the confidence floor; ELEVATED
    requires corroboration (>= 2 components at their top band), mirroring
    S2.1's 'LIKELY needs >= 2 deterministic tells'."""
    s = settings or get_settings()
    if confidence < s.fr_min_confidence:
        return FabricationRiskBand.INSUFFICIENT_DATA
    if score >= s.fr_elevated_threshold and flagged_count >= 2:
        return FabricationRiskBand.ELEVATED
    if score >= s.fr_moderate_threshold:
        return FabricationRiskBand.MODERATE
    return FabricationRiskBand.LOW


def assess_fabrication_risk(
    ai: AIGenerationAssessment | None,
    cross_field: CrossFieldAssessment | None,
    resume_farm: ResumeFarmAssessment | None,
    *,
    settings: Settings | None = None,
) -> FabricationRiskAssessment:
    """Fuse whatever subsystems produced an assessable signal into one advisory
    band. Excluded subsystems (absent or insufficient) never count as risk."""
    s = settings or get_settings()
    components = build_components(ai, cross_field, resume_farm, settings=s)
    if not components:
        return FabricationRiskAssessment(
            band=FabricationRiskBand.INSUFFICIENT_DATA,
            reasoning=(
                "No fabrication subsystem produced an assessable signal; nothing to "
                "fuse. Advisory only — never a rejection signal."
            ),
        )
    score, confidence = fuse_components(components)
    flagged = sum(1 for c in components if c.flagged)
    band = band_for_risk(score, confidence, flagged, settings=s)
    parts = ", ".join(f"{c.id}={c.band}" for c in components)
    reasoning = (
        f"Fused {len(components)} fabrication signal(s): {parts}. Unified risk "
        f"{score:.2f} (confidence {confidence:.2f}) -> {band.value}. Advisory "
        f"context for a human reviewer — fabrication signals never change "
        f"verdicts or depth scores, and are never a rejection signal."
    )
    return FabricationRiskAssessment(
        score=score,
        confidence=confidence,
        band=band,
        components=components,
        reasoning=reasoning,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fabrication_risk.py -q` → all pass.
Run: `pytest -q` → no regressions.

- [ ] **Step 5: Commit**

```bash
git add app/fabrication/risk.py tests/test_fabrication_risk.py
git commit -m "feat(fabrication): unified risk fusion + conservative banding (S2.4)"
```

---

### Task 4: State field + scoring-node wiring (calibration stage)

**Files:**
- Modify: `app/graph/state.py` (scoring section, after `depth_band`)
- Modify: `app/graph/nodes/scoring.py`
- Test: `tests/test_scoring_fabrication_risk.py`

**Interfaces:**
- Consumes: `assess_fabrication_risk` (Task 3); `state.ai_generation`, `state.cross_field`, `state.resume_farm` (already on `EvaluationState`).
- Produces: `EvaluationState.fabrication_risk: Optional[FabricationRiskAssessment]`, written by the scoring node's returned dict under key `"fabrication_risk"`. Report node (Task 5) reads `state.fabrication_risk`. Semantics: `None` when **all three** inputs are `None` (nothing was ever assessed — e.g. resume text never arrived); otherwise always a `FabricationRiskAssessment` (possibly INSUFFICIENT_DATA).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scoring_fabrication_risk.py`:

```python
"""Scoring node computes the unified fabrication risk in the calibration stage —
and provably never lets it touch verdicts or depth outputs."""

from app.graph.nodes.scoring import make_scoring_node
from app.graph.state import EvaluationState
from app.schemas.fabrication import (
    AIGenerationAssessment,
    AILikelihoodBand,
    ConsistencyBand,
    CrossFieldAssessment,
    DuplicationBand,
    FabricationRiskBand,
    ResumeFarmAssessment,
)
from app.schemas.report import CoherenceVerdict
from tests.conftest import make_services


def _verdicts() -> list[CoherenceVerdict]:
    return [
        CoherenceVerdict(
            claim_id="c1", claim_text="t", claim_type="skill",
            coherence_score=0.8, confidence=0.8,
        )
    ]


def _assessments() -> dict:
    return dict(
        ai_generation=AIGenerationAssessment(
            likelihood=0.7, confidence=0.8, band=AILikelihoodBand.LIKELY
        ),
        cross_field=CrossFieldAssessment(
            score=0.6, confidence=0.8, band=ConsistencyBand.MAJOR_ISSUES
        ),
        resume_farm=ResumeFarmAssessment(
            score=0.85, confidence=0.8, band=DuplicationBand.NEAR_DUPLICATE, corpus_size=3
        ),
    )


async def test_scoring_emits_fabrication_risk(settings):
    node = make_scoring_node(make_services(settings))
    out = await node(EvaluationState(verdicts=_verdicts(), **_assessments()))
    risk = out["fabrication_risk"]
    assert risk is not None
    assert risk.band is FabricationRiskBand.ELEVATED
    assert [c.id for c in risk.components] == ["ai_generation", "cross_field", "resume_farm"]


async def test_all_inputs_absent_means_not_assessed(settings):
    node = make_scoring_node(make_services(settings))
    out = await node(EvaluationState(verdicts=_verdicts()))
    assert out["fabrication_risk"] is None


async def test_partial_inputs_still_assess(settings):
    node = make_scoring_node(make_services(settings))
    out = await node(
        EvaluationState(
            verdicts=_verdicts(),
            cross_field=CrossFieldAssessment(
                score=0.1, confidence=0.8, band=ConsistencyBand.CONSISTENT
            ),
        )
    )
    risk = out["fabrication_risk"]
    assert risk is not None
    assert risk.band is FabricationRiskBand.INSUFFICIENT_DATA  # 1 component never asserts


async def test_fabrication_risk_never_touches_depth_or_verdicts(settings):
    node = make_scoring_node(make_services(settings))
    with_risk = await node(EvaluationState(verdicts=_verdicts(), **_assessments()))
    without = await node(EvaluationState(verdicts=_verdicts()))
    assert with_risk["depth_score"] == without["depth_score"]
    assert with_risk["depth_band"] == without["depth_band"]
    assert with_risk["overall_confidence"] == without["overall_confidence"]
    assert [v.status for v in with_risk["verdicts"]] == [v.status for v in without["verdicts"]]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scoring_fabrication_risk.py -q`
Expected: FAIL — `KeyError: 'fabrication_risk'`

- [ ] **Step 3: Implement**

In `app/graph/state.py`, add to the scoring section (after `depth_band`), plus the import of `FabricationRiskAssessment` in the existing `from app.schemas.fabrication import ...` line:

```python
    # S2.4: unified advisory fabrication risk, fused in the calibration stage
    # (scoring node) from ai_generation + cross_field + resume_farm. None when
    # none of the three was ever assessed. Never affects depth or verdicts.
    fabrication_risk: Optional[FabricationRiskAssessment] = None
```

In `app/graph/nodes/scoring.py`, replace the module with:

```python
"""scoring — apply calibration to finalize per-claim status + aggregate depth.

Per-claim: run the conservative classifier over (coherence, confidence).
Aggregate: confidence-weighted depth score + advisory depth band. S2.4: fuse
the fabrication assessments into one advisory fabrication_risk — computed
here because this IS the calibration stage, but it never touches verdicts,
the depth score, or the depth band.
"""

from __future__ import annotations

from app.core.calibration import aggregate_depth, classify
from app.core.logging import get_logger
from app.fabrication.risk import assess_fabrication_risk
from app.graph.state import EvaluationState
from app.services import Services


def make_scoring_node(services: Services):
    log = get_logger("node.scoring")
    settings = services.settings

    async def scoring(state: EvaluationState) -> dict:
        verdicts = state.verdicts
        for v in verdicts:
            v.status = classify(
                coherence=v.coherence_score,
                confidence=v.confidence,
                has_evidence=bool(v.evidence),
                settings=settings,
            )

        depth, overall_conf, band = aggregate_depth(
            [(v.coherence_score, v.confidence) for v in verdicts], settings=settings
        )

        # S2.4: unified advisory fabrication risk. None when nothing was ever
        # assessed (e.g. resume text never arrived and no farm input).
        fabrication_risk = None
        if not (
            state.ai_generation is None
            and state.cross_field is None
            and state.resume_farm is None
        ):
            fabrication_risk = assess_fabrication_risk(
                state.ai_generation,
                state.cross_field,
                state.resume_farm,
                settings=settings,
            )
            log.info(
                "fabrication_risk",
                band=fabrication_risk.band.value,
                score=round(fabrication_risk.score, 3),
                components=len(fabrication_risk.components),
            )

        log.info("scored", depth=round(depth, 3), band=band, confidence=round(overall_conf, 3))
        return {
            "verdicts": verdicts,
            "depth_score": depth,
            "overall_confidence": overall_conf,
            "depth_band": band,
            "fabrication_risk": fabrication_risk,
        }

    return scoring
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scoring_fabrication_risk.py -q` → all pass.
Run: `pytest -q` → no regressions.

- [ ] **Step 5: Commit**

```bash
git add app/graph/state.py app/graph/nodes/scoring.py tests/test_scoring_fabrication_risk.py
git commit -m "feat(graph): fuse fabrication_risk in the scoring/calibration stage (S2.4)"
```

---

### Task 5: Report field + summary note + flywheel record

**Files:**
- Modify: `app/schemas/report.py` (after `resume_farm`, ~line 122)
- Modify: `app/graph/nodes/report.py`
- Test: `tests/test_report_fabrication_risk.py`

**Interfaces:**
- Consumes: `state.fabrication_risk` (Task 4), `FabricationRiskAssessment`/`FabricationRiskBand` (Task 1).
- Produces: `Report.fabrication_risk: Optional[FabricationRiskAssessment] = None`; summary note fires on MODERATE and ELEVATED (the two upper of four bands, mirroring S2.1's possible/likely rule); flywheel record `record_type: "fabrication_risk"` with keys `band, score, confidence, components (dict id->band), outcome: None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_report_fabrication_risk.py`:

```python
"""Report surfaces the unified fabrication risk: field, summary note, flywheel."""

from app.graph.nodes.report import make_report_node
from app.graph.state import EvaluationState
from app.schemas.fabrication import (
    FabricationRiskAssessment,
    FabricationRiskBand,
    RiskComponent,
)


def _risk(band: FabricationRiskBand, score: float = 0.55) -> FabricationRiskAssessment:
    return FabricationRiskAssessment(
        score=score,
        confidence=0.75,
        band=band,
        components=[
            RiskComponent(id="cross_field", band="major_issues", risk=0.75,
                          confidence=0.8, weight=0.8, flagged=True),
            RiskComponent(id="resume_farm", band="near_duplicate", risk=0.80,
                          confidence=0.8, weight=0.8, flagged=True),
        ],
        reasoning="r",
    )


async def test_report_carries_assessment_and_flywheel_record(services, flywheel):
    node = make_report_node(services)
    out = await node(
        EvaluationState(resume_text="t", fabrication_risk=_risk(FabricationRiskBand.ELEVATED))
    )
    rep = out["report"]
    assert rep.fabrication_risk is not None
    assert rep.fabrication_risk.band is FabricationRiskBand.ELEVATED
    assert rep.advisory is True and rep.human_review_required is True
    records = [r for r in flywheel.records if r.get("record_type") == "fabrication_risk"]
    assert len(records) == 1
    assert records[0]["band"] == "elevated"
    assert records[0]["components"] == {"cross_field": "major_issues", "resume_farm": "near_duplicate"}
    assert records[0]["outcome"] is None


async def test_summary_note_on_moderate_and_elevated_only(services):
    node = make_report_node(services)
    for band in (FabricationRiskBand.MODERATE, FabricationRiskBand.ELEVATED):
        out = await node(EvaluationState(resume_text="t", fabrication_risk=_risk(band)))
        assert "Unified fabrication risk" in out["report"].summary
        assert "never a rejection signal" in out["report"].summary

    for band in (FabricationRiskBand.LOW, FabricationRiskBand.INSUFFICIENT_DATA):
        out = await node(
            EvaluationState(resume_text="t", fabrication_risk=_risk(band, score=0.1))
        )
        assert "Unified fabrication risk" not in out["report"].summary
        assert out["report"].fabrication_risk is not None  # field still present


async def test_absent_assessment_stays_absent(services, flywheel):
    node = make_report_node(services)
    out = await node(EvaluationState(resume_text="t"))
    assert out["report"].fabrication_risk is None
    assert not [r for r in flywheel.records if r.get("record_type") == "fabrication_risk"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_report_fabrication_risk.py -q`
Expected: FAIL — `ValidationError`/`AttributeError`: `Report` has no field `fabrication_risk` (the EvaluationState already accepts it after Task 4).

- [ ] **Step 3: Implement**

In `app/schemas/report.py`: extend the fabrication import line to include `FabricationRiskAssessment`, and add after `resume_farm`:

```python
    # S2.4: unified advisory fabrication risk — the three signals above fused in
    # the calibration stage. Reviewer context only, never a verdict and never a
    # rejection signal. None for pre-S2.4 stored reports and runs where nothing
    # was assessed.
    fabrication_risk: Optional[FabricationRiskAssessment] = None
```

In `app/graph/nodes/report.py`: extend the fabrication import line to include `FabricationRiskBand`. After the `rf` summary block, add:

```python
        risk = state.fabrication_risk
        if risk is not None and risk.band in (
            FabricationRiskBand.MODERATE,
            FabricationRiskBand.ELEVATED,
        ):
            summary += (
                f" Unified fabrication risk: {risk.band.value} (score "
                f"{risk.score:.2f}, confidence {risk.confidence:.2f}) across "
                f"{len(risk.components)} signal(s) — fused advisory context for "
                f"the reviewer; it never changes the depth evaluation and is "
                f"never a rejection signal."
            )
```

In the `Report(...)` constructor add `fabrication_risk=state.fabrication_risk,` after `resume_farm=...`. After the `resume_farm` flywheel block, add:

```python
        if state.fabrication_risk is not None:
            services.flywheel.log(
                {
                    "record_type": "fabrication_risk",
                    "evaluation_id": state.evaluation_id,
                    "report_id": rep.id,
                    "domain": state.domain,
                    "band": state.fabrication_risk.band.value,
                    "score": state.fabrication_risk.score,
                    "confidence": state.fabrication_risk.confidence,
                    "components": {c.id: c.band for c in state.fabrication_risk.components},
                    "outcome": None,  # closed later by human/hiring signal
                }
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_report_fabrication_risk.py -q` → all pass.
Run: `pytest -q` → no regressions.

- [ ] **Step 5: Commit**

```bash
git add app/schemas/report.py app/graph/nodes/report.py tests/test_report_fabrication_risk.py
git commit -m "feat(report): surface unified fabrication_risk + flywheel record (S2.4)"
```

---

### Task 6: End-to-end integration through the engine

**Files:**
- Test: `tests/test_fabrication_risk_integration.py`

**Interfaces:**
- Consumes: `EvaluationEngine` (`app.graph.build`), conftest fixtures `settings`, `genuine_resume` (existing), `make_services`; `ResumeFarmAssessment` kwarg path added in S2.3.
- Produces: proof the whole pipeline emits `Report.fabrication_risk` on both entry paths (with and without a farm input) and that depth outputs are unaffected — the regression guard future sprints rely on.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fabrication_risk_integration.py`:

```python
"""Full-pipeline (offline) checks: fabrication_risk lands on real reports."""

from app.graph.build import EvaluationEngine
from app.schemas.fabrication import (
    DuplicationBand,
    FabricationRiskAssessment,
    FabricationRiskBand,
    ResumeFarmAssessment,
    ResumeMatch,
)
from tests.conftest import make_services


def _near_dup() -> ResumeFarmAssessment:
    return ResumeFarmAssessment(
        score=0.91,
        confidence=0.9,
        band=DuplicationBand.NEAR_DUPLICATE,
        matches=[ResumeMatch(candidate_id="c1", resume_id="r1", similarity=0.91)],
        corpus_size=4,
        reasoning="r",
    )


async def test_candidates_path_includes_farm_component(settings, genuine_resume):
    engine = EvaluationEngine(make_services(settings))
    report = await engine.evaluate(resume_text=genuine_resume, resume_farm=_near_dup())
    risk = report.fabrication_risk
    assert isinstance(risk, FabricationRiskAssessment)
    ids = [c.id for c in risk.components]
    assert "resume_farm" in ids
    assert set(ids) <= {"ai_generation", "cross_field", "resume_farm"}
    assert risk.advisory is True


async def test_evaluate_path_has_no_farm_component(settings, genuine_resume):
    engine = EvaluationEngine(make_services(settings))
    report = await engine.evaluate(resume_text=genuine_resume)
    risk = report.fabrication_risk
    assert isinstance(risk, FabricationRiskAssessment)
    assert "resume_farm" not in [c.id for c in risk.components]
    assert isinstance(risk.band, FabricationRiskBand)


async def test_fabrication_risk_never_moves_depth(settings, genuine_resume):
    plain = await EvaluationEngine(make_services(settings)).evaluate(resume_text=genuine_resume)
    farmed = await EvaluationEngine(make_services(settings)).evaluate(
        resume_text=genuine_resume, resume_farm=_near_dup()
    )
    assert plain.depth_score == farmed.depth_score
    assert plain.depth_band == farmed.depth_band
    assert [v.status for v in plain.verdicts] == [v.status for v in farmed.verdicts]


async def test_stored_pre_s24_reports_still_validate(settings, genuine_resume):
    engine = EvaluationEngine(make_services(settings))
    report = await engine.evaluate(resume_text=genuine_resume)
    dumped = report.model_dump(mode="json")
    dumped.pop("fabrication_risk")  # simulate a pre-S2.4 stored report
    from app.schemas.report import Report
    assert Report.model_validate(dumped).fabrication_risk is None
```

Note: `genuine_resume` is the existing conftest fixture used by `tests/test_report_resume_farm.py` — do not redefine it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fabrication_risk_integration.py -q`
Expected: with Tasks 1–5 done these should PASS — that is the point of writing them (they are the cross-task seam check). If any fail, the seam has a real bug: fix the product code, not the test. Only `test_stored_pre_s24_reports_still_validate` is guaranteed new coverage.

- [ ] **Step 3: Run the full suite**

Run: `pytest -q`
Expected: ~345 passed, 0 failed.

- [ ] **Step 4: Commit**

```bash
git add tests/test_fabrication_risk_integration.py
git commit -m "test: end-to-end fabrication_risk integration coverage (S2.4)"
```

---

### Task 7: Smoke script + FABRICATION.md update

**Files:**
- Create: `scripts/smoke_s24.py`
- Modify: `FABRICATION.md` (replace the "Next (S2.4 — planned)" section; extend the Report/config/testing tables)

**Interfaces:**
- Consumes: the running FastAPI app (`app.main:app`), fixtures `tests/fixtures/farm_genai_resume_a.txt`, `farm_genai_resume_b.txt`, `genuine_genai_resume.txt`; Alembic scratch-DB bootstrap pattern from `scripts/smoke_s23.py`.
- Produces: `python scripts/smoke_s24.py` exits 0 with all checks OK, key-less AND live.

- [ ] **Step 1: Write the smoke script**

Create `scripts/smoke_s24.py`:

```python
"""S2.4 smoke: unified fabrication_risk visible over the real HTTP surface.

Boots uvicorn on a scratch, Alembic-migrated SQLite DB and checks the fused
band end to end: a farm near-duplicate upload lands moderate-or-elevated with a
resume_farm component; a genuine resume stays low; POST /evaluate fuses without
a farm component; depth outputs are never moved by fabrication signals.
Works with a live key (LLM extraction) and without one (deterministic floor).
Run from the repo root:
    python scripts/smoke_s24.py
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config

FARM_A = Path("tests/fixtures/farm_genai_resume_a.txt")
FARM_B = Path("tests/fixtures/farm_genai_resume_b.txt")
GENUINE = Path("tests/fixtures/genuine_genai_resume.txt")
PORT = 8024
BASE = f"http://127.0.0.1:{PORT}"


def main() -> int:
    scratch = Path(tempfile.mkdtemp())
    url = "sqlite:///" + (scratch / "smoke_s24.db").as_posix()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    print(f"migrated scratch DB: {url}")

    env = os.environ.copy()
    env.update(
        {
            "DEE_CANDIDATES_DB_URL": url,
            "DEE_REPORT_DB_PATH": (scratch / "reports.db").as_posix(),
            "DEE_FLYWHEEL_PATH": (scratch / "flywheel.jsonl").as_posix(),
            # Chroma init can hang on some machines; the smoke stays bounded.
            "DEE_VECTORSTORE_BACKEND": "memory",
        }
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        env=env,
    )
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok))
        print(f"{'OK  ' if ok else 'FAIL'} {name}{(' — ' + detail) if detail else ''}")

    try:
        with httpx.Client(base_url=BASE, timeout=httpx.Timeout(600, connect=5)) as c:
            for _ in range(60):
                try:
                    if c.get("/healthz").status_code == 200:
                        break
                except httpx.TransportError:
                    time.sleep(0.5)
            else:
                print("FAIL server never became healthy")
                return 1

            text_a = FARM_A.read_text(encoding="utf-8")
            text_b = FARM_B.read_text(encoding="utf-8")
            text_g = GENUINE.read_text(encoding="utf-8")

            first = c.post("/candidates", json={"resume_text": text_a, "domain": "genai"}).json()
            risk_a = (first.get("report") or {}).get("fabrication_risk") or {}
            check("upload A carries fabrication_risk", bool(risk_a), f"band={risk_a.get('band')}")

            second = c.post("/candidates", json={"resume_text": text_b, "domain": "genai"}).json()
            rep_b = second.get("report") or {}
            risk_b = rep_b.get("fabrication_risk") or {}
            comp_ids = [x.get("id") for x in risk_b.get("components", [])]
            check(
                "farm copy B fuses to moderate/elevated",
                risk_b.get("band") in ("moderate", "elevated"),
                f"band={risk_b.get('band')} score={risk_b.get('score')}",
            )
            check("farm copy B includes resume_farm component", "resume_farm" in comp_ids, str(comp_ids))
            check("assessment is advisory", risk_b.get("advisory") is True)
            check(
                "summary carries the fused advisory note",
                "Unified fabrication risk" in rep_b.get("summary", ""),
            )
            check(
                "report still advisory + human-review",
                rep_b.get("advisory") is True and rep_b.get("human_review_required") is True,
            )

            genuine = c.post("/candidates", json={"resume_text": text_g, "domain": "genai"}).json()
            risk_g = (genuine.get("report") or {}).get("fabrication_risk") or {}
            check(
                "genuine resume fuses low (or insufficient)",
                risk_g.get("band") in ("low", "insufficient_data"),
                f"band={risk_g.get('band')}",
            )

            adhoc = c.post("/evaluate", json={"resume_text": text_g, "domain": "genai"}).json()
            risk_e = adhoc.get("fabrication_risk") or {}
            ids_e = [x.get("id") for x in risk_e.get("components", [])]
            check("POST /evaluate carries fabrication_risk", bool(risk_e), f"band={risk_e.get('band')}")
            check("POST /evaluate has no resume_farm component", "resume_farm" not in ids_e, str(ids_e))
            check(
                "depth band untouched by fusion (still present)",
                (genuine.get("report") or {}).get("depth_band") is not None,
            )
    finally:
        proc.terminate()
        proc.wait(timeout=30)

    ok = sum(1 for _, x in checks if x)
    print(f"\n{ok}/{len(checks)} checks OK")
    return 0 if ok == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

Response shapes (verified against `app/api/routes.py`): `CandidateCreateResponse` nests the full report under `"report"` (`report: Optional[Report]`, null when `evaluate=false` or the candidate was erased mid-eval), so `.get("report")` is correct; POST /evaluate returns the Report itself as the response body.

- [ ] **Step 2: Run the smoke key-less**

```bash
python scripts/smoke_s24.py
```

Expected: `10/10 checks OK`, exit 0, with no `DEE_OPENROUTER_API_KEY` set (deterministic floor).

- [ ] **Step 3: Run the smoke live**

With the real `.env` in place (OpenRouter key): `python scripts/smoke_s24.py`
Expected: `10/10 checks OK`, exit 0.

- [ ] **Step 4: Update FABRICATION.md**

Replace the final section `## Next (S2.4 — planned)` with a `## S2.4 — Unified fabrication_risk (calibration stage)` section documenting: the band→risk mapping table, the 70/30 mean/max blend, coverage confidence `min(0.9, 0.30 + 0.15·evaluated)` (single subsystem ⇒ 0.45 ⇒ never asserts), the ≥2-flags ELEVATED gate, and where it is computed (scoring node = calibration stage; never touches verdicts/depth). Add a row to the "What lands on the Report" table: `S2.4 | fabrication_risk | insufficient_data / low / moderate / elevated | moderate, elevated | fabrication_risk`. Add the `fr_*` knobs to the config quick reference. Add the new test files to the testing tree and `scripts/smoke_s24.py` to the smoke list.

- [ ] **Step 5: Full suite + commit**

```bash
pytest -q
git add scripts/smoke_s24.py FABRICATION.md
git commit -m "chore: S2.4 smoke script + FABRICATION.md unified-risk docs"
```

---

## Completion

After all tasks: run `pytest -q` one final time, run both smoke modes, then use superpowers:finishing-a-development-branch (merge `s24-fabrication-risk`, per-repo convention: merge to `main` with a descriptive merge commit like previous sprints). Update `docs/ROADMAP.md`: mark S2.4 `[x]` (PI-2 complete), set current sprint to S3.1 (ledger schema + DPDP consent model), add the session-log entry.

## Self-Review Notes

- Spec coverage: roadmap S2.4 line = "Unified fabrication_risk score fused into calibration + Report; still advisory, never auto-reject" — fusion in the calibration stage (Task 4), Report + summary + flywheel (Task 5), advisory invariants tested at unit (Task 3), node (Task 4), report (Task 5), and pipeline (Task 6) levels. FABRICATION.md's S2.4 note about the MinHash stderr false-positive tail is honored: a lone NEAR_DUPLICATE caps at MODERATE (≥2-flags gate) and its component confidence scales its weight.
- Type consistency: `assess_fabrication_risk(ai, cross_field, resume_farm, *, settings)` used identically in Tasks 3/4; `FabricationRiskBand`/`RiskComponent`/`FabricationRiskAssessment` names identical across Tasks 1/3/4/5/6; flywheel `components` is a `dict[id, band]` in Task 5's code and tests.
- Known judgment call (flag to reviewer): the summary note fires on MODERATE as well as ELEVATED — deliberate, because three soft signals reaching MODERATE is exactly the case where fusion adds information no per-component note carries.
