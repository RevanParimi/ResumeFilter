"""ASR seam -- config-driven, key never hardcoded (S7.3).

Deliberately shaped like app/services/llm.py, which has survived six PIs: an
abstract client, a live OpenRouter implementation, and a Null that refuses so
tests need no network and a key-less deployment still works.

The refusal matters and is not an error path to paper over. With no key an
AUDIO answer is refused with SpeechUnavailable, the route turns that into a 422
naming the text channel, and the interview proceeds as a text interview.
Nothing silently degrades to a worse number.

TTS is deliberately absent (spec section 0.3): OpenRouter serves no TTS and the
local option is a GPU dependency neither the offline suite nor the key-less
smoke could exercise. Questions are delivered as text.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class SpeechUnavailable(Exception):
    """No speech provider is configured. The caller should offer the text
    channel -- this is the designed no-key path, not a malfunction."""


class SpeechFailed(Exception):
    """A configured provider could not transcribe this audio (bad format,
    timeout, upstream error). The caller must NOT record a turn: a retry has to
    be free, so a vendor outage never costs a candidate their answer."""


#: mime -> the `format` string the OpenAI-wire audio part expects.
AUDIO_FORMATS: dict[str, str] = {
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "mp4",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/flac": "flac",
}


def format_for_mime(mime: str) -> str:
    """Resolve a mime type, or refuse before any vendor call is made."""
    fmt = AUDIO_FORMATS.get((mime or "").split(";")[0].strip().casefold())
    if not fmt:
        raise SpeechFailed(f"unsupported audio type: {mime!r}")
    return fmt


class Transcript(BaseModel):
    text: str = ""
    duration_seconds: Optional[float] = None
    model: Optional[str] = None


class SpeechClient(ABC):
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    @abstractmethod
    async def atranscribe(self, *, audio_b64: str, mime: str) -> Transcript:
        ...


class OpenRouterSpeech(SpeechClient):
    """Live ASR through an audio-capable OpenRouter model (`asr_model`), on the
    OpenAI-compatible wire. Same account and SDK as the text tiers -- no second
    vendor relationship for v0 (MODELS.md, 2026-07-26)."""

    _SYSTEM = (
        "Transcribe the spoken answer verbatim in English. Return only the "
        "transcript text, with no commentary, labels, or timestamps."
    )

    def __init__(self, settings: Optional[Settings] = None) -> None:
        super().__init__(settings)
        from openai import AsyncOpenAI  # local import; optional at test time

        headers: dict[str, str] = {}
        if self.settings.openrouter_app_url:
            headers["HTTP-Referer"] = self.settings.openrouter_app_url
        if self.settings.openrouter_app_title:
            headers["X-Title"] = self.settings.openrouter_app_title

        self._client = AsyncOpenAI(
            api_key=self.settings.openrouter_api_key.get_secret_value(),
            base_url=self.settings.openrouter_base_url,
            timeout=self.settings.speech_timeout_seconds,
            max_retries=self.settings.speech_max_retries,
            default_headers=headers or None,
        )

    async def atranscribe(self, *, audio_b64: str, mime: str) -> Transcript:
        fmt = format_for_mime(mime)   # refuse before spending a call
        model = self.settings.asr_model
        try:
            resp = await self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": self._SYSTEM},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Transcribe this answer."},
                            {
                                "type": "input_audio",
                                "input_audio": {"data": audio_b64, "format": fmt},
                            },
                        ],
                    },
                ],
            )
        except Exception as exc:  # noqa: BLE001 -- one failure surface for the caller
            log.warning("asr_failed", model=model, error=str(exc))
            raise SpeechFailed(f"transcription failed: {exc}") from exc

        text = (resp.choices[0].message.content or "").strip()
        if not text:
            raise SpeechFailed("transcription returned no text")
        return Transcript(text=text, model=model)


class NullSpeech(SpeechClient):
    """No-provider fallback: refuses, so the caller offers the text channel."""

    async def atranscribe(self, *, audio_b64: str, mime: str) -> Transcript:
        raise SpeechUnavailable(
            "no speech provider is configured; answer this question in text"
        )


def build_speech(settings: Optional[Settings] = None) -> SpeechClient:
    settings = settings or get_settings()
    if settings.speech_provider == "openrouter" and settings.has_openrouter_key:
        return OpenRouterSpeech(settings)
    # `sarvam` and `local` are DECLARED but unimplemented in v0. They build the
    # refusing client even with a key -- a declared-but-inert provider must
    # answer the same way at every door (the S7.2 review lesson).
    log.warning(
        "speech_unavailable",
        provider=settings.speech_provider,
        detail="Audio answers will be refused; the text channel still works.",
    )
    return NullSpeech(settings)
