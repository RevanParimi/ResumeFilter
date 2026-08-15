"""Every models module must be registered in BOTH places that build a schema.

REVIEW FINDING (S8.3 Phase B). `Base.metadata` only knows a table once its
module has been imported, and there are TWO hand-maintained lists of those
imports: `alembic/env.py` (which migrations use) and `tests/conftest.py` (which
`Base.metadata.create_all` uses). Phase B added `app/rights/models.py` to the
first and not the second.

The suite stayed GREEN, which is the whole problem: within a full run some
earlier test had already imported `app.rights.store`, so the table existed by
the time a later fixture called `create_all`. Running one test on its own --
what a developer actually does while working -- raised
`OperationalError: no such table: data_principal_requests`.

So this is the drift guard for both lists, in the family that already catches
migration-vs-ORM drift in tests/test_migrations.py.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
#: `import app.<x>.models` OR `from app.<x>.models import ...`. Both register
#: the module on Base.metadata, and conftest genuinely uses both spellings --
#: a scanner that knew only the first would report a false gap, which is its
#: own kind of guard that cannot be trusted.
_IMPORT = re.compile(
    r"^(?:import|from) (app\.[\w.]+\.models)\b", re.MULTILINE
)


def _modules_on_disk() -> set[str]:
    """Every `src/app/**/models.py` that actually declares a table.

    S8.7: the base for BOTH the glob and the dotted name is `src/`, not the
    repository root. Only the first is obvious -- leaving `relative_to(ROOT)`
    in place yields `src.app.rights.models`, which matches nothing in either
    import list, so every module reads as missing.
    """
    out: set[str] = set()
    src = ROOT / "src"
    for path in (src / "app").rglob("models.py"):
        text = path.read_text(encoding="utf-8")
        if "__tablename__" not in text:
            continue
        rel = path.relative_to(src).with_suffix("")
        out.add(".".join(rel.parts))
    return out


def _registered_in(relative_path: str) -> set[str]:
    return set(_IMPORT.findall((ROOT / relative_path).read_text(encoding="utf-8")))


def test_the_scan_finds_something():
    """Guards the two tests below from passing by matching nothing."""
    found = _modules_on_disk()
    assert "app.candidates.models" in found
    assert "app.rights.models" in found
    assert len(found) >= 10


def test_alembic_env_registers_every_models_module():
    """A module missing here is a table Alembic autogenerate cannot see, so
    tests/test_migrations.py compares against an incomplete picture."""
    missing = _modules_on_disk() - _registered_in("alembic/env.py")
    assert missing == set(), (
        f"alembic/env.py does not import: {sorted(missing)} -- "
        f"their tables are invisible to migrations"
    )


def test_conftest_registers_every_models_module():
    """A module missing here is a table `Base.metadata.create_all` does not
    create, and the failure is ORDER-DEPENDENT: green in a full run, and
    `no such table` the moment somebody runs one test on its own."""
    missing = _modules_on_disk() - _registered_in("tests/conftest.py")
    assert missing == set(), (
        f"tests/conftest.py does not import: {sorted(missing)} -- "
        f"create_all will silently skip their tables"
    )
