#!/bin/sh
# HerAndHim container entrypoint.
#
# Renders $HERANDHIM_HOME/herandhim.json from HERANDHIM_* environment variables,
# then launches the daemon in the foreground.
#
#   first boot   → the file is created with defaults for every provider
#   every boot   → only env vars that are actually set are applied on top of
#                  the existing file; the companion, her city/timezone, and
#                  anything saved from the dashboard are preserved (#42)
#
# To start over from env vars alone, delete herandhim.json from the volume.
#
# Env vars (written to herandhim.json):
#   HERANDHIM_<PROVIDER>_API_KEY   the only one that's required, e.g.
#                                  HERANDHIM_DEEPSEEK_API_KEY — the provider is inferred
#   HERANDHIM_LLM_PROVIDER         optional override, e.g. "deepseek"
#   HERANDHIM_VISION_PROVIDER      optional: a second model for photos, e.g.
#   HERANDHIM_VISION_MODEL         "ollama" + "llava" next to a text-only chat model
#   HERANDHIM_TELEGRAM_TOKEN       your bot token (optional if web-only)
#   HERANDHIM_IMAGE_PROVIDER       optional: gemini|openai|seedream|fal|replicate|
#                                  sdwebui|comfyui|custom — also inferred from
#                                  whichever image key is set
#
# See deploy/local/.env.example for the full list, and render_config.py for
# exactly how each variable maps onto the file.

set -eu

CONFIG_DIR="${HERANDHIM_HOME:-/data}"
CONFIG_FILE="$CONFIG_DIR/herandhim.json"

mkdir -p "$CONFIG_DIR"

python /usr/local/bin/render_config.py "$CONFIG_FILE"

# ── Launch ──────────────────────────────────────────────────────────────
# Single-process daemon: web dashboard + (if a Telegram token is set) the bot.
exec python -m herandhim --config "$CONFIG_FILE" start --foreground
