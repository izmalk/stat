#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Extract shell code blocks from MyST Markdown tutorial files.

Usage
-----
    # Auto-discover: process all .md files with spread metadata in a directory.
    python3 extract_commands.py docs/tutorial/ tests/tutorial/tasks/

    # Explicit pairs: one or more <input.md> <output.sh> pairs.
    python3 extract_commands.py docs/tutorial/environment.md \
        tests/tutorial/tasks/environment.sh

    # Print to stdout (no output file argument)
    python3 extract_commands.py docs/tutorial/environment.md

    # Verify generated files are up to date (writes nothing; exits 1 when stale).
    python3 extract_commands.py --check docs/tutorial/ tests/tutorial/tasks/

    # Treat extraction warnings (e.g. misspelled annotation options) as errors.
    python3 extract_commands.py --strict docs/tutorial/ tests/tutorial/tasks/

What gets extracted
-------------------
Only fenced code blocks whose opening fence is exactly:

    ```shell

Any other language tag (``bash``, ``text``, ``console``, etc.) is ignored.

Annotations
-----------
Annotations are HTML comments placed before or between fenced code blocks.
They control how blocks are extracted and what additional commands are emitted.
See README.md for full reference.
"""

import argparse
import json
import os
import re
import shlex
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

_SKIP_PATTERN = re.compile(r"<!--\s*test:skip\s*-->")
_SLEEP_PATTERN = re.compile(r"<!--\s*test:wait\s+--seconds\s+(\d+)\s*-->")
_AWAIT_IDLE_PATTERN = re.compile(r"<!--\s*test:await-idle(\s[^>]*?)?\s*-->")
_RETRY_PATTERN = re.compile(r"<!--\s*test:retry\s+(.*?)-->")
_RUN_WITH_TIMEOUT_PATTERN = re.compile(r"<!--\s*test:run-with-timeout\s+--seconds\s+(\d+)\s*-->")
_SET_VARIABLES_START = re.compile(r"<!--\s*test:set-variables\s*$")
_RUN_HIDDEN_START = re.compile(r"<!--\s*test:run\s*$")
_ASSERT_START = re.compile(r"<!--\s*test:assert\s*$")
_SPREAD_META_START = re.compile(r"<!--\s*test:spread\s*$")
_SHELL_OPEN = re.compile(r"^```shell\s*$")
_FENCE_CLOSE = re.compile(r"^```\s*$")
# Any fenced block (``` or ~~~), used to skip fenced content when scanning
# for headings and spread metadata outside the main extraction loop.
_FENCE_LINE = re.compile(r"^\s*(```|~~~)")
_KILL_TIMEOUT_PATTERN = re.compile(r"^\d+(\.\d+)?[smh]$")

# Set by main() from the --strict flag: warnings become fatal errors.
_strict = False


def _warn(message: str) -> None:
    """Print *message* as a warning; exit when strict mode is enabled."""
    if _strict:
        sys.exit(f"Error: {message}")
    print(f"Warning: {message}", file=sys.stderr)


def _int_value(annotation: str, option: str, value: str) -> int:
    """Return *value* as an integer, exiting with a clear error otherwise."""
    try:
        return int(value)
    except ValueError:
        sys.exit(f"Error: {annotation}: {option} expects an integer, got {value!r}")


def _display_path(path: Path) -> str:
    """Return *path* relative to the current directory when possible.

    Keeps the generated file header reproducible regardless of where the
    repository is checked out.
    """
    try:
        return os.path.relpath(path)
    except ValueError:  # e.g. a different drive on Windows
        return str(path)


def _iter_unfenced_lines(source: str) -> Iterator[str]:
    """Yield lines of *source* that are outside fenced code blocks."""
    fenced = False
    for line in source.splitlines():
        if _FENCE_LINE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            yield line


