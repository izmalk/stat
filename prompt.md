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
   - `spread.yaml.template` → `spread.yaml` at project root (customise)

2. **Customise `spread.yaml`** (look for `TODO` comments):

   - Set `project:` to a descriptive identifier (e.g. `my-product-tutorial`)
   - Set `path:` to the VM mirror path (e.g. `/my-product`)
   - Set `instance_name` in `allocate`/`discard` blocks
   - Add any pre-installed snaps or packages your tutorial needs in the `allocate` block
   - Adjust VM resources (`SPREAD_VM_CPUS`, `SPREAD_VM_MEM`, `SPREAD_VM_DISK`) if needed
   - Set the `suites:` path to match where your test scripts will live

3. **Customise `tests/tutorial/Makefile`**:

   - Set `ROOT` (number of `../` levels to reach project root)
   - Set `SCRIPTS` — list of `output.sh:source.md` pairs, one per tutorial page
   - Set `SPREAD_JOB` — the Spread job selector path
   - Adjust `extract` target input/output directory paths

4. **Annotate tutorial Markdown pages** with STAT annotations (HTML comments invisible to readers). Each page that should be tested needs at minimum the `<!-- test:spread -->` metadata block.

5. **Update `.gitignore`** to exclude generated files (`*.sh` and `*/task.yaml` in the test directory)

6. **Do NOT run the tests** as part of this task. After completing the setup, suggest running `make -f tests/tutorial/Makefile test` as the next step.

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

**Environment variables don't persist between Spread tasks.** Each task is a separate bash invocation. If a later page needs variables from an earlier one, it must re-export them. However, files written to disk (e.g. `~/.aws/config`, Juju state in `~/.local/share/juju`) DO persist across tasks since they run on the same VM.

**`newgrp` opens an interactive shell** — it cannot be used directly in a script. If your tutorial has a `newgrp` command (e.g. for snap groups), wrap it with a hidden `<!-- test:run -->` block using a heredoc pattern: `newgrp mygroup << 'EOF'\ntrue\nEOF`.

**Long-running or indefinite commands** (streaming jobs, `kubectl logs -f`, servers): use `<!-- test:run-with-timeout --seconds N -->` before the shell block. The command will be killed after N seconds and the non-zero exit is ignored.

**Mock expensive/auth-gated steps.** If the tutorial downloads large datasets requiring authentication (e.g. Kaggle), use a `<!-- test:run -->` block to create a synthetic mock instead. Keep the original download command in a non-`shell` fence so it stays visible to readers but isn't executed.

**Pre-install in spread.yaml, not in the tutorial script.** VM-level provisioning (creating the VM, installing base tooling like Multipass itself) belongs in the `allocate:` block of `spread.yaml`, not in the tutorial annotations. The tutorial's first page should start from "inside the VM."

**Await-idle after deploys.** Juju charms take time to settle. Place `<!-- test:await-idle --timeout N -->` after every `juju deploy` or `juju integrate` block. Use generous timeouts (600s for simple charms, 1200s+ for bundles like cos-lite or multi-unit deployments). Use `--allow-blocked APP` when a charm is expected to be blocked until a subsequent integration is made.

**Retry flaky commands.** Network-dependent commands (like `aws s3 ls` against a freshly-enabled MinIO) may fail on first attempt. Use either `<!-- test:run -->` with a retry loop, or `<!-- test:retry -->` annotation.

### My tutorial

Locate the tutorial pages in this repository (typically under `docs/tutorial/` or similar). Discover the page order from the tutorial's index/landing page (e.g. a `toctree`, numbered filenames, or an ordered list of links). Infer the product name from the tutorial content. Detect whether Juju is used (look for `juju deploy`, `juju integrate` commands) to determine if `wait_idle` helpers are needed.

Read each page in sequence to understand the full flow before making any changes.

After completing the implementation, verify by running `python3 tests/tutorial/extract_commands.py <tutorial_source_dir> tests/tutorial/` and checking that generated scripts don't contain commands that should have been skipped.

## Verification checklist

After the agent completes the task, verify:

- [ ] `spread.yaml` exists at project root with correct project name, path, VM name, and pre-installs
- [ ] `tests/tutorial/Makefile` has correct SCRIPTS list and paths
- [ ] `tests/tutorial/extract_commands.py` and `tests/tutorial/helpers.sh` are present (unmodified from STAT repo)
- [ ] `.gitignore` excludes generated `*.sh` and `*/task.yaml` in the test directory
- [ ] Every tutorial page has a `<!-- test:spread -->` metadata block with appropriate priority and kill-timeout
- [ ] No interactive/GUI/watch/browser commands appear in `` ```shell `` blocks (they use `` ```bash `` or similar)
- [ ] `juju deploy`/`integrate` blocks are followed by `<!-- test:await-idle -->` (Juju tutorials only)
- [ ] Running `python3 extract_commands.py <input_dir> <output_dir>` succeeds and generates correct scripts
- [ ] Generated `.sh` scripts don't contain skipped commands (grep for known patterns)

## Next step

After completing the implementation, **do not run the tests automatically**. Instead, suggest to the user that the logical next step is:

```
make -f tests/tutorial/Makefile test-continue
```

