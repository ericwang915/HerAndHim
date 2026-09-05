#!/usr/bin/env python3
"""Render herandhim.json from HERANDHIM_* environment variables.

Called by ``entrypoint.sh`` on every container boot.

* **First boot** (no config file yet): write a complete config — every
  provider stubbed with its default model and base URL — so the dashboard has
  something to show and a single ``-e HERANDHIM_<PROVIDER>_API_KEY`` is enough.

* **Every later boot**: load the file that's already on the volume and overlay
  ONLY the env vars that are actually set. Everything else — the companion the
  wizard designed, her city and timezone, keys pasted into the dashboard,
  models changed in Settings — is left exactly as it was.

  The previous behaviour rewrote the whole file from env on each restart,
  which silently wiped the wizard's output and left her waking up on Shanghai
  time (#42).

Env vars (the container's ``.env.example`` documents them all):
  HERANDHIM_<PROVIDER>_API_KEY / _MODEL / _BASE_URL   text LLM, provider inferred
  HERANDHIM_LLM_PROVIDER                              pin the text provider
  HERANDHIM_TELEGRAM_TOKEN / _TELEGRAM_ALLOWED_USERS
  HERANDHIM_IMAGE_PROVIDER / HERANDHIM_IMAGE_MODEL    selfies, backend inferred
  HERANDHIM_<BACKEND>_API_KEY / _BASE_URL             per image backend
  HERANDHIM_DEEPGRAM_API_KEY, HERANDHIM_TAVILY_API_KEY
  PORT
"""

from __future__ import annotations

import copy
import json
import os
import pathlib
import sys
from collections.abc import Mapping
from typing import Any

