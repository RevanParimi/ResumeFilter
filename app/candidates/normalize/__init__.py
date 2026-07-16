"""India normalization (S1.4) — deterministic enrichment of CandidateProfile.

Pure functions over curated lookup tables; no LLM anywhere (nothing to
degrade). Claimed values are NEVER overwritten: canonical values land in
sibling fields and stay None when a value isn't in the tables — advisory
system, never guess. The orchestrator normalize_profile arrives in Task 5.
"""