def _build_retry_command(args_str: str) -> str:
    """Build a ``retry_until_success`` call from ``helpers.sh``.

    Parses the inline arguments from a ``<!-- test:retry ... -->`` annotation
    and returns a shell command that calls ``retry_until_success``.

    By default every command token is shell-quoted, so the command cannot
    contain pipes or redirects. Pass ``--shell`` to run the command through
    ``bash -c`` instead, which allows full shell syntax.
    """
    timeout = 1200
    interval = 120
    description = "command"
    use_shell = False
    command_parts: list[str] = []

    tokens = shlex.split(args_str) if args_str.strip() else []
    i = 0
    while i < len(tokens):
        if tokens[i] == "--timeout" and i + 1 < len(tokens):
            timeout = _int_value("test:retry", "--timeout", tokens[i + 1])
            i += 2
        elif tokens[i] == "--interval" and i + 1 < len(tokens):
            interval = _int_value("test:retry", "--interval", tokens[i + 1])
            i += 2
        elif tokens[i] == "--description" and i + 1 < len(tokens):
            description = tokens[i + 1]
            i += 2
        elif tokens[i] == "--shell":
            use_shell = True
            i += 1
        elif tokens[i] == "--":
            command_parts = tokens[i + 1 :]
            break
        elif tokens[i].startswith("--"):
            _warn(f"test:retry: unknown option '{tokens[i]}'")
            i += 1
        else:
            i += 1

    if not command_parts:
        _warn("test:retry: no command specified after --")

    parts = [
        "retry_until_success",
        "--timeout",
        str(timeout),
        "--interval",
        str(interval),
        "--description",
        shlex.quote(description),
        "--",
    ]
    if use_shell:
        parts.append("bash")
        parts.append("-c")
        parts.append(shlex.quote(" ".join(command_parts)))
    else:
        parts.extend(shlex.quote(p) for p in command_parts)
    return " ".join(parts)


def _build_await_idle_command(args_str: str) -> str:
    """Build a ``wait_idle`` call from ``helpers.sh``.

    The ``wait_idle`` function polls ``juju status`` until every unit is
    active/idle (with optional allow-blocked exceptions).
    """
    timeout = 1200
    interval = 30
    allow_blocked: list[str] = []

    tokens = shlex.split(args_str) if args_str.strip() else []
    i = 0
    while i < len(tokens):
        if tokens[i] == "--timeout" and i + 1 < len(tokens):
            timeout = _int_value("test:await-idle", "--timeout", tokens[i + 1])
            i += 2
        elif tokens[i] == "--interval" and i + 1 < len(tokens):
            interval = _int_value("test:await-idle", "--interval", tokens[i + 1])
            i += 2
        elif tokens[i] == "--allow-blocked" and i + 1 < len(tokens):
            allow_blocked = [a.strip() for a in tokens[i + 1].split(",") if a.strip()]
            i += 2
        elif tokens[i].startswith("--"):
            _warn(f"test:await-idle: unknown option '{tokens[i]}'")
            i += 1
        else:
            i += 1

    parts = ["wait_idle", "--timeout", str(timeout), "--interval", str(interval)]
    if allow_blocked:
        parts.extend(["--allow-blocked", ",".join(allow_blocked)])

    return " ".join(parts)


def _parse_set_variables_block(
    lines: list[str], start: int
) -> tuple[str, list[tuple[str, str]], int]:
    """Parse a <!-- test:set-variables ... --> block starting at line `start`.

    Returns (bash_snippet, substitutions, next_index) where:
      - bash_snippet     is the generated variable-assignment bash code
      - substitutions    is [(placeholder, shell_var_ref), ...] for later replacement
      - next_index       is the index of the first line after the closing -->
    """
    i = start + 1
    command = ""
    mappings: list[tuple[str, str]] = []  # [(var_name, field_name), ...]

    while i < len(lines):
        raw = lines[i]
        if "-->" in raw:
            i += 1
            break
        stripped = raw.strip()
        if stripped and ":" in stripped:
            key, _, value = stripped.partition(":")
            key, value = key.strip(), value.strip()
            if key == "command":
                command = value
            elif key and value:
                mappings.append((key, value))
        i += 1

    if not command:
        return "", [], i

    snippet_lines = [f"_CMD_OUTPUT=$({command})"]
    substitutions: list[tuple[str, str]] = []
    for var_name, field_name in mappings:
        snippet_lines.append(
            f"{var_name}=$(echo \"$_CMD_OUTPUT\" | grep '{field_name}:' | awk '{{print $2}}')"
        )
        substitutions.append((f"<{field_name}>", f"${{{var_name}}}"))

    return "\n".join(snippet_lines), substitutions, i


