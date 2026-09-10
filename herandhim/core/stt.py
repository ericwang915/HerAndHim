"""
Speech-to-text: Deepgram (cloud) or faster-whisper (local).

Provides both sync and async helpers so every channel can call
``transcribe_audio`` without worrying about event-loop differences.

Returns the transcript string on success, or ``None`` when no usable
provider is configured (no Deepgram key and no local model installed).

Provider selection — ``stt.provider`` in herandhim.json (or the
``HERANDHIM_STT_PROVIDER`` env var):
  - ``"auto"`` (default) — Deepgram when a key is set, otherwise local
    faster-whisper when installed. If Deepgram errors out and the local
    model is installed, it steps in as a fallback so the voice note is
    never lost.
  - ``"deepgram"`` — cloud only; audio goes to Deepgram.
  - ``"local"``  — faster-whisper only; audio never leaves the machine.
    Requires ``pip install "herandhim[stt-local]"``.

Local model settings live under ``stt.local``:
  - ``model``: ``tiny`` / ``base`` (default) / ``small`` — bigger is more
    accurate but slower and hungrier (~1 GB / ~1 GB / ~2 GB RAM at int8).
  - ``computeType``: ``int8`` (default — fastest on CPU), ``float32``, …
  - ``device``: ``cpu`` (default) or ``cuda``.
  - ``language``: ``auto`` (default) or a code like ``zh`` / ``en``.

Deepgram language is configurable via ``deepgram.language``:
  - ``"auto"`` (default) — auto-detect, with fallback retries for short clips
  - ``"zh"``/``"en"``/``"ja"``/… — force a specific language
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_DEEPGRAM_BASE = "https://api.deepgram.com/v1/listen"

_FALLBACK_LANGUAGES = ("zh", "en", "ja", "ko", "es", "fr", "de")

_NO_KEY_MSG = (
    "Voice messages are not enabled yet.\n\n"
    "To unlock voice input, you need a Deepgram API key:\n"
    "1. Go to https://console.deepgram.com/signup and create a free account\n"
    "2. After signing in, go to API Keys (left sidebar)\n"
    "3. Click \"Create a New API Key\", give it a name, and copy the key\n"
    "4. Set it in Config -> deepgram -> apiKey (or set the DEEPGRAM_API_KEY env var)\n\n"
    "Deepgram offers $200 free credits on signup — no credit card required.\n\n"
    "Prefer to keep audio on your machine? Install local transcription instead:\n"
    "pip install \"herandhim[stt-local]\" — no key needed, audio never leaves the box."
)

_NO_LOCAL_MSG = (
    "Local voice transcription is selected but faster-whisper is not installed.\n\n"
    "Install it with:\n"
    "pip install \"herandhim[stt-local]\"\n\n"
    "Then send your voice note again — audio will be transcribed on this "
    "machine and never leave it."
)

_VALID_PROVIDERS = ("auto", "deepgram", "local")


def _get_provider() -> str:
    from .. import config
    val = (config.get_str("stt", "provider", env="HERANDHIM_STT_PROVIDER") or "auto").strip().lower()
    if val not in _VALID_PROVIDERS:
        logger.warning("[STT] Unknown stt.provider %r; using 'auto'", val)
        return "auto"
    return val


def _get_key() -> str | None:
    from .. import config
    return config.get("deepgram", "apiKey", env="DEEPGRAM_API_KEY") or None


def _get_config_language() -> str:
    from .. import config
    return config.get_str("deepgram", "language") or "auto"


def _get_model() -> str:
    from .. import config
    return config.get_str("deepgram", "model") or "nova-2"


def _build_url(language: str | None = None) -> str:
    """Build the Deepgram API URL.

    If *language* is given, use it directly (e.g. ``"zh"``).
    If ``None``, read from config (default ``"auto"`` → detect_language).
    """
    model = _get_model()
    lang = language or _get_config_language()

    params = [f"model={model}", "smart_format=true", "punctuate=true"]

    if lang == "auto":
        params.append("detect_language=true")
    else:
        params.append(f"language={lang}")

    return f"{_DEEPGRAM_BASE}?{'&'.join(params)}"


def _headers(key: str, content_type: str) -> dict[str, str]:
    return {
        "Authorization": f"Token {key}",
        "Content-Type": content_type,
    }


# ── Local (faster-whisper) ────────────────────────────────────────────────────

# The loaded model is cached: loading takes seconds, transcribing takes
# fractions of one. Keyed so a config change picks up the new model.
_local_model = None
_local_model_key: tuple[str, str, str] | None = None


def local_available() -> bool:
    """True when the faster-whisper package is importable."""
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _get_local_settings() -> tuple[str, str, str, str]:
    """Returns (model_size, device, compute_type, language)."""
    from .. import config
    size = config.get_str("stt", "local", "model", env="HERANDHIM_STT_LOCAL_MODEL") or "base"
    device = config.get_str("stt", "local", "device") or "cpu"
    compute = config.get_str("stt", "local", "computeType") or "int8"
    lang = config.get_str("stt", "local", "language") or "auto"
    return size, device, compute, lang


def _get_local_model():
    global _local_model, _local_model_key
    from faster_whisper import WhisperModel

    size, device, compute, _lang = _get_local_settings()
    key = (size, device, compute)
    if _local_model is None or _local_model_key != key:
        logger.info("[STT] Loading faster-whisper model=%s device=%s compute=%s "
                    "(first load downloads the model)", size, device, compute)
        _local_model = WhisperModel(size, device=device, compute_type=compute)
        _local_model_key = key
    return _local_model


def transcribe_bytes_local(audio: bytes) -> str:
    """Transcribe on this machine with faster-whisper. Blocking; run in a thread."""
    import io

    model = _get_local_model()
    _size, _device, _compute, lang = _get_local_settings()
    language = None if lang == "auto" else lang

    segments, info = model.transcribe(io.BytesIO(audio), language=language, vad_filter=True)
    text = " ".join(seg.text.strip() for seg in segments).strip()
    logger.info("[STT] Local transcription done (lang=%s, bytes=%d)",
                getattr(info, "language", language), len(audio))
    return text


async def _transcribe_local_async(audio: bytes) -> str:
    import asyncio
    return await asyncio.to_thread(transcribe_bytes_local, audio)


# ── Async ─────────────────────────────────────────────────────────────────────

async def transcribe_bytes_async(
    audio: bytes, content_type: str = "audio/ogg"
) -> str | None:
    """Non-blocking transcription via the configured provider.

    Returns the transcript text (possibly ``""`` when no speech was
    recognised), or ``None`` when no usable provider is configured.
    """
    provider = _get_provider()
    key = _get_key()

    if provider == "local":
        if not local_available():
            return None
        return await _transcribe_local_async(audio)

    if provider == "deepgram":
        if not key:
            return None
        return await _transcribe_deepgram_async(key, audio, content_type)

    # auto: Deepgram when a key is set, local otherwise; local also covers
    # for Deepgram when the cloud call blows up.
    if key:
        try:
            return await _transcribe_deepgram_async(key, audio, content_type)
        except Exception as exc:
            if local_available():
                logger.warning("[STT] Deepgram failed (%s); falling back to local faster-whisper", exc)
                return await _transcribe_local_async(audio)
            raise
    if local_available():
        return await _transcribe_local_async(audio)
    return None


async def _transcribe_deepgram_async(
    key: str, audio: bytes, content_type: str
) -> str:
    """Deepgram transcription with automatic language fallback for short clips."""
    cfg_lang = _get_config_language()

    if cfg_lang != "auto":
        return await _call_async(key, audio, content_type, language=cfg_lang)

    transcript = await _call_async(key, audio, content_type, language=None)
    if transcript:
        return transcript

    for lang in _FALLBACK_LANGUAGES:
        transcript = await _call_async(key, audio, content_type, language=lang)
        if transcript:
            logger.info("[STT] Fallback to language=%s succeeded", lang)
            return transcript

    logger.warning("[STT] All fallback languages returned empty (bytes=%d)", len(audio))
    return ""


async def _call_async(
    key: str, audio: bytes, content_type: str, language: str | None
) -> str:
    import httpx

    url = _build_url(language=language or "auto")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url, content=audio,
            headers=_headers(key, content_type),
        )
        resp.raise_for_status()
        return _extract_transcript(resp.json())


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_transcript(data: dict) -> str:
    try:
        return (
            data.get("results", {})
            .get("channels", [{}])[0]
            .get("alternatives", [{}])[0]
            .get("transcript", "")
        )
    except (IndexError, KeyError):
        return ""


def no_key_message() -> str:
    """User-facing message when no STT provider is usable."""
    if _get_provider() == "local":
        return _NO_LOCAL_MSG
    return _NO_KEY_MSG
