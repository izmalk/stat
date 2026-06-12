# Prompt: Implement STAT (Spread Tutorial Automated Testing)

Use this prompt when asking an AI agent to set up automated end-to-end tutorial testing for your product using STAT.

## Prompt

I want to implement automated tutorial testing using [STAT (Spread Tutorial Automated Testing)](https://github.com/izmalk/stat). It extracts shell commands from MyST Markdown tutorial pages and runs them sequentially in a clean VM via [Spread](https://github.com/canonical/spread).

### What is STAT

STAT works by:

1. **Extracting** only `` ```shell `` fenced code blocks from tutorial Markdown files (any other language tag like `` ```bash ``, `` ```text ``, `` ```python `` is naturally ignored)
2. **Generating** a `.sh` script and a `task.yaml` file per tutorial page
3. **Running** the scripts in the exact order inside a fresh VM provisioned by Spread

Generated scripts run with `set -euo pipefail` — any command failure aborts the test for the entire step / page of the tutorial.

### Source files

Get the STAT framework files from https://github.com/izmalk/stat:

- `extract_commands.py` — the parser/generator (do NOT modify this file)
- `helpers.sh` — shared shell helpers (`wait_idle`, `retry_until_success`; sourced automatically by generated scripts)
- `spread.yaml.template` — Spread configuration template for the Multipass adhoc backend
- `Makefile.template` — build/run targets (`extract`, `test`, `test-continue`, `test-debug`)

### Your task

Set up STAT for my project by completing these steps:

1. **Copy STAT files** into the test directory (e.g. `tests/tutorial/`):

   - `extract_commands.py` → `tests/tutorial/extract_commands.py`
   - `helpers.sh` → `tests/tutorial/helpers.sh`
   - `Makefile.template` → `tests/tutorial/Makefile` (customise)
   - `spread.yaml.template` → `tests/tutorial/spread.yaml` (customise; see note below about placement)

2. **Customise `spread.yaml`** (look for `TODO` comments):

   - Set `project:` to a descriptive identifier (e.g. `my-product-tutorial`)
   - Set `path:` to the VM mirror path (e.g. `/my-product`)
   - Set `instance_name` in `allocate`/`discard` blocks
   - Add any pre-installed snaps or packages your tutorial needs in the `allocate` block
   - Adjust VM resources (`SPREAD_VM_CPUS`, `SPREAD_VM_MEM`, `SPREAD_VM_DISK`) if needed
   - Set the `suites:` path to match where your test scripts will live (use relative `./tasks/` when spread.yaml is inside the test directory)

3. **Customise `tests/tutorial/Makefile`**:

   - Set `ROOT` (number of `../` levels to reach project root)
   - Set `SCRIPTS` — list of `output.sh:source.md` pairs, one per tutorial page
   - Set `SPREAD_JOB` — the Spread job selector path
   - Adjust `extract` target input/output directory paths

4. **Annotate tutorial Markdown pages** with STAT annotations (HTML comments invisible to readers). Each page that should be tested needs at minimum the `<!-- test:spread -->` metadata block.

5. **Update `.gitignore`** to exclude generated files (`*.sh` and `*/task.yaml` in the test directory)

6. **Do NOT run the tests** as part of this task. After completing the setup, suggest running `make -f tests/tutorial/Makefile test` as the next step.

### spread.yaml placement

Place `spread.yaml` **inside** the test directory (`tests/tutorial/spread.yaml`) rather than at the project root, especially when the project already has a root-level `spread.yaml` for other tests (e.g. integration tests). This keeps the tutorial suite self-contained and avoids conflicts.

When `spread.yaml` lives in `tests/tutorial/`:
- Use a **self-contained project name** (e.g. `opensearch-tutorial`) distinct from the root spread project
- Set `suites:` to `./tasks/` (relative to the spread.yaml location)
- Run spread from within the `tests/tutorial/` directory, or use `tox` with `change_dir`
- The `$SPREAD_PATH` variable will point to `tests/tutorial/` — the location of `spread.yaml`

### Available annotations

| Annotation | Purpose |
|---|---|
| `<!-- test:spread -->` | **Required.** Spread task metadata (priority, kill-timeout). Makes the page discoverable. Higher priority = runs first. |
| `<!-- test:skip -->` | Skip the next `` ```shell `` block. **Prefer using a non-`shell` fence tag instead** (e.g. `` ```bash ``) — it achieves the same effect without an extra comment. |
| `<!-- test:wait --seconds N -->` | Emit `sleep N` at that point. |
| `<!-- test:await-idle -->` | Wait until all Juju units are active/idle. Accepts `--timeout S`, `--allow-blocked APP1,APP2`. |
| `<!-- test:run -->` | Emit hidden shell commands (not rendered in docs). Ends at `-->`. |
| `<!-- test:run-with-timeout --seconds N -->` | Run the next shell block inside `timeout N`; ignore exit code (for commands that run indefinitely like streaming jobs or `kubectl logs -f`). |
| `<!-- test:set-variables -->` | Run a command, extract named fields into shell variables for placeholder substitution. |
| `<!-- test:assert -->` | Hidden assertion block. Relies on `set -e` to abort on failure. |
| `<!-- test:retry --timeout N --interval M --description "..." -- COMMAND -->` | Retry a command until success or timeout. |

### Key design principles (lessons learned)

