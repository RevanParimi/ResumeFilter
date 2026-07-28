import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _settings() -> Settings:
    return Settings(_env_file=None, openrouter_api_key="")


def test_dash_board_top_n_default():
    assert _settings().dash_board_top_n == 20


def test_dash_board_top_n_env_override(monkeypatch):
    monkeypatch.setenv("DEE_DASH_BOARD_TOP_N", "5")
    assert Settings(_env_file=None, openrouter_api_key="").dash_board_top_n == 5


def test_dash_board_top_n_rejects_zero():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, openrouter_api_key="", dash_board_top_n=0)
