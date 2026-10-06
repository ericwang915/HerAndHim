"""The dashboard must not be reachable — let alone drive a shell — by anyone
who happens to share a network with it.

Before this, `web.host` defaulted to 0.0.0.0, the shipped Docker/Fly files
published the port on every interface, `/ws/chat` accepted every connection,
and the agent always carried `run_command` (shell=True behind a regex
denylist). These tests pin the replacement model:

* loopback by default, token optional there (local-first use stays free);
* any other bind refuses to start without `web.accessToken`;
* with a token, `/api/*` and `/ws/chat` reject callers that don't present it;
* `run_command` is withheld and refuses whenever the dashboard is not
  loopback-only, unless the operator opts in.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from herandhim import config

TOKEN = "correct-horse-battery-staple-7788"


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERANDHIM_HOME", str(tmp_path))
    monkeypatch.setattr(config, "_HERANDHIM_BASE", tmp_path)
    for var in ("HERANDHIM_WEB_HOST", "HERANDHIM_WEB_PORT", "HERANDHIM_WEB_ACCESS_TOKEN",
                "HERANDHIM_TOOLS_RUN_COMMAND", "HERANDHIM_ALLOWED_ORIGINS"):
        monkeypatch.delenv(var, raising=False)
    config._configs.clear()
    yield
    config._configs.clear()


def _write_config(tmp_path, data: dict) -> None:
    path = tmp_path / "herandhim.json"
    path.write_text(json.dumps(data))
    config.load(str(path), force=True)


def _client(host: str) -> TestClient:
    from herandhim.web.app import create_app
    return TestClient(create_app(None, host=host))


# ── Bind default ─────────────────────────────────────────────────────────


def test_dashboard_binds_loopback_unless_told_otherwise(tmp_path):
    assert config.web_host() == "127.0.0.1"
    assert config.web_is_loopback()

    _write_config(tmp_path, {"web": {"host": "0.0.0.0"}})
    assert config.web_host() == "0.0.0.0"
    assert not config.web_is_loopback()


def test_env_overrides_the_file_for_host_and_token(tmp_path, monkeypatch):
    _write_config(tmp_path, {"web": {"host": "0.0.0.0", "accessToken": "file-token-0123456"}})
    monkeypatch.setenv("HERANDHIM_WEB_HOST", "localhost")
    monkeypatch.setenv("HERANDHIM_WEB_ACCESS_TOKEN", "env-token-0123456789")
    assert config.web_host() == "localhost"
    assert config.web_access_token() == "env-token-0123456789"


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "localhost", "LOCALHOST", "::1", "[::1]"])
def test_loopback_detection_accepts_every_local_spelling(host):
    assert config.is_loopback_host(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10", "10.0.0.5", "myhost.lan", "", "   "])
def test_loopback_detection_rejects_anything_reachable_from_elsewhere(host):
    assert not config.is_loopback_host(host)


def test_example_config_and_wizard_default_to_loopback(tmp_path):
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    example = json.loads((root / "herandhim.example.json").read_text())
    assert example["web"]["host"] == "127.0.0.1"
    assert example["web"]["accessToken"] == ""

    from herandhim.onboard import _save_config
    out = _save_config({"llm": {"provider": "ollama"}}, str(tmp_path / "wizard.json"))
    assert json.loads(out.read_text())["web"]["host"] == "127.0.0.1"


# ── Fail closed ──────────────────────────────────────────────────────────


def test_non_loopback_bind_without_a_token_refuses_to_start():
    from herandhim.web.access import WebAuthError
    from herandhim.web.app import create_app

    with pytest.raises(WebAuthError, match="no access token"):
        create_app(None, host="0.0.0.0")
    with pytest.raises(WebAuthError):
        create_app(None, host="192.168.1.10")


def test_non_loopback_bind_with_a_token_starts(monkeypatch):
    monkeypatch.setenv("HERANDHIM_WEB_ACCESS_TOKEN", TOKEN)
    app_client = _client("0.0.0.0")
    assert app_client.app.state.auth.enforced


def test_start_command_exits_instead_of_serving_unauthenticated(tmp_path, monkeypatch):
    """`herandhim start` on a 0.0.0.0 config must die with a message, not bind."""
    from herandhim import main as hh_main

    _write_config(tmp_path, {"web": {"host": "0.0.0.0", "port": 7788}})
    monkeypatch.setattr(hh_main, "_build_provider", lambda: None)
    uvicorn_run = MagicMock()
    monkeypatch.setattr("uvicorn.run", uvicorn_run)

    with pytest.raises(SystemExit) as exc:
        hh_main._run_foreground(MagicMock(config=None))
    assert exc.value.code == 2
    uvicorn_run.assert_not_called()


# ── Loopback without a token: local-first stays open ─────────────────────


def test_loopback_without_a_token_is_open_as_before():
    c = _client("127.0.0.1")
    assert c.get("/api/status").status_code == 200
    assert c.get("/api/access/status").json() == {"required": False, "authenticated": True, "loopback": True}
    with c.websocket_connect("/ws/chat"):
        pass
    # Unlock is a no-op rather than an error, so a UI that always calls it works.
    assert c.post("/api/access/unlock", json={"token": "anything"}).json() == {"ok": True, "required": False}


def test_loopback_with_a_token_enforces_it(monkeypatch):
    """Opting in locally is honoured — the token is not loopback-only."""
    monkeypatch.setenv("HERANDHIM_WEB_ACCESS_TOKEN", TOKEN)
    c = _client("127.0.0.1")
    assert c.get("/api/status").status_code == 401
    assert c.get("/api/status", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200


# ── Token-gated server ───────────────────────────────────────────────────


@pytest.fixture
def gated(monkeypatch):
    monkeypatch.setenv("HERANDHIM_WEB_ACCESS_TOKEN", TOKEN)
    return _client("0.0.0.0")


SENSITIVE_GETS = ["/api/status", "/api/config", "/api/identity", "/api/memories", "/api/memory/index",
                  "/api/identity/tools", "/api/files", "/api/chat/history", "/api/user/telegram",
                  "/api/setup/companion", "/api/tools", "/api/sanctum/photos", "/api/channels"]
SENSITIVE_POSTS = ["/api/config", "/api/identity/soul", "/api/identity/persona", "/api/identity/tools",
                   "/api/memory/index", "/api/user/telegram", "/api/setup/companion", "/api/files/clear",
                   "/api/channels/restart", "/api/transcribe", "/api/tools/tavily/connect"]


@pytest.mark.parametrize("path", SENSITIVE_GETS)
def test_api_reads_need_the_token(gated, path):
    r = gated.get(path)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert r.json()["authRequired"] is True


@pytest.mark.parametrize("path", SENSITIVE_POSTS)
def test_api_mutations_need_the_token(gated, path):
    assert gated.post(path, json={"config": {}, "content": "x", "token": ""}).status_code == 401


def test_delete_needs_the_token_too(gated):
    assert gated.delete("/api/tools/tavily").status_code == 401


def test_unauthenticated_config_save_changes_nothing(gated, tmp_path):
    before = config.as_dict()
    r = gated.post("/api/config", json={"config": {"llm": {"provider": "pwned"}}})
    assert r.status_code == 401
    assert not (tmp_path / "herandhim.json").exists()
    assert config.as_dict() == before


def test_unauthenticated_memory_and_identity_writes_change_nothing(gated, tmp_path):
    for path in ("/api/memory/index", "/api/identity/soul", "/api/identity/persona"):
        assert gated.post(path, json={"content": "injected"}).status_code == 401
    assert not (tmp_path / "context").exists()


def test_bearer_header_unlocks_the_api(gated):
    r = gated.get("/api/status", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200
    assert gated.get("/api/status", headers={"Authorization": f"Bearer {TOKEN}x"}).status_code == 401
    assert gated.get("/api/status", headers={"Authorization": f"Bearer {TOKEN[:-1]}"}).status_code == 401
    assert gated.get("/api/status", headers={"Authorization": TOKEN}).status_code == 401


def test_unlock_sets_an_httponly_cookie_that_unlocks_everything(gated):
    assert gated.get("/api/access/status").json()["authenticated"] is False

    bad = gated.post("/api/access/unlock", json={"token": "nope"})
    assert bad.status_code == 401
    assert "set-cookie" not in bad.headers

    good = gated.post("/api/access/unlock", json={"token": TOKEN})
    assert good.status_code == 200
    cookie = good.headers["set-cookie"].lower()
    assert "herandhim_access=" in cookie and "httponly" in cookie and "samesite=strict" in cookie

    # The client keeps the cookie from here on.
    assert gated.get("/api/access/status").json()["authenticated"] is True
    assert gated.get("/api/status").status_code == 200
    with gated.websocket_connect("/ws/chat"):
        pass

    gated.post("/api/access/lock")
    assert gated.get("/api/status").status_code == 401


def test_unlock_cookie_is_secure_when_served_over_https(gated):
    r = gated.post("/api/access/unlock", json={"token": TOKEN}, headers={"X-Forwarded-Proto": "https"})
    assert "secure" in r.headers["set-cookie"].lower()


def test_websocket_without_the_token_is_refused_before_accept(gated):
    with pytest.raises(WebSocketDisconnect) as exc:
        with gated.websocket_connect("/ws/chat"):
            pass
    assert exc.value.code == 4401

    with pytest.raises(WebSocketDisconnect):
        with gated.websocket_connect("/ws/chat", headers={"Authorization": f"Bearer {TOKEN}x"}):
            pass


def test_websocket_with_bearer_or_cookie_connects(gated):
    with gated.websocket_connect("/ws/chat", headers={"Authorization": f"Bearer {TOKEN}"}):
        pass
    with gated.websocket_connect("/ws/chat", headers={"Cookie": f"herandhim_access={TOKEN}"}):
        pass


def test_shell_and_probe_stay_reachable_without_the_token(gated):
    """The page that hosts the token prompt, its assets, and the Fly health
    check must work before the user has unlocked anything — and must not
    carry anything worth protecting."""
    assert gated.get("/").status_code == 200
    assert gated.get("/healthz").json() == {"ok": True}
    assert gated.get("/api/access/status").status_code == 200
    assert gated.get("/static/logo.png").status_code == 200


def test_unknown_paths_are_gated_too(gated):
    assert gated.get("/api/does-not-exist").status_code == 401
    assert gated.get("/docs").status_code == 401


# ── Browser-origin check on the socket ───────────────────────────────────


def test_cross_site_browser_cannot_open_the_chat_socket(monkeypatch):
    """No CORS for WebSockets: a page on another site can open
    ws://localhost:7788/ws/chat with the visitor's cookies. The Origin must
    match the Host the request came in on."""
    c = _client("127.0.0.1")                               # even on an open local install
    with pytest.raises(WebSocketDisconnect) as exc:
        with c.websocket_connect("/ws/chat", headers={"Origin": "http://evil.example"}):
            pass
    assert exc.value.code == 4403
    with c.websocket_connect("/ws/chat", headers={"Origin": "http://testserver"}):
        pass

    monkeypatch.setenv("HERANDHIM_ALLOWED_ORIGINS", "https://dash.example.com")
    with c.websocket_connect("/ws/chat", headers={"Origin": "https://dash.example.com"}):
        pass


# ── run_command gating ───────────────────────────────────────────────────


def _bare_agent():
    from herandhim.core.agent import Agent
    a = Agent.__new__(Agent)
    a._web_search_enabled = False
    a.rag = None
    a._cron_manager = None
    return a


def _tool_names(agent) -> set[str]:
    from herandhim.core.agent import Agent
    return {t["function"]["name"] for t in Agent._build_tools(agent)}


def test_run_command_is_offered_on_a_loopback_install():
    assert config.run_command_enabled()
    assert "run_command" in _tool_names(_bare_agent())


def test_run_command_is_withheld_when_the_dashboard_is_network_exposed(tmp_path):
    _write_config(tmp_path, {"web": {"host": "0.0.0.0", "accessToken": TOKEN}})
    assert not config.run_command_enabled()
    names = _tool_names(_bare_agent())
    assert "run_command" not in names
    assert {"read_file", "write_file", "send_file", "use_skill", "remember"} <= names


def test_run_command_refuses_to_execute_when_withheld(tmp_path, monkeypatch):
    """The schema is gone, but a model can still emit the call by name — the
    implementation itself must refuse, before the denylist, before shell=True."""
    from herandhim.core import tools

    _write_config(tmp_path, {"web": {"host": "0.0.0.0", "accessToken": TOKEN}})
    run = MagicMock()
    monkeypatch.setattr(tools.subprocess, "run", run)
    out = tools.run_command("echo hi")
    assert out == tools.RUN_COMMAND_DISABLED_MSG
    run.assert_not_called()

    # …and the dispatcher routes a hallucinated call to that refusal.
    from herandhim.core.agent import Agent
    a = _bare_agent()
    a.verbose = False
    tc = MagicMock()
    tc.function.name = "run_command"
    tc.function.arguments = '{"command": "cat /data/herandhim.json"}'
    assert "disabled" in Agent._execute_tool_call(a, tc)
    run.assert_not_called()


def test_run_command_runs_when_allowed(monkeypatch):
    from herandhim.core import tools
    with patch.object(tools.subprocess, "run") as run:
        run.return_value = MagicMock(returncode=0, stdout="hi\n", stderr="")
        assert tools.run_command("echo hi") == "hi\n"
        assert run.call_args.kwargs["shell"] is True


@pytest.mark.parametrize("value", [True, "true", "on", "1"])
def test_operator_can_opt_in_on_an_exposed_install(tmp_path, value):
    _write_config(tmp_path, {"web": {"host": "0.0.0.0", "accessToken": TOKEN}, "tools": {"runCommand": value}})
    assert config.run_command_enabled()
    assert "run_command" in _tool_names(_bare_agent())


@pytest.mark.parametrize("value", [False, "false", "off", "0"])
def test_operator_can_switch_it_off_even_on_loopback(tmp_path, value):
    _write_config(tmp_path, {"tools": {"runCommand": value}})
    assert not config.run_command_enabled()
    assert "run_command" not in _tool_names(_bare_agent())


def test_env_var_opt_in_wins_over_auto(tmp_path, monkeypatch):
    _write_config(tmp_path, {"web": {"host": "0.0.0.0", "accessToken": TOKEN}})
    monkeypatch.setenv("HERANDHIM_TOOLS_RUN_COMMAND", "true")
    assert config.run_command_enabled()


def test_identity_api_hides_the_withheld_tool(gated, tmp_path):
    _write_config(tmp_path, {"web": {"host": "0.0.0.0", "accessToken": TOKEN}})
    r = gated.get("/api/identity", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200
    assert "run_command" not in {t["name"] for t in r.json()["tools"]}


def test_token_never_leaks_through_the_config_api(gated):
    r = gated.get("/api/config", headers={"Authorization": f"Bearer {TOKEN}"})
    assert TOKEN not in json.dumps(r.json())
