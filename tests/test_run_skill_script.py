"""
run_skill_script: the narrow replacement for `run_command` on exposed installs.

After #58 the shell tool is off whenever the dashboard is not loopback-only —
which is every Docker / Fly install — so the bundled skills whose SKILL.md
runs a script went dark there. `run_skill_script` brings them back without a
shell. These tests pin the trust rules:

* bundled scripts (inside the package) run in every mode but "off";
* scripts authored into the install's own skills dir (create_skill,
  write_file) run only while `run_command` itself is available (loopback or
  explicit opt-in) — on an exposed install they are refused;
* argv list, never shell=True; same env scrubbing / timeout as run_command;
* nothing outside a skill directory can be executed.
"""

from __future__ import annotations

import json
import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from herandhim import config
from herandhim.core import tools

TOKEN = "correct-horse-battery-staple-7788"
EXPOSED = {"web": {"host": "0.0.0.0", "accessToken": TOKEN}}

BUNDLED = tools.bundled_skills_dir()
TIME_UTIL = os.path.join(BUNDLED, "system", "time", "time_util.py")
WRITE_IDENTITY = os.path.join(BUNDLED, "system", "onboarding", "write_identity.py")


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HERANDHIM_HOME", str(home))
    monkeypatch.setattr(config, "_HERANDHIM_BASE", home)
    for var in ("HERANDHIM_WEB_HOST", "HERANDHIM_WEB_ACCESS_TOKEN",
                "HERANDHIM_TOOLS_RUN_COMMAND", "HERANDHIM_TOOLS_RUN_SKILL_SCRIPT"):
        monkeypatch.delenv(var, raising=False)
    config._configs.clear()
    user_skills = home / "context" / "skills"
    user_skills.mkdir(parents=True)
    tools.set_sandbox([str(home)])
    tools.set_skill_script_roots([BUNDLED, str(user_skills)])
    yield home
    config._configs.clear()
    tools.set_sandbox([])
    tools.set_skill_script_roots([])


def _write_config(home, data: dict) -> None:
    path = home / "herandhim.json"
    path.write_text(json.dumps(data))
    config.load(str(path), force=True)


def _user_skills(home):
    return home / "context" / "skills"


def _make_user_skill(home, name="echo_args", body="import sys; print(repr(sys.argv[1:]))"):
    """A skill as create_skill would lay it out: <skills>/<name>/SKILL.md + script."""
    d = _user_skills(home) / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: test\n---\n")
    script = d / "script.py"
    script.write_text(body + "\n")
    return str(script)


def _bare_agent():
    from herandhim.core.agent import Agent
    a = Agent.__new__(Agent)
    a._web_search_enabled = False
    a.rag = None
    a._cron_manager = None
    a.verbose = False
    a.session_id = ""
    return a


def _tool_names(agent) -> set[str]:
    from herandhim.core.agent import Agent
    return {t["function"]["name"] for t in Agent._build_tools(agent)}


def _call(agent, name: str, **args) -> str:
    from herandhim.core.agent import Agent
    tc = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return Agent._execute_tool_call(agent, tc)


# ── Mode resolution ──────────────────────────────────────────────────────


def test_loopback_default_is_mode_all():
    assert config.run_command_enabled()
    assert config.skill_script_mode() == "all"


def test_exposed_default_is_mode_bundled(isolated_home):
    _write_config(isolated_home, EXPOSED)
    assert not config.run_command_enabled()
    assert config.skill_script_mode() == "bundled"


@pytest.mark.parametrize("value", [True, "true", "all", "on"])
def test_operator_can_opt_into_install_local_scripts_while_exposed(isolated_home, value):
    _write_config(isolated_home, {**EXPOSED, "tools": {"runSkillScript": value}})
    assert config.skill_script_mode() == "all"
    assert not config.run_command_enabled(), "the shell stays off — this is a narrower opt-in"


def test_run_command_opt_in_also_unlocks_install_local_scripts(isolated_home):
    _write_config(isolated_home, {**EXPOSED, "tools": {"runCommand": True}})
    assert config.skill_script_mode() == "all"


@pytest.mark.parametrize("value", [False, "false", "off", "0"])
def test_operator_can_switch_the_tool_off(isolated_home, value):
    _write_config(isolated_home, {"tools": {"runSkillScript": value}})
    assert config.skill_script_mode() == "off"
    assert not tools.run_skill_script_available()


