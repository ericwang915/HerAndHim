"""Local text-to-speech via Piper (or Kokoro), as an ElevenLabs alternative.

``tts.provider`` selects the engine: ``auto`` (default — ElevenLabs when a
key is set, otherwise local), ``elevenlabs``, or ``local``. The local path
keeps text on the machine; the whole thing is opt-in and ElevenLabs
behaviour is unchanged when a key exists. Mirrors test_stt_provider.py —
the two sides of the voice story share one shape.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types

import pytest

from herandhim import config
from herandhim.core import tts


@pytest.fixture(autouse=True)
def _isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HERANDHIM_HOME", str(tmp_path))
    monkeypatch.setattr(config, "_HERANDHIM_BASE", tmp_path)
    for var in ("ELEVENLABS_API_KEY", "HERANDHIM_TTS_PROVIDER",
                "HERANDHIM_TTS_LOCAL_VOICE", "HERANDHIM_REPLY_IN_KIND_VOICE"):
        monkeypatch.delenv(var, raising=False)
    config._configs.clear()
    config._config_paths.clear()
    # The loaded Piper voice / Kokoro pipeline is cached module-wide;
    # never leak across tests.
    monkeypatch.setattr(tts, "_piper_voice", None)
    monkeypatch.setattr(tts, "_piper_voice_key", None)
    monkeypatch.setattr(tts, "_kokoro_pipeline", None)
    monkeypatch.setattr(tts, "_kokoro_pipeline_key", None)
    yield
    config._configs.clear()
    config._config_paths.clear()


def _configure(tmp_path, cfg: dict) -> None:
    path = tmp_path / "herandhim.json"
    path.write_text(json.dumps(cfg))
    config.load(str(path), force=True)


def _fake_piper(monkeypatch, voices: list | None = None):
    """Install a fake ``piper`` module; returns it."""
    mod = types.ModuleType("piper")

    class PiperVoice:
        def __init__(self, path):
            self.path = path
            self.calls: list[str] = []

        @classmethod
        def load(cls, path):
            voice = cls(str(path))
            if voices is not None:
                voices.append(voice)
            return voice

        def synthesize_wav(self, text, wav_file):
            self.calls.append(text)
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\x00\x01" * 64)

    mod.PiperVoice = PiperVoice
    monkeypatch.setitem(sys.modules, "piper", mod)
    return mod


def _no_piper(monkeypatch):
    """Make ``import piper`` raise ImportError."""
    monkeypatch.setitem(sys.modules, "piper", None)


def _fake_download(monkeypatch):
    """Voice 'download' that just drops an .onnx file in place; returns calls."""
    calls: list[str] = []

    def fake_dl(name, dest_dir):
        calls.append(name)
        (dest_dir / f"{name}.onnx").write_bytes(b"onnx")

    monkeypatch.setattr(tts, "_download_piper_voice", fake_dl)
    return calls


def _fake_ffmpeg(monkeypatch, present: bool = True):
    monkeypatch.setattr(tts, "_ffmpeg_available", lambda: present)
    monkeypatch.setattr(tts, "_wav_to_ogg", lambda wav: b"OGG:" + wav[:8])


def _elevenlabs_answers(monkeypatch):
    async def fake(key, text):
        return tts.VoiceClip(data=b"MP3DATA", format="mp3")
    monkeypatch.setattr(tts, "_synthesize_elevenlabs_async", fake)


def _elevenlabs_explodes(monkeypatch):
    async def fake(key, text):
        raise RuntimeError("elevenlabs down")
    monkeypatch.setattr(tts, "_synthesize_elevenlabs_async", fake)


def _elevenlabs_must_not_be_called(monkeypatch):
    async def fake(key, text):
        raise AssertionError("ElevenLabs was called but should not have been")
    monkeypatch.setattr(tts, "_synthesize_elevenlabs_async", fake)


# ── Provider selection (auto) ─────────────────────────────────────────────


def test_auto_prefers_elevenlabs_when_a_key_is_set(tmp_path, monkeypatch):
    """Existing users see no change: key set → cloud, even with Piper installed."""
    _configure(tmp_path, {"elevenlabs": {"apiKey": "el-key"}})
    _fake_piper(monkeypatch)
    _elevenlabs_answers(monkeypatch)

    clip = asyncio.run(tts.synthesize_async("晚安"))
    assert clip.format == "mp3"
    assert clip.data == b"MP3DATA"
    assert clip.telegram_ready


def test_auto_uses_local_when_no_key_but_piper_installed(tmp_path, monkeypatch):
    _configure(tmp_path, {"elevenlabs": {"apiKey": ""}})
    _fake_piper(monkeypatch)
    _fake_download(monkeypatch)
    _fake_ffmpeg(monkeypatch)
    _elevenlabs_must_not_be_called(monkeypatch)

    clip = asyncio.run(tts.synthesize_async("晚安"))
    assert clip.format == "ogg"
    assert clip.data.startswith(b"OGG:")
    assert clip.telegram_ready


def test_auto_with_nothing_available_returns_none(tmp_path, monkeypatch):
    _configure(tmp_path, {})
    _no_piper(monkeypatch)

    assert asyncio.run(tts.synthesize_async("晚安")) is None
    # The hint still leads with ElevenLabs but mentions the local alternative.
    msg = tts.no_provider_message()
    assert "ElevenLabs" in msg
    assert "herandhim[tts-local]" in msg


def test_auto_falls_back_to_local_when_elevenlabs_errors(tmp_path, monkeypatch):
    _configure(tmp_path, {"elevenlabs": {"apiKey": "el-key"}})
    _fake_piper(monkeypatch)
    _fake_download(monkeypatch)
    _fake_ffmpeg(monkeypatch)
    _elevenlabs_explodes(monkeypatch)

    clip = asyncio.run(tts.synthesize_async("晚安"))
    assert clip.format == "ogg"


def test_auto_reraises_elevenlabs_error_when_no_local_fallback(tmp_path, monkeypatch):
    _configure(tmp_path, {"elevenlabs": {"apiKey": "el-key"}})
    _no_piper(monkeypatch)
    _elevenlabs_explodes(monkeypatch)

    with pytest.raises(RuntimeError, match="elevenlabs down"):
        asyncio.run(tts.synthesize_async("晚安"))


# ── Forced providers ──────────────────────────────────────────────────────


def test_provider_local_keeps_text_off_the_cloud_even_with_a_key(tmp_path, monkeypatch):
    _configure(tmp_path, {
        "elevenlabs": {"apiKey": "el-key"},
        "tts": {"provider": "local"},
    })
    _fake_piper(monkeypatch)
    _fake_download(monkeypatch)
    _fake_ffmpeg(monkeypatch)
    _elevenlabs_must_not_be_called(monkeypatch)

    clip = asyncio.run(tts.synthesize_async("晚安"))
    assert clip.format == "ogg"


def test_provider_local_without_the_package_explains_the_install(tmp_path, monkeypatch):
    _configure(tmp_path, {"tts": {"provider": "local"}})
    _no_piper(monkeypatch)

    assert asyncio.run(tts.synthesize_async("晚安")) is None
    msg = tts.no_provider_message()
    assert 'pip install "herandhim[tts-local]"' in msg
    assert "ElevenLabs API key" not in msg


def test_provider_elevenlabs_never_falls_back_to_local(tmp_path, monkeypatch):
    """Explicit cloud pin: no key means off, even with Piper installed."""
    _configure(tmp_path, {"tts": {"provider": "elevenlabs"}})
    _fake_piper(monkeypatch)

    assert asyncio.run(tts.synthesize_async("晚安")) is None


def test_env_var_selects_the_provider(tmp_path, monkeypatch):
    _configure(tmp_path, {"elevenlabs": {"apiKey": "el-key"}})
    monkeypatch.setenv("HERANDHIM_TTS_PROVIDER", "local")
    _fake_piper(monkeypatch)
    _fake_download(monkeypatch)
    _fake_ffmpeg(monkeypatch)
    _elevenlabs_must_not_be_called(monkeypatch)

    clip = asyncio.run(tts.synthesize_async("晚安"))
    assert clip.format == "ogg"


def test_an_unknown_provider_value_degrades_to_auto(tmp_path, monkeypatch):
    _configure(tmp_path, {
        "elevenlabs": {"apiKey": "el-key"},
        "tts": {"provider": "espeak"},
    })
    _elevenlabs_answers(monkeypatch)
    clip = asyncio.run(tts.synthesize_async("晚安"))
    assert clip.format == "mp3"


# ── Local voice configuration ─────────────────────────────────────────────


def test_default_voice_is_mandarin_and_downloads_once(tmp_path, monkeypatch):
    _configure(tmp_path, {"tts": {"provider": "local"}})
    voices: list = []
    _fake_piper(monkeypatch, voices=voices)
    downloads = _fake_download(monkeypatch)
    _fake_ffmpeg(monkeypatch)

    asyncio.run(tts.synthesize_async("晚安"))
    asyncio.run(tts.synthesize_async("早安"))
    assert downloads == ["zh_CN-huayan-medium"]
    assert len(voices) == 1  # loaded once, reused
    assert voices[0].path.endswith("zh_CN-huayan-medium.onnx")
    assert len(voices[0].calls) == 2


def test_voice_can_be_a_model_path(tmp_path, monkeypatch):
    model = tmp_path / "my-voice.onnx"
    model.write_bytes(b"onnx")
    _configure(tmp_path, {"tts": {"provider": "local", "local": {"voice": str(model)}}})
    voices: list = []
    _fake_piper(monkeypatch, voices=voices)
    downloads = _fake_download(monkeypatch)
    _fake_ffmpeg(monkeypatch)

    asyncio.run(tts.synthesize_async("晚安"))
    assert downloads == []
    assert voices[0].path == str(model)


def test_without_ffmpeg_local_yields_wav(tmp_path, monkeypatch):
    """No ffmpeg → WAV comes back and is flagged as not Telegram-ready,
    so the channel falls back to text instead of sending a broken note."""
    _configure(tmp_path, {"tts": {"provider": "local"}})
    _fake_piper(monkeypatch)
    _fake_download(monkeypatch)
    _fake_ffmpeg(monkeypatch, present=False)

    clip = asyncio.run(tts.synthesize_async("晚安"))
    assert clip.format == "wav"
    assert not clip.telegram_ready


def test_kokoro_engine_is_selectable(tmp_path, monkeypatch):
    _configure(tmp_path, {"tts": {"provider": "local", "local": {"engine": "kokoro"}}})
    _fake_ffmpeg(monkeypatch)

    import numpy as np
    mod = types.ModuleType("kokoro")
    seen: dict = {}

    class KPipeline:
        def __init__(self, lang_code):
            seen["lang"] = lang_code

        def __call__(self, text, voice):
            seen["voice"] = voice
            yield ("gs", "ps", np.zeros(64, dtype=np.float32))

    mod.KPipeline = KPipeline
    monkeypatch.setitem(sys.modules, "kokoro", mod)

    clip = asyncio.run(tts.synthesize_async("晚安"))
    assert clip.format == "ogg"
    assert seen == {"lang": "z", "voice": "zf_xiaobei"}


def test_kokoro_engine_missing_means_local_unavailable(tmp_path, monkeypatch):
    """With engine=kokoro but no kokoro package, local is simply unusable —
    Piper being installed doesn't silently override the explicit choice."""
    _configure(tmp_path, {"tts": {"provider": "local", "local": {"engine": "kokoro"}}})
    _fake_piper(monkeypatch)
    monkeypatch.setitem(sys.modules, "kokoro", None)

    assert asyncio.run(tts.synthesize_async("晚安")) is None


# ── Speech text cleanup ───────────────────────────────────────────────────


def test_strip_for_speech_removes_emoji_and_markdown():
    assert tts.strip_for_speech("想你了宝贝～😘 **晚安**") == "想你了宝贝～ 晚安"


def test_strip_for_speech_keeps_plain_chinese_and_english():
    assert tts.strip_for_speech("晚安, sweet dreams!") == "晚安, sweet dreams!"
