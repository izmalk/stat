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
   ```

2. **Customise templates**: edit `spread.yaml` and `tests/tutorial/Makefile`:
   - Set your project name, VM instance name, and paths (look for `TODO` comments).
   - List your tutorial pages in the `SCRIPTS` variable in the Makefile.

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
| `<!-- test:skip -->` | single-line | Skip the next `` ```shell `` block (must be immediately before it; any text in between cancels the skip). |
| `<!-- test:wait --seconds N -->` | single-line | Emit `sleep N` at that point. |
| `<!-- test:await-idle -->` | single-line | Wait until all Juju units are `active/idle`. Accepts `--timeout S` (default 1200), `--allow-blocked APP1,APP2`. |
| `<!-- test:run-with-timeout --seconds N -->` | single-line | Run the next shell block inside `timeout N`; ignore exit code. |
| `<!-- test:set-variables -->` | multi-line | Run a command, extract named fields into shell variables. |
| `<!-- test:run -->` | multi-line | Emit hidden shell commands (not rendered in docs). |
| `<!-- test:assert -->` | multi-line | Hidden assertion. Relies on `set -e` to abort on failure. |
| `<!-- test:retry -->` | single-line | Retry a command until success or timeout. Accepts `--timeout`, `--interval`, `--description`, `-- COMMAND`. |

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

### `<!-- test:await-idle -->`

```html
<!-- test:await-idle --timeout 900 -->
<!-- test:await-idle --timeout 600 --allow-blocked my-app,data-integrator -->
```

Emits a call to the `wait_idle` helper (see `helpers.sh`), which polls `juju status` until every unit is `active/idle`.

- **Default timeout**: the annotation injects `--timeout 1200` (20 min) when omitted. Note this differs from the `wait_idle` shell function's own default of 600s — the annotation always passes an explicit value.
- **`--allow-blocked`**: comma-separated app names whose units are allowed to be `blocked/idle` (e.g. a data-integrator without a relation).
- **`--interval`**: supported by the underlying `wait_idle` function but **not** passable via the annotation (silently dropped by the parser). To change the poll interval, edit the generated script or call `wait_idle` directly in a `<!-- test:run -->` block.

### `<!-- test:skip -->` placement

The skip marker must be **immediately** before the `` ```shell `` fence. Any **non-empty** line between the marker and the fence (including headings, paragraphs, or other annotations) cancels the skip:

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

- **`SCRIPTS`**: list of `output.sh:source.md` pairs (one per tutorial page)
- **`ROOT`**: adjust `../..` levels if your test directory depth differs
- **`SPREAD_JOB`**: the Spread job selector (default: `multipass:ubuntu-24.04-64:tasks/`)

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `SPREAD_VM_CPUS` | `8` | Multipass VM CPU count |
| `SPREAD_VM_MEM` | `16G` | Multipass VM RAM |
| `SPREAD_VM_DISK` | `50G` | Multipass VM disk |

## Run modes

| Command | Behaviour |
|---|---|
| `make extract` | Generate `.sh` scripts and `task.yaml` only (no Spread run) |
| `make test` | Extract + run Spread, abort on first failure |
| `make test-continue` | Extract + run all stages even if some fail |
| `make test-debug` | Abort on failure, drop into interactive VM shell |

**`test-debug`** is the most useful mode during development. On failure, Spread prints SSH credentials for the VM. Connect, inspect state, re-run commands manually, then `exit` to let Spread clean up.

## Alternative wait implementations

STAT supports three implementations of the `wait_idle` helper (used by `<!-- test:await-idle -->`):

| Implementation | File | Mechanism |
|---|---|---|
| `shell` (default) | `wait-shell.sh` | Polls `juju status` on a fixed interval |
| `jubilant` | `wait-jubilant.sh` | Uses the [Jubilant](https://canonical.com/juju/docs/jubilant/) Python library's `Juju.wait()` |
| `waitfor` | `wait-juju-waitfor.sh` | Uses native `juju wait-for` (Juju 3.6 only) |

Select at runtime via the `STAT_WAIT_IMPL` environment variable, or use the Makefile convenience targets:

```bash
# Default (shell) — no env var needed
make -f tests/tutorial/Makefile test