def test_bundled_mode_can_be_forced_on_loopback(isolated_home):
    _write_config(isolated_home, {"tools": {"runSkillScript": "bundled"}})
    assert config.skill_script_mode() == "bundled"


def test_env_var_overrides_the_file(isolated_home, monkeypatch):
    _write_config(isolated_home, {"tools": {"runSkillScript": "all"}})
    monkeypatch.setenv("HERANDHIM_TOOLS_RUN_SKILL_SCRIPT", "false")
    assert config.skill_script_mode() == "off"


# ── What the model is offered ────────────────────────────────────────────


def test_exposed_install_offers_run_skill_script_but_not_run_command(isolated_home):
    """The Docker / Fly default: token-gated 0.0.0.0 bind, no shell opt-in."""
    _write_config(isolated_home, EXPOSED)
    names = _tool_names(_bare_agent())
    assert "run_skill_script" in names
    assert "run_command" not in names


def test_loopback_install_offers_both():
    names = _tool_names(_bare_agent())
    assert {"run_command", "run_skill_script"} <= names


def test_off_mode_withholds_the_schema_and_refuses(isolated_home):
    _write_config(isolated_home, {"tools": {"runSkillScript": False}})
    assert "run_skill_script" not in _tool_names(_bare_agent())
    with patch.object(tools.subprocess, "run") as run:
        assert tools.run_skill_script(TIME_UTIL, []) == tools.RUN_SKILL_SCRIPT_DISABLED_MSG
        run.assert_not_called()


def test_system_prompt_points_at_run_skill_script_when_the_shell_is_off(isolated_home):
    _write_config(isolated_home, EXPOSED)
    from herandhim.core.agent import Agent
    a = _bare_agent()
    a.skills_dirs = [BUNDLED]
    a.soul_instruction = a.persona_instruction = a.profile_instruction = ""
    a.calendar_instruction = a.tools_notes = ""
    a.MAX_PARALLEL_SKILLS = 3
    a.messages = []
    Agent._init_system_prompt(a)
    prompt = a.messages[0]["content"]
    assert "`run_skill_script`" in prompt
    assert "`run_command` is disabled" in prompt
    assert "skills that need to run a script are unavailable" not in prompt


def test_identity_api_lists_run_skill_script_without_run_command_when_exposed(isolated_home):
    _write_config(isolated_home, EXPOSED)
    from fastapi.testclient import TestClient

    from herandhim.web.app import create_app
    client = TestClient(create_app(None, host="0.0.0.0"))
    r = client.get("/api/identity", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["tools"]}
    assert "run_skill_script" in names
    assert "run_command" not in names


# ── Bundled scripts run on an exposed install (the Docker default) ──────


def test_bundled_script_really_runs_on_an_exposed_install(isolated_home):
    _write_config(isolated_home, EXPOSED)
    out = tools.run_skill_script(TIME_UTIL, ["--tz", "Asia/Tokyo"])
    assert not out.startswith("Error"), out
    assert "Asia/Tokyo" in out


@pytest.mark.parametrize("rel", [
    "media/selfie/take_selfie.py",
    "data/weather/weather.py",
    "media/tts/speak.py",
    "system/onboarding/write_identity.py",
])
def test_the_skills_the_readme_promises_are_allowed_while_exposed(isolated_home, rel):
    """selfie / weather / TTS / onboarding resolve as bundled and reach the
    interpreter (``--help`` exercises argparse without network or keys)."""
    _write_config(isolated_home, EXPOSED)
    script = os.path.join(BUNDLED, rel)
    assert tools._resolve_skill_script(script) == (os.path.realpath(script), "bundled")
    out = tools.run_skill_script(script, ["--help"])
    assert out.lstrip().lower().startswith("usage:"), out


def test_every_bundled_script_resolves_as_bundled(isolated_home):
    _write_config(isolated_home, EXPOSED)
    seen = 0
    for root, _dirs, files in os.walk(BUNDLED):
        for f in files:
            if f.endswith((".py", ".sh")):
                seen += 1
                assert tools._resolve_skill_script(os.path.join(root, f))[1] == "bundled", f
    assert seen >= 16