def _parse_run_hidden_block(
    lines: list[str], start: int, active_substitutions: list[tuple[str, str]]
) -> tuple[str, int]:
    """Parse a <!-- test:run ... --> block starting at line `start`.

    Returns (bash_snippet, next_index).
    """
    i = start + 1
    cmd_lines: list[str] = []

    while i < len(lines):
        raw = lines[i]
        if "-->" in raw:
            i += 1
            break
        stripped = raw.rstrip()
        if stripped:
            cmd_lines.append(stripped)
        i += 1

    content = "\n".join(cmd_lines)
    for placeholder, variable in active_substitutions:
        content = content.replace(placeholder, variable)
    return content, i


def _handle_marker_line(
    line: str,
    blocks: list[str],
) -> str | None:
    """Check *line* for a standalone annotation marker.

    Returns a short tag (``"skip"``, ``"sleep"``, ``"await_idle"``) when
    the line was consumed, or ``None`` when the line is not a marker.
    """
    stripped = line.strip()

    if _SKIP_PATTERN.match(stripped):
        return "skip"

    sleep_match = _SLEEP_PATTERN.match(stripped)
    if sleep_match:
        blocks.append(f"sleep {sleep_match.group(1)}")
        return "sleep"

    await_idle_match = _AWAIT_IDLE_PATTERN.match(stripped)
    if await_idle_match:
        args = await_idle_match.group(1).strip()
        blocks.append(_build_await_idle_command(args))
        return "await_idle"

    retry_match = _RETRY_PATTERN.match(stripped)
    if retry_match:
        args = retry_match.group(1).strip()
        blocks.append(_build_retry_command(args))
        return "retry"

    return None


def _collect_shell_block(
    lines: list[str],
    start: int,
    skip: bool,
    timeout_seconds: int | None,
    active_substitutions: list[tuple[str, str]],
    blocks: list[str],
) -> int:
    """Read a shell fence starting at *start* (one past the opening fence).

    Appends the processed content to *blocks* (unless *skip* is True) and
    returns the index of the first line after the closing fence.
    """
    i = start
    block_lines: list[str] = []
    while i < len(lines) and not _FENCE_CLOSE.match(lines[i]):
        block_lines.append(lines[i])
        i += 1
    i += 1  # consume closing fence

    if not skip and block_lines:
        content = "\n".join(block_lines)
        for placeholder, variable in active_substitutions:
            content = content.replace(placeholder, variable)
        if timeout_seconds is not None:
            blocks.append(
                f"( timeout {timeout_seconds} bash << 'TUTORIAL_TIMEOUT_EOF'\n"
                f"{content}\n"
                f"TUTORIAL_TIMEOUT_EOF\n) || true"
            )
        else:
            blocks.append(content)
    return i


class _ParseState:
    """Mutable state carried through the extraction loop."""

    __slots__ = ("skip_next", "run_with_timeout_seconds", "active_substitutions")

    def __init__(self) -> None:
        self.skip_next: bool = False
        self.run_with_timeout_seconds: int | None = None
        self.active_substitutions: list[tuple[str, str]] = []


def _handle_run_with_timeout(
    lines: list[str],
    i: int,
    blocks: list[str],
    state: _ParseState,
) -> int:
    seconds = _int_value(
        "test:run-with-timeout",
        "--seconds",
        _RUN_WITH_TIMEOUT_PATTERN.match(lines[i].strip()).group(1),  # noqa: E501
    )
    state.run_with_timeout_seconds = seconds
    return i + 1


def _handle_set_variables(
    lines: list[str],
    i: int,
    blocks: list[str],
    state: _ParseState,
) -> int:
    snippet, substitutions, next_i = _parse_set_variables_block(lines, i)
    if snippet:
        blocks.append(snippet)
    state.active_substitutions.extend(substitutions)
    return next_i


