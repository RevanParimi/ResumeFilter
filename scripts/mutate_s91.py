"""S9.1's mutation pass: 15 deliberate one-line breaks, 15 that must die.

THE NUMBERS ARE THIS SPRINT'S WHOLE DELIVERABLE, so a suite that survives
mutating them is not testing them. Every tie rule, every boundary and every
refusal direction has a mutant here that kills it.

COMMITTED, unlike the mutation passes of S8.3 and S8.5 which were run by hand
and recorded only as a count in the roadmap. A count nobody can re-derive is a
claim, not evidence -- and the metrics this sprint ships are exactly the kind
of code that rots silently, because a wrong AUC still returns a plausible
float.

Run from the repo root:   python scripts/mutate_s91.py
Exit 0 means every mutant died. A SURVIVOR MEANS A TEST IS MISSING, not that
the mutant is acceptable.

Each mutant is applied to a real file, the targeted suite is run, and the file
is restored from an in-memory copy of its own bytes before the next one -- so
an interrupted run leaves at most one mutation on disk, and `git diff` shows it.
"""

import pathlib, subprocess, sys, shutil

SQ = pathlib.Path("src/app/signal_quality")
M, L, S = SQ / "metrics.py", SQ / "labels.py", SQ / "service.py"

MUTANTS = [
 ("auc: rank by position, no tie averaging", M,
  "        shared = (i + j) / 2.0 + 1.0", "        shared = i + 1.0"),
 ("auc: >= in the tie scan", M,
  "values[order[j + 1]] == values[order[i]]", "values[order[j + 1]] >= values[order[i]]"),
 ("auc: n_pos*(n_pos-1)/2", M,
  "rank_sum - n_pos * (n_pos + 1) / 2.0", "rank_sum - n_pos * (n_pos - 1) / 2.0"),
 ("auc: return 0.5 instead of raising", M,
  '        raise DegenerateClass(\n            f"AUC undefined: {n_pos} positive and {n_neg} negative labels"\n        )',
  "        return 0.5"),
 ("brier: absolute instead of squared", M,
  "(s - (1.0 if lab else 0.0)) ** 2", "abs(s - (1.0 if lab else 0.0))"),
 ("calibration: empty bin reports 0.0", M,
  "out.append((lower, upper, 0, None, None))", "out.append((lower, upper, 0, 0.0, 0.0))"),
 ("calibration: drop the upper clamp", M,
  "idx = min(max(idx, 0), bins - 1)", "idx = max(idx, 0)"),
 ("lift: 0.0 on a zero base rate", M,
  "(rate / base) if base > 0 else None", "(rate / base) if base > 0 else 0.0"),
 ("labels: leakage < instead of <=", L,
  "if recorded_at <= as_of:", "if recorded_at < as_of:"),
 ("labels: operator labels on by default", L,
  "include_operator_labels: bool = False", "include_operator_labels: bool = True"),
 ("labels: last qualifying wins", L,
  "            if report.id not in chosen:", "            if True:"),
 ("labels: CANDIDATE_CLARIFIED is positive", L,
  "frozenset({OutcomeLabel.VERIFIED_FABRICATED})",
  "frozenset({OutcomeLabel.VERIFIED_FABRICATED, OutcomeLabel.CANDIDATE_CLARIFIED})"),
 ("service: sample floor <= instead of <", S,
  "if n < min_samples:", "if n <= min_samples:"),
 ("service: skip the label-kind check", S,
  "    if spec.kind is not source_kind:", "    if False:"),
 ("service: extract None as 0.0", S,
  "        if value is None:\n            continue  # never assessed -- not a zero, and not counted",
  "        if value is None:\n            value = 0.0"),
]

dead = survived = 0
for name, path, old, new in MUTANTS:
    src = path.read_text(encoding="utf-8")
    if old not in src:
        print(f"  ?? NOT APPLIED  {name}  (anchor missing in {path.name})")
        survived += 1
        continue
    backup = src
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q",
                        "tests/test_signal_quality_metrics.py",
                        "tests/test_signal_quality_labels.py",
                        "tests/test_signal_quality_service.py",
                        "tests/test_signal_quality_signals.py"],
                       capture_output=True, text=True)
    path.write_text(backup, encoding="utf-8")
    if r.returncode != 0:
        first = next((l for l in r.stdout.splitlines() if l.startswith("FAILED")), "")
        print(f"  DEAD  {name}\n          killed by: {first.replace('FAILED ','')[:95]}")
        dead += 1
    else:
        print(f"  SURVIVED  {name}   <-- a test is missing")
        survived += 1

print(f"\n{dead}/{len(MUTANTS)} mutants dead, {survived} survived")
sys.exit(1 if survived else 0)
