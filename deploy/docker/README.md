# Deploying HerAndHim

HerAndHim is a single-process app: a web dashboard, plus a Telegram bot when you
set a token. It stores everything under `/data` (or `~/.herandhim` outside
Docker). No database, no cloud services.

## Option A — Docker (recommended)

The fastest path. From the repo root:

```bash
cp deploy/local/.env.example deploy/local/.env   # add your DeepSeek key (+ Telegram token, optional)
docker compose -f deploy/local/docker-compose.yml up --build
```

Open http://localhost:7788, paste the **access token** from the container log
(`[entrypoint] dashboard access token: …`), finish the browser wizard, and
chat. Data persists in the `herandhim_data` volume across restarts.

The compose file publishes the port to `127.0.0.1` only. See
[Exposing the dashboard](#exposing-the-dashboard) before changing that.

`herandhim.json` on that volume is yours: the wizard and the dashboard write
to it, and a restart keeps every edit. Env vars are applied on top on every
boot — so rotating a key in `.env` takes effect, and `HERANDHIM_LLM_PROVIDER`
still pins the provider — but nothing you saved is ever removed. To start
over from env vars alone, delete the file from the volume.

Or run the prebuilt image directly (no clone, no build):

```bash
docker run -e HERANDHIM_DEEPSEEK_API_KEY=sk-... -p 127.0.0.1:7788:7788 \
  -v herandhim:/data ghcr.io/ericwang915/herandhim
```

Add `-e HERANDHIM_WEB_ACCESS_TOKEN=...` to choose the token yourself instead
of reading the generated one from the log.

## Option B — pip

```bash
pip install -e .
herandhim onboard   # interactive: pick a provider, paste your key, design your companion
herandhim start     # dashboard at http://localhost:7788
```

Outside Docker the dashboard binds `127.0.0.1` and needs no token.

## Option C — Fly.io (host your own instance in the cloud)

`fly.toml` runs one always-on instance of your personal HerAndHim — on a
public URL, so the dashboard is token-gated. Set the token as a secret before
the first deploy:

```bash
fly launch --config deploy/docker/fly.toml --dockerfile deploy/docker/Dockerfile --no-deploy
fly secrets set HERANDHIM_DEEPSEEK_API_KEY=sk-... HERANDHIM_TELEGRAM_TOKEN=123:AA... \
  HERANDHIM_WEB_ACCESS_TOKEN="$(openssl rand -base64 32)" --app <your-app>
fly deploy --config deploy/docker/fly.toml --dockerfile deploy/docker/Dockerfile --app <your-app>
```

Then open `https://<your-app>.fly.dev` and paste the token. (If you skip the
secret, the container mints a random token on first boot and prints it in
`fly logs`; it is stored on the volume so it survives redeploys.) The health
check hits `/healthz`, which is the one endpoint that never needs the token.

The app name is global on `fly.dev` — change `app = "herandhim"` in `fly.toml`
if it's taken. `swap_size_mb` gives the small instance headroom for the first
model call.

## Exposing the dashboard

Whoever reaches the dashboard can chat as you, read the companion's memory,
edit the config, and — when enabled — run shell commands through the agent.
The rules, in order of exposure:

| Setup | Bind / publish | Token |
|---|---|---|
| pip, `herandhim start` | `web.host` defaults to `127.0.0.1` | optional (`web.accessToken`) |
| Docker, `docker compose` | container binds `0.0.0.0`; port published to `127.0.0.1` only | **always enforced** — generated if unset |
| `web.host: 0.0.0.0` / LAN / VPS / Fly | reachable from other machines | **required** — the app refuses to start without one |

- **Token** — `web.accessToken` in `herandhim.json` or `HERANDHIM_WEB_ACCESS_TOKEN`.
  Long and random. The browser asks for it once and keeps an HttpOnly cookie;
  scripts send `Authorization: Bearer <token>`.
- **Shell tool** — `run_command` is off by default whenever the dashboard is
  not loopback-only (that includes every Docker install). The bundled skills
  that execute a script (selfie, weather, horoscope, news, TTS, onboarding…)
  do not need it: they run through `run_skill_script`, which only executes
  the scripts shipped inside the image, with an argv list and no shell.
  Skills the agent creates for itself are not runnable here unless you allow
  them with `HERANDHIM_TOOLS_RUN_SKILL_SCRIPT=true`. Opt into the full shell
  with `HERANDHIM_TOOLS_RUN_COMMAND=true` / `"tools": {"runCommand": true}`
  once the token is set.
- **Publishing to the LAN** — change `127.0.0.1:7788:7788` to `7788:7788`
  only after setting a token, and prefer HTTPS (a reverse proxy or Fly's
  `force_https`) so the token isn't sent in the clear. An SSH tunnel or VPN
  to the localhost port is the simpler option.
- **Migrating from `web.host: 0.0.0.0`** — older configs and the old example
  file set this. The app now refuses to start with it unless a token is set;
  either add one or switch the host back to `127.0.0.1`.

## Environment variables

See [`deploy/local/.env.example`](../local/.env.example) — every key is
documented there. The only required one is a text-LLM key
(`HERANDHIM_DEEPSEEK_API_KEY`). Everything else (Telegram, Gemini vision, photo
selfies, Deepgram voice) is optional and degrades gracefully when unset.