def test_onboarding_write_identity_writes_into_this_installs_home(isolated_home):
    """End to end on the exposed default: the onboarding skill writes SOUL.md
    into HERANDHIM_HOME (Docker sets HOME=/data, so ~/.herandhim is wrong)."""
    _write_config(isolated_home, EXPOSED)
    out = tools.run_skill_script(WRITE_IDENTITY, [
        "--type", "soul", "--user-name", "Chen", "--personality", "warm & teasing",
        "--focus", "daily life", "--language", "Chinese",
    ])
    assert out.startswith("Written:"), out
    soul = isolated_home / "context" / "soul" / "SOUL.md"
    assert soul.is_file()
    text = soul.read_text(encoding="utf-8")
    assert "Chen" in text
    assert "Chinese" in text
    assert not (isolated_home / ".herandhim").exists(), "must not fall back to ~/.herandhim"


def test_dispatcher_routes_run_skill_script_and_still_refuses_run_command(isolated_home):
    _write_config(isolated_home, EXPOSED)
    a = _bare_agent()
    out = _call(a, "run_skill_script", script=TIME_UTIL, args=["--unix"])
    assert not out.startswith("Error"), out
    assert "disabled" in _call(a, "run_command", command="python " + TIME_UTIL)


# ── create_skill-authored scripts: refused while exposed, fine on loopback ─


def test_create_skill_script_is_refused_while_exposed(isolated_home):
    _write_config(isolated_home, EXPOSED)
    result = tools.create_skill("pwn", "x", "y", resources={"pwn.py": "print('pwned')"})
    assert "will NOT run" in result
    script = _user_skills(isolated_home) / "pwn" / "pwn.py"
    assert script.is_file(), "create_skill itself still works — it is the execution that is gated"
    with patch.object(tools.subprocess, "run") as run:
        out = tools.run_skill_script(str(script), [])
        assert out == tools.RUN_SKILL_SCRIPT_UNTRUSTED_MSG
        run.assert_not_called()


def test_create_skill_with_a_category_is_refused_too(isolated_home):
    _write_config(isolated_home, EXPOSED)
    tools.create_skill("pwn", "x", "y", category="dev", resources={"run.sh": "echo pwned"})
    script = _user_skills(isolated_home) / "dev" / "pwn" / "run.sh"
    assert script.is_file()
    assert tools.run_skill_script(str(script)) == tools.RUN_SKILL_SCRIPT_UNTRUSTED_MSG


def test_write_file_authored_script_is_refused_while_exposed(isolated_home):
    """write_file can reach context/skills too — same rule."""
    _write_config(isolated_home, EXPOSED)
    d = _user_skills(isolated_home) / "sneaky"
    assert tools.write_file(str(d / "SKILL.md"), "---\nname: sneaky\n---\n").startswith("Written")
    assert tools.write_file(str(d / "go.py"), "print('pwned')").startswith("Written")
    assert tools.run_skill_script(str(d / "go.py")) == tools.RUN_SKILL_SCRIPT_UNTRUSTED_MSG


def test_create_skill_script_runs_on_loopback(isolated_home):
    assert config.skill_script_mode() == "all"
    result = tools.create_skill("hello", "x", "y", resources={"hello.py": "print('hi from skill')"})
    assert "will NOT run" not in result
    out = tools.run_skill_script(str(_user_skills(isolated_home) / "hello" / "hello.py"))
    assert out.strip() == "hi from skill"


def test_create_skill_script_runs_when_the_operator_opts_in_while_exposed(isolated_home):
    _write_config(isolated_home, {**EXPOSED, "tools": {"runSkillScript": True}})
    script = _make_user_skill(isolated_home, body="print('opted in')")
    assert tools.run_skill_script(script).strip() == "opted in"


def test_user_dir_copy_of_a_bundled_script_is_not_bundled(isolated_home):
    """`herandhim init` copies the templates into context/skills. Those copies
    are writable by the model, so they do not inherit the bundled trust."""
    _write_config(isolated_home, EXPOSED)
    import shutil
    dst = _user_skills(isolated_home) / "system" / "time"
    shutil.copytree(os.path.dirname(TIME_UTIL), dst)
    copy = str(dst / "time_util.py")
    assert tools._resolve_skill_script(copy)[1] == "user"
    assert tools.run_skill_script(copy) == tools.RUN_SKILL_SCRIPT_UNTRUSTED_MSG


# ── argv, not a shell ────────────────────────────────────────────────────


def test_arguments_are_argv_entries_not_a_shell_line(isolated_home):
    script = _make_user_skill(isolated_home)
    evil = "Tokyo; rm -rf / # $(whoami) `id` | cat /etc/passwd"
    out = tools.run_skill_script(script, [evil, "--flag", "two words"])
    assert out.strip() == repr([evil, "--flag", "two words"])


