# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Email **wangchen2007915@gmail.com** with:
- a description of the issue and its impact,
- steps to reproduce (a PoC if you have one),
- any suggested fix.

You'll get an acknowledgment within 72 hours. Please give us a reasonable
window to ship a fix before public disclosure.

## Scope notes for self-hosters

HerAndHim stores intimate conversation data. If you run your own instance:

- Keep `HERANDHIM_HOME` on an encrypted disk; it contains the companion's
  long-term memory of your conversations.
- Never commit `.env` / `herandhim.json` — they hold your LLM keys and
  Telegram bot token. The repo's `.gitignore` already excludes them.
- Set `HERANDHIM_TELEGRAM_ALLOWED_USERS` so only your own Telegram account can
  talk to your bot; an open bot is an open door to your API budget.
- **The web dashboard is a control plane, not a viewer.** Anyone who reaches it
  can chat as you, read the companion's memory, rewrite the config (including
  the Telegram token) and, when the shell tool is enabled, run commands as the
  daemon's user. It is therefore loopback-only by default (`web.host` =
  `127.0.0.1`) and must be gated by `web.accessToken` /
  `HERANDHIM_WEB_ACCESS_TOKEN` for any other bind — the app refuses to start
  otherwise. Docker publishes the port to `127.0.0.1` only and always enforces
  a token (auto-generated when unset). Fly.io and any LAN/VPS deploy require
  one. Send it as `Authorization: Bearer …` from scripts; the browser keeps it
  as an HttpOnly cookie. Use HTTPS when the dashboard leaves your machine.
- **`run_command` is authorization-gated, not denylist-gated.** The command
  denylist in `herandhim/core/tools.py` is defence in depth against an LLM
  going off-script; it is not what keeps strangers out. The tool is withheld
  from the model (and refuses to execute) whenever the dashboard is not
  loopback-only, unless the operator opts in with `tools.runCommand: true`.
- The crisis-safety guardrail (`herandhim/core/safety.py`) and the image
  content guard (`herandhim/core/image_gen/guard.py`) ship **enabled and are
  not configuration-removable by design**. Forks that strip them are on
  their own, legally and morally.

## Supported versions

Only the latest release receives security fixes.