# provider -> (default model, default base URL). Keep in sync with
# _OPENAI_COMPATIBLE in herandhim/main.py. Claude and Gemini use native SDKs
# and take no base URL.
LLM_PROVIDERS: dict[str, tuple[str, str]] = {
    "openai":      ("gpt-4o-mini",                             "https://api.openai.com/v1"),
    "openrouter":  ("deepseek/deepseek-chat",                  "https://openrouter.ai/api/v1"),
    "ollama":      ("llama3.1",                                "http://localhost:11434/v1"),
    "lmstudio":    ("local-model",                             "http://localhost:1234/v1"),
    "deepseek":    ("deepseek-chat",                           "https://api.deepseek.com/v1"),
    "grok":        ("grok-3",                                  "https://api.x.ai/v1"),
    "kimi":        ("moonshot-v1-128k",                        "https://api.moonshot.cn/v1"),
    "glm":         ("glm-4-flash",                             "https://open.bigmodel.cn/api/paas/v4/"),
    "qwen":        ("qwen-plus",                               "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    "mistral":     ("mistral-large-latest",                    "https://api.mistral.ai/v1"),
    "groq":        ("llama-3.3-70b-versatile",                 "https://api.groq.com/openai/v1"),
    "together":    ("meta-llama/Llama-3.3-70B-Instruct-Turbo", "https://api.together.xyz/v1"),
    "siliconflow": ("deepseek-ai/DeepSeek-V3",                 "https://api.siliconflow.cn/v1"),
    "custom":      ("",                                        ""),
}
NATIVE_PROVIDERS: dict[str, str] = {
    "claude": "claude-sonnet-4-20250514",
    "gemini": "gemini-2.0-flash",
}
# Order matters: it's the order a provider is inferred from whichever key is set.
PROVIDER_ORDER = list(LLM_PROVIDERS) + list(NATIVE_PROVIDERS)
DEFAULT_PROVIDER = "deepseek"

# backend -> (key env var, default model, default base URL). Setting one key
# is enough: the backend is inferred, same as for the LLM.
IMAGE_BACKENDS: dict[str, tuple[str, str, str]] = {
    "seedream":     ("HERANDHIM_SEEDREAM_API_KEY",     "seedream-5-0-lite-260128",
                     "https://ark.ap-southeast.bytepluses.com/api/v3"),
    "openai":       ("HERANDHIM_IMAGE_OPENAI_KEY",     "gpt-image-1", ""),
    "gemini":       ("HERANDHIM_IMAGE_GEMINI_KEY",     "gemini-2.5-flash-image", ""),
    "openrouter":   ("HERANDHIM_IMAGE_OPENROUTER_KEY", "google/gemini-2.5-flash-image", ""),
    "bfl":          ("HERANDHIM_BFL_API_KEY",          "flux-kontext-pro", ""),
    "fal":          ("HERANDHIM_FAL_KEY",              "fal-ai/flux/schnell", ""),
    "replicate":    ("HERANDHIM_REPLICATE_API_TOKEN",  "black-forest-labs/flux-schnell", ""),
    "stability":    ("HERANDHIM_STABILITY_API_KEY",    "core", ""),
    "dashscope":    ("HERANDHIM_DASHSCOPE_API_KEY",    "wan2.2-t2i-flash", ""),
    "sdwebui":      ("",                               "", "http://localhost:7860"),
    "comfyui":      ("",                               "", "http://localhost:8188"),
    "pollinations": ("",                               "flux", ""),
    "custom":       ("HERANDHIM_IMAGE_API_KEY",        "", ""),
}


# ── Tiny nested-dict helpers ─────────────────────────────────────────────────

def _get(cfg: dict, path: tuple[str, ...], default: Any = None) -> Any:
    cur: Any = cfg
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _set(cfg: dict, path: tuple[str, ...], value: Any) -> None:
    cur = cfg
    for key in path[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = cur[key] = {}
        cur = nxt
    cur[path[-1]] = value


# ── Rendering ────────────────────────────────────────────────────────────────

def render(existing: dict | None, environ: Mapping[str, str] = os.environ) -> dict:
    """Return the config to write.

    ``existing`` is the parsed file already on the volume, or ``None`` on first
    boot. With a file present, only env vars that are actually set are applied
    on top of it; nothing is ever removed.
    """
    fresh = existing is None
    cfg: dict = {} if fresh else copy.deepcopy(existing)

    def env(key: str, default: str = "") -> str:
        return environ.get(key, default)

    def put(path: tuple[str, ...], env_key: str, default: str | None = None) -> None:
        """Env var wins whenever set; a fresh render falls back to ``default``
        (skipped when ``None``); an existing value is otherwise left alone."""
        val = env(env_key)
        if val != "":
            _set(cfg, path, val)
        elif fresh and default is not None:
            _set(cfg, path, default)

    # ── Text LLM ────────────────────────────────────────────────────────
    # Provider: an explicit pin always wins. Otherwise infer from whichever
    # key is set — but only when the file doesn't already say (a choice made
    # in the dashboard must survive a restart).
    provider = env("HERANDHIM_LLM_PROVIDER").lower()
    if not provider and (fresh or not _get(cfg, ("llm", "provider"))):
        provider = next(
            (name for name in PROVIDER_ORDER if env(f"HERANDHIM_{name.upper()}_API_KEY")),
            DEFAULT_PROVIDER,
        )
    if provider:
        _set(cfg, ("llm", "provider"), provider)

    for name, (model, base) in LLM_PROVIDERS.items():
        upper = name.upper()
        put(("llm", name, "apiKey"),  f"HERANDHIM_{upper}_API_KEY",  "")
        put(("llm", name, "model"),   f"HERANDHIM_{upper}_MODEL",    model)
        put(("llm", name, "baseUrl"), f"HERANDHIM_{upper}_BASE_URL", base or None)
    for name, model in NATIVE_PROVIDERS.items():
        upper = name.upper()
        put(("llm", name, "apiKey"), f"HERANDHIM_{upper}_API_KEY", "")
        put(("llm", name, "model"),  f"HERANDHIM_{upper}_MODEL",   model)

    # ── Telegram ────────────────────────────────────────────────────────
    put(("channels", "telegram", "token"), "HERANDHIM_TELEGRAM_TOKEN", "")
    allowed = env("HERANDHIM_TELEGRAM_ALLOWED_USERS")
    if allowed:
        _set(cfg, ("channels", "telegram", "allowedUsers"),
             [int(x) for x in allowed.replace(",", " ").split() if x])
    elif fresh:
        _set(cfg, ("channels", "telegram", "allowedUsers"), [])

    # ── Photos ──────────────────────────────────────────────────────────
    image_provider = env("HERANDHIM_IMAGE_PROVIDER").lower()
    if not image_provider and (fresh or not _get(cfg, ("skills", "image", "provider"))):
        image_provider = next(
            (name for name, (key_env, *_r) in IMAGE_BACKENDS.items()
             if key_env and env(key_env)),
            "",
        )
        if not image_provider:
            # Local servers, then keys already set for chat/vision. An
            # explicitly set image key always wins over these.
            if env("HERANDHIM_COMFYUI_BASE_URL"):
                image_provider = "comfyui"
            elif env("HERANDHIM_SDWEBUI_BASE_URL"):
                image_provider = "sdwebui"
            elif env("HERANDHIM_GEMINI_API_KEY"):
                image_provider = "gemini"
            elif env("HERANDHIM_OPENROUTER_API_KEY"):
                image_provider = "openrouter"
    if image_provider:
        _set(cfg, ("skills", "image", "provider"), image_provider)
    effective_image = image_provider or _get(cfg, ("skills", "image", "provider"), "")

    for name, (key_env, model, base) in IMAGE_BACKENDS.items():
        upper = name.upper()
        if fresh:
            cfg.setdefault("skills", {}).setdefault(name, {})
        key = env(key_env) if key_env else ""
        # Gemini and OpenRouter keys already set for chat/vision work for
        # images too — don't make people paste the same key under a second name.
        if not key and name == effective_image:
            key = env(f"HERANDHIM_{upper}_API_KEY")
        if key:
            _set(cfg, ("skills", name, "apiKey"), key)
        override = env("HERANDHIM_IMAGE_MODEL") if name == effective_image else ""
        if name == "seedream":
            override = override or env("HERANDHIM_SEEDREAM_MODEL")
        if override:
            _set(cfg, ("skills", name, "model"), override)
        elif fresh and model:
            _set(cfg, ("skills", name, "model"), model)
        put(("skills", name, "baseUrl"), f"HERANDHIM_{upper}_BASE_URL", base or None)

    # ── Voice, search ───────────────────────────────────────────────────
    put(("deepgram", "apiKey"), "HERANDHIM_DEEPGRAM_API_KEY", "")
    put(("tavily", "apiKey"),   "HERANDHIM_TAVILY_API_KEY",   "")

    # ── Web ─────────────────────────────────────────────────────────────
    # Inside a container the dashboard must bind every interface and the
    # port the image EXPOSEs, whatever the file says — otherwise a stray
    # dashboard edit makes the container unreachable.
    _set(cfg, ("web", "host"), "0.0.0.0")
    _set(cfg, ("web", "port"), int(env("PORT", "7788")))

    return cfg


# ── File I/O ─────────────────────────────────────────────────────────────────

def _parse(text: str) -> dict:
    """Parse the on-disk file. Hand-edited configs may carry // comments and
    trailing commas — the app tolerates them, so must we."""
    try:
        from herandhim.config import _strip_json5
        text = _strip_json5(text)
    except ImportError:  # running outside the image, plain JSON only
        pass
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("config root must be a JSON object")
    return data


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = pathlib.Path(argv[0] if argv else os.environ.get("CONFIG_FILE", "/data/herandhim.json"))
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict | None = None
    if path.is_file() and path.stat().st_size > 0:
        try:
            existing = _parse(path.read_text(encoding="utf-8"))
        except (ValueError, json.JSONDecodeError) as exc:
            # Never crash-loop the container over a bad edit — but never
            # silently discard the user's file either.
            backup = path.with_suffix(path.suffix + ".bak")
            path.replace(backup)
            print(f"[entrypoint] {path} is not valid JSON ({exc}); "
                  f"moved it to {backup} and starting from env vars", file=sys.stderr)

    mode = "merging env vars into" if existing is not None else "creating"
    print(f"[entrypoint] {mode} {path}")
    cfg = render(existing)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