def test_subprocess_is_invoked_with_a_list_and_without_shell(isolated_home):
    with patch.object(tools.subprocess, "run") as run:
        run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
        assert tools.run_skill_script(TIME_UTIL, ["--tz", "UTC"]) == "ok\n"
    argv = run.call_args.args[0]
    assert isinstance(argv, list)
    assert argv[0] == tools._venv_python()
    assert argv[1:] == [os.path.realpath(TIME_UTIL), "--tz", "UTC"]
    assert run.call_args.kwargs["shell"] is False
    assert run.call_args.kwargs["timeout"] == tools.SKILL_SCRIPT_TIMEOUT == 60
    assert run.call_args.kwargs["cwd"] == str(config.files_dir())


def test_shell_scripts_run_under_bash_with_argv(isolated_home):
    d = _user_skills(isolated_home) / "sh_skill"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: sh_skill\n---\n")
    (d / "run.sh").write_text('printf "%s|" "$@"\n')
    out = tools.run_skill_script(str(d / "run.sh"), ["a b", "$HOME", "; echo no"])
    assert out == "a b|$HOME|; echo no|"


def test_a_single_string_arg_is_one_argument_not_split(isolated_home):
    script = _make_user_skill(isolated_home)
    assert tools.run_skill_script(script, "two words --flag").strip() == repr(["two words --flag"])


def test_numbers_are_stringified_and_nested_values_are_rejected(isolated_home):
    script = _make_user_skill(isolated_home)
    assert tools.run_skill_script(script, [1, 2.5, True]).strip() == repr(["1", "2.5", "true"])
    with patch.object(tools.subprocess, "run") as run:
        assert tools.run_skill_script(script, [["nested"]]).startswith("Error:")
        assert tools.run_skill_script(script, {"a": 1}).startswith("Error:")
        assert tools.run_skill_script(script, ["nul\x00byte"]).startswith("Error:")
        run.assert_not_called()


# ── Only files inside a skill directory ───────────────────────────────────


def test_scripts_outside_every_skill_dir_are_refused(isolated_home, tmp_path):
    stray = tmp_path / "stray.py"
    stray.write_text("print('no')")
    with patch.object(tools.subprocess, "run") as run:
        for path in (str(stray), "/etc/passwd", "/bin/sh", TIME_UTIL + "/../../../../core/tools.py"):
            out = tools.run_skill_script(path)
            assert out.startswith("Error:"), (path, out)
        run.assert_not_called()


def test_non_script_files_inside_a_skill_are_refused(isolated_home):
    skill_md = os.path.join(os.path.dirname(TIME_UTIL), "SKILL.md")
    with patch.object(tools.subprocess, "run") as run:
        assert "not a runnable skill script" in tools.run_skill_script(skill_md)
        run.assert_not_called()


def test_a_file_under_the_skills_root_but_in_no_skill_is_refused(isolated_home):
    loose = _user_skills(isolated_home) / "loose.py"
    loose.write_text("print('loose')")
    cat_level = _user_skills(isolated_home) / "cat"
    cat_level.mkdir()
    (cat_level / "CATEGORY.md").write_text("---\nname: cat\n---\n")
    (cat_level / "helper.py").write_text("print('cat')")
    for p in (loose, cat_level / "helper.py"):
        assert "not inside a skill directory" in tools.run_skill_script(str(p))


def test_scripts_subdirectory_per_agent_skills_spec_is_allowed(isolated_home):
    d = _user_skills(isolated_home) / "spec_skill"
    (d / "scripts").mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: spec_skill\n---\n")
    (d / "scripts" / "main.py").write_text("print('from scripts/')")
    assert tools.run_skill_script(str(d / "scripts" / "main.py")).strip() == "from scripts/"


def test_symlink_out_of_the_skill_dir_is_refused(isolated_home, tmp_path):
    target = tmp_path / "outside.py"
    target.write_text("print('escaped')")
    d = _user_skills(isolated_home) / "linky"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: linky\n---\n")
    (d / "run.py").symlink_to(target)
    with patch.object(tools.subprocess, "run") as run:
        assert tools.run_skill_script(str(d / "run.py")).startswith("Error:")
        run.assert_not_called()


def test_missing_script_is_reported_not_executed(isolated_home):
    with patch.object(tools.subprocess, "run") as run:
        out = tools.run_skill_script(os.path.join(os.path.dirname(TIME_UTIL), "nope.py"))
        assert "not found" in out
        run.assert_not_called()


