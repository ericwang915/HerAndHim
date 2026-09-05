"""The Docker entrypoint must not wipe what the wizard and dashboard saved.

Restarting the container used to regenerate herandhim.json from env vars
alone, discarding the companion, her city and timezone, and every key or
model pasted into Settings (#42). The renderer now merges: on first boot it
writes a full default file, afterwards it only applies env vars that are set.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy" / "docker" / "render_config.py"


def _load():
    spec = importlib.util.spec_from_file_location("render_config", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def rc():
    return _load()


# What a wizard + dashboard session leaves behind on the volume.
def _saved_config() -> dict:
    return {
        "llm": {
            "provider": "openrouter",
            "openrouter": {"apiKey": "sk-or-old", "model": "anthropic/claude-sonnet-4",
                           "baseUrl": "https://openrouter.ai/api/v1"},
            "ollama": {"apiKey": "", "model": "llama3.1", "baseUrl": "http://localhost:11434/v1"},
        },
        "companion": {"companionName": "Aria", "companionCountry": "US",
                      "companionRegion": "Austin, TX", "userTimezone": "America/Chicago"},
        "persona": {"timezone": "America/Chicago"},
        "user": {"timezone": "America/Chicago"},
        "agent": {"culture": "us", "language": "en"},
        "proactive": {"enabled": True, "maxDaily": 4},
        "channels": {"telegram": {"token": "111:saved", "allowedUsers": [42]}},
        "skills": {"image": {"provider": "bfl"}, "bfl": {"apiKey": "bfl-saved", "model": "flux-kontext-pro"}},
        "web": {"host": "0.0.0.0", "port": 7788},
    }


# ── First boot ───────────────────────────────────────────────────────────


def test_fresh_render_infers_provider_from_the_one_key_set(rc):
    cfg = rc.render(None, {"HERANDHIM_OPENAI_API_KEY": "sk-openai"})
    assert cfg["llm"]["provider"] == "openai"
    assert cfg["llm"]["openai"] == {"apiKey": "sk-openai", "model": "gpt-4o-mini",
                                    "baseUrl": "https://api.openai.com/v1"}
    # Every other provider is stubbed so the dashboard has something to show.
    assert cfg["llm"]["deepseek"]["model"] == "deepseek-chat"
    assert cfg["llm"]["claude"] == {"apiKey": "", "model": "claude-sonnet-4-20250514"}
    assert cfg["channels"]["telegram"] == {"token": "", "allowedUsers": []}
    assert cfg["web"] == {"host": "0.0.0.0", "port": 7788}


def test_fresh_render_reuses_the_gemini_chat_key_for_photos(rc):
    cfg = rc.render(None, {"HERANDHIM_GEMINI_API_KEY": "g-key"})
    assert cfg["llm"]["provider"] == "gemini"
    assert cfg["skills"]["image"]["provider"] == "gemini"
    assert cfg["skills"]["gemini"]["apiKey"] == "g-key"
    assert cfg["skills"]["gemini"]["model"] == "gemini-2.5-flash-image"


def test_vision_env_vars_land_under_llm_vision(rc):
    """#43: text on one local model, photos on another."""
    cfg = rc.render(None, {"HERANDHIM_LLM_PROVIDER": "ollama",
                           "HERANDHIM_VISION_PROVIDER": "ollama",
                           "HERANDHIM_VISION_MODEL": "llava"})
    assert cfg["llm"]["provider"] == "ollama"
    assert cfg["llm"]["vision"] == {"provider": "ollama", "model": "llava"}

    # Not set → not written, fresh or otherwise; a saved one survives a restart.
    assert "vision" not in rc.render(None, {})["llm"]
    saved = _saved_config()
    saved["llm"]["vision"] = {"provider": "ollama", "model": "moondream"}
    assert rc.render(saved, {})["llm"]["vision"] == {"provider": "ollama", "model": "moondream"}


def test_fresh_render_with_no_keys_still_boots(rc):
    cfg = rc.render(None, {})
    assert cfg["llm"]["provider"] == "deepseek"
    assert "image" not in cfg["skills"]


# ── Restart ──────────────────────────────────────────────────────────────


def test_restart_keeps_everything_the_wizard_and_dashboard_saved(rc):
    saved = _saved_config()
    cfg = rc.render(saved, {"HERANDHIM_OPENROUTER_API_KEY": "sk-or-old", "PORT": "7788"})

    for section in ("companion", "persona", "user", "agent", "proactive"):
        assert cfg[section] == saved[section], section
    # The model chosen in Settings, not the env default.
    assert cfg["llm"]["openrouter"]["model"] == "anthropic/claude-sonnet-4"
    # The bot token pasted into the dashboard (no env var set for it).
    assert cfg["channels"]["telegram"] == {"token": "111:saved", "allowedUsers": [42]}
    # The photo backend picked in the dashboard, key included.
    assert cfg["skills"]["image"]["provider"] == "bfl"
    assert cfg["skills"]["bfl"]["apiKey"] == "bfl-saved"
    # And no default stubs are sprayed over an existing file.
    assert "deepseek" not in cfg["llm"]
    assert "pollinations" not in cfg["skills"]


