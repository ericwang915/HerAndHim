"""
Text-to-speech: ElevenLabs (cloud) or Piper / Kokoro (local).

The speak side of the voice story — ``core/stt.py`` hears, this module
speaks. Same shape as STT on purpose: one provider knob, an ``auto`` mode
that never surprises existing users, and a local engine that keeps text on
the machine.

Returns a :class:`VoiceClip` on success, or ``None`` when no usable
provider is configured (no ElevenLabs key and no local engine installed).

Provider selection — ``tts.provider`` in herandhim.json (or the
``HERANDHIM_TTS_PROVIDER`` env var):
  - ``"auto"`` (default) — ElevenLabs when a key is set, otherwise local
    Piper when installed. If ElevenLabs errors out and the local engine is
    installed, it steps in as a fallback so the voice reply is never lost.
  - ``"elevenlabs"`` — cloud only; text goes to ElevenLabs.
  - ``"local"`` — Piper (or Kokoro) only; text never leaves the machine.
    Requires ``pip install "herandhim[tts-local]"``.

Local engine settings live under ``tts.local``:
  - ``engine``: ``piper`` (default — small, CPU-friendly) or ``kokoro``
    (better prosody, needs ``pip install kokoro soundfile`` yourself).
  - ``voice``: a Piper voice name (auto-downloaded on first use, default
    ``zh_CN-huayan-medium`` — a natural Mandarin voice) or an absolute
    path to a ``.onnx`` voice model you downloaded yourself.
  - ``kokoroVoice`` / ``kokoroLang``: Kokoro voice (default ``zf_xiaobei``)
    and language code (default ``z`` = Mandarin).

Telegram voice notes must be OGG/Opus or MP3. ElevenLabs already returns
MP3; Piper/Kokoro produce WAV, which is converted with **ffmpeg** (with
opus support — the standard build has it). Without ffmpeg the local
engines still work but yield WAV, which channels treat as "no voice" and
fall back to text — install ffmpeg to complete the local voice path.

Reply-in-kind (voice note in → voice note back) is decided here too, via
``channels.telegram.replyInKindVoice``: ``"auto"`` (default — voice-reply
when a provider is usable, capped by ``voiceReplyMaxChars``, and only
sometimes for tiny acks so it never spams), ``true`` (always, still
length-capped), or ``false`` (never). On any TTS failure the channel
silently falls back to text — a reply is never dropped.
"""

from __future__ import annotations

import logging
import random
import re
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_ELEVENLABS_API = "https://api.elevenlabs.io/v1/text-to-speech"
_ELEVENLABS_DEFAULT_VOICE = "ByhETIclHirOlWnWKhHc"
_ELEVENLABS_DEFAULT_MODEL = "eleven_multilingual_v2"

_DEFAULT_PIPER_VOICE = "zh_CN-huayan-medium"
_DEFAULT_KOKORO_VOICE = "zf_xiaobei"
_DEFAULT_KOKORO_LANG = "z"  # Mandarin

_VALID_PROVIDERS = ("auto", "elevenlabs", "local")

_NO_KEY_MSG = (
    "Voice replies are not enabled yet.\n\n"
    "To unlock her voice, you need an ElevenLabs API key:\n"
    "1. Go to https://elevenlabs.io and create a free account\n"
    "2. Open your profile -> API Keys and copy the key\n"
    "3. Set it in Config -> elevenlabs -> apiKey (or set the ELEVENLABS_API_KEY env var)\n\n"
    "Prefer to keep text on your machine? Install local speech instead:\n"
    "pip install \"herandhim[tts-local]\" — no key needed, nothing leaves the box\n"
    "(plus ffmpeg, which converts audio for Telegram voice notes)."
)

_NO_LOCAL_MSG = (
    "Local speech is selected but Piper is not installed.\n\n"
    "Install it with:\n"
    "pip install \"herandhim[tts-local]\"\n\n"
    "Also make sure ffmpeg is on the PATH — it converts Piper's audio into "
    "the OGG/Opus format Telegram voice notes need. The voice model "
    "downloads automatically on first use."
)


