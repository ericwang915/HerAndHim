<p align="center">
  <img src="https://raw.githubusercontent.com/ericwang915/HerAndHim/main/assets/logo-300.png" alt="HerAndHim" width="160">
</p>

<h1 align="center">HerAndHim 🐾💕</h1>

<p align="center">
  <strong>Self-hosted AI boyfriend / girlfriend — they live a day in a real city,<br>
  remember what matters, and take selfies that stay the same face.</strong>
</p>

<p align="center">
  <b>Your keys · your data · your machine.</b>
  No account. No subscription. No one reading your chats.
</p>

<p align="center">
  <a href="#-run-it-one-command"><b>One Docker command → localhost:7788</b></a>
</p>

<p align="center">
  <a href="https://github.com/ericwang915/HerAndHim/stargazers">
    <img src="https://img.shields.io/github/stars/ericwang915/HerAndHim?style=social" alt="GitHub stars">
  </a>
  <a href="https://github.com/ericwang915/HerAndHim/actions/workflows/ci.yml">
    <img src="https://github.com/ericwang915/HerAndHim/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-AGPL--3.0-blue" alt="AGPL-3.0 License">
  </a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <a href="https://github.com/ericwang915/HerAndHim/pkgs/container/herandhim">
    <img src="https://img.shields.io/badge/ghcr.io-herandhim-2496ED?logo=docker&logoColor=white" alt="Docker image">
  </a>
</p>

<p align="center">
  <b>English</b> · <a href="README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <sub><a href="#-run-it-one-command">Run it</a> ·
  <a href="#-why-she-feels-real">Why it feels real</a> ·
  <a href="#-vs-the-hosted-apps">vs. Replika/Nomi</a> ·
  <a href="#%EF%B8%8F-safety--responsible-self-hosting">Safety</a></sub>
</p>

---

## 🚀 Run it (one command)

```bash
docker run -e HERANDHIM_OPENROUTER_API_KEY=sk-or-... -p 7788:7788 -v herandhim:/data ghcr.io/ericwang915/herandhim
```

