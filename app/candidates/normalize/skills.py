"""Skill taxonomy for the Indian tech market (S1.4).

Curated, extensible table: canonical snake_case id -> (category, aliases).
Matching is exact on norm_key — a skill line is already a single claimed
token by the time it gets here (the extractor splits on separators), so no
fuzzy matching: unknown skills stay None rather than being guessed.
"""

from __future__ import annotations

from typing import NamedTuple, Optional

from app.candidates.normalize.text import norm_key


class SkillMatch(NamedTuple):
    canonical: str
    category: str


SKILL_CATEGORIES = frozenset(
    {
        "language", "web", "mobile", "data", "ml", "cloud",
        "devops", "database", "testing", "analytics",
    }
)

# canonical_id: (category, aliases). Aliases are raw human forms; the index
# is built with norm_key so punctuation/case variants collapse.
_TAXONOMY: dict[str, tuple[str, tuple[str, ...]]] = {
    # languages
    "python": ("language", ("python", "python3")),
    "java": ("language", ("java", "core java")),
    "javascript": ("language", ("javascript", "js", "ecmascript", "es6")),
    "typescript": ("language", ("typescript", "ts")),
    "c": ("language", ("c", "c language", "c programming")),
    "cpp": ("language", ("c++", "cpp")),
    "csharp": ("language", ("c#", "csharp", "c sharp")),
    "go": ("language", ("go", "golang")),
    "rust": ("language", ("rust",)),
    "kotlin": ("language", ("kotlin",)),
    "swift": ("language", ("swift",)),
    "php": ("language", ("php",)),
    "ruby": ("language", ("ruby",)),
    "scala": ("language", ("scala",)),
    "r": ("language", ("r", "r programming")),
    "sql": ("language", ("sql",)),
    # web / backend
    "react": ("web", ("react", "reactjs", "react.js")),
    "angular": ("web", ("angular", "angularjs", "angular.js")),
    "vuejs": ("web", ("vue", "vuejs", "vue.js")),
    "nextjs": ("web", ("next.js", "nextjs")),
    "nodejs": ("web", ("node", "nodejs", "node.js")),
    "express": ("web", ("express", "express.js", "expressjs")),
    "django": ("web", ("django", "django rest framework", "drf")),
    "flask": ("web", ("flask",)),
    "fastapi": ("web", ("fastapi", "fast api")),
    "spring": ("web", ("spring", "spring boot", "springboot")),
    "dotnet": ("web", (".net", "dotnet", ".net core", "asp.net")),
    "html": ("web", ("html", "html5")),
    "css": ("web", ("css", "css3")),
    "graphql": ("web", ("graphql",)),
    "rest_api": ("web", ("rest", "rest api", "restful api", "rest apis", "restful apis")),
    # mobile
    "android": ("mobile", ("android", "android development")),
    "ios": ("mobile", ("ios", "ios development")),
    "flutter": ("mobile", ("flutter",)),
    "react_native": ("mobile", ("react native",)),
    # data engineering
    "apache_spark": ("data", ("spark", "apache spark", "pyspark")),
    "kafka": ("data", ("kafka", "apache kafka")),
    "airflow": ("data", ("airflow", "apache airflow")),
    "hadoop": ("data", ("hadoop", "apache hadoop")),
    "hive": ("data", ("hive", "apache hive")),
    "dbt": ("data", ("dbt",)),
    "snowflake": ("data", ("snowflake",)),
    "databricks": ("data", ("databricks",)),
    "etl": ("data", ("etl", "elt", "etl pipelines")),
    "pandas": ("data", ("pandas",)),
    "numpy": ("data", ("numpy",)),
    # ML / AI
    "machine_learning": ("ml", ("machine learning", "ml")),
    "deep_learning": ("ml", ("deep learning", "neural networks")),
    "pytorch": ("ml", ("pytorch", "torch")),
    "tensorflow": ("ml", ("tensorflow", "tf")),
    "scikit_learn": ("ml", ("scikit-learn", "sklearn", "scikit learn")),
    "nlp": ("ml", ("nlp", "natural language processing")),
    "computer_vision": ("ml", ("computer vision", "opencv")),
    "generative_ai": ("ml", ("generative ai", "genai", "gen ai", "llm", "llms", "large language models")),
    "langchain": ("ml", ("langchain", "langgraph")),
    "hugging_face": ("ml", ("hugging face", "huggingface", "transformers")),
    "rag": ("ml", ("rag", "retrieval augmented generation")),
    "mlops": ("ml", ("mlops", "ml ops")),
    # cloud
    "aws": ("cloud", ("aws", "amazon web services")),
    "azure": ("cloud", ("azure", "microsoft azure")),
    "gcp": ("cloud", ("gcp", "google cloud", "google cloud platform")),
    # devops
    "docker": ("devops", ("docker", "containers")),
    "kubernetes": ("devops", ("kubernetes", "k8s")),
    "jenkins": ("devops", ("jenkins",)),
    "terraform": ("devops", ("terraform",)),
    "git": ("devops", ("git", "github", "gitlab", "bitbucket")),
    "ci_cd": ("devops", ("ci/cd", "cicd", "ci cd", "continuous integration")),
    "linux": ("devops", ("linux", "unix", "shell scripting", "bash")),
    # databases
    "mysql": ("database", ("mysql",)),
    "postgresql": ("database", ("postgres", "postgresql")),
    "mongodb": ("database", ("mongo", "mongodb")),
    "redis": ("database", ("redis",)),
    "oracle_db": ("database", ("oracle", "oracle db", "pl/sql", "plsql")),
    "sql_server": ("database", ("sql server", "mssql", "microsoft sql server", "t-sql")),
    "elasticsearch": ("database", ("elasticsearch", "elastic search", "opensearch")),
    "cassandra": ("database", ("cassandra",)),
    "dynamodb": ("database", ("dynamodb", "dynamo db")),
    # testing
    "selenium": ("testing", ("selenium", "selenium webdriver")),
    "cypress": ("testing", ("cypress",)),
    "junit": ("testing", ("junit", "testng")),
    "pytest": ("testing", ("pytest",)),
    "manual_testing": ("testing", ("manual testing", "qa", "quality assurance")),
    # analytics / BI
    "power_bi": ("analytics", ("power bi", "powerbi")),
    "tableau": ("analytics", ("tableau",)),
    "excel": ("analytics", ("excel", "ms excel", "microsoft excel", "advanced excel")),
}