def _handle_spread_meta(
    lines: list[str],
    i: int,
    blocks: list[str],
    state: _ParseState,
) -> int:
    j = i
    while j < len(lines) and "-->" not in lines[j]:
        j += 1
    return j + 1


def _handle_assert(
    lines: list[str],
    i: int,
    blocks: list[str],
    state: _ParseState,
) -> int:
    snippet, next_i = _parse_run_hidden_block(lines, i, state.active_substitutions)
    if snippet:
        blocks.append(f"# --- Test assertion ---\n{snippet}")
    return next_i


def _handle_run_hidden(
    lines: list[str],
    i: int,
    blocks: list[str],
    state: _ParseState,
) -> int:
    snippet, next_i = _parse_run_hidden_block(lines, i, state.active_substitutions)
    if snippet:
        blocks.append(snippet)
    return next_i


def _handle_shell_open(
    lines: list[str],
    i: int,
    blocks: list[str],
    state: _ParseState,
) -> int:
    next_i = _collect_shell_block(
        lines,
        i + 1,
        state.skip_next,
        state.run_with_timeout_seconds,
        state.active_substitutions,
        blocks,
    )
    state.skip_next = False
    state.run_with_timeout_seconds = None
    return next_i


# Each entry is (pattern, handler).  The pattern is tested against the
# stripped line for multi-line annotations, or the raw line for shell fences.
_Handler = Callable[[list[str], int, list[str], _ParseState], int]
_BLOCK_HANDLERS: list[tuple[re.Pattern[str], bool, _Handler]] = [
    (_RUN_WITH_TIMEOUT_PATTERN, True, _handle_run_with_timeout),
    (_SET_VARIABLES_START, True, _handle_set_variables),
    (_SPREAD_META_START, True, _handle_spread_meta),
    (_ASSERT_START, True, _handle_assert),
    (_RUN_HIDDEN_START, True, _handle_run_hidden),
    (_SHELL_OPEN, False, _handle_shell_open),
]


def extract_shell_blocks(source: str) -> list[str]:
    """Return shell code block contents and generated commands from Markdown.

    Each returned string is either the raw content between shell fences, a
    ``sleep N`` line, a ``wait_idle`` command, or injected code from
    other annotations.  Blocks marked with ``<!-- test:skip -->`` are omitted.
    """
    lines = source.splitlines()
    blocks: list[str] = []
    state = _ParseState()
    i = 0

    while i < len(lines):
        line = lines[i]

        # Detect standalone annotation markers (skip / sleep / await_idle).
        marker = _handle_marker_line(line, blocks)
        if marker == "skip":
            state.skip_next = True
            i += 1
            continue
        if marker is not None:
            i += 1
            continue

        # Try multi-line annotations and shell fences via dispatch table.
        for pattern, use_stripped, handler in _BLOCK_HANDLERS:
            text = line.strip() if use_stripped else line
            if pattern.match(text):
                i = handler(lines, i, blocks, state)
                break
        else:
            # No handler matched — non-empty lines reset the skip flag.
            if line.strip():
                state.skip_next = False
            i += 1

    return blocks


def build_script(input_path: Path, blocks: list[str]) -> str:
    """Assemble the final bash script from extracted blocks."""
    display = _display_path(input_path)
    header = (
        "#!/bin/bash\n"
        f"# Extracted from : {display}\n"
        f"# Regenerate with: python3 extract_commands.py {display} <output.sh>\n"
        "#\n"
        "# Only ```shell fences are extracted; use any other tag to naturally"
        " exclude a block.\n"
        "\n"
        "set -euo pipefail\n"
        "\n"
        "# Load shared helpers (wait_idle, retry_until_success, etc.).\n"
        'HELPERS="${SPREAD_PATH:-$(cd "$(dirname "$0")" && pwd)}/helpers.sh"\n'
        '. "$HELPERS"\n'
        "\n"
    )
    return header + "\n\n".join(blocks) + "\n"


