# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.

## Project overview

STAT (**S**pread **T**utorial **A**utomated **T**esting) is a small Python +
Bash toolkit, not an application. It parses MyST Markdown tutorial pages,
extracts annotated ` ```shell ` fenced code blocks, and generates:

- a self-contained `.sh` script per tutorial page
- a Spread `task.yaml` per page

These are then run in order inside a clean VM by
[Spread](https://github.com/canonical/spread) to catch documentation drift.

This repo is the **distributable framework itself** (meant to be copied into
downstream product repos, e.g. `opensearch-operator`, `kafka-operator`), not
a deployed service. There is no server, no database, no build step beyond
"run the Python script".

## Repository structure

| Path | Purpose | Edit? |
|---|---|---|
| `extract_commands.py` | Core parser/generator. The only "real" program in the repo. | Yes, carefully — see below |
| `helpers.sh` | Bash helpers (`wait_idle`, `retry_until_success`) sourced by every generated script | Yes |
| `Makefile.template` | Template copied into a downstream repo's test dir, then customised | Yes (keep `TODO` markers) |
| `spread.yaml.template` | Template Spread config (Multipass adhoc backend, `debug-each` diagnostics) | Yes (keep `TODO` markers) |
| `tox.ini.template` | Template tox envs (`tutorial-extract`, `tutorial`, `tutorial-check`) | Yes (keep paths generic) |
| `.github/workflows/tutorial-tests.yaml.template` | Template CI workflow (KVM preflight, idempotent installs, VM purge) | Yes (keep `TODO` markers) |
| `TESTING.md.template` | Template contributor docs for the downstream test dir | Yes |
| `tests/` | STAT's own test suite: pytest golden-file tests, bats tests with a mocked `juju`, fixtures | Yes |
| `examples/sample-page.md` | Reference Markdown demonstrating every annotation | Keep in sync with README |
| `prompt.md` | A ready-to-use prompt for an agent to *integrate* STAT into a downstream product repo | Keep in sync with README/annotations |
| `README.md` | User-facing documentation: annotation reference, integration steps, lessons learned | Keep in sync with code |
| `tasks/` | **Not tracked by git.** Locally generated example output (see `.gitignore`). Ignore when reasoning about repo contents; regenerate via `extract` if needed for testing. | Generated, don't hand-edit |

`extract_commands.py`, `Makefile.template`, and `spread.yaml.template` are
copied verbatim (or lightly customised) into downstream repos per the
"Integration steps" in `README.md`. Treat `README.md` as the contract for
their expected behavior — if you change the script's CLI, annotation syntax,
or generated output shape, update `README.md`, `prompt.md`, and
`examples/sample-page.md` in the same change.

## Setup / running locally

No package installation is required to work on `extract_commands.py` — it
uses only the Python standard library (`re`, `shlex`, `sys`, `pathlib`).
Requires **Python 3.10+** (uses `list[str]`, `dict[str, str]`, `X | None`
syntax).

Quick manual checks (no test suite exists in this repo — see Testing below):

```bash
# Print the generated script for a single page to stdout
python3 extract_commands.py examples/sample-page.md

# Explicit input/output pair
python3 extract_commands.py examples/sample-page.md /tmp/out.sh