**Fence language is the primary skip mechanism.** Only `` ```shell `` blocks are extracted. If a command should NOT run in tests (interactive tools, browser commands, GUI apps, watch commands, multipass commands on host, etc.), simply use `` ```bash `` or `` ```text `` as the fence tag. No `<!-- test:skip -->` annotation needed — this keeps the Markdown cleaner.

**Priority ordering:** Spread executes tasks with higher priority first. Assign decreasing priorities by a margin of 100 (e.g. 700, 600, 500, ..., 100) so page 1 runs first and page 7 runs last.

**Environment variables don't persist between Spread tasks.** Each task is a separate bash invocation. If a later page needs variables from an earlier one, it must re-export them (use `<!-- test:set-variables -->` again). However, files written to disk (e.g. `~/.aws/config`, Juju state in `~/.local/share/juju`) DO persist across tasks since they run on the same VM.

**`newgrp` opens an interactive shell** — it cannot be used directly in a script. If your tutorial has a `newgrp` command (e.g. for snap groups), wrap it with a hidden `<!-- test:run -->` block using a heredoc pattern: `newgrp mygroup << 'EOF'\ntrue\nEOF`.

**Long-running or indefinite commands** (streaming jobs, `kubectl logs -f`, servers): use `<!-- test:run-with-timeout --seconds N -->` before the shell block. The command will be killed after N seconds and the non-zero exit is ignored.

**Mock expensive/auth-gated steps.** If the tutorial downloads large datasets requiring authentication (e.g. Kaggle), use a `<!-- test:run -->` block to create a synthetic mock instead. Keep the original download command in a non-`shell` fence so it stays visible to readers but isn't executed.

**Pre-install in spread.yaml, not in the tutorial script.** VM-level provisioning (creating the VM, installing base tooling like Multipass itself) belongs in the `allocate:` block of `spread.yaml`, not in the tutorial annotations. The tutorial's first page should start from "inside the VM."

**Await-idle after deploys AND integrations.** Juju charms take time to settle. Place `<!-- test:await-idle --timeout N -->` after every `juju deploy` or `juju integrate` block. Use generous timeouts (600s for simple charms, 1200s+ for bundles like cos-lite or multi-unit deployments). Use `--allow-blocked APP` when a charm is expected to be blocked until a subsequent integration is made.

**Split shell blocks when actions depend on state.** If a tutorial shows two commands in the same shell block (e.g. `juju integrate ...` followed by `juju run ... get-credentials`), the second may fail because the first hasn't settled. Split them into **separate** `` ```shell `` blocks with `<!-- test:await-idle -->` between them.

**Add sleeps after scaling operations.** After `juju add-unit` or similar scale-up commands, internal rebalancing (e.g. shard redistribution in databases) takes time. A `<!-- test:wait --seconds 60 -->` before assertions that check cluster state prevents flaky failures.

**Retry flaky commands.** Network-dependent commands (like `aws s3 ls` against a freshly-enabled MinIO) may fail on first attempt. Use either `<!-- test:run -->` with a retry loop, or `<!-- test:retry -->` annotation.

**Use `--channel` in deploy commands.** Always include `--channel` in `juju deploy` commands in the tutorial to pin to a specific track. Omitting it makes the tutorial dependent on whichever channel is marked as default at the time, causing drift.

### CI integration

For CI, the recommended approach is:

1. **tox** targets for extraction and test execution
2. **GitHub Actions** workflow for scheduled/on-demand runs

#### tox integration

Add two environments to your project's `tox.ini`:

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

#### GitHub Actions

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

**Note:** Self-hosted runner labels (like `xlarge`) may trigger actionlint warnings about "unknown labels". This is a false positive — the linter only knows about GitHub-hosted runner labels.

### My tutorial

Locate the tutorial pages in this repository (typically under `docs/tutorial/` or similar). Discover the page order from the tutorial's index/landing page (e.g. a `toctree`, numbered filenames, or an ordered list of links). Infer the product name from the tutorial content. Detect whether Juju is used (look for `juju deploy`, `juju integrate` commands) to determine if `wait_idle` helpers are needed.

Read each page in sequence to understand the full flow before making any changes.

After completing the implementation, verify by running `python3 tests/tutorial/extract_commands.py <tutorial_source_dir> tests/tutorial/tasks/` and checking that generated scripts don't contain commands that should have been skipped.

## Verification checklist

After the agent completes the task, verify:

- [ ] `spread.yaml` exists (either at project root or in `tests/tutorial/`) with correct project name, path, VM name, and pre-installs
- [ ] `tests/tutorial/Makefile` has correct SCRIPTS list and paths
- [ ] `tests/tutorial/extract_commands.py` and `tests/tutorial/helpers.sh` are present (unmodified from STAT repo)
- [ ] `.gitignore` excludes generated `*.sh` and `*/task.yaml` in the test directory
- [ ] Every tutorial page has a `<!-- test:spread -->` metadata block with appropriate priority and kill-timeout
- [ ] No interactive/GUI/watch/browser commands appear in `` ```shell `` blocks (they use `` ```bash `` or similar)
- [ ] `juju deploy`/`integrate` blocks are followed by `<!-- test:await-idle -->` (Juju tutorials only)
- [ ] Commands that depend on state from a previous command are in **separate** shell blocks with appropriate waits between
- [ ] Running `python3 extract_commands.py <input_dir> <output_dir>` succeeds and generates correct scripts
- [ ] Generated `.sh` scripts don't contain skipped commands (grep for known patterns)

## Next step

After completing the implementation, **do not run the tests automatically**. Instead, suggest to the user that the logical next step is:

```
make -f tests/tutorial/Makefile test-continue
```

Or, if tox is configured:

```
tox -e tutorial
```
