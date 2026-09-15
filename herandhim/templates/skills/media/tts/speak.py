#!/usr/bin/env python3
"""Text-to-speech: ElevenLabs (cloud) or Piper/Kokoro (local), gTTS last resort.

Engine selection (``--engine auto``, the default) follows ``tts.provider``
in herandhim.json / HERANDHIM_TTS_PROVIDER, same as voice replies:
ElevenLabs when a key is set, otherwise local Piper when installed
(pip install "herandhim[tts-local]"). gTTS (Google, online) is kept only
as the very last resort when neither is available, so a bare install can
still speak — pin ``tts.provider`` to "local" to guarantee nothing
leaves the machine."""

import argparse
import json
import os
import ssl
import sys
import urllib.request

ELEVENLABS_API = "https://api.elevenlabs.io/v1/text-to-speech"
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel (premade, works on free tier)
DEFAULT_MODEL = "eleven_multilingual_v2"


def _cfg(*keys: str, env: str = "") -> str | None:
    """Read a dotted config value from env, then the loaded config, then the
    config file on disk (skills run as subprocesses without HERANDHIM_* in env)."""
    if env and os.environ.get(env):
        return os.environ[env]
    try:
        from herandhim.config import get as cfg_get
        val = cfg_get(*keys)
        if val:
            return val
    except ImportError:
        pass
    for path in [
        os.path.join(os.environ.get("HERANDHIM_HOME", ""), "herandhim.json"),
        os.path.expanduser("~/.herandhim/herandhim.json"),
        os.path.join(os.getcwd(), "herandhim.json"),
    ]:
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.loads(f.read(), strict=False)
                val = cfg
                for k in keys:
                    val = val.get(k, {}) if isinstance(val, dict) else None
                if val:
                    return val
            except Exception:
                pass
    return None


def _get_api_key() -> str | None:
    return _cfg("elevenlabs", "apiKey", env="ELEVENLABS_API_KEY")


def _get_voice_id() -> str:
    """The voice configured in herandhim.json, else a premade free-tier one."""
    return _cfg("elevenlabs", "voiceId") or DEFAULT_VOICE_ID


def tts_elevenlabs(
    text: str,
    output: str,
    voice_id: str = "",
    model_id: str = DEFAULT_MODEL,
    api_key: str | None = None,
) -> bool:
    """Generate speech via ElevenLabs. Returns True on success."""
    key = api_key or _get_api_key()
    if not key:
        print("ElevenLabs API key not found.", file=sys.stderr)
        return False

    url = f"{ELEVENLABS_API}/{voice_id or _get_voice_id()}?output_format=mp3_44100_128"
    body = json.dumps({
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.3,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "xi-api-key": key,
        },
        method="POST",
    )

    try:
        ctx = ssl.create_default_context()
        try:
            import certifi
            ctx.load_verify_locations(certifi.where())
        except ImportError:
            pass
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            audio = resp.read()
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        with open(output, "wb") as f:
            f.write(audio)
        size_kb = len(audio) / 1024
        print(f"Saved: {output} (ElevenLabs, {size_kb:.1f} KB)")
        return True
    except Exception as exc:
        print(f"ElevenLabs TTS failed: {exc}", file=sys.stderr)
        return False


def tts_local(text: str, output: str) -> bool:
    """Local TTS (Piper by default, Kokoro via tts.local.engine) through
    herandhim.core.tts — the same engine that powers voice replies.
    Returns True on success; prints the install hint when missing."""
    try:
        from herandhim.core import tts as core_tts
    except ImportError:
        print("herandhim package not importable — local TTS unavailable.", file=sys.stderr)
        return False

    if not core_tts.local_available():
        print('Local TTS not installed. Run: pip install "herandhim[tts-local]"',
              file=sys.stderr)
        return False

    try:
        clip = core_tts.synthesize_local(text)
    except Exception as exc:
        print(f"Local TTS failed: {exc}", file=sys.stderr)
        return False

    # The local engine yields .ogg (Opus, Telegram-ready) with ffmpeg
    # installed, .wav without — fix the extension to match reality.
    base, ext = os.path.splitext(output)
    if ext.lower().lstrip(".") != clip.format:
        output = f"{base}.{clip.format}"
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "wb") as f:
        f.write(clip.data)
    print(f"Saved: {output} (local, {len(clip.data) / 1024:.1f} KB)")
    if clip.format == "wav":
        print("Note: install ffmpeg to get OGG/Opus — required for Telegram "
              "voice notes.", file=sys.stderr)
    return True


def tts_gtts(text: str, lang: str, slow: bool, output: str) -> bool:
    """Fallback TTS via gTTS."""
    try:
        from gtts import gTTS
    except ImportError:
        print("gTTS not installed. Run: pip install gTTS", file=sys.stderr)
        return False
    tts = gTTS(text=text, lang=lang, slow=slow)
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    tts.save(output)
    print(f"Saved: {output} (gTTS, lang={lang})")
    return True


def _local_installed() -> bool:
    try:
        from herandhim.core import tts as core_tts
        return core_tts.local_available()
    except ImportError:
        return False


def _resolve_engine() -> str:
    """Map ``tts.provider`` (auto/elevenlabs/local) onto a concrete engine,
    mirroring core.tts: key → ElevenLabs, else local when installed, else
    gTTS as the documented last resort."""
    provider = (_cfg("tts", "provider", env="HERANDHIM_TTS_PROVIDER") or "auto").lower()
    if provider == "elevenlabs":
        return "elevenlabs"
    if provider == "local":
        return "local"
    if _get_api_key():
        return "elevenlabs"
    if _local_installed():
        return "local"
    return "gtts"


def main():
    parser = argparse.ArgumentParser(
        description="Text-to-speech (ElevenLabs / local Piper / gTTS last resort)")
    parser.add_argument("text", help="Text to speak")
    parser.add_argument("--engine", default="auto",
                        choices=["auto", "elevenlabs", "local", "gtts"],
                        help="auto (default) follows tts.provider in config")
    parser.add_argument("--voice", default="",
                        help="ElevenLabs voice ID (default: elevenlabs.voiceId in config)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="ElevenLabs model ID")
    parser.add_argument("--lang", default="zh", help="Language code for gTTS fallback")
    parser.add_argument("--slow", action="store_true", help="Slow speech (gTTS only)")
    parser.add_argument("--output", "-o", default="voice.mp3", help="Output file path")
    args = parser.parse_args()

    engine = _resolve_engine() if args.engine == "auto" else args.engine

    if engine == "elevenlabs":
        ok = tts_elevenlabs(args.text, args.output, args.voice, args.model)
        if not ok and _local_installed():
            print("Falling back to local TTS...", file=sys.stderr)
            ok = tts_local(args.text, args.output)
        if not ok:
            print("Falling back to gTTS...", file=sys.stderr)
            tts_gtts(args.text, args.lang, args.slow, args.output)
    elif engine == "local":
        ok = tts_local(args.text, args.output)
        if not ok:
            print("Falling back to gTTS...", file=sys.stderr)
            tts_gtts(args.text, args.lang, args.slow, args.output)
    else:
        tts_gtts(args.text, args.lang, args.slow, args.output)


if __name__ == "__main__":
    main()