def extract_spread_meta(source: str) -> dict[str, str]:
    """Extract spread test metadata from a ``<!-- test:spread ... -->`` block.

    Only blocks outside fenced code are considered, so a ``test:spread``
    sample shown inside a code fence is ignored.
    """
    lines = list(_iter_unfenced_lines(source))
    for i, line in enumerate(lines):
        if _SPREAD_META_START.match(line.strip()):
            meta: dict[str, str] = {}
            j = i + 1
            while j < len(lines):
                raw = lines[j]
                if "-->" in raw:
                    break
                stripped = raw.strip()
                if stripped and ":" in stripped:
                    key, _, value = stripped.partition(":")
                    meta[key.strip()] = value.strip()
                j += 1
            return meta
    return {}


def extract_heading(source: str) -> str:
    """Return the text of the first Markdown heading outside fenced code."""
    for line in _iter_unfenced_lines(source):
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def build_task_yaml(heading: str, meta: dict[str, str]) -> str:
    """Generate a Spread task.yaml file.

    Uses ``$SPREAD_TASK`` (set by Spread at runtime to the task's relative
    path, e.g. ``tasks/2-deploy``) so the generated task.yaml is portable
    regardless of where the suite is nested within the project.
    """
    priority = meta.get("priority", "0")
    try:
        int(priority)
    except ValueError:
        sys.exit(f"Error: test:spread: priority must be an integer, got {priority!r}")

    kill_timeout = meta.get("kill-timeout", "30m")
    if not _KILL_TIMEOUT_PATTERN.match(kill_timeout):
        sys.exit(
            "Error: test:spread: kill-timeout must be a duration like 30m, 1h or 90s,"
            f" got {kill_timeout!r}"
        )

    summary = heading or "task"
    return (
        f"summary: {json.dumps(summary)}\n"
        f"priority: {priority}\n"
        f"kill-timeout: {kill_timeout}\n"
        f"execute: |\n"
        f'  bash "$SPREAD_PATH/$SPREAD_TASK.sh"\n'
    )


def _process_pair(
    input_path: Path,
    output_path: Path,
    *,
    source: str,
    meta: dict[str, str],
) -> None:
    """Extract shell blocks from *input_path* and write the script.

    *source* is the already-read file content and *meta* is the already-extracted
    spread metadata. Both are passed in so the caller controls how many times
    the file is read and parsed.
    """
    blocks = extract_shell_blocks(source)

    if not blocks:
        print(f"Warning: no shell blocks found in {input_path}", file=sys.stderr)

    script = build_script(input_path, blocks)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(script, encoding="utf-8")
    print(f"Written {len(blocks)} block(s) → {output_path}")

    # Generate task.yaml alongside the .sh file if spread metadata exists.
    if meta:
        heading = extract_heading(source)
        task_dir = output_path.with_suffix("")  # environment.sh → environment/
        task_yaml = task_dir / "task.yaml"
        task_yaml.parent.mkdir(parents=True, exist_ok=True)
        task_content = build_task_yaml(heading, meta)
        task_yaml.write_text(task_content, encoding="utf-8")
        print(f"Written task.yaml → {task_yaml}")


def _check_pair(
    input_path: Path,
    output_path: Path,
    *,
    source: str,
    meta: dict[str, str],
) -> bool:
    """Return True when the on-disk outputs for *input_path* are up to date."""
    blocks = extract_shell_blocks(source)
    expected_script = build_script(input_path, blocks)
    if not output_path.exists():
        print(f"Out of date: {output_path} is missing")
        return False
    if output_path.read_text(encoding="utf-8") != expected_script:
        print(f"Out of date: {output_path} does not match {input_path}")
        return False

    if meta:
        heading = extract_heading(source)
        task_yaml = output_path.with_suffix("") / "task.yaml"
        expected_yaml = build_task_yaml(heading, meta)
        if not task_yaml.exists():
            print(f"Out of date: {task_yaml} is missing")
            return False
        if task_yaml.read_text(encoding="utf-8") != expected_yaml:
            print(f"Out of date: {task_yaml} does not match {input_path}")
            return False
    return True


