"""The twelve measured signals (S9.1, spec 4.1).

A SIGNAL DECLARES ITS OWN METRIC SET. The alternative -- computing four numbers
for everything and letting a reader work out which are nonsense -- puts a Brier
score on an unbounded count and an AUC on an ordinal that was cast to a float to
make it fit. Both look like measurements.

  - a [0,1] score        -> AUC + Brier
  - a *_band ordinal     -> lift only
  - an unbounded count   -> AUC + lift, never Brier

AN ABSENT ASSESSMENT EXTRACTS AS None, NEVER 0.0. Pre-S2.x stored reports and
ad-hoc POST /evaluate runs carry None for these, and 0.0 on a risk score reads
as a confident "no risk" rather than "never assessed". A None drops that report
from THAT signal's sample and is counted in nothing.

Note the asymmetry that makes ``major_findings`` correct: an assessment that
RAN and found nothing is a real 0.0 and belongs in the sample; only the absent
assessment itself is None.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Union

from app.schemas.fabrication import FindingSeverity
from app.schemas.report import Report
from app.signal_quality.schema import LabelKind, MetricKind

_SCORE = frozenset({MetricKind.AUC, MetricKind.BRIER})
_BAND = frozenset({MetricKind.LIFT})
_COUNT = frozenset({MetricKind.AUC, MetricKind.LIFT})


@dataclass(frozen=True)
class SignalSpec:
    name: str
    kind: LabelKind
    metrics: frozenset[MetricKind]
    extract: Callable[[Report], Optional[Union[float, str]]]
    #: True when `extract` yields a category rather than a number. Drives which
    #: metric family the service routes it to, and is asserted against
    #: `metrics` IN BOTH DIRECTIONS by a guard test -- a numeric signal wrongly
    #: flagged would be routed to lift and never caught by a one-way check.
    band: bool = False


def _opt(assessment, attr: str):
    return None if assessment is None else getattr(assessment, attr)


def _band_value(assessment, attr: str = "band"):
    got = _opt(assessment, attr)
    return None if got is None else str(got.value)


def _major_findings(report: Report) -> Optional[float]:
    if report.cross_field is None:
        return None
    return float(
        sum(1 for f in report.cross_field.findings
            if f.severity is FindingSeverity.MAJOR)
    )


SIGNALS: tuple[SignalSpec, ...] = (
    # --- FRAUD: scored by `outcomes`, measurable today -----------------------
    SignalSpec("fabrication_risk.score", LabelKind.FRAUD, _SCORE,
               lambda r: _opt(r.fabrication_risk, "score")),
    SignalSpec("fabrication_risk.band", LabelKind.FRAUD, _BAND,
               lambda r: _band_value(r.fabrication_risk), band=True),
    SignalSpec("ai_generation.likelihood", LabelKind.FRAUD, _SCORE,
               lambda r: _opt(r.ai_generation, "likelihood")),
    SignalSpec("ai_generation.band", LabelKind.FRAUD, _BAND,
               lambda r: _band_value(r.ai_generation), band=True),
    SignalSpec("cross_field.score", LabelKind.FRAUD, _SCORE,
               lambda r: _opt(r.cross_field, "score")),
    SignalSpec("cross_field.band", LabelKind.FRAUD, _BAND,
               lambda r: _band_value(r.cross_field), band=True),
    SignalSpec("cross_field.major_findings", LabelKind.FRAUD, _COUNT,
               _major_findings),
    SignalSpec("resume_farm.score", LabelKind.FRAUD, _SCORE,
               lambda r: _opt(r.resume_farm, "score")),
    SignalSpec("resume_farm.band", LabelKind.FRAUD, _BAND,
               lambda r: _band_value(r.resume_farm), band=True),
    # --- HIRE: scored by the ledger, refuses until real orgs exist -----------
    SignalSpec("depth_score", LabelKind.HIRE, _SCORE, lambda r: r.depth_score),
    SignalSpec("depth_band", LabelKind.HIRE, _BAND,
               lambda r: _band_value(r, "depth_band"), band=True),
    SignalSpec("overall_confidence", LabelKind.HIRE, _SCORE,
               lambda r: r.overall_confidence),
)


def by_name(name: str) -> SignalSpec:
    for spec in SIGNALS:
        if spec.name == name:
            return spec
    raise KeyError(f"unknown signal {name!r}")