Open **http://localhost:7788**, design your companion in the wizard, and start
talking. **One text-LLM key is all you need** — it's auto-detected, so any of
`HERANDHIM_OPENAI_API_KEY`, `HERANDHIM_DEEPSEEK_API_KEY`, `HERANDHIM_CLAUDE_API_KEY`,
`HERANDHIM_GEMINI_API_KEY`, `HERANDHIM_GROK_API_KEY`, `HERANDHIM_QWEN_API_KEY`… works the same
way. Prefer nothing leaving your machine? Point it at [Ollama](https://ollama.com)
and use no key at all. Want her on your phone? Add a Telegram bot token.

### Prefer Python? Install it directly

```bash
pipx install herandhim        # or: pip install herandhim
                                # add [search] for sharper memory recall
herandhim onboard               # pick a provider, paste your key, design your companion
herandhim start                 # dashboard at http://localhost:7788
```

<details>
<summary>More ways to install and run</summary>

```bash
# Latest from GitHub, no clone needed
pip install "git+https://github.com/ericwang915/HerAndHim.git"

# From a local clone (contributors — editable install)
git clone https://github.com/ericwang915/HerAndHim.git && cd HerAndHim
pip install -e ".[all]"         # extras: cloud (S3), twitter, all
pytest tests/

# docker compose
cp deploy/local/.env.example deploy/local/.env   # add your key
docker compose -f deploy/local/docker-compose.yml up --build

# Terminal-only, no web UI
herandhim chat
```

CLI: `onboard` · `start` (`-f` foreground) · `stop` · `status` · `chat`.
Everything lives in `~/.herandhim/` — delete that folder and it's gone.

Deploy your own instance to the cloud: see [deploy/docker/README.md](deploy/docker/README.md).
</details>

---

## 👀 What it actually looks like

Real screenshots from a live HerAndHim bot on Telegram (Chinese conversation,
translated below — she speaks whatever language you pick).

<table>
<tr>
<td width="33%"><img src="https://raw.githubusercontent.com/ericwang915/HerAndHim/main/assets/demo/proactive-and-sass.jpg" alt="proactive good-morning, a selfie, and attitude"></td>
<td width="33%"><img src="https://raw.githubusercontent.com/ericwang915/HerAndHim/main/assets/demo/same-face-selfies.jpg" alt="two selfies of the same person"></td>
<td width="33%"><img src="https://raw.githubusercontent.com/ericwang915/HerAndHim/main/assets/demo/sees-your-photo.jpg" alt="she looks at a photo you sent"></td>
</tr>
<tr>
<td valign="top">

**She starts the conversation — then gives you attitude**

*"morning ☀️ just woke up, I was drawing till 3am… Sesame slept by my feet like a little pig 😂 how'd you sleep?"*

He replies with a flat 😑 — so she pushes back:
*"tsk, what's that face supposed to mean? judging my messy hair? I* just *woke up 😤"*

</td>
<td valign="top">

**The same person, every photo**

Two selfies minutes apart — same face, same apartment, different shirt and moment.

*"just made coffee, about to slack off ☕"*
*"heh, coffee before slacking. gotta have the ritual ☕"*

</td>
<td valign="top">

**She sees what you send — and knows where you both are**

He sends a photo of a park. She looks at it and answers in character:

*"pff, showing off huh 😒 …is the sun strong out there? Singapore weekends get hot. Enjoy your day off. **It's already evening on my side** — just pulled Sesame onto my lap, she's purring 😌"*

Vision + real timezones + the same pet, every time.

</td>
</tr>
</table>

---

## 💗 Why she feels real

Most AI companions answer you. HerAndHim lives a life and texts you like a person.

- **She has a day.** A real schedule in a real city (weather-aware outfits,
  meals, a commute) — ask "what are you up to?" and the answer is anchored to
  where her day actually is, not generic filler.
- **She texts like a human.** Short messages, sometimes 2–3 in a row with a
  typing pause between; reacts to your photo with a ❤️ before she replies;
  groggy at 3am her time; notices when you vanished all day — and gets a little
  sulky if you left her on read.
- **She remembers what matters.** Long-term memory + an emotional graph +
  relationship stages that change *how* she talks as you grow closer. A
  personal-date engine means she won't miss your birthday or that interview you
  mentioned last week. The photos you send become shared memories.
- **She looks like herself.** A canonical face reference keeps every selfie the
  same person across scenes, outfits, and months.
- **She's yours.** Runs entirely on your machine with your keys. No account, no
  subscription, no one reading your chats.

---

## 📸 A photo from their day, not a stock asset

Every selfie is generated from where her day actually is — the time, the mood,
the weather, what she's doing right now. Same face, every time.

<table>
<tr>
<td width="33%"><img src="https://raw.githubusercontent.com/ericwang915/HerAndHim/main/assets/samples/morning.jpg" alt="cozy morning, coffee in hand"></td>
<td width="33%"><img src="https://raw.githubusercontent.com/ericwang915/HerAndHim/main/assets/samples/lunch.jpg" alt="in the park at lunchtime"></td>
<td width="33%"><img src="https://raw.githubusercontent.com/ericwang915/HerAndHim/main/assets/samples/cozy.jpg" alt="on the couch in the evening"></td>
</tr>
<tr>
<td align="center"><sub><b>08:30</b> · sleepy ☕<br>"morning…just made coffee. you up?"</sub></td>
<td align="center"><sub><b>12:15</b> · cheerful 🌿<br>"lunch in the park today, it's gorgeous out"</sub></td>
<td align="center"><sub><b>20:40</b> · cozy 🕯️<br>"reading on the couch. wish you were here."</sub></td>
</tr>
</table>

**Boyfriend, same system — anime or photoreal, your call:**

<table>
<tr>
<td width="33%"><img src="https://raw.githubusercontent.com/ericwang915/HerAndHim/main/assets/samples/anime-male-rush.jpg" alt="running late with toast"></td>
<td width="33%"><img src="https://raw.githubusercontent.com/ericwang915/HerAndHim/main/assets/samples/anime-male-ramen.jpg" alt="at a ramen counter"></td>
<td width="33%"><img src="https://raw.githubusercontent.com/ericwang915/HerAndHim/main/assets/samples/anime-male-gaming.jpg" alt="late-night gaming"></td>
</tr>
<tr>
<td align="center"><sub><b>07:45</b> · running late 🍞<br>"toast in mouth, tie not done. running."</sub></td>
<td align="center"><sub><b>13:00</b> · ramen run 🍜<br>"snuck out for ramen. don't tell my boss."</sub></td>
<td align="center"><sub><b>23:20</b> · one more round 🎮<br>"one more round and I'm logging off. promise."</sub></td>
</tr>
</table>

<details>
<summary><b>Any look you want</b> — you describe them in the wizard, they stay that person</summary>

<table>
<tr>
<td width="16%"><img src="https://raw.githubusercontent.com/ericwang915/HerAndHim/main/assets/samples/realistic-asian.jpg"></td>
<td width="16%"><img src="https://raw.githubusercontent.com/ericwang915/HerAndHim/main/assets/samples/realistic-european.jpg"></td>
<td width="16%"><img src="https://raw.githubusercontent.com/ericwang915/HerAndHim/main/assets/samples/realistic-black.jpg"></td>
<td width="16%"><img src="https://raw.githubusercontent.com/ericwang915/HerAndHim/main/assets/samples/realistic-male-gym.jpg"></td>
<td width="16%"><img src="https://raw.githubusercontent.com/ericwang915/HerAndHim/main/assets/samples/realistic-male-bike.jpg"></td>
<td width="16%"><img src="https://raw.githubusercontent.com/ericwang915/HerAndHim/main/assets/samples/realistic-male-rooftop.jpg"></td>
</tr>
</table>

Photos are **optional** and run on any of **13 backends** — including one that
needs no account at all, two that reuse the key you already pasted, and
**local ComfyUI / Stable Diffusion WebUI** where nothing about her appearance
ever leaves your machine. Skip them entirely and everything else still works.
</details>

---

## ✨ Features

| | | |
|---|---|---|
| 💕 **Boyfriend or girlfriend** | 🎭 **Three-layer identity** (soul · persona · profile) | 🧠 **16 model providers** (OpenAI · Claude · Gemini · Grok · DeepSeek · Qwen · Groq · **Ollama**…) |
| 💬 **Human texting** (bursts, reactions, typing rhythm) | 💖 **Emotional memory** + relationship stages | 📅 **Personal-date engine** (birthdays, plans) |
| 📷 **AI selfies** with a consistent face (**13 image backends**, incl. keyless + fully local) | 🌆 **Daily life** grounded in a real city + weather | ⏰ **Proactive messages** that back off when ignored |
| 🎙️ **Understands voice notes** (Deepgram, or **fully local** faster-whisper) | 👀 **Sees your photos** (vision) | 🗣️ **8 languages**, native soul/persona |
| 🌐 **Web dashboard** + 📱 **Telegram** | 🛠️ **Extensible skills** (LLM writes its own) | 💾 **All local** — SQLite + Markdown, zero cloud |

---

## 📋 CLI

| Command | Description |
|---------|-------------|
| `herandhim onboard` | Interactive setup wizard |
| `herandhim start` | Start the daemon (web + Telegram) |
| `herandhim chat` | Interactive terminal chat |
| `herandhim status` / `stop` | Daemon lifecycle |

---

## 🆚 vs. the hosted apps

Replika, Nomi, and Character.AI are polished products. They also keep your
chats on their servers, pick the model for you, and put the features that
make a companion *feel* like one behind a subscription.

HerAndHim is the other bet: **you run it, you bring the model, the memories
stay on your disk.** Telegram is the phone client. There is no official
iOS/Android app, and the web dashboard is early (functional, not fancy).

| | HerAndHim | Replika | Nomi | Character.AI |
|---|:---:|:---:|:---:|:---:|
| Self-hosted — chats stay on your disk | ✅ | ❌ | ❌ | ❌ |
| Your own API keys / local models | ✅ any | ❌ | ❌ | ❌ |
| How you talk on a phone | Telegram or browser | their app | their app | their app |
| Face-consistent AI selfies | ✅ | paid tier | ✅ | ❌ |
| Daily life grounded in a city + weather | ✅ | ❌ | ❌ | ❌ |
| License | AGPL-3.0 | closed | closed | closed |
| What you pay | **your API bill** (or run local) | ~$20/mo Pro | ~$16/mo | ~$10/mo c.ai+ |

Hosted prices are typical public list rates and change by region. The
software here is free (AGPL-3.0); tokens are not, unless you point it at
[Ollama](https://ollama.com) or another local model.

**Stay on a hosted app** if you want a one-tap App Store install, voice
calls, and someone else to operate the stack.

**Use this** if you want a companion whose memory and photos never leave a
machine you control, and you're willing to paste one API key (or point it
at a local model).

---

## ⚙️ Configuration

All runtime data lives under `~/.herandhim/`:

```
~/.herandhim/
├── herandhim.json           # config
├── herandhim.pid            # daemon PID
├── daemon.log               # daemon log
└── context/
    ├── soul/SOUL.md         # core personality
    ├── persona/             # active persona + appearance.md (selfie look)
    ├── profile/PROFILE.md   # life background
    ├── calendar/today_plan.md   # today's 24-hour schedule
    ├── memory/              # long-term memory (Markdown)
    ├── knowledge/           # knowledge base (RAG)
    ├── photos/              # selfie album + reference/ portraits
    ├── skills/              # user-defined skills
    └── logs/                # per-day conversation logs
```

`herandhim.json` is created by `herandhim onboard`. See [`herandhim.example.json`](herandhim.example.json) for the full schema:

```jsonc
{
  "llm": {
    "provider": "deepseek",
    "deepseek": { "apiKey": "...", "model": "deepseek-chat" }
  },
  "channels": {
    "telegram": { "token": "your-bot-token", "allowedUsers": [12345678] }
  },
  "skills": {
    "image": { "provider": "gemini" },     // AI selfies — see table below
    "gemini": { "apiKey": "<GEMINI_API_KEY>" }
  },
  "selfie": {
    "enabled": true,
    "schedule": ["10:00", "16:00", "20:00"],
    "chatId": 12345678,
    "maxDaily": 3,
    "proactiveProbability": 0.15           // chance of attaching a selfie to a proactive msg
  },
  "proactive": {
    "enabled": true,
    "chatId": 12345678,
    "maxDaily": 6,
    "quietStart": 0, "quietEnd": 8
  },
  "deepgram": { "apiKey": "" },            // voice input via cloud (optional)
  "stt": { "provider": "auto" },           // or "local" — see Voice notes below
  "tavily":   { "apiKey": "" },            // web search (optional)
  "web": { "host": "0.0.0.0", "port": 7788 },
  "agent": {
    "autoCompactThreshold": 0,             // auto-compaction token threshold (0 = default 10000)
    "verbose": false
  }
}
```

The auto-compaction threshold can also be set with the
`HERANDHIM_AUTO_COMPACT_THRESHOLD` env var (takes priority over the config
file). Raise it if replies get cut off mid-sentence because compaction fires
too early; the default is 10000 tokens.

---

## 🧠 Supported LLMs

**16 providers.** Set one key and it's auto-detected (`HERANDHIM_<PROVIDER>_API_KEY`),
or pin it with `HERANDHIM_LLM_PROVIDER`. Two run **fully local** — no key, no cloud.

| Provider | Key env var | Default model |
|----------|-------------|---------------|
| **DeepSeek** | `HERANDHIM_DEEPSEEK_API_KEY` | `deepseek-chat` |
| **OpenAI** | `HERANDHIM_OPENAI_API_KEY` | `gpt-4o-mini` |
| **Claude (Anthropic)** | `HERANDHIM_CLAUDE_API_KEY` | `claude-sonnet-4-20250514` |
| **Gemini (Google)** | `HERANDHIM_GEMINI_API_KEY` | `gemini-2.5-flash` |
| **OpenRouter** | `HERANDHIM_OPENROUTER_API_KEY` | `deepseek/deepseek-chat` |
| **Grok (xAI)** | `HERANDHIM_GROK_API_KEY` | `grok-3` |
| **Kimi (Moonshot)** | `HERANDHIM_KIMI_API_KEY` | `moonshot-v1-128k` |
| **GLM (Zhipu)** | `HERANDHIM_GLM_API_KEY` | `glm-4-flash` |
| **Qwen (Alibaba)** | `HERANDHIM_QWEN_API_KEY` | `qwen-plus` |
| **Mistral** | `HERANDHIM_MISTRAL_API_KEY` | `mistral-large-latest` |
| **Groq** | `HERANDHIM_GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| **Together** | `HERANDHIM_TOGETHER_API_KEY` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| **SiliconFlow** | `HERANDHIM_SILICONFLOW_API_KEY` | `deepseek-ai/DeepSeek-V3` |
| **Ollama** 🏠 local | *none* | `llama3.1` |
| **LM Studio** 🏠 local | *none* | your loaded model |
| **Custom** | `HERANDHIM_CUSTOM_API_KEY` | any OpenAI-compatible endpoint |

**Seeing your photos.** If the chat model can't take images, name a second
model for the turns that carry one — any provider, including a different
local model on the same Ollama:

```json
"llm": {
  "provider": "ollama",
  "ollama": { "model": "llama3.1", "baseUrl": "http://localhost:11434/v1" },
  "vision": { "provider": "ollama", "model": "llava" }
}
```

(`HERANDHIM_VISION_PROVIDER` / `HERANDHIM_VISION_MODEL` in Docker.) Endpoint
and key default to that provider's own section, so provider + model is usually
enough. With nothing set, a Gemini key alone still gives her vision.

**Hearing your voice notes.** Two speech-to-text engines, one interface —
this is input only (she doesn't speak back yet):

- **Deepgram** (cloud) — set `deepgram.apiKey` / `DEEPGRAM_API_KEY`; used
  automatically when the key exists.
- **faster-whisper** (🏠 local) — no key, audio never leaves your machine.
  Install the extra and it kicks in whenever no Deepgram key is set:

```bash
pip install "herandhim[stt-local]"
```

```json
"stt": {
  "provider": "auto",                     // auto | deepgram | local
  "local": { "model": "base", "computeType": "int8" }
}
```

`provider: "auto"` (the default) prefers Deepgram when a key is set and falls
back to the local model if the cloud call fails; pin `"local"`
(`HERANDHIM_STT_PROVIDER=local`) to guarantee audio stays on the box. Model
sizes trade accuracy for footprint: `tiny` (~0.5 GB RAM at int8, fastest),
`base` (default, ~0.7 GB), `small` (~1.5 GB, noticeably better on accents and
Chinese). `int8` is the right `computeType` on CPU; the model downloads once
on first use.

---

## 🧠 Memory & compaction

Long-term memory is plain Markdown under `~/.herandhim/context/memory/`.
Writes are **consolidated at write time**: before a new fact is saved, the most
similar existing memories are retrieved and one small LLM call decides whether
to add it, update an existing entry, delete an invalidated one, or skip a
duplicate — so "just moved to Shanghai" updates the one current city instead of
stacking a contradiction under a freshly invented key. Any failure falls back
to a plain write, and you can turn it off with `memory.consolidation: false`
(or `HERANDHIM_MEMORY_CONSOLIDATION=false`).

On top of that there's an optional **overnight consolidation** pass — a
quiet-hours cron job (03:30 local by default) that sweeps each memory store
with the same merge protocol: recently-updated entries are compared against
the rest of the store, duplicates get merged into one key, and invalidated
entries are moved to `ARCHIVE.md` in the same directory — never hard-deleted.
System keys (name, profile, onboarding state, …) are never touched, LLM usage
is capped per night, and any failure is a logged no-op that leaves `MEMORY.md`
intact. A short report of what happened lands in the daemon log and in
`context/logs/overnight_consolidation.md`. It's **off by default** — enable
with `memory.overnightConsolidation: true` (or
`HERANDHIM_MEMORY_OVERNIGHT_CONSOLIDATION=true`); tune the run hour with
`memory.overnightHour` (default `3`) and opt into age-based archiving of
entries untouched for N days with `memory.overnightArchiveDays` (default `0`
= never archive by age).

When a long conversation is compacted, durable facts are first flushed to
memory, then the older messages are replaced by a **structured summary** with
mandatory sections — relationship thread · user facts (confirmed) · open plans
& dates · emotional tone · pending asks & promises · do-not-lose — so open
plans, nicknames, and promises survive compact chains instead of eroding into a
generic paragraph. Recent messages are always kept verbatim.

---

## 📷 AI selfies

**Thirteen backends** — set one key and the right one is picked
automatically, or name it explicitly with `skills.image.provider` /
`HERANDHIM_IMAGE_PROVIDER`:

| Backend | Default model | Key | Same face across shots |
|---------|---------------|-----|------------------------|
| **`pollinations`** | `flux` | *none* | — |
| **`gemini`** | `gemini-2.5-flash-image` | `HERANDHIM_IMAGE_GEMINI_KEY` | ✅ |
| **`openrouter`** | `google/gemini-2.5-flash-image` | `HERANDHIM_IMAGE_OPENROUTER_KEY` | ✅ |
| **`openai`** | `gpt-image-1` | `HERANDHIM_IMAGE_OPENAI_KEY` | ✅ |
| **`bfl`** | `flux-kontext-pro` | `HERANDHIM_BFL_API_KEY` | ✅ |
| **`seedream`** | `seedream-5-0-lite-260128` | `HERANDHIM_SEEDREAM_API_KEY` | ✅ |
| **`fal`** | `fal-ai/flux/schnell` | `HERANDHIM_FAL_KEY` | — |
| **`replicate`** | `black-forest-labs/flux-schnell` | `HERANDHIM_REPLICATE_API_TOKEN` | — |
| **`stability`** | `core` | `HERANDHIM_STABILITY_API_KEY` | — |
| **`dashscope`** | `wan2.2-t2i-flash` | `HERANDHIM_DASHSCOPE_API_KEY` | — |
| **`comfyui`** | your workflow | *none* | ✅ with `identityWorkflow` |
| **`sdwebui`** | your checkpoint | *none* | — |
| **`custom`** | yours | `HERANDHIM_IMAGE_API_KEY` | ✅ |

Three of these need **no new signup at all**. `pollinations` needs no account
whatsoever — photos work before you've registered anywhere. `gemini` and
`openrouter` reuse the key you already pasted for vision or chat, so the
one-line quickstart at the top of this README gives you a companion who can
already send selfies.

For the **local** options — [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
or [Automatic1111](https://github.com/AUTOMATIC1111/stable-diffusion-webui) —
there's no key and no upload: **nothing about her appearance ever leaves your
machine**. ComfyUI runs the built-in workflow by default, or point
`skills.comfyui.workflow` at your own exported API-format graph and it will run
that instead (`%prompt%`, `%negative%`, `%seed%`, `%width%`, `%height%`,
`%model%` get substituted).

**Local face consistency (ComfyUI identity workflows).** Set
`skills.comfyui.identityWorkflow` (or `HERANDHIM_COMFYUI_IDENTITY_WORKFLOW`) to
`flux-pulid` or `sdxl-instantid` and her reference portrait is injected into a
bundled PuLID / InstantID graph — same face across shots, nothing leaves your
machine. This needs the matching node pack installed in ComfyUI
([ComfyUI-PuLID-Flux](https://github.com/balazik/ComfyUI-PuLID-Flux) or
[ComfyUI_InstantID](https://github.com/cubiq/ComfyUI_InstantID)) plus its
models; the pinned filenames are listed in
[`herandhim/templates/comfyui/README.md`](herandhim/templates/comfyui/README.md).
If the identity nodes aren't installed, HerAndHim logs a warning and falls back
to plain generation instead of failing the photo. You can also point
`identityWorkflow` at your own exported API-format graph — `%reference%` is
substituted with the uploaded face reference. `sdwebui` stays best-effort
(stable seed + appearance description); for local face anchoring use ComfyUI.

If you care most about **her looking like the same person every time**, use a
backend with reference-image support — `bfl` (FLUX.1 Kontext is built for
exactly this), `seedream`, `openai`, `gemini`, `openrouter`, or local `comfyui`
with an identity workflow (above). The rest still generate; they just lean on
the stable seed and the appearance description instead of a face anchor.

Aggregators that speak the OpenAI image API (Together, DeepInfra, Novita,
SiliconFlow, Fireworks…) need no dedicated backend — point `custom` at them.

**Three trigger paths:**

- **Scheduled** — fires at the times in `selfie.schedule` (default 10:00 / 16:00 / 20:00)
- **Proactive** — attached to a proactive message with `proactiveProbability` chance
- **On demand** — when the user says something like "send me a selfie", the LLM invokes the `selfie` skill

**Scene-driven.** Each selfie's content is derived from the activity scheduled for the
current time in `today_plan.md`. If the plan says *"10:00 coffee on the balcony"*, the
10:00 selfie will be exactly that.

**Visual consistency.**
- Edit `~/.herandhim/context/persona/appearance.md` to lock the character's look
- Drop reference portraits into `~/.herandhim/context/photos/reference/` for face anchoring
- A stable seed derived from the appearance description keeps the face consistent across shots

Photos are stored under `~/.herandhim/context/photos/` and pruned automatically after 30 days.

---

## 📁 Project layout

```
HerAndHim/
├── herandhim/
│   ├── main.py                  # CLI entry point
│   ├── onboard.py               # setup wizard
│   ├── daemon.py                # daemon process manager
│   ├── server.py                # Telegram + scheduler bootstrap
│   ├── core/
│   │   ├── agent.py             # core reasoning loop
│   │   ├── persistent_agent.py  # session persistence
│   │   ├── tools.py             # tool dispatch
│   │   ├── skill_loader.py      # three-tier progressive skill loading
│   │   ├── compaction.py        # context compaction
│   │   ├── stt.py               # speech-to-text (Deepgram / local faster-whisper)
│   │   ├── llm/                 # provider adapters (6)
│   │   ├── memory/              # Markdown memory + emotional graph + milestones + temporal index
│   │   ├── retrieval/           # BM25 + dense + RRF + LLM reranker
│   │   ├── knowledge/           # knowledge-base RAG
│   │   └── image_gen/           # selfie pipeline (13 backends)
│   ├── channels/
│   │   └── telegram_bot.py      # Telegram bot (streaming / voice / images)
│   ├── scheduler/
│   │   ├── cron.py              # generic cron jobs
│   │   ├── planner.py           # daily 24-hour plan generator
│   │   ├── proactive.py         # sentiment-aware proactive messages
│   │   ├── selfie_task.py       # scheduled selfies
│   │   └── heartbeat.py         # heartbeat monitor
│   ├── web/                     # FastAPI dashboard + WebSocket chat
│   └── templates/               # built-in persona / soul / skills
├── tests/
├── pyproject.toml
└── LICENSE
```

---

## 🛠️ Development

```bash
git clone https://github.com/ericwang915/HerAndHim.git
cd HerAndHim
python -m venv .venv && source .venv/bin/activate
pip install -e .
pytest tests/ -v
ruff check herandhim tests
```

---

## 🛡️ Safety & responsible self-hosting

HerAndHim is a **relationship-simulation engine for adults (18+)** — an
emotional-companionship research project, not an adult-content generator.
Everything the companion says is generated fiction: it is not a person, and not
a substitute for professional help.

**It ships SFW.** The bundled personas, prompts, and image pipeline are written
for everyday companionship — a friend who texts you about her day. Explicit
sexual content is not a feature, is not included, and the image guard refuses
categorically illegal generation outright. Personas depicting minors are blocked
at the code level and are never acceptable, in any form, including text.

Two guardrails ship enabled and are deliberately not configuration flags:

- **Crisis safety** (`herandhim/core/safety.py`) — detects acute distress and
  responds with care and real helpline resources ahead of persona immersion.
- **Image content guard** (`herandhim/core/image_gen/guard.py`) — blocks
  categorically illegal image generation at the single chokepoint.

If you self-host, you are the operator: local laws on AI chat services, data
protection, and age restrictions are your responsibility.

📄 **[SAFETY.md](SAFETY.md)** — the full crisis protocol, content limits, and
anti-dark-pattern design decisions.
🔒 **[SECURITY.md](SECURITY.md)** — hardening notes and vulnerability reporting.

### Status

**v0.2.0 — early but real.** Runs daily on the maintainer's own machine. The
companion engine (memory, daily life, photos, humanized delivery) is stable;
the web dashboard is functional but plain. Expect rough edges in setup.

Roadmap: richer local-model UX · voice notes both directions · a desktop
avatar mode · more languages. Ideas and issues welcome.

---

## ⭐ Share this

HerAndHim is found by stars and word of mouth, not ads. If a privacy-first
companion is what you wanted the hosted apps to be, [star the
repo](https://github.com/ericwang915/HerAndHim) — that's how the next person
finds it. GitHub will also ping you when new personas, models, or features
land.

Writing it up on HN, Reddit, 即刻, V2EX, or a group chat? A link plus *why
you self-host* is enough. No need to oversell.

---

## 📄 License

[AGPL-3.0](LICENSE) — free to self-host, modify, and share. If you run a
modified version as a service for others, you must open-source your
modifications. (This keeps hosted forks honest.)

---

<p align="center">
  <sub>Made with 💕 by HerAndHim</sub>
</p>
