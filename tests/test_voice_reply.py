"""Reply-in-kind: a voice note in prefers a voice note back.

``channels.telegram.replyInKindVoice`` decides (false / true / auto —
auto is the default, with a length cap and a tiny-ack probability so
voice replies stay special instead of becoming spam). Every TTS miss —
no provider, synthesis error, WAV-only output, Telegram send failure —
falls back to text: the reply itself is never dropped.
"""

from __future__ import annotations

import asyncio
import json
import types

import pytest

from herandhim import config
from herandhim.channels.telegram_bot import TelegramBot
from herandhim.core import tts


@pytest.fixture(autouse=True)
def _isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HERANDHIM_HOME", str(tmp_path))
    monkeypatch.setattr(config, "_HERANDHIM_BASE", tmp_path)
    for var in ("ELEVENLABS_API_KEY", "HERANDHIM_TTS_PROVIDER",
                "HERANDHIM_REPLY_IN_KIND_VOICE"):
        monkeypatch.delenv(var, raising=False)
    config._configs.clear()
    config._config_paths.clear()
    yield
    config._configs.clear()
    config._config_paths.clear()


def _configure(tmp_path, cfg: dict) -> None:
    path = tmp_path / "herandhim.json"
    path.write_text(json.dumps(cfg))
    config.load(str(path), force=True)


_LONG_ENOUGH = "宝贝晚安，今天辛苦啦，梦里见～"  # normal reply, above the tiny-ack floor


# ── The decision: should this reply be voice? ─────────────────────────────


def test_default_mode_is_auto(tmp_path):
    _configure(tmp_path, {})
    assert tts.reply_in_kind_mode() == "auto"


def test_false_never_voices(tmp_path):
    _configure(tmp_path, {"channels": {"telegram": {"replyInKindVoice": "false"}}})
    assert tts.should_voice_reply(_LONG_ENOUGH) is False


def test_json_booleans_work_too(tmp_path):
    _configure(tmp_path, {"channels": {"telegram": {"replyInKindVoice": False}}})
    assert tts.reply_in_kind_mode() == "false"
    _configure(tmp_path, {"channels": {"telegram": {"replyInKindVoice": True}}})
    assert tts.reply_in_kind_mode() == "true"


def test_env_var_wins(tmp_path, monkeypatch):
    _configure(tmp_path, {"channels": {"telegram": {"replyInKindVoice": "true"}}})
    monkeypatch.setenv("HERANDHIM_REPLY_IN_KIND_VOICE", "false")
    assert tts.reply_in_kind_mode() == "false"


def test_auto_voices_a_normal_length_reply(tmp_path):
    _configure(tmp_path, {})
    assert tts.should_voice_reply(_LONG_ENOUGH) is True


def test_auto_caps_the_length(tmp_path):
    """An essay read aloud is a podcast, not a voice note — long replies stay text."""
    _configure(tmp_path, {})
    assert tts.should_voice_reply("好长" * 400) is False


def test_the_length_cap_is_configurable(tmp_path):
    _configure(tmp_path, {"channels": {"telegram": {"voiceReplyMaxChars": 10}}})
    assert tts.should_voice_reply(_LONG_ENOUGH) is False
    _configure(tmp_path, {"channels": {"telegram": {"voiceReplyMaxChars": 2000}}})
    assert tts.should_voice_reply("好长" * 400) is True


def test_auto_only_sometimes_voices_a_tiny_ack(tmp_path, monkeypatch):
    """'嗯嗯' as a voice note every time reads as a gimmick — probability-capped."""
    _configure(tmp_path, {})
    monkeypatch.setattr(tts.random, "random", lambda: 0.99)
    assert tts.should_voice_reply("嗯嗯") is False
    monkeypatch.setattr(tts.random, "random", lambda: 0.01)
    assert tts.should_voice_reply("嗯嗯") is True


def test_true_mode_voices_even_tiny_acks(tmp_path, monkeypatch):
    _configure(tmp_path, {"channels": {"telegram": {"replyInKindVoice": "true"}}})
    monkeypatch.setattr(tts.random, "random", lambda: 0.99)
    assert tts.should_voice_reply("嗯嗯") is True


def test_true_mode_still_respects_the_length_cap(tmp_path):
    _configure(tmp_path, {"channels": {"telegram": {"replyInKindVoice": "true"}}})
    assert tts.should_voice_reply("好长" * 400) is False


def test_empty_reply_is_never_voiced(tmp_path):
    _configure(tmp_path, {"channels": {"telegram": {"replyInKindVoice": "true"}}})
    assert tts.should_voice_reply("   ") is False


# ── The Telegram delivery path ────────────────────────────────────────────


class _FakeBot:
    def __init__(self, fail_send: bool = False):
        self.voice_calls: list = []
        self.actions: list[str] = []
        self._fail = fail_send

    async def send_chat_action(self, chat_id, action):
        self.actions.append(action)

    async def send_voice(self, chat_id, voice, caption=None):
        if self._fail:
            raise RuntimeError("telegram down")
        self.voice_calls.append(voice)


