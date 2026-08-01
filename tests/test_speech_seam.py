"""The ASR seam mirrors the LLM seam: an ABC, a live client, and a Null that
refuses. No key => audio is refused with a distinct error and the interview
runs as a TEXT interview. That is the deterministic fallback, stated honestly
rather than degraded silently."""

import pytest

from app.core.config import Settings
from app.services.speech import (
    NullSpeech, OpenRouterSpeech, SpeechClient, SpeechFailed, SpeechUnavailable,
    Transcript, build_speech, format_for_mime,
)


@pytest.fixture
def s(monkeypatch) -> Settings:
    monkeypatch.setenv("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    return Settings(_env_file=None, openrouter_api_key="")


def test_no_key_builds_the_refusing_client(s):
    assert isinstance(build_speech(s), NullSpeech)


def test_a_key_plus_the_openrouter_provider_builds_the_live_client(monkeypatch):
    monkeypatch.setenv("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    keyed = Settings(_env_file=None, openrouter_api_key="sk-test",
                     speech_provider="openrouter")
    assert isinstance(build_speech(keyed), OpenRouterSpeech)


@pytest.mark.parametrize("provider", ["sarvam", "local"])
def test_declared_but_unimplemented_providers_are_inert_even_with_a_key(
    monkeypatch, provider
):
    """Inertness must read the same at every door -- the S7.2 review lesson."""
    monkeypatch.setenv("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    keyed = Settings(_env_file=None, openrouter_api_key="sk-test",
                     speech_provider=provider)
    assert isinstance(build_speech(keyed), NullSpeech)


async def test_null_speech_refuses_with_speech_unavailable(s):
    with pytest.raises(SpeechUnavailable):
        await NullSpeech(s).atranscribe(audio_b64="AAAA", mime="audio/wav")


def test_known_mimes_map_to_provider_formats():
    assert format_for_mime("audio/wav") == "wav"
    assert format_for_mime("audio/mpeg") == "mp3"
    assert format_for_mime("audio/webm") == "webm"
    assert format_for_mime("audio/WAV; codecs=1") == "wav"


def test_an_unknown_mime_is_refused_before_any_call():
    with pytest.raises(SpeechFailed):
        format_for_mime("application/pdf")


def test_transcript_carries_text_and_optional_duration():
    t = Transcript(text="hello", duration_seconds=1.5, model="voxtral")
    assert t.text == "hello" and t.duration_seconds == 1.5


def test_speech_client_is_abstract(s):
    with pytest.raises(TypeError):
        SpeechClient(s)   # type: ignore[abstract]


async def test_fake_speech_records_calls_and_returns_its_script(s):
    from tests.conftest import FakeSpeech

    fake = FakeSpeech(text="I used 8 A100s for 14 hours")
    out = await fake.atranscribe(audio_b64="AAAA", mime="audio/wav")
    assert out.text == "I used 8 A100s for 14 hours"
    assert fake.calls == [("AAAA", "audio/wav")]


async def test_fake_speech_can_be_scripted_to_fail(s):
    from tests.conftest import FakeSpeech

    fake = FakeSpeech(fail=SpeechFailed("upstream down"))
    with pytest.raises(SpeechFailed):
        await fake.atranscribe(audio_b64="AAAA", mime="audio/wav")