def _build_index() -> dict[str, SkillMatch]:
    index: dict[str, SkillMatch] = {}
    for canonical, (category, aliases) in _TAXONOMY.items():
        match = SkillMatch(canonical=canonical, category=category)
        for alias in aliases:
            key = norm_key(alias)
            existing = index.get(key)
            if existing is not None and existing != match:  # taxonomy bug
                raise ValueError(
                    f"skill alias {alias!r} claimed by {existing.canonical} and {canonical}"
                )
            index[key] = match
    return index


_INDEX = _build_index()

# Curation overlay (S6.3): human-reviewed alias -> SkillMatch, loaded from the
# curation store at startup and refreshed on each resolve. Static _INDEX always
# wins; the overlay only fills genuine gaps. No per-call I/O — normalize_skill
# stays a pure dict lookup.
_CURATED_OVERLAY: dict[str, SkillMatch] = {}


def set_curated_overlay(mapping: dict[str, SkillMatch]) -> None:
    """Replace the curation overlay (a copy is stored)."""
    global _CURATED_OVERLAY
    _CURATED_OVERLAY = dict(mapping)


def clear_curated_overlay() -> None:
    _CURATED_OVERLAY.clear()


def canonical_ids() -> frozenset[str]:
    """Every known canonical skill id — static plus curated — for validation."""
    return frozenset(_TAXONOMY.keys()) | {m.canonical for m in _CURATED_OVERLAY.values()}


def category_for_canonical(canonical: str) -> Optional[str]:
    """Category of a known canonical id (static first, then curated); None if unknown."""
    entry = _TAXONOMY.get(canonical)
    if entry is not None:
        return entry[0]
    for m in _CURATED_OVERLAY.values():
        if m.canonical == canonical:
            return m.category
    return None


def normalize_skill(name: str) -> Optional[SkillMatch]:
    key = norm_key(name or "")
    if not key:
        return None
    return _INDEX.get(key) or _CURATED_OVERLAY.get(key)
