"""Access-token gate for the web dashboard.

The dashboard can drive the agent — and through it ``run_command`` — so
anything that is not loopback-only has to be gated.  The model is a single
shared secret (``web.accessToken`` / ``HERANDHIM_WEB_ACCESS_TOKEN``), not
user accounts:

* **Loopback bind, no token** — open, as before.  It is your machine.
* **Any token configured** — every ``/api/*`` route and ``/ws/chat`` require
  it, however the server is bound.
* **Non-loopback bind, no token** — refused at startup (``WebAuthError``).
  There is no way to run an unauthenticated dashboard on ``0.0.0.0``.

Clients present the token as ``Authorization: Bearer <token>`` or via the
``herandhim_access`` cookie that ``POST /api/access/unlock`` sets.  The cookie is
what the browser UI uses: it rides along on every ``fetch`` and on the
WebSocket handshake with no per-call plumbing.  A browser-origin check on
the WebSocket handshake stops other sites from driving a local dashboard
through the visitor's browser.
"""

from __future__ import annotations

import hmac
import logging
import os
from http.cookies import SimpleCookie
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

from .. import config

logger = logging.getLogger(__name__)

COOKIE_NAME = "herandhim_access"
COOKIE_MAX_AGE = 30 * 24 * 3600
WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_BAD_ORIGIN = 4403

# Reachable without a token: the shell that hosts the token prompt, and the
# endpoints the prompt itself needs.  Everything else under /api and /ws is
# gated when a token is configured.
_PUBLIC_EXACT = {"/", "/healthz", "/api/access/status", "/api/access/unlock", "/api/access/lock"}
_PUBLIC_PREFIXES = ("/static/",)


class WebAuthError(RuntimeError):
    """Raised when the configured bind would expose the dashboard unauthenticated."""


class WebAuth:
    """Token policy for one server instance."""

    def __init__(self, token: str, *, host: str):
        self.token = token
        self.host = host
        self.loopback = config.is_loopback_host(host)

    @classmethod
    def from_config(cls, host: str) -> "WebAuth":
        token = config.web_access_token()
        if not token and not config.is_loopback_host(host):
            raise WebAuthError(
                f"web.host is '{host}', which accepts connections from other machines, "
                "but no access token is set. The dashboard can run shell commands and "
                "read your memories and keys, so it refuses to start unauthenticated.\n"
                "  Either set web.accessToken in herandhim.json (or the "
                "HERANDHIM_WEB_ACCESS_TOKEN env var) to a long random secret,\n"
                "  or bind loopback only: web.host = \"127.0.0.1\" (the default)."
            )
        if token and len(token) < 16:
            logger.warning(
                "[Web] web.accessToken is only %d characters; use at least 16 random ones.",
                len(token),
            )
        return cls(token, host=host)

    @property
    def enforced(self) -> bool:
        return bool(self.token)

    # ── Credential checks ────────────────────────────────────────────────

    def matches(self, presented: str | None) -> bool:
        if not self.enforced or not presented:
            return False
        return hmac.compare_digest(presented.encode("utf-8"), self.token.encode("utf-8"))

    def authorized(self, headers: dict[bytes, bytes]) -> bool:
        """True if the request headers carry the token (Bearer or cookie)."""
        if not self.enforced:
            return True
        auth = headers.get(b"authorization", b"").decode("latin-1")
        if auth[:7].lower() == "bearer " and self.matches(auth[7:].strip()):
            return True
        raw_cookie = headers.get(b"cookie", b"").decode("latin-1")
        if raw_cookie:
            jar = SimpleCookie()
            try:
                jar.load(raw_cookie)
            except Exception:
                return False
            morsel = jar.get(COOKIE_NAME)
            if morsel is not None and self.matches(morsel.value):
                return True
        return False

    def request_authorized(self, request: Request) -> bool:
        return self.authorized(_header_map(request.scope))


# ── ASGI middleware ──────────────────────────────────────────────────────────

def _header_map(scope: dict) -> dict[bytes, bytes]:
    return {k.lower(): v for k, v in scope.get("headers") or []}


