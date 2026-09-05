"""A separate model for the turns that carry an image (#43).

``llm.vision`` names any provider + model; when set it always takes the
image turns. Otherwise the primary handles them if it can, else the original
Gemini fallback kicks in when a Gemini key exists.
"""

from __future__ import annotations

import json

import pytest

from herandhim import config, main
from herandhim.core.llm.openai_compatible import OpenAICompatibleProvider
from herandhim.core.llm.routing import RoutingProvider


@pytest.fixture(autouse=True)
def _isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HERANDHIM_HOME", str(tmp_path))
    monkeypatch.setattr(config, "_HERANDHIM_BASE", tmp_path)
    for var in ("LLM_PROVIDER", "GEMINI_API_KEY", "VISION_PROVIDER", "VISION_MODEL",
                "VISION_BASE_URL", "VISION_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    config._configs.clear()
    config._config_paths.clear()
    yield
    config._configs.clear()
    config._config_paths.clear()


def _configure(tmp_path, llm: dict) -> None:
    path = tmp_path / "herandhim.json"
    path.write_text(json.dumps({"llm": llm}))
    config.load(str(path), force=True)


def _ollama(model: str, base: str = "http://ollama.lan:11434/v1") -> dict:
    return {"apiKey": "", "model": model, "baseUrl": base}


# ── Explicit vision model ────────────────────────────────────────────────


def test_local_chat_model_plus_local_vision_model(tmp_path):
    """The request in #43: llama3.1 for chat, llava for photos, both on Ollama."""
    _configure(tmp_path, {
        "provider": "ollama",
        "ollama": _ollama("llama3.1"),
        "vision": {"provider": "ollama", "model": "llava"},
    })
    p = main._build_provider()

    assert isinstance(p, RoutingProvider)
    assert p.primary.model_name == "llama3.1"
    assert p.vision.model_name == "llava"
    # The vision model reuses the Ollama endpoint configured for chat.
    assert str(p.vision.client.base_url).startswith("http://ollama.lan:11434/v1")
    assert p.vision.supports_images is True


def test_vision_model_is_trusted_even_if_the_name_heuristic_would_not_be(tmp_path):
    """Nobody can keep a list of every Ollama tag; the user said it sees."""
    _configure(tmp_path, {
        "provider": "ollama",
        "ollama": _ollama("llama3.1"),
        "vision": {"provider": "ollama", "model": "some-custom-vl-finetune:latest"},
    })
    p = main._build_provider()
    assert isinstance(p, RoutingProvider)
    assert p.vision.supports_images is True


def test_vision_model_may_live_on_a_different_provider(tmp_path):
    _configure(tmp_path, {
        "provider": "deepseek",
        "deepseek": {"apiKey": "sk-ds", "model": "deepseek-chat",
                     "baseUrl": "https://api.deepseek.com/v1"},
        "ollama": _ollama("llama3.1"),
        "vision": {"provider": "ollama", "model": "qwen2.5vl:7b"},
    })
    p = main._build_provider()
    assert isinstance(p, RoutingProvider)
    assert p.primary.model_name == "deepseek-chat"
    assert p.vision.model_name == "qwen2.5vl:7b"
    assert str(p.vision.client.base_url).startswith("http://ollama.lan:11434/v1")


def test_vision_section_can_override_endpoint_and_key(tmp_path):
    _configure(tmp_path, {
        "provider": "ollama",
        "ollama": _ollama("llama3.1"),
        "vision": {"provider": "ollama", "model": "llava",
                   "baseUrl": "http://gpu-box:11434/v1", "apiKey": "shh"},
    })
    p = main._build_provider()
    assert str(p.vision.client.base_url).startswith("http://gpu-box:11434/v1")
    assert p.vision.client.api_key == "shh"


def test_explicit_vision_model_wins_over_a_primary_that_could_see(tmp_path):
    _configure(tmp_path, {
        "provider": "ollama",
        "ollama": _ollama("llava"),
        "vision": {"provider": "ollama", "model": "qwen2.5vl:32b"},
    })
    p = main._build_provider()
    assert isinstance(p, RoutingProvider)
    assert p.vision.model_name == "qwen2.5vl:32b"


def test_env_vars_configure_the_vision_model_too(tmp_path, monkeypatch):
    _configure(tmp_path, {"provider": "ollama", "ollama": _ollama("llama3.1")})
    monkeypatch.setenv("VISION_PROVIDER", "ollama")
    monkeypatch.setenv("VISION_MODEL", "moondream")
    p = main._build_provider()
    assert isinstance(p, RoutingProvider)
    assert p.vision.model_name == "moondream"


def test_a_broken_vision_config_does_not_stop_her_starting(tmp_path, caplog):
    _configure(tmp_path, {
        "provider": "ollama",
        "ollama": _ollama("llama3.1"),
        "vision": {"provider": "no-such-provider", "model": "x"},
    })
    p = main._build_provider()
    assert isinstance(p, OpenAICompatibleProvider)
    assert p.model_name == "llama3.1"
    assert "Vision model unavailable" in caplog.text


# ── Without llm.vision: the old behaviour, unchanged ────────────────────


def test_text_only_primary_without_any_vision_config_stays_bare(tmp_path):
    _configure(tmp_path, {"provider": "ollama", "ollama": _ollama("llama3.1")})
    p = main._build_provider()
    assert isinstance(p, OpenAICompatibleProvider)
    assert p.supports_images is False


def test_primary_that_can_see_needs_no_routing(tmp_path):
    _configure(tmp_path, {"provider": "ollama", "ollama": _ollama("llava")})
    p = main._build_provider()
    assert isinstance(p, OpenAICompatibleProvider)
    assert p.supports_images is True


def test_gemini_key_still_gives_the_legacy_fallback(tmp_path):
    _configure(tmp_path, {
        "provider": "ollama",
        "ollama": _ollama("llama3.1"),
        "gemini": {"apiKey": "g-key", "model": "gemini-2.5-flash"},
    })
    p = main._build_provider()
    assert isinstance(p, RoutingProvider)
    assert p.vision.model_name == "gemini-2.5-flash"


# ── Ollama tags the heuristic now recognises ─────────────────────────────


@pytest.mark.parametrize("tag", ["qwen2.5vl:7b", "qwen3-vl:8b", "minicpm-v", "moondream:latest",
                                 "bakllava", "pixtral:12b", "llama3.2-vision", "llava:13b"])
def test_common_ollama_vision_tags_are_detected(tag):
    p = OpenAICompatibleProvider(api_key="local", base_url="http://localhost:11434/v1", model_name=tag)
    assert p.supports_images is True


@pytest.mark.parametrize("tag", ["llama3.1", "qwen3:8b", "gemma3:1b", "deepseek-chat", "mistral"])
def test_text_tags_are_not_misdetected(tag):
    p = OpenAICompatibleProvider(api_key="local", base_url="http://localhost:11434/v1", model_name=tag)
    assert p.supports_images is False