# Jubilant
make -f tests/tutorial/Makefile test-jubilant

# juju wait-for (Juju 3.6 only)
make -f tests/tutorial/Makefile test-waitfor
```

`test-continue-*` and `test-debug-*` variants are also available for each implementation.

**Default is `shell`** for backward compatibility — existing repos that update STAT get zero behavior change. Jubilant is installed on-the-fly via `pip install jubilant` (no `spread.yaml` change needed).

For a detailed feature comparison (parity, gaps, workarounds, Juju version compatibility), see [`alternative-implementations.md`](alternative-implementations.md). That document is analysis-only — it presents trade-offs without firm conclusions, so you can decide which implementation works best for your environment via A/B testing.

### Copying the new helper files

When integrating STAT into a project, copy all helper files (not just `helpers.sh`):

```bash
cp <stat-repo>/helpers.sh tests/tutorial/
cp <stat-repo>/wait-*.sh tests/tutorial/
```

`helpers.sh` is now a dispatcher that sources the selected `wait-*.sh` file based on `STAT_WAIT_IMPL`.

## Self-testing

STAT includes its own test infrastructure to run a real tutorial (the [Charmed OpenSearch tutorial](https://github.com/canonical/opensearch-operator/tree/main/docs/tutorial), copied into `docs/tutorial/`) through each `wait_idle` implementation. This is useful for verifying changes to STAT itself and for A/B testing the implementations.

### Prerequisites

| Requirement | Notes |
|---|---|
| [Multipass](https://multipass.run/) | VM provisioning backend |
| [Spread](https://github.com/canonical/spread) | `go install github.com/canonical/spread/cmd/spread@latest` |
| `tox` | `sudo apt install tox` or `pip install tox` |

### Running the tests

```bash
# Run a single implementation
tox -e stat-shell       # classic polling (default)
tox -e stat-jubilant    # Jubilant Python library
tox -e stat-waitfor     # juju wait-for (Juju 3.6 only)

# Run all three sequentially
tox -e stat-all
```

Or use `make` directly (bypasses tox):

```bash
make test              # classic (shell)
make test-jubilant     # Jubilant
make test-waitfor      # juju wait-for
```

Each environment provisions a fresh Multipass VM, installs Juju + LXD, runs the 7-step OpenSearch tutorial (deploy, TLS, integrate, passwords, scale, clean up), and discards the VM. The `STAT_WAIT_IMPL` environment variable is set automatically by each tox environment.

### What the tutorial tests

The tutorial (`docs/tutorial/`) is a real Charmed OpenSearch tutorial with STAT annotations added. It exercises `wait_idle` extensively — after every `juju deploy` and `juju integrate`, with `--allow-blocked` for apps that are expected to be blocked (e.g. `opensearch` before TLS, `data-integrator` before relation). The `examples/sample-page.md` file remains as a minimal demo of all STAT annotations.

## CI integration

### tox

Add two environments to your `tox.ini`:

```ini
[testenv:tutorial-extract]
description = Regenerate tutorial test scripts from docs
deps =
skip_install = true
commands =
    python3 {tox_root}/tests/tutorial/extract_commands.py {tox_root}/docs/tutorial/ {tox_root}/tests/tutorial/tasks/

[testenv:tutorial]
description = Run tutorial end-to-end tests via spread
deps =
skip_install = true
allowlist_externals =
    spread
change_dir = {tox_root}/tests/tutorial
commands =
    python3 {tox_root}/tests/tutorial/extract_commands.py {tox_root}/docs/tutorial/ {tox_root}/tests/tutorial/tasks/
    spread -abend -vv multipass:ubuntu-24.04-64:tasks/
