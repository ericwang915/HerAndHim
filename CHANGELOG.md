# Changelog

All notable changes to HerAndHim. The newest release is at the top; each
section is written so it can be pasted into the matching GitHub Release.

## 0.3.0 — 2026-10-07

**This is a security release.** Every `pip` / `pipx` install of 0.2.0 or
earlier should upgrade:

```bash
pipx upgrade herandhim        # or: pip install -U herandhim
```

Docker users who pull `ghcr.io/ericwang915/herandhim:latest` already have
these changes; re-check your port mapping below.

### 🔒 Security

The web dashboard is a control panel for the agent: whoever reaches it can
chat as you, read the companion's memory, rewrite the config (including the
Telegram token) and — through the `run_command` tool — run shell commands as
the daemon's user. In 0.2.0 and earlier it listened on **`0.0.0.0` with no
authentication**, and `run_command` was always available to the model, so
anyone who could reach port 7788 on your machine had an agent with a shell.
On a laptop behind a home router that meant your LAN; on a VPS, or with Docker's
old `-p 7788:7788`, it meant the internet. ([#58](https://github.com/ericwang915/HerAndHim/pull/58))

- **Loopback by default.** `web.host` now defaults to `127.0.0.1` (was
  `0.0.0.0`); override with `HERANDHIM_WEB_HOST`. The wizard and
  `herandhim.example.json` write `127.0.0.1` too.
- **Access token for anything that isn't loopback.** `web.accessToken` /
  `HERANDHIM_WEB_ACCESS_TOKEN` is a shared secret. Binding to a non-loopback
  address without one makes `herandhim start` **refuse to start** (exit code
  2) instead of serving an open dashboard. When a token is set, every
  `/api/*` route and the `/ws/chat` WebSocket require it — as an
  `Authorization: Bearer <token>` header or the HttpOnly, `SameSite=Strict`
  cookie the browser gets after you paste the token once (constant-time
  comparison). WebSocket handshakes from a foreign browser `Origin` are
  refused even on an open loopback install. `/healthz` is the only
  unauthenticated probe.
- **`run_command` is authorization-gated.** New `tools.runCommand` /
  `HERANDHIM_TOOLS_RUN_COMMAND` setting: `true`, `false`, or `"auto"`
  (default) = enabled only while the dashboard binds loopback. When disabled
  the tool is withheld from the model's tool list, dropped from the system
  prompt and `/api/identity`, and refuses to execute even if called. The
  command denylist in `core/tools.py` stays as defence in depth; it is no
  longer what keeps strangers out.
- **Docker always enforces a token.** The container binds `0.0.0.0`
  internally and cannot tell how its port was published, so the entrypoint
  now guarantees one: `HERANDHIM_WEB_ACCESS_TOKEN` wins, a saved token is
  kept, and a fresh install mints a random one, printed in the log on every
  boot and stored in `/data/herandhim.json` (`chmod 600`). Every documented
  `docker run` and `docker-compose.yml` publish the port as
  `127.0.0.1:7788:7788`. `fly.toml` documents the secret and health-checks
  `/healthz`, since `/api/status` is now gated.
- `tests/test_web_access.py` covers the bind default, fail-closed start,
  401s on every sensitive route, WebSocket rejection, the cookie flow, the
  origin check and `run_command` gating.

### ⚠️ Upgrading from 0.2.0 — what to change

**pip / pipx.** `herandhim onboard` in 0.2.0 wrote
`"web": { "host": "0.0.0.0", "port": 7788 }` into `~/.herandhim/herandhim.json`.
After upgrading, `herandhim start` prints `Refusing to start: …` and exits
until you do one of:

```jsonc
// recommended — local only, no token needed
"web": { "host": "127.0.0.1", "port": 7788 }

// or keep it reachable from other machines, behind a token
"web": { "host": "0.0.0.0", "port": 7788, "accessToken": "<openssl rand -base64 32>" }
```

If you need the dashboard from your phone or another PC, an SSH tunnel or
VPN to the localhost port is the simplest option; if you do expose it, set a
token and put HTTPS in front so the token isn't sent in the clear.

**Docker / docker compose.** Change `-p 7788:7788` to
`-p 127.0.0.1:7788:7788` (compose: `"127.0.0.1:7788:7788"`); the old mapping
published the dashboard on every interface of the host. On first start the
container prints the access token — paste it into the browser once — or set
`-e HERANDHIM_WEB_ACCESS_TOKEN=...` to choose your own. Skills that run a
script (weather, horoscope, news, local TTS…) need the shell tool, which is
now off in containers: opt back in with `-e HERANDHIM_TOOLS_RUN_COMMAND=true`
once the token is in place.

**Existing `herandhim.json` with a `web.host: 0.0.0.0` you want to keep
open on a trusted LAN** — add `web.accessToken`; there is no way to run an
unauthenticated dashboard off loopback any more, by design.

Full rules: README → [Exposing the dashboard](README.md#exposing-the-dashboard),
[SECURITY.md](SECURITY.md), [deploy/docker/README.md](deploy/docker/README.md).

### ✨ Features since 0.2.0

- **Memory consolidation (Mem0-lite).** Before a new fact is saved, similar
  memories are retrieved and one small LLM call decides add / update /
  delete / skip, so "just moved to Shanghai" updates the current city
  instead of stacking a contradiction. Falls back to a plain write on any
  failure; `memory.consolidation: false` turns it off.
  ([#52](https://github.com/ericwang915/HerAndHim/pull/52))
- **Overnight consolidation (opt-in).** A quiet-hours cron pass (03:30
  local by default) merges duplicates and moves invalidated entries to
  `ARCHIVE.md` — never hard-deleted, system keys never touched, LLM usage
  capped per night. `memory.overnightConsolidation: true`,
  `memory.overnightHour`, `memory.overnightArchiveDays`.
  ([#53](https://github.com/ericwang915/HerAndHim/pull/53))
- **Structured compaction.** Compacted history is replaced by a summary
  with mandatory sections (relationship thread · confirmed user facts · open
  plans & dates · emotional tone · pending asks & promises · do-not-lose) so
  plans and promises survive compact chains.
  ([#52](https://github.com/ericwang915/HerAndHim/pull/52))
- **Local speech-to-text.** `stt.provider` = `auto | deepgram | local`
  (`HERANDHIM_STT_PROVIDER`); `pip install "herandhim[stt-local]"` adds
  faster-whisper so voice notes never leave your machine. `auto` keeps
  Deepgram when a key is set and falls back to local if the cloud call fails.
  ([#54](https://github.com/ericwang915/HerAndHim/pull/54))
- **Local text-to-speech and voice replies.** `tts.provider` =
  `auto | elevenlabs | local` (`HERANDHIM_TTS_PROVIDER`);
  `pip install "herandhim[tts-local]"` + ffmpeg adds Piper (Kokoro optional).
  She now **answers voice notes with voice** —
  `channels.telegram.replyInKindVoice` (`auto` by default, with
  `voiceReplyMaxChars`), falling back to text on any miss — and the agent
  gets a `send_voice` tool.
  ([#55](https://github.com/ericwang915/HerAndHim/pull/55))
- **A separate model for image turns.** `llm.vision` names any provider +
  model (for example `llava` on the same Ollama as a text-only `llama3.1`);
  endpoint and key default to that provider's own section. Docker:
  `HERANDHIM_VISION_PROVIDER` / `_MODEL` / `_BASE_URL` / `_API_KEY`.
  ([#48](https://github.com/ericwang915/HerAndHim/pull/48))
- **Local face consistency with ComfyUI.** `skills.comfyui.identityWorkflow`
  = `flux-pulid` or `sdxl-instantid` injects her reference portrait into a
  bundled PuLID / InstantID graph; falls back to plain generation with a
  warning if the node pack isn't installed.
  ([#52](https://github.com/ericwang915/HerAndHim/pull/52))
- **Tunable auto-compaction.** `agent.autoCompactThreshold` is now honoured
  (it was written by onboarding but never read) and
  `HERANDHIM_AUTO_COMPACT_THRESHOLD` overrides it; `0` keeps the 10000-token
  default. ([#50](https://github.com/ericwang915/HerAndHim/pull/50))

### 🐛 Fixes

- **Dashboard rendered black-on-black** when Tailwind's CDN was unreachable
  (Firefox on Linux Mint, blocked hosts, offline). The runtime is now
  vendored under `web/static/vendor` and the page carries element-level
  fallbacks, so the dashboard works fully offline with no third-party
  requests. ([#45](https://github.com/ericwang915/HerAndHim/pull/45), fixes #41)
- **Docker restarts no longer wipe `herandhim.json`.** The entrypoint
  merges env vars into the existing file instead of regenerating it, so the
  companion, her city/timezone and keys pasted into Settings survive a
  restart. ([#44](https://github.com/ericwang915/HerAndHim/pull/44), fixes #42)
- `herandhim.__version__` now matches the package version (it was stuck at
  `1.0.0`).

### Other

- The herandhim.ai landing site lives in `frontend/`
  ([#47](https://github.com/ericwang915/HerAndHim/pull/47)); README
  rewrite with a sharper comparison table
  ([#51](https://github.com/ericwang915/HerAndHim/pull/51)).

**Full diff:** [v0.2.0...v0.3.0](https://github.com/ericwang915/HerAndHim/compare/v0.2.0...v0.3.0)

## 0.2.0 — 2026-08-13

First release published to PyPI as `herandhim`
(`pip install herandhim`). The `v0.2.0` git tag was cut two days earlier
under the previous name; the PyPI upload also includes the rename.

- Rename ClawSoul → HerAndHim: package, CLI, config dir (`~/.herandhim/`),
  env prefix `HERANDHIM_*` ([#40](https://github.com/ericwang915/HerAndHim/pull/40)).
- 16 LLM providers with auto-detection from whichever key is set, including
  OpenAI, OpenRouter, Ollama and LM Studio.
- 13 image backends, including keyless `pollinations` and local ComfyUI /
  SD WebUI ([#33](https://github.com/ericwang915/HerAndHim/pull/33)).
- Express onboarding — 4 questions instead of ~30
  ([#39](https://github.com/ericwang915/HerAndHim/pull/39)).
- First-class `pip install`, PyPI publish workflow, fixed sdist.
- Simplified Chinese README.
- Fix: presence timestamps read as local time, not UTC
  ([#37](https://github.com/ericwang915/HerAndHim/pull/37)).

Known issue, fixed in 0.3.0: the dashboard bound `0.0.0.0` with no
authentication and the agent's shell tool was always enabled.

## 0.1.0 — 2026-08-08

First public release, as ClawSoul. See the
[GitHub Release](https://github.com/ericwang915/HerAndHim/releases/tag/v0.1.0).
Same open-bind issue as 0.2.0 — upgrade.
