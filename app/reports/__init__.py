"""Durable reports + human outcome records, in the MAIN database (S8.1).

Folded out of ``app/services/report_store.py``, which was raw stdlib sqlite3 in
a second database file: no foreign key to ``candidates``, no cascade, no
atomicity with candidate erasure, and a bespoke ``ALTER TABLE ... ADD COLUMN``
in a try/except standing in for a migration system. See PI-8 §2.1.
"""
