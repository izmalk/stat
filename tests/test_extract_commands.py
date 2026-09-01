# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for extract_commands.py.

Golden files under tests/golden/ hold the expected generated script for each
fixture in tests/fixtures/. To regenerate a golden file intentionally:

    python3 tests/regen_golden.py <fixture-name>

Run the suite with:

    pytest tests/
"""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
EXTRACT = REPO_ROOT / "extract_commands.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLDEN = Path(__file__).resolve().parent / "golden"


def _load_module():
    spec = importlib.util.spec_from_file_location("extract_commands", EXTRACT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ec = _load_module()


def _fixture(name: str) -> str:
    return (FIXTURES / f"{name}.md").read_text(encoding="utf-8")


def _golden(name: str) -> str:
    return (GOLDEN / f"{name}.sh").read_text(encoding="utf-8")


def _blocks(name: str) -> list[str]:
    return ec.extract_shell_blocks(_fixture(name))


def _body(script: str) -> str:
    """Strip the generated header, keeping only the extracted blocks."""
    marker = '. "$HELPERS"\n'
    return script.split(marker, 1)[1].lstrip("\n")


# ---------------------------------------------------------------------------
# Golden comparisons per fixture
# ---------------------------------------------------------------------------

GOLDEN_CASES = [
    "skip-basic",
    "skip-cancelled-by-text",
    "skip-not-cancelled-by-annotation",
    "wait",
    "await-idle-defaults",
    "await-idle-args",
    "retry-simple",
    "retry-defaults",
    "run-with-timeout",
    "set-variables",
    "run-hidden",
    "assert",
    "non-shell-fences",
    "heading-in-fence",
    "unterminated-fence",
    "multi-annotation-page",
]


@pytest.mark.parametrize("name", GOLDEN_CASES)
def test_golden_script(name: str):
    blocks = _blocks(name)
    script = ec.build_script(FIXTURES / f"{name}.md", blocks)
    assert _body(script) == _body(_golden(name))


def test_golden_header_invariants():
    script = ec.build_script(FIXTURES / "wait.md", _blocks("wait"))
    assert script.startswith("#!/bin/bash\n")
    assert "set -euo pipefail" in script
    assert 'HELPERS="${SPREAD_PATH:-$(cd "$(dirname "$0")" && pwd)}/helpers.sh"' in script
    assert '. "$HELPERS"' in script
    # Header paths must be relative, not absolute local paths.
    assert "# Extracted from : tests/fixtures/wait.md" in script


# ---------------------------------------------------------------------------
# Annotation semantics
# ---------------------------------------------------------------------------


def test_skip_basic():
    assert _blocks("skip-basic") == ["echo kept"]


def test_skip_cancelled_by_text():
    assert _blocks("skip-cancelled-by-text") == ["echo kept"]


def test_skip_not_cancelled_by_annotation():
    # An intervening annotation does NOT cancel the skip (by design): the
    # annotation's own effect (the sleep) is still emitted, but the following
    # shell block remains skipped.
    assert _blocks("skip-not-cancelled-by-annotation") == ["sleep 5", "echo kept"]


def test_wait():
    assert _blocks("wait") == ["sleep 5", "echo done"]


def test_await_idle_defaults():
    assert _blocks("await-idle-defaults") == [
        "wait_idle --timeout 1200 --interval 30",
        "echo done",
    ]


def test_await_idle_args():
    assert _blocks("await-idle-args") == [
        "wait_idle --timeout 900 --interval 30 --allow-blocked my-app,data-integrator",
        "echo done",
    ]


def test_retry_simple():
    assert _blocks("retry-simple") == [
        "retry_until_success --timeout 600 --interval 60"
        " --description 'wait for endpoint'"
        " -- curl -sf http://localhost:8080/health"
    ]


def test_retry_defaults():
    assert _blocks("retry-defaults") == [
        "retry_until_success --timeout 1200 --interval 120 --description command"
        " -- curl -sf http://localhost:8080/health"
    ]


def test_run_with_timeout():
    assert _blocks("run-with-timeout") == [
        "( timeout 120 bash << 'TUTORIAL_TIMEOUT_EOF'\n"
        "my-app rebuild-index\n"
        "TUTORIAL_TIMEOUT_EOF\n) || true"
    ]


def test_set_variables():
    assert _blocks("set-variables") == [
        "_CMD_OUTPUT=$(juju run my-app/leader get-credentials)\n"
        "MY_USER=$(echo \"$_CMD_OUTPUT\" | grep 'username:' | awk '{print $2}')\n"
        "MY_PASS=$(echo \"$_CMD_OUTPUT\" | grep 'password:' | awk '{print $2}')",
        "my-cli login --user ${MY_USER} --password ${MY_PASS}",
    ]


def test_run_hidden():
    assert _blocks("run-hidden") == ["juju config my-app debug-mode=true", "echo visible"]


def test_assert():
    assert _blocks("assert") == [
        "# --- Test assertion ---\n"
        "juju status --format json | jq -e"
        ' \'.applications."my-app".application-status.current == "active"\''
    ]


def test_non_shell_fences_ignored():
    assert _blocks("non-shell-fences") == ["echo extracted"]


def test_unterminated_fence_consumed_to_eof():
    # The block runs to EOF; the trailing newline of the file is captured too.
    assert _blocks("unterminated-fence") == ["echo one\necho two\n"]


def test_retry_shell_pipeline():
    source = (
        "# Retry shell\n\n"
        "<!-- test:retry --shell -- curl -sf http://localhost:8080/health"
        " | grep -q ok -->\n"
    )
    (blocks,) = ec.extract_shell_blocks(source)
    assert blocks == (
        "retry_until_success --timeout 1200 --interval 120 --description command"
        " -- bash -c 'curl -sf http://localhost:8080/health | grep -q ok'"
    )


def test_unknown_option_warns(capsys):
    ec.extract_shell_blocks("<!-- test:await-idle --timout 900 -->\n")
    captured = capsys.readouterr()
    assert "unknown option '--timout'" in captured.err


def test_unknown_option_strict_exits(monkeypatch, capsys):
    monkeypatch.setattr(ec, "_strict", True)
    with pytest.raises(SystemExit, match="unknown option '--timout'"):
        ec.extract_shell_blocks("<!-- test:await-idle --timout 900 -->\n")


def test_bad_integer_exits():
    with pytest.raises(SystemExit, match="--timeout"):
        ec.extract_shell_blocks("<!-- test:await-idle --timeout abc -->\n")


def test_await_idle_typo_not_matched():
    # test:await-idleXYZ must not be recognised as an await-idle annotation.
    assert ec.extract_shell_blocks("<!-- test:await-idleXYZ -->\n") == []


def test_skip_no_spaces_recognised():
    assert ec.extract_shell_blocks("<!--test:skip-->\n\n```shell\necho x\n```\n") == []


# ---------------------------------------------------------------------------
# Metadata / heading extraction
# ---------------------------------------------------------------------------


def test_extract_spread_meta():
    meta = ec.extract_spread_meta(_fixture("spread-meta"))
    assert meta == {"priority": "600", "kill-timeout": "60m"}


def test_extract_spread_meta_missing():
    assert ec.extract_spread_meta(_fixture("no-spread-meta")) == {}


def test_extract_spread_meta_ignores_fenced_sample():
    source = "# Page\n\n```text\n<!-- test:spread\npriority: 999\n-->\n```\n"
    assert ec.extract_spread_meta(source) == {}


def test_extract_heading():
    assert ec.extract_heading(_fixture("spread-meta")) == "Spread meta page"


def test_extract_heading_ignores_fenced():
    assert ec.extract_heading(_fixture("heading-in-fence")) == "Real heading"


def test_extract_heading_missing():
    assert ec.extract_heading("No heading here.\n") == ""


# ---------------------------------------------------------------------------
# task.yaml generation
# ---------------------------------------------------------------------------


def test_build_task_yaml_defaults():
    assert ec.build_task_yaml("My task", {}) == (
        'summary: "My task"\n'
        "priority: 0\n"
        "kill-timeout: 30m\n"
        "execute: |\n"
        '  bash "$SPREAD_PATH/$SPREAD_TASK.sh"\n'
    )


def test_build_task_yaml_uses_spread_task():
    # Portability contract: never hardcode the script path.
    yaml_text = ec.build_task_yaml("t", {"priority": "100", "kill-timeout": "1h"})
    assert "$SPREAD_PATH/$SPREAD_TASK.sh" in yaml_text


def test_build_task_yaml_escapes_summary():
    yaml_text = ec.build_task_yaml('Deploy "my-app" \\ the quoted heading', {})
    loaded = yaml.safe_load(yaml_text)
    assert loaded["summary"] == 'Deploy "my-app" \\ the quoted heading'


def test_build_task_yaml_rejects_bad_priority():
    with pytest.raises(SystemExit, match="priority"):
        ec.build_task_yaml("t", {"priority": "abc"})


def test_build_task_yaml_rejects_bad_kill_timeout():
    with pytest.raises(SystemExit, match="kill-timeout"):
        ec.build_task_yaml("t", {"kill-timeout": "soon"})


def test_build_task_yaml_accepts_valid_kill_timeouts():
    for value in ("30s", "30m", "1h", "1.5h"):
        ec.build_task_yaml("t", {"kill-timeout": value})  # must not raise


# ---------------------------------------------------------------------------
# CLI end-to-end
# ---------------------------------------------------------------------------


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(EXTRACT), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_cli_stdout_mode():
    result = _run(str(FIXTURES / "wait.md"))
    assert result.returncode == 0
    assert "sleep 5" in result.stdout
    assert "set -euo pipefail" in result.stdout


def test_cli_help_exits_zero():
    result = _run("--help")
    assert result.returncode == 0
    assert "usage:" in result.stdout


def test_cli_no_args_exits_nonzero():
    result = _run()
    assert result.returncode != 0


def test_cli_lone_directory_clear_error(tmp_path):
    result = _run(str(tmp_path))
    assert result.returncode != 0
    assert "is a directory" in result.stderr


def test_cli_odd_args_error():
    result = _run("a.md", "b.sh", "c.md")
    assert result.returncode != 0
    assert "pairs" in result.stderr


def test_cli_pair_mode(tmp_path):
    out = tmp_path / "spread-meta.sh"
    result = _run(str(FIXTURES / "spread-meta.md"), str(out))
    assert result.returncode == 0
    assert out.exists()
    task_yaml = tmp_path / "spread-meta" / "task.yaml"
    assert task_yaml.exists()
    loaded = yaml.safe_load(task_yaml.read_text())
    assert loaded["priority"] == 600
    assert loaded["kill-timeout"] == "60m"
    assert "$SPREAD_TASK" in loaded["execute"]


def test_cli_pair_mode_requires_spread_meta(tmp_path):
    out = tmp_path / "no-meta.sh"
    result = _run(str(FIXTURES / "no-spread-meta.md"), str(out))
    assert result.returncode != 0
    assert "no spread metadata" in result.stderr
    assert not out.exists()


def test_cli_discovery_mode(tmp_path):
    out_dir = tmp_path / "tasks"
    result = _run(str(FIXTURES), str(out_dir))
    assert result.returncode == 0
    # Only fixtures with spread metadata are processed.
    assert (out_dir / "spread-meta.sh").exists()
    assert (out_dir / "multi-annotation-page.sh").exists()
    assert not (out_dir / "no-spread-meta.sh").exists()
    assert not (out_dir / "wait.sh").exists()


def test_cli_check_mode(tmp_path):
    out_dir = tmp_path / "tasks"
    # Generate, then check passes.
    assert _run(str(FIXTURES), str(out_dir)).returncode == 0
    result = _run("--check", str(FIXTURES), str(out_dir))
    assert result.returncode == 0
    assert "up to date" in result.stdout

    # Touch a fixture: check must fail without rewriting anything.
    fixture = tmp_path / "copy" / "spread-meta.md"
    fixture.parent.mkdir()
    fixture.write_text(
        "# Spread meta page\n\n<!-- test:spread\npriority: 700\n-->\n\n"
        "```shell\necho changed\n```\n"
    )
    before = (out_dir / "spread-meta.sh").read_text()
    result = _run("--check", str(fixture.parent), str(out_dir))
    assert result.returncode == 1
    assert "Out of date" in result.stdout
    assert (out_dir / "spread-meta.sh").read_text() == before


def test_cli_strict_flag(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text(
        "# Bad\n\n<!-- test:spread\npriority: 1\n-->\n\n<!-- test:await-idle --timout 900 -->\n"
    )
    out_dir = tmp_path / "tasks"
    result = _run("--strict", str(bad.parent), str(out_dir))
    assert result.returncode != 0
    assert "--timout" in result.stderr


# ---------------------------------------------------------------------------
# Generated scripts are valid bash
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", GOLDEN_CASES)
def test_generated_script_is_valid_bash(name: str):
    script = ec.build_script(FIXTURES / f"{name}.md", _blocks(name))
    result = subprocess.run(["bash", "-n"], input=script, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_examples_generate_valid_bash(tmp_path):
    out_dir = tmp_path / "tasks"
    result = _run(str(REPO_ROOT / "examples"), str(out_dir))
    assert result.returncode == 0
    for sh in out_dir.glob("*.sh"):
        check = subprocess.run(["bash", "-n", str(sh)], capture_output=True)
        assert check.returncode == 0, sh


# ---------------------------------------------------------------------------
# helpers.sh sanity
# ---------------------------------------------------------------------------


def test_helpers_sh_sources_cleanly():
    result = subprocess.run(["bash", "-n", str(REPO_ROOT / "helpers.sh")], capture_output=True)
    assert result.returncode == 0


def test_collect_diagnostics_writes_files(tmp_path):
    """collect_diagnostics must succeed even when juju is unavailable."""
    script = f"""
. "{REPO_ROOT / "helpers.sh"}"
collect_diagnostics --dir "{tmp_path / "diag"}"
"""
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "diag" / "free.txt").exists()
    assert (tmp_path / "diag" / "df.txt").exists()


def test_wait_idle_unknown_option():
    script = f"""
. "{REPO_ROOT / "helpers.sh"}"
wait_idle --bogus 2>/dev/null
"""
    result = subprocess.run(["bash", "-c", script], capture_output=True)
    assert result.returncode == 1


def test_retry_until_success_unknown_option():
    script = f"""
. "{REPO_ROOT / "helpers.sh"}"
retry_until_success --bogus -- true 2>/dev/null
"""
    result = subprocess.run(["bash", "-c", script], capture_output=True)
    assert result.returncode == 1


def test_retry_until_success_no_command():
    script = f"""
. "{REPO_ROOT / "helpers.sh"}"
retry_until_success --timeout 1 --interval 1 -- 2>/dev/null
"""
    result = subprocess.run(["bash", "-c", script], capture_output=True)
    assert result.returncode == 1


# Keep shutil import used (regen helper reference); avoids lint noise if the
# helper script moves.
_ = shutil
