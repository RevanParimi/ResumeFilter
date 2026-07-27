from app.core.config import Settings


def test_search_default_limit_default_and_bound():
    assert Settings(_env_file=None, openrouter_api_key="").search_default_limit == 50