def _discover(
    input_dir: Path, output_dir: Path, *, check: bool
) -> list[tuple[Path, Path, str, dict[str, str]]]:
    """Find all .md files with spread metadata under *input_dir*.

    Returns (input, output, source, meta) tuples. Only files containing a
    ``<!-- test:spread ... -->`` block are included. The output filename is
    ``<stem>.sh`` where *stem* is the Markdown filename without the ``.md``
    extension.
    """
    md_files = sorted(input_dir.glob("*.md"))
    if not md_files:
        sys.exit(f"Error: no .md files found in {input_dir}")

    discovered: list[tuple[Path, Path, str, dict[str, str]]] = []
    for md_file in md_files:
        source = md_file.read_text(encoding="utf-8")
        meta = extract_spread_meta(source)
        if not meta:
            continue
        output_path = output_dir / f"{md_file.stem}.sh"
        discovered.append((md_file, output_path, source, meta))

    if not discovered:
        sys.exit(f"Error: no files with spread metadata found in {input_dir}")
    return discovered


def _run_jobs(jobs: list[tuple[Path, Path, str, dict[str, str]]], *, check: bool) -> None:
    """Process (or, with *check*, verify) every discovered job."""
    if check:
        stale = [
            job for job in jobs if not _check_pair(job[0], job[1], source=job[2], meta=job[3])
        ]
        if stale:
            sys.exit(
                f"Error: {len(stale)} generated file(s) out of date;"
                " re-run without --check to regenerate"
            )
        print(f"All {len(jobs)} generated file(s) up to date")
        return

    for input_path, output_path, source, meta in jobs:
        _process_pair(input_path, output_path, source=source, meta=meta)
    print(f"Processed {len(jobs)} file(s)")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="extract_commands.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help=(
            "either a single <input.md> (script printed to stdout),"
            " an <input.md> <output.sh> pair (repeatable),"
            " or an <input dir> <output dir> pair for auto-discovery"
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "verify generated files are up to date instead of writing;"
            " exits 1 when stale (useful in CI)"
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat extraction warnings (e.g. unknown annotation options) as errors",
    )
    return parser.parse_args(argv)


def _stdout_mode(input_path: Path) -> None:
    """Print the generated script for *input_path* to stdout."""
    if input_path.is_dir():
        sys.exit(
            f"Error: {input_path} is a directory; provide an output directory as a second argument"
        )
    if not input_path.exists():
        sys.exit(f"Error: {input_path} does not exist")
    source = input_path.read_text(encoding="utf-8")
    blocks = extract_shell_blocks(source)
    if not blocks:
        print(f"Warning: no shell blocks found in {input_path}", file=sys.stderr)
    print(build_script(input_path, blocks), end="")


def _pairs_mode(paths: list[Path], *, check: bool) -> None:
    """Process explicit <input.md> <output.sh> argument pairs."""
    if len(paths) % 2 != 0:
        sys.exit("Error: arguments must be pairs of <input.md> <output.sh>")

    jobs: list[tuple[Path, Path, str, dict[str, str]]] = []
    for i in range(0, len(paths), 2):
        input_path, output_path = paths[i], paths[i + 1]
        if input_path.is_dir():
            sys.exit(f"Error: {input_path} is a directory; use directory mode instead")
        if not input_path.exists():
            sys.exit(f"Error: {input_path} does not exist")
        source = input_path.read_text(encoding="utf-8")
        meta = extract_spread_meta(source)
        if not meta:
            sys.exit(
                f"Error: {input_path} has no spread metadata;"
                " a <!-- test:spread ... --> block is required."
            )
        jobs.append((input_path, output_path, source, meta))
    _run_jobs(jobs, check=check)


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and dispatch to the selected mode."""
    global _strict
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    _strict = args.strict
    paths = [Path(p) for p in args.paths]

    if not paths:
        sys.exit("Error: no input files given; see --help for usage")

    # Directory mode: discover files with spread metadata automatically.
    if len(paths) == 2 and paths[0].is_dir():
        if paths[1].is_file():
            sys.exit(f"Error: output path {paths[1]} is a file, not a directory")
        jobs = _discover(paths[0], paths[1], check=args.check)
        _run_jobs(jobs, check=args.check)
    elif len(paths) == 1:
        _stdout_mode(paths[0])
    else:
        _pairs_mode(paths, check=args.check)


if __name__ == "__main__":
    main()
