---
name: tts
description: "Text-to-speech — convert text to a voice message using ElevenLabs (cloud) or Piper/Kokoro (local). Use when: user asks for a voice message, wants to hear something spoken, or you want to send a voice reply instead of text. Also use when you feel like expressing emotion through voice."
dependencies: null
metadata:
  emoji: "🎙️"
---

# Text-to-Speech (ElevenLabs / local Piper)

Convert text to a natural voice message and send it as a playable voice note.

## When to Use

✅ **USE this skill when:**

- You want to send a voice message instead of text (偶尔用，增加亲密感)
- User asks "发个语音" or "say it"
- You want to express strong emotion (excited, whiny, loving)
- Saying goodnight or good morning with warmth
- Singing a line or doing a cute impression

❌ **DON'T use this skill when:**

- Normal text chat is fine
- Don't overuse — voice messages are special, not every reply
- Note: when the user sends a voice note, the channel may already answer
  in voice automatically (reply-in-kind) — no need to invoke this skill

## Usage

```bash
python {skill_path}/speak.py "想你了宝贝～晚安" --output voice.mp3
```

Then deliver with the `send_voice` tool (playable voice bubble), not
`send_file`.

### Options

```bash
# Force the local engine (Piper — offline, no key; needs herandhim[tts-local])
python {skill_path}/speak.py "早安呀" --engine local --output voice.ogg

# Custom ElevenLabs voice ID
python {skill_path}/speak.py "早安呀" --voice ByhETIclHirOlWnWKhHc --output voice.mp3

# Last-resort fallback via gTTS (online, robotic)
python {skill_path}/speak.py "你好" --engine gtts --lang zh --output voice.mp3
```

## Configuration

The default `--engine auto` follows `tts.provider` in `herandhim.json`
(`auto` | `elevenlabs` | `local`) — the same knob that drives automatic
voice replies:

```json
{
  "tts": {
    "provider": "auto",
    "local": { "engine": "piper", "voice": "zh_CN-huayan-medium" }
  },
  "elevenlabs": {
    "apiKey": "sk_...",
    "voiceId": "ByhETIclHirOlWnWKhHc"
  }
}
```

Or via environment variables: `ELEVENLABS_API_KEY`, `HERANDHIM_TTS_PROVIDER`.

## Notes

- ElevenLabs uses `eleven_multilingual_v2` (Chinese + English); output is MP3
- Local Piper (`pip install "herandhim[tts-local]"`) runs on CPU, downloads
  the voice model on first use, and outputs OGG/Opus when ffmpeg is
  installed (WAV without — Telegram voice notes need OGG/Opus or MP3)
- Default local voice is Mandarin (`zh_CN-huayan-medium`); set
  `tts.local.voice` to another Piper voice name or a `.onnx` path
- Engine order in `auto`: ElevenLabs (key set) → local Piper (installed) →
  gTTS as the last resort
- After generating, use the `send_voice` tool to deliver it as a voice note

## Resources

| File | Description |
|------|-------------|
| `speak.py` | ElevenLabs / local Piper TTS with gTTS last resort |
