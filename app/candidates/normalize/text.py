"""Shared key normalization for the S1.4 lookup tables.

Alias tables are indexed by norm_key(alias) and probed with norm_key(input),
so "Node.js", "node js" and "NODE-JS" hit the same row. '+' and '#' survive
because C++/C# would die under plain word-splitting.
"""

from __future__ import annotations

import re

_NON_KEY = re.compile(r"[^\w+#]+")


def norm_key(value: str) -> str:
    """Lowercase; collapse punctuation/whitespace runs to single spaces."""
    return _NON_KEY.sub(" ", value.lower()).strip()
