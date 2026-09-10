"""Local speech-to-text via faster-whisper, as a Deepgram alternative.

``stt.provider`` selects the engine: ``auto`` (default — Deepgram when a
key is set, otherwise local), ``deepgram``, or ``local``. The local path
keeps the audio on the machine; the whole thing is opt-in and Deepgram
behaviour is unchanged when a key exists.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types

import pytest

from herandhim import config
from herandhim.core import stt


@pytest.fixture(autouse=True)
def _isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HERANDHIM_HOME", str(tmp_path))
    monkeypatch.setattr(config, "_HERANDHIM_BASE", tmp_path)
    for var in ("DEEPGRAM_API_KEY", "HERANDHIM_STT_PROVIDER", "HERANDHIM_STT_LOCAL_MODEL"):
        monkeypatch.delenv(var, raising=False)
    config._configs.clear()
    config._config_paths.clear()
    # The loaded whisper model is cached module-wide; never leak across tests.
    monkeypatch.setattr(stt, "_local_model", None)
    monkeypatch.setattr(stt, "_local_model_key", None)
    yield
    config._configs.clear()
    config._config_paths.clear()


def _configure(tmp_path, cfg: dict) -> None:
    path = tmp_path / "herandhim.json"
    path.write_text(json.dumps(cfg))
    config.load(str(path), force=True)


def _fake_whisper(monkeypatch, transcript="hello from whisper", models: list | None = None):
    """Install a fake ``faster_whisper`` module; returns it."""
    mod = types.ModuleType("faster_whisper")

    class WhisperModel:
        def __init__(self, size, device="cpu", compute_type="int8"):
            self.size = size
            self.device = device
            self.compute_type = compute_type
            self.calls: list[dict] = []
            if models is not None:
                models.append(self)

        def transcribe(self, audio, language=None, vad_filter=True):
            self.calls.append({"language": language, "vad_filter": vad_filter})
            segments = iter([types.SimpleNamespace(text=f" {transcript} ")])
            info = types.SimpleNamespace(language=language or "en")
            return segments, info

    mod.WhisperModel = WhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    return mod


def _no_whisper(monkeypatch):
    """Make ``import faster_whisper`` raise ImportError."""
    monkeypatch.setitem(sys.modules, "faster_whisper", None)


def _deepgram_answers(monkeypatch, text="cloud transcript"):
    async def fake_call(key, audio, content_type, language):
        return text
    monkeypatch.setattr(stt, "_call_async", fake_call)


def _deepgram_explodes(monkeypatch):
    async def fake_call(key, audio, content_type, language):
        raise RuntimeError("deepgram down")
    monkeypatch.setattr(stt, "_call_async", fake_call)


def _deepgram_must_not_be_called(monkeypatch):
    async def fake_call(key, audio, content_type, language):
        raise AssertionError("Deepgram was called but should not have been")
    monkeypatch.setattr(stt, "_call_async", fake_call)


# ── Provider selection (auto) ─────────────────────────────────────────────


def test_auto_prefers_deepgram_when_a_key_is_set(tmp_path, monkeypatch):
    """Existing users see no change: key set → cloud, even with whisper installed."""
    _configure(tmp_path, {"deepgram": {"apiKey": "dg-key"}})
    _fake_whisper(monkeypatch)
    _deepgram_answers(monkeypatch, "cloud transcript")

    out = asyncio.run(stt.transcribe_bytes_async(b"opus...", "audio/ogg"))
    assert out == "cloud transcript"


def test_auto_uses_local_when_no_key_but_whisper_installed(tmp_path, monkeypatch):
    _configure(tmp_path, {"deepgram": {"apiKey": ""}})
    _fake_whisper(monkeypatch, transcript="local transcript")
    _deepgram_must_not_be_called(monkeypatch)

    out = asyncio.run(stt.transcribe_bytes_async(b"opus..."))
    assert out == "local transcript"


def test_auto_with_nothing_available_returns_none(tmp_path, monkeypatch):
    _configure(tmp_path, {})
    _no_whisper(monkeypatch)

    assert asyncio.run(stt.transcribe_bytes_async(b"opus...")) is None
    # The hint still leads with Deepgram but mentions the local alternative.
    msg = stt.no_key_message()
    assert "Deepgram" in msg
    assert "herandhim[stt-local]" in msg


def test_auto_falls_back_to_local_when_deepgram_errors(tmp_path, monkeypatch):
    _configure(tmp_path, {"deepgram": {"apiKey": "dg-key"}})
    _fake_whisper(monkeypatch, transcript="rescued locally")
    _deepgram_explodes(monkeypatch)

    out = asyncio.run(stt.transcribe_bytes_async(b"opus..."))
    assert out == "rescued locally"


def test_auto_reraises_deepgram_error_when_no_local_fallback(tmp_path, monkeypatch):
    _configure(tmp_path, {"deepgram": {"apiKey": "dg-key"}})
    _no_whisper(monkeypatch)
    _deepgram_explodes(monkeypatch)

    with pytest.raises(RuntimeError, match="deepgram down"):
        asyncio.run(stt.transcribe_bytes_async(b"opus..."))


# ── Forced providers ──────────────────────────────────────────────────────


def test_provider_local_keeps_audio_off_the_cloud_even_with_a_key(tmp_path, monkeypatch):
    _configure(tmp_path, {
        "deepgram": {"apiKey": "dg-key"},
        "stt": {"provider": "local"},
    })
    _fake_whisper(monkeypatch, transcript="on this machine")
    _deepgram_must_not_be_called(monkeypatch)

    out = asyncio.run(stt.transcribe_bytes_async(b"opus..."))
    assert out == "on this machine"


def test_provider_local_without_the_package_explains_the_install(tmp_path, monkeypatch):
    _configure(tmp_path, {"stt": {"provider": "local"}})
    _no_whisper(monkeypatch)

    assert asyncio.run(stt.transcribe_bytes_async(b"opus...")) is None
    msg = stt.no_key_message()
    assert 'pip install "herandhim[stt-local]"' in msg
    assert "Deepgram API key" not in msg


def test_provider_deepgram_never_falls_back_to_local(tmp_path, monkeypatch):
    """Explicit cloud pin: no key means off, even with whisper installed."""
    _configure(tmp_path, {"stt": {"provider": "deepgram"}})
    _fake_whisper(monkeypatch)

    assert asyncio.run(stt.transcribe_bytes_async(b"opus...")) is None


def test_env_var_selects_the_provider(tmp_path, monkeypatch):
    _configure(tmp_path, {"deepgram": {"apiKey": "dg-key"}})
    monkeypatch.setenv("HERANDHIM_STT_PROVIDER", "local")
    _fake_whisper(monkeypatch, transcript="env said local")
    _deepgram_must_not_be_called(monkeypatch)

    out = asyncio.run(stt.transcribe_bytes_async(b"opus..."))
    assert out == "env said local"


def test_an_unknown_provider_value_degrades_to_auto(tmp_path, monkeypatch):
    _configure(tmp_path, {
        "deepgram": {"apiKey": "dg-key"},
        "stt": {"provider": "whisperx"},
    })
    _deepgram_answers(monkeypatch, "auto took over")
    assert asyncio.run(stt.transcribe_bytes_async(b"opus...")) == "auto took over"


# ── Local model configuration ─────────────────────────────────────────────


def test_local_model_settings_come_from_config(tmp_path, monkeypatch):
    _configure(tmp_path, {"stt": {
        "provider": "local",
        "local": {"model": "small", "device": "cpu", "computeType": "float32"},
    }})
    models: list = []
    _fake_whisper(monkeypatch, models=models)

    asyncio.run(stt.transcribe_bytes_async(b"opus..."))
    assert len(models) == 1
    assert (models[0].size, models[0].device, models[0].compute_type) == \
        ("small", "cpu", "float32")


def test_local_defaults_are_base_cpu_int8(tmp_path, monkeypatch):
    _configure(tmp_path, {"stt": {"provider": "local"}})
    models: list = []
    _fake_whisper(monkeypatch, models=models)

    asyncio.run(stt.transcribe_bytes_async(b"opus..."))
    assert (models[0].size, models[0].device, models[0].compute_type) == \
        ("base", "cpu", "int8")


def test_the_loaded_model_is_reused_across_calls(tmp_path, monkeypatch):
    _configure(tmp_path, {"stt": {"provider": "local"}})
    models: list = []
    _fake_whisper(monkeypatch, models=models)

    asyncio.run(stt.transcribe_bytes_async(b"one"))
    asyncio.run(stt.transcribe_bytes_async(b"two"))
    assert len(models) == 1
    assert len(models[0].calls) == 2


def test_local_language_auto_lets_whisper_detect(tmp_path, monkeypatch):
    _configure(tmp_path, {"stt": {"provider": "local"}})
    models: list = []
    _fake_whisper(monkeypatch, models=models)

    asyncio.run(stt.transcribe_bytes_async(b"opus..."))
    assert models[0].calls[0]["language"] is None


def test_local_language_can_be_pinned(tmp_path, monkeypatch):
    _configure(tmp_path, {"stt": {"provider": "local", "local": {"language": "zh"}}})
    models: list = []
    _fake_whisper(monkeypatch, models=models)

    asyncio.run(stt.transcribe_bytes_async(b"opus..."))
    assert models[0].calls[0]["language"] == "zh"


def test_segments_are_joined_and_trimmed(tmp_path, monkeypatch):
    _configure(tmp_path, {"stt": {"provider": "local"}})
    mod = _fake_whisper(monkeypatch)

    class Multi(mod.WhisperModel):
        def transcribe(self, audio, language=None, vad_filter=True):
            segments = iter([
                types.SimpleNamespace(text=" Hello, "),
                types.SimpleNamespace(text=" world. "),
            ])
            return segments, types.SimpleNamespace(language="en")

    mod.WhisperModel = Multi
    out = asyncio.run(stt.transcribe_bytes_async(b"opus..."))
    assert out == "Hello, world."
