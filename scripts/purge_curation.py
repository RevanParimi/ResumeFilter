"""Physically remove expired owned curation observations; run daily after migrations.

Uses the configured candidates database. Prints a count only, never raw terms.
Does not remove legacy content or approved vocabulary.
"""

from app.curation.service import build_curation_service


def main() -> None:
    removed = build_curation_service().purge_expired()
    print(f"Expired curation observations removed: {removed}")


if __name__ == "__main__":
    main()