def _is_public(path: str) -> bool:
    return path in _PUBLIC_EXACT or path.startswith(_PUBLIC_PREFIXES)


def _allowed_origins() -> set[str]:
    raw = os.environ.get("HERANDHIM_ALLOWED_ORIGINS", "")
    return {o.strip().lower().rstrip("/") for o in raw.split(",") if o.strip()}


def websocket_origin_ok(headers: dict[bytes, bytes]) -> bool:
    """Reject browser WebSocket handshakes from other sites.

    Browsers always send ``Origin`` on a WebSocket handshake and a page on
    ``evil.example`` can open ``ws://localhost:7788/ws/chat`` with the
    visitor's cookies — there is no CORS for WebSockets.  The origin must
    match the ``Host`` the request arrived on, or be explicitly allowed via
    ``HERANDHIM_ALLOWED_ORIGINS``.  Non-browser clients send no ``Origin``
    and are judged by the token alone.
    """
    origin = headers.get(b"origin", b"").decode("latin-1").strip()
    if not origin:
        return True
    if origin.lower().rstrip("/") in _allowed_origins():
        return True
    origin_host = (urlsplit(origin).netloc or "").lower()
    request_host = headers.get(b"host", b"").decode("latin-1").strip().lower()
    return bool(origin_host) and origin_host == request_host


class AccessTokenMiddleware:
    """Gate ``/api/*`` and WebSocket routes behind :class:`WebAuth`.

    Pure ASGI so it covers WebSocket handshakes too — Starlette's HTTP-only
    ``@app.middleware("http")`` would leave ``/ws/chat`` open.
    """

    def __init__(self, app, auth: WebAuth):
        self.app = app
        self.auth = auth

    async def __call__(self, scope, receive, send):
        kind = scope.get("type")
        if kind not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        headers = _header_map(scope)
        path = scope.get("path", "")

        if kind == "websocket" and not websocket_origin_ok(headers):
            logger.warning("[Web] WebSocket handshake refused: cross-site origin %s",
                           headers.get(b"origin", b"").decode("latin-1"))
            await send({"type": "websocket.close", "code": WS_CLOSE_BAD_ORIGIN})
            return

        if not self.auth.enforced or (kind == "http" and _is_public(path)):
            return await self.app(scope, receive, send)

        if self.auth.authorized(headers):
            return await self.app(scope, receive, send)

        if kind == "websocket":
            # Closing before accept makes uvicorn answer the handshake with 403.
            await send({"type": "websocket.close", "code": WS_CLOSE_UNAUTHORIZED})
            return

        response = JSONResponse(
            {"ok": False, "error": "access token required", "authRequired": True},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
        await response(scope, receive, send)


# ── Unlock / status endpoints ─────────────────────────────────────────────────

def _request_is_https(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "")
    return request.url.scheme == "https" or forwarded.split(",")[0].strip().lower() == "https"


def make_access_routes(auth: WebAuth):
    """Return ``(status, unlock, lock)`` handlers bound to *auth*."""

    async def status(request: Request):
        return JSONResponse({
            "required": auth.enforced,
            "authenticated": (not auth.enforced) or auth.request_authorized(request),
            "loopback": auth.loopback,
        })

    async def unlock(request: Request):
        if not auth.enforced:
            return JSONResponse({"ok": True, "required": False})
        try:
            body = await request.json() if await request.body() else {}
        except Exception:
            body = {}
        presented = (body or {}).get("token", "")
        if not isinstance(presented, str) or not auth.matches(presented.strip()):
            logger.warning("[Web] Rejected access token from %s",
                           request.client.host if request.client else "?")
            return JSONResponse({"ok": False, "error": "wrong access token"}, status_code=401)
        resp = JSONResponse({"ok": True, "required": True})
        resp.set_cookie(
            COOKIE_NAME, auth.token,
            max_age=COOKIE_MAX_AGE, path="/",
            httponly=True, samesite="strict", secure=_request_is_https(request),
        )
        return resp

    async def lock(request: Request):
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE_NAME, path="/")
        return resp

    return status, unlock, lock


async def healthz():
    """Liveness probe for Fly / Docker — deliberately carries no state."""
    return JSONResponse({"ok": True})
