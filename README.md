# STAT: Spread Tutorial Automated Testing

A tool for testing documentation tutorials end-to-end. STAT extracts shell commands from Markdown tutorial pages (respecting special HTML-comment annotations) and runs them sequentially in a clean VM via [Spread](https://github.com/canonical/spread).

Developed for [Canonical](https://canonical.com/) **Charmed Operator** tutorials to catch tutorial drift as the product changes. Actively used in production:

- [Charmed OpenSearch](https://github.com/canonical/opensearch-operator/tree/2/edge/tests/tutorial)
- [Charmed Apache Kafka](https://github.com/canonical/kafka-operator/tree/main/tests/tutorial)
- [Charmed Apache Spark](https://github.com/canonical/spark-k8s-bundle/tree/main/python/tests/tutorial)

### Supported formats

- **MyST Markdown** (`.md`): fully supported
- **reStructuredText** (`.rst`): planned

## Quick start

Get STAT running against your tutorial in four steps.

### Prerequisites

| Requirement | Notes |
|---|---|
| Ubuntu host | Tested on 24.04 |
| [Multipass](https://documentation.ubuntu.com/multipass/latest/how-to-guides/install-multipass/) | VM provisioning backend |
| [Go](https://go.dev/doc/install) | Required to install Spread |
| [Spread](https://github.com/canonical/spread) | `go install github.com/canonical/spread/cmd/spread@latest` |
| Python 3, `make` | Usually pre-installed on Ubuntu |

### Integration steps

1. **Copy STAT files** into your project (e.g. `tests/tutorial/`):

   ```bash
   # From your project root:
   mkdir -p tests/tutorial
   cp <stat-repo>/extract_commands.py tests/tutorial/
   cp <stat-repo>/helpers.sh tests/tutorial/
   cp <stat-repo>/Makefile.template tests/tutorial/Makefile
   cp <stat-repo>/spread.yaml.template tests/tutorial/spread.yaml
   cp <stat-repo>/tox.ini.template snippets into your tox.ini   # optional
   cp <stat-repo>/TESTING.md.template tests/tutorial/TESTING.md  # optional
   cp <stat-repo>/.github/workflows/tutorial-tests.yaml.template \
      .github/workflows/tutorial-tests.yaml                        # optional
   ```

2. **Customise templates**: edit `spread.yaml` and `tests/tutorial/Makefile`:
   - Set your project name, VM instance name, and paths (look for `TODO` comments).
   - Optionally list your tutorial pages in the `SCRIPTS` variable in the Makefile (for incremental `make all` builds; `make extract` uses directory discovery and needs no list).

3. **Annotate your tutorial pages**: add a `<!-- test:spread -->` metadata block to each page and use annotations to control execution (see below).

4. **Generate and run**:

   ```bash
   make -f tests/tutorial/Makefile test
   ```

## spread.yaml placement

Place `spread.yaml` **inside** the test directory (`tests/tutorial/spread.yaml`) rather than at the project root. This is especially important when the project already has a root-level `spread.yaml` for other tests (e.g. integration tests).

When `spread.yaml` lives in `tests/tutorial/`:

- Use a **self-contained project name** (e.g. `opensearch-tutorial`) distinct from any root-level spread project
- Set `suites:` to `./tasks/` (relative to spread.yaml)
- Run spread from within `tests/tutorial/`, or use tox with `change_dir`
- `$SPREAD_PATH` points to the directory containing `spread.yaml`
- `$SPREAD_TASK` is set by Spread to the task's relative path (e.g. `tasks/2-deploy`)

This approach avoids conflicts with other test suites and keeps the tutorial test infrastructure self-contained.

## Annotations

Annotations are HTML comments in your Markdown source. They are invisible to readers but consumed by `extract_commands.py`. Only `` ```shell `` fenced code blocks are extracted; any other language tag (`` ```bash ``, `` ```text ``, etc.) is ignored.

Some annotations are **single-line** (opening tag and `-->` on the same line); others are **multi-line** (opening tag on its own line, content on following lines, `-->` on a separate line). The parser requires multi-line annotations to have the opening tag alone on its line — `<!-- test:spread -->` (single-line) is **not** recognised.

| Annotation | Form | Effect |
|---|---|---|
| `<!-- test:spread -->` | multi-line | Spread task metadata (`priority`, `kill-timeout`). Makes the page discoverable. At least one field is required. |
| `<!-- test:skip -->` | single-line | Skip the next `` ```shell `` block (must be immediately before it; any plain text in between cancels the skip). |
| `<!-- test:wait --seconds N -->` | single-line | Emit `sleep N` at that point. |
| `<!-- test:await-idle -->` | single-line | Wait until all Juju units are `active/idle`. Accepts `--timeout S` (default 1200), `--interval S` (default 30), `--allow-blocked APP1,APP2`. |
| `<!-- test:run-with-timeout --seconds N -->` | single-line | Run the next shell block inside `timeout N`; ignore exit code. |
| `<!-- test:set-variables -->` | multi-line | Run a command, extract named fields into shell variables. |
| `<!-- test:run -->` | multi-line | Emit hidden shell commands (not rendered in docs). |
| `<!-- test:assert -->` | multi-line | Hidden assertion. Relies on `set -e` to abort on failure. |
| `<!-- test:retry -->` | single-line | Retry a command until success or timeout. Accepts `--timeout`, `--interval`, `--description`, `--shell`, `-- COMMAND`. |

### `<!-- test:spread -->`

Place at the top of each tutorial page. Required for the page to be discovered and tested. The opening tag must be on its own line (multi-line form); the single-line form `<!-- test:spread -->` is **not** recognised. At least one metadata field (e.g. `priority`) is required — an empty block is treated as absent and the page will be skipped during discovery.

```html
<!-- test:spread
priority: 300
kill-timeout: 15m
-->
```

- **priority**: higher values run first (determines execution order across pages). Defaults to `0` if omitted.
- **kill-timeout**: Spread kills the task if it exceeds this duration. Defaults to `30m` if omitted.

### `<!-- test:set-variables -->`

Captures command output into variables for use in subsequent shell blocks:

```html
<!-- test:set-variables
command: juju run data-integrator/leader get-credentials
KAFKA_USERNAME: username
KAFKA_PASSWORD: password
-->
```

After this annotation, `<username>` and `<password>` placeholders in shell blocks are replaced with `${KAFKA_USERNAME}` and `${KAFKA_PASSWORD}`.

### `<!-- test:assert -->`

```html
<!-- test:assert
juju status --format json | jq -e '.applications.kafka.units | length == 3'
-->
```

The assertion runs with `set -e` active, so a non-zero exit aborts the test.

### `<!-- test:retry -->`

```html
<!-- test:retry --timeout 600 --interval 60 --description "endpoint ready" -- curl -sf http://localhost:8080/health -->
```

Defaults: `--timeout 1200` (20 min), `--interval 120` (2 min), `--description command`.

By default every command token is shell-quoted, so the command **cannot contain pipes, redirects or `&&`**. Add `--shell` to run the command through `bash -c` instead, which enables full shell syntax:

```html
<!-- test:retry --shell -- curl -sf http://localhost:8080/health | grep -q ok -->
```

### `<!-- test:await-idle -->`

```html
<!-- test:await-idle --timeout 900 -->
<!-- test:await-idle --timeout 600 --interval 15 --allow-blocked my-app,data-integrator -->
```

Emits a call to the `wait_idle` helper (see `helpers.sh`), which polls `juju status` until every unit is `active/idle`.

- **`--timeout`**: default 1200 (20 min). The `wait_idle` shell function uses the same default, so the two can no longer drift apart.
- **`--interval`**: poll interval in seconds, default 30.
- **`--allow-blocked`**: comma-separated app names whose units are allowed to be `blocked/idle` (e.g. a data-integrator without a relation).

### `<!-- test:skip -->` placement

The skip marker must be **immediately** before the `` ```shell `` fence. Any plain-text line between the marker and the fence (headings, paragraphs, blank-then-prose) cancels the skip. Intervening **annotations do not cancel it** — a `<!-- test:wait -->` between the skip and the fence still emits its `sleep`, and the block remains skipped. This lets you combine a skip with other annotations deliberately:

~~~markdown
<!-- test:skip -->

```shell
# This block IS skipped
```

<!-- test:skip -->
Some explanatory text here cancels the skip.

```shell
# This block is NOT skipped
```
~~~

~~~markdown
<!-- test:skip -->

```shell
# This block IS skipped
```

<!-- test:skip -->
Some explanatory text here cancels the skip.

```shell
# This block is NOT skipped
```
~~~

See [`examples/sample-page.md`](examples/sample-page.md) for a complete demonstration of all annotations in context.

### Unknown options are reported

A misspelled annotation option (e.g. `--timout` instead of `--timeout`) is reported as a warning on stderr rather than silently ignored. Run with `--strict` to turn these warnings into hard errors — useful in CI to catch typos in annotations.

## Configuration

Both templates contain `TODO` comments marking values you must set.

### `spread.yaml`

Copy `spread.yaml.template` into your test directory. Key settings:

| Field | Purpose |
|---|---|
| `project` | Spread project identifier (use a distinct name from root spread.yaml) |
| `path` | Where project files are mirrored inside the VM |
| `instance_name` | Multipass VM name (in `allocate`/`discard` scripts) |
| `SPREAD_VM_CPUS/MEM/DISK` | VM resources (env var overrides) |
| `suites` | Path to your test suite directory (use `./tasks/` for self-contained setup) |

### `Makefile`

Copy `Makefile.template` into your test directory. Customise:

- **`SCRIPTS`**: optional list of `output.sh:source.md` pairs enabling incremental `make all` builds (directory discovery via `make extract` needs no list)
- **`ROOT`**: adjust `../..` levels if your test directory depth differs
- **`SPREAD_JOB`**: the Spread job selector (default: `multipass:ubuntu-24.04-64:tasks/`)

### `extract_commands.py` CLI modes

| Invocation | Behaviour |
|---|---|
| `extract_commands.py <input.md>` | Print the generated script to stdout |
| `extract_commands.py <input.md> <output.sh>` | Write one pair (repeatable for N pairs; requires a `test:spread` block) |
| `extract_commands.py <input dir> <output dir>` | Directory discovery: process every `.md` with a `test:spread` block |
| `--check` | Verify generated files are up to date; write nothing, exit 1 when stale (CI guard) |
| `--strict` | Treat annotation warnings (e.g. misspelled options) as errors |
| `--help` | Usage (exit 0) |

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `SPREAD_VM_CPUS` | `8` | Multipass VM CPU count |
| `SPREAD_VM_MEM` | `16G` | Multipass VM RAM |
| `SPREAD_VM_DISK` | `50G` | Multipass VM disk |

## Run modes

| Command | Behaviour |
|---|---|
| `make all` | Regenerate only changed pages (via the `SCRIPTS` list) |
| `make extract` | Generate `.sh` scripts and `task.yaml` only (directory discovery; no Spread run) |
| `make check` | Verify generated files are up to date; no writes (CI guard) |
| `make clean` | Remove generated scripts and task directories |
| `make test` | Extract + run Spread, abort on first failure |
| `make test-continue` | Extract + run all stages even if some fail |
| `make test-debug` | Abort on failure, drop into interactive VM shell |

**`test-debug`** is the most useful mode during development. On failure, Spread prints SSH credentials for the VM. Connect, inspect state, re-run commands manually, then `exit` to let Spread clean up.

## CI integration

### tox

Add these environments to your `tox.ini` (see `tox.ini.template` for a ready-to-copy version):

```ini
[testenv:tutorial-extract]
description = Generate tutorial test scripts from Markdown sources
skip_install = True
commands =
    python3 tests/tutorial/extract_commands.py docs/tutorial/ tests/tutorial/tasks/

[testenv:tutorial]
description = Run the tutorial end-to-end test suite via Spread (requires Multipass and Spread)
skip_install = True
change_dir = {tox_root}/tests/tutorial
allowlist_externals =
    spread
commands =
    python3 extract_commands.py ../../docs/tutorial/ ./tasks/
    spread -vv multipass:ubuntu-24.04-64:tasks/

[testenv:tutorial-check]
description = Verify generated tutorial scripts are up to date (CI guard; writes nothing)
skip_install = True
commands =
    python3 tests/tutorial/extract_commands.py --check docs/tutorial/ tests/tutorial/tasks/
```

**Important:** Use `change_dir = {tox_root}/tests/tutorial` so spread discovers the tutorial's `spread.yaml` (not a root-level one meant for other tests).

### GitHub Actions

A complete, production-tested workflow template is provided at
[`.github/workflows/tutorial-tests.yaml.template`](.github/workflows/tutorial-tests.yaml.template).
It includes a KVM preflight check (Multipass requires KVM), idempotent installs,
`permissions: contents: read`, `persist-credentials: false`, a 3-hour job timeout,
and an `if: always()` Multipass VM purge so failed runs cannot leak VMs.

**Note:** Self-hosted runner labels like `xlarge` must be allowlisted in `.github/actionlint.yaml`, otherwise the actionlint check fails.

## How it works

```
┌─────────────────┐       ┌──────────────────┐       ┌─────────────────┐
│  docs/tutorial/  │──────▶│ extract_commands  │──────▶│ tests/tutorial/  │
│  *.md (source)   │       │     .py          │       │  tasks/*.sh +   │
└─────────────────┘       └──────────────────┘       │  */task.yaml    │
                                                      └─────────────────┘
                                                              │
                                                              ▼
                                                     ┌─────────────────┐
                                                     │   Spread (VM)    │
                                                     │  executes .sh    │
                                                     │  sequentially    │
                                                     └─────────────────┘
```

1. **Source**: tutorial pages are standard MyST Markdown. Test annotations are HTML comments, invisible when rendered.
2. **Extract**: `extract_commands.py` parses each `.md` file containing a multi-line `<!-- test:spread ... -->` block (with at least one metadata field), extracts `` ```shell `` fences, processes annotations, and writes a self-contained `.sh` script plus a `task.yaml` for Spread.
3. **Run**: Spread provisions a Multipass VM, mirrors the project into it, and executes each task in priority order. Scripts run with `set -euo pipefail`; any command failure aborts the page.

Generated files (`.sh`, `task.yaml`) are **not committed to git**. They are regenerated before each test run.

### Portability: `$SPREAD_TASK`

Generated `task.yaml` files use `$SPREAD_TASK` (set by Spread at runtime to the task's relative path) rather than a hardcoded script path. This makes the suite portable — it works correctly regardless of where spread.yaml is placed within the project:

```yaml
execute: |
  bash "$SPREAD_PATH/$SPREAD_TASK.sh"
```

At runtime, Spread sets `$SPREAD_TASK` to e.g. `tasks/2-deploy-opensearch`, so the full path resolves to `$SPREAD_PATH/tasks/2-deploy-opensearch.sh`.

## Diagnostics on failure

When a task fails, Spread runs the suite's `debug-each` script. The template `spread.yaml` wires this to `collect_diagnostics` (from `helpers.sh`), which dumps `juju status`, `juju debug-log --replay`, `juju models`, `juju machines`, and host state (`sysctl`, `free`, `df`) into `tasks/artifacts/<system>/`. Every command is individually guarded, so diagnostics collection can never fail the run itself.

Fetch the artifacts locally with:

```bash
spread -artifacts=./artifacts -vv multipass:ubuntu-24.04-64:tasks/
```

Spread downloads each job's artifacts into a per-job subdirectory of the
`-artifacts` target, named after the full job:

```
./artifacts/multipass:ubuntu-24.04-64:tasks/2-deploy-opensearch/
```

So the exact locations are:

- **Inside the VM** (printed by `collect_diagnostics` when it runs):
  `$SPREAD_PATH/tasks/artifacts/<system>/`
- **After fetching** (on the machine that ran Spread):
  `./artifacts/<backend>:<system>:<suite>/<task>/tasks/artifacts/<system>/`

## Lessons learned

These patterns emerged from real-world usage across multiple Charmed Operator tutorials:

**Split shell blocks when actions depend on state.** If a tutorial shows two commands in the same shell block (e.g. `juju integrate ...` followed by `juju run ... get-credentials`), the second may fail because the first hasn't settled. Split them into **separate** `` ```shell `` blocks with `<!-- test:await-idle -->` between them.

**Add sleeps after scaling operations.** After `juju add-unit` or similar scale-up commands, internal rebalancing (e.g. shard redistribution in databases) takes time. A `<!-- test:wait --seconds 60 -->` before assertions that check cluster state prevents flaky failures.

**Use `--channel` in deploy commands.** Always include `--channel` in `juju deploy` commands in the tutorial to pin to a specific track. Omitting it makes the tutorial dependent on whichever channel is marked as default at the time, causing drift.

**Verify revisions for the correct architecture/base.** Charmhub shows the highest revision across all architectures. The correct revision for `amd64` + `ubuntu@24.04` may differ from what's shown in the UI. Always verify via `charmcraft status <charm>`.

**Be careful with root spread.yaml conflicts.** If the project has a root `spread.yaml` for integration tests, placing the tutorial `spread.yaml` at the root will conflict. Use the test-directory-local approach instead.

**tox `change_dir` is essential.** Without it, tox runs spread from the project root, which picks up the wrong `spread.yaml` if one exists at the root level.

**Prefer Python over grep for structured assertions.** When asserting on `juju status`, a small inline Python snippet parsing `--format=json` is more robust than grepping formatted output: unit counts and per-unit workload status survive formatting changes that break text matching.

**Keep assertions deliberately loose.** `grep -q '"found":true'` beats a full-output comparison: strict assertions fail on harmless formatting changes and create false negatives. For multi-value checks, assert each key separately with a diagnostic `echo` of the actual output on failure, rather than one opaque grep.

**Use hidden `test:run` blocks for non-interactive variants.** When the docs show an interactive command (e.g. `juju remove-unit opensearch/3`), keep it visible but execute a hidden non-interactive variant (`--no-prompt`) via `<!-- test:run -->` so the test doesn't hang on a prompt.

**Materialise data files via heredocs in `test:run`.** When a tutorial shows a JSON/CSV data file in a non-shell fence, use a hidden `<!-- test:run -->` block with `cat > file << 'EOF' ... EOF` to create the real file on the VM.

**Extract multi-line values with `test:set-variables` + `test:run`.** Action outputs containing multi-line values (e.g. a PEM CA certificate) can be sliced out with `sed -n '/tls-ca:/,/username:/{...p}'` in a hidden block and written to a file.

**Use `--allow-blocked` for expected-blocked apps.** Apps that are legitimately `blocked/idle` at a given tutorial step (e.g. a data-integrator before its relation exists) must be allow-listed in `<!-- test:await-idle -->`, or the wait never settles.

**Making docs executable catches doc bugs, not just product bugs.** The OpenSearch adoption surfaced wrong `--classic` flags, outdated revisions/versions, incorrect status messages, wrong leader markers, and sample output mistakenly fenced as `shell` — none of which a normal doc review would have caught.

## Downstream linting

Downstream repos typically lint the copied `extract_commands.py` with ruff. STAT keeps its own code lint-clean under the strictest common configuration so the copy lands clean:

- `target-version = "py310"`, `line-length = 99`
- `select = ["E", "W", "F", "C90", "N", "D", "I"]` with `max-complexity = 10` (this is why the parser uses a dispatch table and small handler functions)
- Google-style docstrings on every function

STAT's own CI (`.github/workflows/ci.yaml`) runs exactly this configuration, plus pytest golden-file tests and bats tests with a mocked `juju`.

## File reference

| File | Purpose |
|---|---|
| `extract_commands.py` | Parses Markdown, extracts shell blocks, generates `.sh` scripts and `task.yaml` |
| `helpers.sh` | Shell helpers (`wait_idle`, `retry_until_success`, `collect_diagnostics`) sourced by generated scripts |
| `spread.yaml.template` | Template Spread configuration (Multipass adhoc backend, diagnostics collection) |
| `Makefile.template` | Template build/run automation (`all`, `extract`, `check`, `clean`, `test*`) |
| `tox.ini.template` | Template tox environments (`tutorial-extract`, `tutorial`, `tutorial-check`) |
| `.github/workflows/tutorial-tests.yaml.template` | Template CI workflow (KVM preflight, idempotent installs, VM purge) |
| `TESTING.md.template` | Template contributor documentation for the downstream test directory |
| `examples/sample-page.md` | Annotated tutorial page demonstrating all annotations |
| `prompt.md` | AI agent prompt for automated STAT implementation |
| `tests/` | STAT's own test suite: pytest golden-file tests, bats tests with a mocked `juju`, fixtures |

## Naming

The name **STAT** (*Spread Tutorial Automated Testing*) is experimental. Feedback and alternative suggestions are welcome: [open an issue](https://github.com/izmalk/stat/issues/new).

## License

Copyright 2025 Canonical Ltd. Licensed under the [GNU GPLv3](LICENSE).
