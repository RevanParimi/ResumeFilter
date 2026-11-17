# Feature registry, materialization and ranking

Reviewed on 2026-11-17. `src/app/features/` defines deterministic features from
candidate profiles and evaluation reports, persists point-in-time vectors and
provides the ranking primitives used by [job boards](MATCHING.md).

## Catalog and contracts

`FeatureSpec` pins a name, version, type, source, nullability and optional range
or categories. `FeatureRegistry` validates extractor outputs against their spec.
Extractors read only `FeatureContext{candidate_id, as_of, profile, report}`;
they do not read stores or the wall clock.

The default view is **`core_v1`, version 4**, containing **23 features**:

| Source | Count | Members |
|---|---:|---|
| `candidate.*` | 12 | Experience, education, institution tier, CGPA, notice period, location, GitHub presence and profile counts |
| `depth.*` | 7 | Depth score/band, confidence, verdict/flag/deferred counts and coherent-claim ratio |
| `fabrication.*` | 4 | Factual-risk score/band, major cross-field findings and content-overlap band |

Version 3 removed cross-company ledger/reputation features; version 4 removed
the writing-style feature. Older member sets are not served as version 4.
Unknown or incompatible historical risk semantics yield missing risk values.
`FeatureView` pins exact member versions. Change a feature's version when its
computation changes; materialization preserves the selected view version.

## Point-in-time materialization

`build_context` reads the latest profile extraction at or before `as_of` and
the latest report whose own creation time is at or before that cutoff. It
returns `None` for an absent candidate and applies no consent policy itself.

`materialize_candidate` computes and validates the selected view, then masks
consent-tagged values when authorization is withheld. `materialize_all` shares
one resolved cutoff across a run. The operator route
`POST /features/materialize` returns that cutoff and materialized/skipped counts.

`FeatureStore` upserts one `ml_feature_vectors` row per
`(candidate_id, as_of, view_name, view_version)`, storing values, missing fields,
consent state and materialization time. Distinct cutoffs coexist; equal cutoffs
update in place. Timestamps are stored and queried as naive UTC. The candidate
foreign key cascades on erasure.

If erasure wins before the consent audit commits, the materializer skips the
missing subject. A failed audit transaction is rolled back before testing
whether the candidate disappeared; unrelated errors propagate. If the audit
commits first, erasure cascades it away and the vector write guard refuses a
subsequent write for that subject.

## Consent masking

No shipped feature is consent-tagged. The mechanism remains intact and its
tests use three gated probe features. This dormancy applies only to feature
masking; verification and interview disclosures still enforce their consent
purposes. All `ConsentPurpose` values remain valid for stored grants.

A spec with source `ledger` or `reputation` must require consent. Materialization
checks for any active `ledger_read` grant at the historical cutoff, org-specific
or wildcard, and audits allowed and withheld decisions as `feature.materialize`.
Withheld features become `None` and appear in `missing`; first-party features
are unchanged.

Serving checks **current** consent for the requesting org or a wildcard before
filters, normalization and scoring. Historical consent or a cached allowed bit
cannot authorize a current read. Masking changes only the serving copy; a new
grant cannot fill a value withheld in the stored vector. Consent reads are
snapshots, not locks across response delivery.

## Ranking

`ranking_schema.py` and `ranking.py` are pure: no I/O, store or clock. Filters
validate operators against feature types; null fails comparisons, while
`exists`/`missing` handle absence explicitly. Ordinal comparisons use category
order. Unknown features and invalid type/operator combinations raise errors.

Scoring normalizes present terms to `[0, 1]`, reverses lower-is-better terms,
and computes their weighted mean. Ranged numeric features use the declared
range; ordinals use category position; booleans use 0/1. Range-less counts use
pool min/max, with neutral 0.5 for a degenerate pool. Unordered categorical
values cannot be ranked.

Missing or withheld terms drop out and remaining weights are renormalized.
Results expose `missing`, weighted `coverage` and per-term contributions. There
is no missing-consent score penalty or automatic rejection; relative order can
still change when terms or normalization pools change. Ties use candidate ID.

Matching selects each candidate's newest vector at or before the cutoff and
reads that candidate's profile at the vector's own timestamp. Refreshing one
candidate does not remove older eligible snapshots for other candidates.

## Validation

Offline tests cover spec/output validation, the 23-feature catalog, versioned
views, historical slicing, idempotent storage, consent masking and audits,
erasure races, filters, normalization, coverage and ranking explanations.