@dataclass
class VoiceClip:
    """A synthesized voice message ready to send."""

    data: bytes
    format: str  # "mp3" | "ogg" | "wav"

    @property
    def filename(self) -> str:
        return f"voice.{self.format}"

    @property
    def telegram_ready(self) -> bool:
        """Telegram send_voice accepts OGG/Opus, MP3 and M4A — not WAV."""
        return self.format in ("ogg", "mp3", "m4a")


# ── Config accessors ──────────────────────────────────────────────────────────


def _get_provider() -> str:
    from .. import config
    val = (config.get_str("tts", "provider", env="HERANDHIM_TTS_PROVIDER") or "auto").strip().lower()
    if val not in _VALID_PROVIDERS:
        logger.warning("[TTS] Unknown tts.provider %r; using 'auto'", val)
        return "auto"
    return val


def _get_key() -> str | None:
    from .. import config
    return config.get("elevenlabs", "apiKey", env="ELEVENLABS_API_KEY") or None


def _get_elevenlabs_voice() -> str:
    from .. import config
    return config.get_str("elevenlabs", "voiceId") or _ELEVENLABS_DEFAULT_VOICE


def _get_elevenlabs_model() -> str:
    from .. import config
    return config.get_str("elevenlabs", "model") or _ELEVENLABS_DEFAULT_MODEL


def _get_local_settings() -> tuple[str, str]:
    """Returns (engine, voice) for the local path."""
    from .. import config
    engine = (config.get_str("tts", "local", "engine") or "piper").strip().lower()
    voice = config.get_str("tts", "local", "voice", env="HERANDHIM_TTS_LOCAL_VOICE") \
        or _DEFAULT_PIPER_VOICE
    return engine, voice


# ── Local (Piper / Kokoro) ────────────────────────────────────────────────────

# The loaded voice is cached: loading takes seconds, synthesis fractions of
# one. Keyed so a config change picks up the new voice.
_piper_voice = None
_piper_voice_key: str | None = None
_kokoro_pipeline = None
_kokoro_pipeline_key: str | None = None


def local_available() -> bool:
    """True when the configured local engine is importable."""
    engine, _voice = _get_local_settings()
    try:
        if engine == "kokoro":
            import kokoro  # noqa: F401
        else:
            import piper  # noqa: F401
        return True
    except ImportError:
        return False


def _voices_dir():
    from .. import config
    d = config.home() / "tts" / "voices"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _download_piper_voice(name: str, dest_dir) -> None:
    """Fetch a Piper voice by name into *dest_dir* (first use only)."""
    logger.info("[TTS] Downloading Piper voice %s (first use only)", name)
    try:
        from piper.download_voices import download_voice
        download_voice(name, dest_dir)
        return
    except Exception as exc:  # older piper-tts or API change — use the CLI
        logger.debug("[TTS] download_voice API unavailable (%s); trying CLI", exc)
    import sys
    subprocess.run(
        [sys.executable, "-m", "piper.download_voices", "--data-dir", str(dest_dir), name],
        check=True, capture_output=True,
    )


def _resolve_piper_voice(voice: str) -> str:
    """Resolve a config value into a path to a ``.onnx`` voice model.

    Accepts an absolute path (used as-is) or a voice name like
    ``zh_CN-huayan-medium`` (looked up under ``<home>/tts/voices/``,
    downloaded on first use).
    """
    import os
    if os.path.isfile(voice):
        return voice
    dest = _voices_dir()
    path = dest / f"{voice}.onnx"
    if not path.is_file():
        _download_piper_voice(voice, dest)
    if not path.is_file():
        raise FileNotFoundError(
            f"Piper voice {voice!r} not found at {path} after download. "
            "Set tts.local.voice to a voice name from "
            "https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md "
            "or to the path of a downloaded .onnx model."
        )
    return str(path)