def test_empty_script_path_is_refused(isolated_home):
    assert tools.run_skill_script("").startswith("Error:")
    assert tools.run_skill_script(None).startswith("Error:")  # type: ignore[arg-type]


# ── Environment scrubbing and timeout, as in run_command ─────────────────


def test_secrets_are_scrubbed_from_the_script_environment(isolated_home, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-leak")
    monkeypatch.setenv("HERANDHIM_DEEPSEEK_API_KEY", "sk-leak-2")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-leak")
    monkeypatch.setenv("HARMLESS_VAR", "stays")
    script = _make_user_skill(isolated_home, body=(
        "import os, json; print(json.dumps({k: os.environ.get(k) for k in "
        "['OPENAI_API_KEY', 'HERANDHIM_DEEPSEEK_API_KEY', 'TAVILY_API_KEY', 'HARMLESS_VAR', 'HERANDHIM_HOME']}))"
    ))
    env = json.loads(tools.run_skill_script(script))
    assert env["OPENAI_API_KEY"] is None
    assert env["HERANDHIM_DEEPSEEK_API_KEY"] is None
    assert env["TAVILY_API_KEY"] is None
    assert env["HARMLESS_VAR"] == "stays"
    assert env["HERANDHIM_HOME"] == str(isolated_home), "the per-install home is re-injected"


def test_timeout_is_reported_cleanly(isolated_home):
    with patch.object(tools.subprocess, "run", side_effect=subprocess.TimeoutExpired("x", 60)):
        out = tools.run_skill_script(TIME_UTIL)
    assert out == "Error: script timed out after 60s"


def test_nonzero_exit_surfaces_stderr(isolated_home):
    script = _make_user_skill(isolated_home, body="import sys; print('partial'); sys.exit('boom')")
    out = tools.run_skill_script(script)
    assert out.startswith("Error (exit 1):")
    assert "boom" in out


# ── The bundled directory cannot be edited by the agent ──────────────────


def test_write_tools_refuse_to_touch_the_package(isolated_home):
    """Bundled scripts are the trust anchor on an exposed install; a dev
    checkout under ~ would otherwise be inside the write sandbox."""
    tools.set_sandbox([str(isolated_home), os.path.dirname(tools._package_root())])
    target = os.path.join(BUNDLED, "system", "time", "time_util.py")
    before = open(target, encoding="utf-8").read()
    out = tools.write_file(target, "print('owned')")
    assert out.startswith("Blocked:")
    assert open(target, encoding="utf-8").read() == before
    with pytest.raises(PermissionError):
        tools._resolve_in_sandbox(os.path.join(BUNDLED, "new_skill", "x.py"))


# ── The bundled SKILL.md files no longer ask for a shell ─────────────────


def _bundled_skills_with_scripts():
    for root, _dirs, files in os.walk(BUNDLED):
        if "SKILL.md" in files and any(f.endswith((".py", ".sh")) for f in files):
            yield root


def test_every_bundled_skill_with_a_script_uses_run_skill_script():
    found = list(_bundled_skills_with_scripts())
    assert len(found) >= 15
    for skill_dir in found:
        text = open(os.path.join(skill_dir, "SKILL.md"), encoding="utf-8").read()
        assert "python {skill_path}/" not in text, skill_dir
        mentions_a_script = any(
            f in text for f in os.listdir(skill_dir) if f.endswith((".py", ".sh"))
        )
        if mentions_a_script:  # candid drives a direct tool, not its script
            assert "run_skill_script(" in text, skill_dir


def test_skill_md_tool_calls_parse_as_valid_argv_lists():
    """Every `run_skill_script(...)` example in a bundled SKILL.md names a
    script that exists and passes a JSON list of strings for args."""
    import re
    call_re = re.compile(r'run_skill_script\(\s*script="\{skill_path\}/([^"]+)"(?:,\s*args=(\[.*?\]))?\s*\)', re.S)
    seen = 0
    for skill_dir in _bundled_skills_with_scripts():
        text = open(os.path.join(skill_dir, "SKILL.md"), encoding="utf-8").read()
        for m in call_re.finditer(text):
            seen += 1
            script = m.group(1)
            assert os.path.isfile(os.path.join(skill_dir, script)), (skill_dir, script)
            if m.group(2):
                args = json.loads(m.group(2))
                assert all(isinstance(a, str) for a in args), (skill_dir, args)
    assert seen >= 40