def _make_bot(fail_send: bool = False) -> tuple[TelegramBot, _FakeBot]:
    tg = TelegramBot(session_manager=None, token="t0ken")
    fake = _FakeBot(fail_send=fail_send)
    tg._app = types.SimpleNamespace(bot=fake)
    return tg, fake


def _tts_answers(monkeypatch, fmt: str = "ogg"):
    async def fake(text):
        return tts.VoiceClip(data=b"AUDIO", format=fmt)
    monkeypatch.setattr(tts, "synthesize_async", fake)


def _tts_returns_none(monkeypatch):
    async def fake(text):
        return None
    monkeypatch.setattr(tts, "synthesize_async", fake)


def _tts_explodes(monkeypatch):
    async def fake(text):
        raise RuntimeError("no voice today")
    monkeypatch.setattr(tts, "synthesize_async", fake)


def _tts_must_not_be_called(monkeypatch):
    async def fake(text):
        raise AssertionError("TTS was called but should not have been")
    monkeypatch.setattr(tts, "synthesize_async", fake)


def test_voice_reply_is_sent_when_tts_succeeds(tmp_path, monkeypatch):
    _configure(tmp_path, {"channels": {"telegram": {"replyInKindVoice": "true"}}})
    _tts_answers(monkeypatch)
    tg, fake = _make_bot()

    assert asyncio.run(tg._maybe_send_voice_reply(1, _LONG_ENOUGH)) is True
    assert fake.voice_calls == [b"AUDIO"]
    assert "record_voice" in fake.actions  # she "records", like a person


def test_text_fallback_when_tts_fails(tmp_path, monkeypatch):
    _configure(tmp_path, {"channels": {"telegram": {"replyInKindVoice": "true"}}})
    _tts_explodes(monkeypatch)
    tg, fake = _make_bot()

    assert asyncio.run(tg._maybe_send_voice_reply(1, _LONG_ENOUGH)) is False
    assert fake.voice_calls == []


def test_text_fallback_when_no_provider_is_usable(tmp_path, monkeypatch):
    _configure(tmp_path, {"channels": {"telegram": {"replyInKindVoice": "true"}}})
    _tts_returns_none(monkeypatch)
    tg, fake = _make_bot()

    assert asyncio.run(tg._maybe_send_voice_reply(1, _LONG_ENOUGH)) is False
    assert fake.voice_calls == []


def test_text_fallback_when_local_could_only_make_wav(tmp_path, monkeypatch):
    """No ffmpeg → WAV — not a valid Telegram voice note, so text it is."""
    _configure(tmp_path, {"channels": {"telegram": {"replyInKindVoice": "true"}}})
    _tts_answers(monkeypatch, fmt="wav")
    tg, fake = _make_bot()

    assert asyncio.run(tg._maybe_send_voice_reply(1, _LONG_ENOUGH)) is False
    assert fake.voice_calls == []


def test_text_fallback_when_telegram_send_fails(tmp_path, monkeypatch):
    _configure(tmp_path, {"channels": {"telegram": {"replyInKindVoice": "true"}}})
    _tts_answers(monkeypatch)
    tg, fake = _make_bot(fail_send=True)

    assert asyncio.run(tg._maybe_send_voice_reply(1, _LONG_ENOUGH)) is False


def test_mode_false_never_even_calls_tts(tmp_path, monkeypatch):
    _configure(tmp_path, {"channels": {"telegram": {"replyInKindVoice": "false"}}})
    _tts_must_not_be_called(monkeypatch)
    tg, fake = _make_bot()

    assert asyncio.run(tg._maybe_send_voice_reply(1, _LONG_ENOUGH)) is False
    assert fake.voice_calls == []


# ── The send_voice tool (skill-generated audio → voice bubble) ────────────


def test_send_voice_tool_uses_the_voice_sender(tmp_path):
    from herandhim.core import tools
    audio = tmp_path / "v.ogg"
    audio.write_bytes(b"opus")
    sent: list = []
    tools.set_voice_sender("s1", lambda path, caption: sent.append(path))
    try:
        out = tools.send_voice(str(audio), session_id="s1")
    finally:
        tools.set_voice_sender("s1", None)
    assert "sent" in out
    assert sent and sent[0].endswith("v.ogg")


def test_send_voice_tool_falls_back_to_send_file(tmp_path):
    from herandhim.core import tools

    def broken(path, caption):
        raise RuntimeError("channel can't voice")

    audio = tmp_path / "v.ogg"
    audio.write_bytes(b"opus")
    fallback: list = []
    tools.set_voice_sender("s1", broken)
    tools.set_file_sender("s1", lambda path, caption: fallback.append(path))
    try:
        out = tools.send_voice(str(audio), session_id="s1")
    finally:
        tools.set_voice_sender("s1", None)
        tools.set_file_sender("s1", None)
    assert "sent" in out
    assert fallback and fallback[0].endswith("v.ogg")