```

**Important:** Use `change_dir = {tox_root}/tests/tutorial` so spread discovers the tutorial's `spread.yaml` (not a root-level one meant for other tests).

### GitHub Actions

```yaml
name: Tutorial tests
on:
  schedule:
    - cron: '0 3 1 * *'  # Monthly
  workflow_dispatch:

jobs:
  tutorial:
    runs-on: [self-hosted, linux, AMD64, X64, xlarge, noble]
    steps:
      - uses: actions/checkout@v4
      - name: Install Multipass
        run: sudo snap install multipass
      - name: Install Go + Spread
        run: |
          sudo snap install go --classic
          go install github.com/canonical/spread/cmd/spread@latest
          echo "$HOME/go/bin" >> "$GITHUB_PATH"
      - name: Install tox
        run: |
          sudo apt-get update
          sudo apt-get install -y tox
      - name: Run tutorial tests
        run: tox -e tutorial
      - name: Cleanup VM
        if: always()
        run: multipass delete --purge my-tutorial-vm 2>/dev/null || true
```

**Note:** Self-hosted runner labels like `xlarge` may trigger actionlint warnings. This is a false positive — the linter only knows about GitHub-hosted runner labels.

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

## Lessons learned

These patterns emerged from real-world usage across multiple Charmed Operator tutorials:

**Split shell blocks when actions depend on state.** If a tutorial shows two commands in the same shell block (e.g. `juju integrate ...` followed by `juju run ... get-credentials`), the second may fail because the first hasn't settled. Split them into **separate** `` ```shell `` blocks with `<!-- test:await-idle -->` between them.

**Add sleeps after scaling operations.** After `juju add-unit` or similar scale-up commands, internal rebalancing (e.g. shard redistribution in databases) takes time. A `<!-- test:wait --seconds 60 -->` before assertions that check cluster state prevents flaky failures.

**Use `--channel` in deploy commands.** Always include `--channel` in `juju deploy` commands in the tutorial to pin to a specific track. Omitting it makes the tutorial dependent on whichever channel is marked as default at the time, causing drift.

**Verify revisions for the correct architecture/base.** Charmhub shows the highest revision across all architectures. The correct revision for `amd64` + `ubuntu@24.04` may differ from what's shown in the UI. Always verify via `charmcraft status <charm>`.

**Be careful with root spread.yaml conflicts.** If the project has a root `spread.yaml` for integration tests, placing the tutorial `spread.yaml` at the root will conflict. Use the test-directory-local approach instead.

**tox `change_dir` is essential.** Without it, tox runs spread from the project root, which picks up the wrong `spread.yaml` if one exists at the root level.

## File reference

| File | Purpose |
|---|---|
| `extract_commands.py` | Parses Markdown, extracts shell blocks, generates `.sh` scripts and `task.yaml` |
| `helpers.sh` | Dispatcher: sources the selected `wait_idle` implementation + defines `retry_until_success` |
| `wait-shell.sh` | Classic polling `wait_idle` (default) |
| `wait-jubilant.sh` | Jubilant-based `wait_idle` (alternative) |
| `wait-juju-waitfor.sh` | `juju wait-for` based `wait_idle` (alternative, Juju 3.6 only) |
| `alternative-implementations.md` | Feature comparison of the three `wait_idle` implementations |
| `spread.yaml.template` | Template Spread configuration (Multipass adhoc backend) |
| `Makefile.template` | Template build/run automation |
| `examples/sample-page.md` | Annotated tutorial page demonstrating all annotations |
| `prompt.md` | AI agent prompt for automated STAT implementation |

## Naming

The name **STAT** (*Spread Tutorial Automated Testing*) is experimental. Feedback and alternative suggestions are welcome: [open an issue](https://github.com/izmalk/stat/issues/new).

## License

Copyright 2025 Canonical Ltd. Licensed under the [GNU GPLv3](LICENSE).