def test_restart_applies_a_rotated_key_but_nothing_else(rc):
    cfg = rc.render(_saved_config(), {"HERANDHIM_OPENROUTER_API_KEY": "sk-or-NEW"})
    assert cfg["llm"]["openrouter"]["apiKey"] == "sk-or-NEW"
    assert cfg["llm"]["openrouter"]["model"] == "anthropic/claude-sonnet-4"
    assert cfg["llm"]["provider"] == "openrouter"


def test_restart_does_not_switch_provider_just_because_another_key_appeared(rc):
    """The dashboard set openrouter; adding a DeepSeek key must not hijack it."""
    cfg = rc.render(_saved_config(), {"HERANDHIM_DEEPSEEK_API_KEY": "sk-ds"})
    assert cfg["llm"]["provider"] == "openrouter"
    assert cfg["llm"]["deepseek"]["apiKey"] == "sk-ds"       # stored, ready to switch to


def test_restart_honours_an_explicit_provider_pin(rc):
    cfg = rc.render(_saved_config(), {"HERANDHIM_LLM_PROVIDER": "ollama",
                                      "HERANDHIM_OLLAMA_MODEL": "qwen3"})
    assert cfg["llm"]["provider"] == "ollama"
    assert cfg["llm"]["ollama"]["model"] == "qwen3"
    assert cfg["llm"]["ollama"]["baseUrl"] == "http://localhost:11434/v1"   # untouched


def test_restart_fills_in_a_provider_when_the_file_has_none(rc):
    """An older file without llm.provider still gets one inferred."""
    saved = _saved_config()
    del saved["llm"]["provider"]
    cfg = rc.render(saved, {"HERANDHIM_OPENROUTER_API_KEY": "sk-or-old"})
    assert cfg["llm"]["provider"] == "openrouter"


def test_restart_keeps_the_dashboards_photo_backend(rc):
    cfg = rc.render(_saved_config(), {"HERANDHIM_GEMINI_API_KEY": "g-key"})
    assert cfg["skills"]["image"]["provider"] == "bfl"
    assert cfg["skills"]["bfl"]["apiKey"] == "bfl-saved"


def test_restart_always_binds_the_container_port(rc):
    """A stray host/port edit must not make the container unreachable."""
    saved = _saved_config()
    saved["web"] = {"host": "127.0.0.1", "port": 9999}
    cfg = rc.render(saved, {"PORT": "7788"})
    assert cfg["web"] == {"host": "0.0.0.0", "port": 7788}


def test_render_never_mutates_its_input(rc):
    saved = _saved_config()
    snapshot = json.loads(json.dumps(saved))
    rc.render(saved, {"HERANDHIM_OPENROUTER_API_KEY": "x"})
    assert saved == snapshot


# ── main(): the file on disk ─────────────────────────────────────────────


def test_main_creates_then_preserves(rc, tmp_path, monkeypatch):
    path = tmp_path / "herandhim.json"
    monkeypatch.setenv("HERANDHIM_OPENROUTER_API_KEY", "sk-or-1")

    assert rc.main([str(path)]) == 0
    first = json.loads(path.read_text())
    assert first["llm"]["provider"] == "openrouter"

    # The wizard runs and saves the companion…
    first["companion"] = {"companionName": "Aria"}
    first["persona"] = {"timezone": "America/Chicago"}
    path.write_text(json.dumps(first))

    # …and the container restarts.
    assert rc.main([str(path)]) == 0
    second = json.loads(path.read_text())
    assert second["companion"] == {"companionName": "Aria"}
    assert second["persona"] == {"timezone": "America/Chicago"}


def test_main_tolerates_a_hand_edited_json5_file(rc, tmp_path):
    path = tmp_path / "herandhim.json"
    path.write_text('{\n  // my notes\n  "companion": {"companionName": "Aria"},\n}\n')
    assert rc.main([str(path)]) == 0
    assert json.loads(path.read_text())["companion"] == {"companionName": "Aria"}


def test_main_backs_up_a_corrupt_file_instead_of_crash_looping(rc, tmp_path, capsys):
    path = tmp_path / "herandhim.json"
    path.write_text("{ this is not json")
    assert rc.main([str(path)]) == 0
    assert (tmp_path / "herandhim.json.bak").read_text() == "{ this is not json"
    assert json.loads(path.read_text())["llm"]["provider"] == "deepseek"
    assert "not valid JSON" in capsys.readouterr().err


def test_entrypoint_delegates_to_the_renderer():
    sh = (ROOT / "deploy/docker/entrypoint.sh").read_text()
    assert "render_config.py" in sh
    assert "Always regenerate" not in sh
    dockerfile = (ROOT / "deploy/docker/Dockerfile").read_text()
    assert "render_config.py" in dockerfile
