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

| Annotation | Effect |
|---|---|
| `<!-- test:spread -->` | Spread task metadata (`priority`, `kill-timeout`). Makes the page discoverable. |
| `<!-- test:skip -->` | Skip the next `` ```shell `` block. |
| `<!-- test:wait --seconds N -->` | Emit `sleep N` at that point. |
| `<!-- test:await-idle -->` | Wait until all Juju units are `active/idle`. Accepts `--timeout S`, `--allow-blocked APP1,APP2`. |
| `<!-- test:run-with-timeout --seconds N -->` | Run the next shell block inside `timeout N`; ignore exit code. |
| `<!-- test:set-variables -->` | Run a command, extract named fields into shell variables. |
| `<!-- test:run -->` | Emit hidden shell commands (not rendered in docs). |
| `<!-- test:assert -->` | Hidden assertion. Relies on `set -e` to abort on failure. |
| `<!-- test:retry -->` | Retry a command until success or timeout. Accepts `--timeout`, `--interval`, `--description`, `-- COMMAND`. |

### `<!-- test:spread -->`

Place at the top of each tutorial page. Required for the page to be discovered and tested.

```html
<!-- test:spread
priority: 300
kill-timeout: 15m
-->
```

- **priority**: higher values run first (determines execution order across pages)
- **kill-timeout**: Spread kills the task if it exceeds this duration

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
2. **Extract**: `extract_commands.py` parses each `.md` file containing a `<!-- test:spread -->` block, extracts `` ```shell `` fences, processes annotations, and writes a self-contained `.sh` script plus a `task.yaml` for Spread.
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
| `helpers.sh` | Shell helpers (`wait_idle`, `retry_until_success`) sourced by generated scripts |
| `spread.yaml.template` | Template Spread configuration (Multipass adhoc backend) |
| `Makefile.template` | Template build/run automation |
| `examples/sample-page.md` | Annotated tutorial page demonstrating all annotations |
| `prompt.md` | AI agent prompt for automated STAT implementation |

## Naming

The name **STAT** (*Spread Tutorial Automated Testing*) is experimental. Feedback and alternative suggestions are welcome: [open an issue](https://github.com/izmalk/stat/issues/new).

## License

Copyright 2025 Canonical Ltd. Licensed under the [GNU GPLv3](LICENSE).