# Directory discovery mode (mirrors real downstream usage)
python3 extract_commands.py examples/ /tmp/tasks/
```

`Makefile.template` and `spread.yaml.template` are **not runnable in this
repo as-is** — they contain `TODO` placeholders and are only meaningful once
copied into a downstream product repo with real tutorial content and a real
Juju/product setup. Do not attempt to `make test` here; there is no VM
backend or tutorial source configured in this repo.

## Testing / validation

This repo has a full test suite (pytest golden-file tests + bats tests with
a mocked `juju` + shellcheck + ruff). Run everything with:

```bash
tox -e lint,unit,shell
# or directly:
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python -m pytest
shellcheck helpers.sh && bats tests/bats
```

### Golden-file workflow

`tests/fixtures/*.md` are small single-purpose pages; `tests/golden/*.sh`
hold the expected generated output. When a change to `extract_commands.py`
**intentionally** alters generated output:

1. Regenerate the goldens: `python3 tests/regen_golden.py`
2. Review the resulting `git diff` carefully — it is the explicit record of
   the behavior change.

When adding a new annotation or behavior, add a fixture + golden file and a
small test rather than only testing manually.

### Manual checks

1. Run it against `examples/sample-page.md` (covers every annotation type)
   and inspect the generated script for correctness:
   ```bash
   python3 extract_commands.py examples/sample-page.md
   ```
2. Cross-check every annotation against the "Annotations" table in
   `README.md`.
3. If you change the `task.yaml` generation (`build_task_yaml`), verify the
   output still uses `$SPREAD_TASK` (not a hardcoded path) — this is what
   makes generated suites portable across different `spread.yaml` locations.
4. When adding a new annotation, add a demonstrating snippet to
   `examples/sample-page.md` and document it in the README's annotation
   table and `prompt.md`'s annotation table (both must stay in sync).
5. Keep the code lint-clean under the downstream ruff config
   (`py310`, 99 cols, `E,W,F,C90,N,D,I`, mccabe ≤ 10) — downstream repos lint
   the copied file, and the dispatch-table structure exists to satisfy
   `max-complexity = 10`.

## Code style

- **Python**: stdlib only, no third-party dependencies. Add type hints using
  modern syntax (`list[str]`, `X | None`) consistent with the existing file.
  Functions are kept small and dispatch-table driven (`_BLOCK_HANDLERS`) —
  follow that pattern when adding a new annotation type rather than adding
  ad-hoc `if` branches to the main loop.
- **Bash** (`helpers.sh`, generated scripts): `set -euo pipefail` is
  mandatory in every generated script — don't introduce constructs that
  silently swallow errors. Guard pipelines that may legitimately fail (e.g.
  `juju status` while a machine is still provisioning) with explicit
  `set +o pipefail` subshells, following the existing pattern in
  `wait_idle`.
- Keep generated shell scripts POSIX/bash-portable; they run unattended
  inside a Multipass Ubuntu VM via Spread, with no interactive TTY.
- Copyright header: new Python/shell files should start with
  `# Copyright 2025 Canonical Ltd.` / `# See LICENSE file for licensing
  details.`, matching `extract_commands.py`.

## Key constraints and invariants (read before changing behavior)

- **Only ` ```shell ` fences are extracted.** Any other language tag
  (`bash`, `text`, `console`, etc.) must continue to be ignored — this is
  the primary "skip" mechanism documented throughout the README and
  `prompt.md`. Do not make extraction language-tag-agnostic.
- **Multi-line annotations require the opening tag alone on its line**
  (e.g. `<!-- test:spread` on its own line, `-->` closing on another line).
  Single-line forms of these same tags are intentionally *not* recognised.
  Don't "fix" this without updating the README, which documents it as
  by-design.
- **`<!-- test:skip -->` cancels on any intervening plain-text line** before
  the next ` ```shell ` fence, but **not** on intervening annotations (an
  annotation between the skip and the fence still emits its own effect and
  the block remains skipped). Preserve this behavior exactly (see
  `state.skip_next` reset logic in `extract_shell_blocks` and the
  `skip-not-cancelled-by-annotation` fixture).
- **`task.yaml` must use `$SPREAD_TASK`**, not a hardcoded script path, so
  generated suites remain portable regardless of where `spread.yaml` lives
  in a downstream repo.
- **`task.yaml` `summary` must be YAML-safe** (emitted via `json.dumps`),
  and `priority` / `kill-timeout` are validated — headings with quotes must
  not produce broken YAML.
- **Unknown annotation options must warn** (and fail under `--strict`),
  never be silently dropped. `extract_heading` / `extract_spread_meta`
  must stay fence-aware (ignore content inside code samples).
- **Generated file headers must use repo-relative paths** so output is
  reproducible regardless of checkout location.
- **Environment variables set via `test:set-variables` do not persist
  across Spread tasks** (each page is a separate script/process). Don't
  design new features that assume in-memory state survives between pages;
  persistence only works via files written to disk on the VM.
- Generated `.sh` files and `*/task.yaml` are build artifacts and must stay
  out of git (see `.gitignore`). Never commit files under a `tasks/`
  directory produced by running the extractor.

## Documentation sync requirement

This repo has four places describing the same annotation surface:
`README.md` (Annotations section + Lessons learned), `prompt.md`
(Available annotations table + Key design principles), and
`examples/sample-page.md` (live demonstration). **Any change to annotation
syntax, defaults, or generated behavior in `extract_commands.py` must be
reflected in all three simultaneously.** Treat a PR that changes one without
the others as incomplete.

## Commit / PR guidelines

- No enforced commit message convention observed in history; write clear,
  imperative-mood summaries (e.g. `Fix skip-marker reset on blank lines`).
- Keep `Makefile.template` / `spread.yaml.template` free of repo-specific
  values — they must stay generic templates with `TODO` comments for
  downstream integrators to fill in. Don't accidentally hardcode this repo's
  own naming (e.g. `opensearch-tutorial`) into the templates.
- Before opening a PR that touches `extract_commands.py`, run the manual
  validation steps above and mention the exact commands/output you checked,
  since there is no CI test suite to rely on.

## Licensing

GNU GPLv3 (`LICENSE`). New source files should carry the same
`Copyright 2025 Canonical Ltd.` header as `extract_commands.py`.