def _get_piper_voice():
    global _piper_voice, _piper_voice_key
    from piper import PiperVoice

    _engine, voice = _get_local_settings()
    if _piper_voice is None or _piper_voice_key != voice:
        path = _resolve_piper_voice(voice)
        logger.info("[TTS] Loading Piper voice %s", path)
        _piper_voice = PiperVoice.load(path)
        _piper_voice_key = voice
    return _piper_voice


def _synthesize_piper(text: str) -> bytes:
    """Piper synthesis → WAV bytes. Blocking; run in a thread."""
    import io
    import wave

    voice = _get_piper_voice()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        # piper-tts >= 1.3 has synthesize_wav; 1.2 writes via synthesize.
        if hasattr(voice, "synthesize_wav"):
            voice.synthesize_wav(text, wav_file)
        else:
            voice.synthesize(text, wav_file)
    return buf.getvalue()


def _get_kokoro_settings() -> tuple[str, str]:
    from .. import config
    kvoice = config.get_str("tts", "local", "kokoroVoice") or _DEFAULT_KOKORO_VOICE
    klang = config.get_str("tts", "local", "kokoroLang") or _DEFAULT_KOKORO_LANG
    return kvoice, klang


def _synthesize_kokoro(text: str) -> bytes:
    """Kokoro synthesis → WAV bytes. Blocking; run in a thread."""
    import io
    import wave

    import numpy as np

    global _kokoro_pipeline, _kokoro_pipeline_key
    from kokoro import KPipeline

    kvoice, klang = _get_kokoro_settings()
    if _kokoro_pipeline is None or _kokoro_pipeline_key != klang:
        logger.info("[TTS] Loading Kokoro pipeline (lang=%s)", klang)
        _kokoro_pipeline = KPipeline(lang_code=klang)
        _kokoro_pipeline_key = klang

    chunks: list[bytes] = []
    for item in _kokoro_pipeline(text, voice=kvoice):
        audio = item[2] if isinstance(item, tuple) else getattr(item, "audio", None)
        if audio is None:
            continue
        arr = np.asarray(getattr(audio, "numpy", lambda: audio)(), dtype=np.float32)
        chunks.append((np.clip(arr, -1.0, 1.0) * 32767).astype(np.int16).tobytes())

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)  # Kokoro's fixed output rate
        wav_file.writeframes(b"".join(chunks))
    return buf.getvalue()


def _ffmpeg_available() -> bool:
    import shutil
    return shutil.which("ffmpeg") is not None


