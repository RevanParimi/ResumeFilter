"""Screening batches: the surface the fraud-screen wedge is sold on (S8.4 Phase B).

An organisation registers a batch of resumes, drives bounded processing calls,
and reads a ranked queue plus a roll-up summary. Every read here is org-scoped
by construction -- see ``store.ScreeningStore``, whose every method takes
``org_id`` first, and ``TENANCY.md``.
"""