def _wav_to_ogg(wav: bytes) -> bytes:
    """WAV → OGG/Opus via ffmpeg — the format Telegram voice notes want."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "wav", "-i", "pipe:0",
         "-c:a", "libopus", "-b:a", "32k", "-ar", "48000", "-ac", "1",
         "-f", "ogg", "pipe:1"],
        input=wav, capture_output=True, check=True,
    )
    return proc.stdout


def synthesize_local(text: str) -> VoiceClip:
    """Synthesize on this machine. Blocking; run in a thread.

    Returns OGG/Opus when ffmpeg is available, plain WAV otherwise
    (fine for local playback, not accepted for Telegram voice notes).
    """
    engine, _voice = _get_local_settings()
    wav = _synthesize_kokoro(text) if engine == "kokoro" else _synthesize_piper(text)
    if _ffmpeg_available():
        return VoiceClip(data=_wav_to_ogg(wav), format="ogg")
    logger.warning("[TTS] ffmpeg not found — returning WAV; install ffmpeg "
                   "to send local voice as Telegram voice notes")
    return VoiceClip(data=wav, format="wav")


async def _synthesize_local_async(text: str) -> VoiceClip:
    import asyncio
    return await asyncio.to_thread(synthesize_local, text)


# ── ElevenLabs (cloud) ────────────────────────────────────────────────────────


async def _synthesize_elevenlabs_async(key: str, text: str) -> VoiceClip:
    import httpx

    url = f"{_ELEVENLABS_API}/{_get_elevenlabs_voice()}?output_format=mp3_44100_128"
    body = {
        "text": text,
        "model_id": _get_elevenlabs_model(),
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.3},
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=body, headers={"xi-api-key": key})
        resp.raise_for_status()
        return VoiceClip(data=resp.content, format="mp3")


# ── Async entry point ─────────────────────────────────────────────────────────


async def synthesize_async(text: str) -> VoiceClip | None:
    """Synthesize *text* via the configured provider.

    Returns a :class:`VoiceClip`, or ``None`` when no usable provider is
    configured. Raises when the selected provider exists but fails and no
    fallback is available.
    """
    provider = _get_provider()
    key = _get_key()

    if provider == "local":
        if not local_available():
            return None
        return await _synthesize_local_async(text)

    if provider == "elevenlabs":
        if not key:
            return None
        return await _synthesize_elevenlabs_async(key, text)

    # auto: ElevenLabs when a key is set, local otherwise; local also covers
    # for ElevenLabs when the cloud call blows up.
    if key:
        try:
            return await _synthesize_elevenlabs_async(key, text)
        except Exception as exc:
            if local_available():
                logger.warning("[TTS] ElevenLabs failed (%s); falling back to local", exc)
                return await _synthesize_local_async(text)
            raise
    if local_available():
        return await _synthesize_local_async(text)
    return None


def no_provider_message() -> str:
    """User-facing hint when no TTS provider is usable."""
    if _get_provider() == "local":
        return _NO_LOCAL_MSG
    return _NO_KEY_MSG


# ── Reply-in-kind (voice note in → voice note back) ───────────────────────────

_VALID_RIK_MODES = ("false", "true", "auto")

# In auto mode a tiny ack ("嗯嗯", "好呀～") only *sometimes* becomes voice —
# voicing every two-character acknowledgment reads as a gimmick, not a person.
_TINY_ACK_CHARS = 12
_TINY_ACK_PROBABILITY = 0.4

_DEFAULT_MAX_CHARS = 350


def reply_in_kind_mode() -> str:
    """``channels.telegram.replyInKindVoice`` normalised to false/true/auto."""
    from .. import config
    val = config.get("channels", "telegram", "replyInKindVoice",
                     env="HERANDHIM_REPLY_IN_KIND_VOICE")
    if val is None or val == "":
        return "auto"
    if isinstance(val, bool):
        return "true" if val else "false"
    val = str(val).strip().lower()
    if val not in _VALID_RIK_MODES:
        logger.warning("[TTS] Unknown replyInKindVoice %r; using 'auto'", val)
        return "auto"
    return val


def voice_reply_max_chars() -> int:
    from .. import config
    return config.get_int("channels", "telegram", "voiceReplyMaxChars",
                          default=_DEFAULT_MAX_CHARS) or _DEFAULT_MAX_CHARS


def should_voice_reply(reply_text: str) -> bool:
    """Decide whether a reply to an inbound voice note should itself be voice.

    ``false`` — never. ``true`` — whenever the reply fits the length cap.
    ``auto`` (default) — same cap, plus tiny acks only sometimes become
    voice so short back-and-forths don't turn into voice-note spam.
    """
    mode = reply_in_kind_mode()
    if mode == "false":
        return False
    text = (reply_text or "").strip()
    if not text:
        return False
    if len(text) > voice_reply_max_chars():
        return False
    if mode == "auto" and len(text) < _TINY_ACK_CHARS:
        return random.random() < _TINY_ACK_PROBABILITY
    return True


# Emoji and markdown don't speak well — strip them before synthesis.
_UNSPEAKABLE_RE = re.compile(
    "["
    "\U0001f000-\U0001ffff"   # emoji & symbols
    "\u2600-\u27bf"           # misc symbols, dingbats
    "\ufe0e\ufe0f\u200d"      # variation selectors, ZWJ
    "*_`#"                    # markdown leftovers
    "]+"
)


def strip_for_speech(text: str) -> str:
    """Clean a chat reply into speakable text (emoji/markdown removed)."""
    cleaned = _UNSPEAKABLE_RE.sub("", text or "")
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()
