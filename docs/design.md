# Tutorial testing automation

We call it STAT: Spread Tutorial Automated Testing.

## The problem

Tutorials for Charmed Operators walk users through multi-step deployments that involve Juju, LXD/MicroK8s, multiple charms, and integrations between them. These tutorials are the first experience many users have with our products.

Two failure modes hurt us repeatedly:

1. **Tutorial drift**: a tutorial page gets outdated (a flag changes, a snap channel moves, an output format shifts) and nobody notices until a user reports it.
2. **Product regression**: a new charm or Juju release introduces a behavioural change that silently breaks a tutorial flow. The documentation team has no automated signal.

Manual verification does not scale. A full Kafka tutorial run takes 30+ minutes of human attention. Multiply that by every charm with a tutorial and every release cycle, and it becomes clear that this needs automation.

## Design goals

- **Single source of truth**: the tutorial Markdown file is _the_ test. No separate test script to keep in sync.
- **Zero reader impact**: all test metadata lives in HTML comments, invisible in rendered documentation.
- **Deterministic ordering**: tutorial steps must execute in page order and page order must be explicit (via priority).
- **Debuggability**: when a step fails, an engineer should be able to SSH into the exact VM state and poke around.
- **Low coupling**: the framework should not depend on the charm's CI system, Python test runner, or tox configuration to function.

## Architecture

```{eval-rst}
.. uml:: architecture.uml
   :width: 90%
   :alt: STAT architecture: Markdown source to extraction to Spread execution
```

### Layer 1: Annotations in Markdown

Annotations are HTML comments placed in the `.md` files. The parser recognises them; Sphinx/MyST ignores them. This means the same file serves both rendered documentation and test input.

Key annotations:

| Annotation | Role |
|---|---|
| `test:spread` | Marks a page as testable; provides priority and timeout |
| `test:skip` | Excludes a block (e.g. `open https://...`) |
| `test:await-idle` | Inserts a Juju wait loop after a deploy/relate step |
| `test:assert` | Hidden validation (not shown to readers) |
| `test:set-variables` | Captures dynamic output for use in later commands |
| `test:run` | Hidden commands needed only for test flow |
| `test:retry` | Wraps a flaky or eventually-consistent check |
| `test:wait` | Static sleep (last resort) |
| `test:run-with-timeout` | Caps execution time for known-slow operations |

### Layer 2: Extraction (`extract_commands.py`)

A single-file Python script (no dependencies beyond the stdlib) that:

1. Scans a directory of `.md` files for `<!-- test:spread -->` metadata blocks.
2. For each matching file, extracts only `` ```shell `` fenced blocks (other tags like `` ```bash `` or `` ```text `` are ignored, giving authors an easy opt-out).
3. Processes annotations to inject `sleep`, `wait_idle`, `retry_until_success` calls, variable capture, assertions, and timeouts.
4. Writes a standalone `.sh` script and a `task.yaml` (Spread task definition).

The extraction is deterministic and fast (pure text processing). Generated files are not committed to git; they are recreated before every test run.

### Layer 3: Execution (Spread + Multipass)

[Spread](https://github.com/canonical/spread) handles:

- Provisioning a Multipass VM with specified resources.
- Mirroring the project tree into the VM.
- Running tasks sequentially in priority order.
- Providing debug access on failure (`-debug` flag drops you into the VM).

We use the **adhoc backend** with Multipass rather than the native LXD backend because tutorials themselves often use LXD inside the VM (nested containers). Multipass gives us a clean Ubuntu VM where the tutorial can set up its own LXD/MicroK8s environment from scratch, exactly as a real user would.

### Layer 4: Helpers (`helpers.sh`)

Two functions cover the most common waiting patterns in Juju-based tutorials:

- `wait_idle`: polls `juju status --format=json` until all units report `active/idle` (with configurable exceptions for expected `blocked` states).
- `retry_until_success`: retries a command at fixed intervals until it succeeds or times out.

These are sourced automatically by every generated script.

## Why Spread?

We evaluated several alternatives:

| Option | Why not |
|---|---|
| pytest + subprocess | No built-in VM lifecycle; would need custom fixtures for Multipass/LXD provisioning and teardown |
| GitHub Actions `run:` steps | Tightly coupled to CI; no local reproduction; no debug shell |
| Bash script with `set -e` | No ordering across files; no timeout/kill management; no parallelism potential |
| Spread | Purpose-built for multi-system task distribution; has VM lifecycle, debug shells, priority ordering, and timeout/kill semantics out of the box |

Spread also has a track record at Canonical (used extensively by the snapd team) and is maintained in-house.

## Why "only `shell` fences"?

A tutorial typically has both executable commands (`` ```shell ``) and example output (`` ```text ``, `` ```bash ``). By only extracting `` ```shell ``, authors can naturally exclude output blocks without any annotation. This convention also matches what many Sphinx/MyST doc sets already use to distinguish runnable commands from display-only content.

## Trade-offs and limitations

- **Sequential execution only**: tutorials are inherently sequential, so parallelism across pages is not useful. Spread's priority mechanism gives us explicit ordering.
- **Juju-specific helpers**: `wait_idle` and `retry_until_success` assume Juju. Non-Juju tutorials need custom helpers.
- **MyST Markdown only**: reStructuredText support is planned but not yet implemented. The annotation format (HTML comments) works in both, but the fenced-block extraction logic is Markdown-specific.
- **VM resource requirements**: a full tutorial run needs a beefy host (8 CPUs, 16 GB RAM recommended) because the VM runs real workloads (LXD containers, Juju controllers, deployed applications).
- **No partial reruns**: if step 5 of 8 fails, you currently cannot resume from step 5. You debug in the VM, fix the issue, then rerun from scratch. This matches Spread's model.

## Regression detection in practice

When a new charm revision or Juju release introduces a regression that affects the tutorial:

1. The tutorial test fails at the exact step that broke.
2. The `test-debug` mode drops an engineer into the VM at that point.
3. The engineer can inspect `juju status`, logs, and rerun commands interactively.
4. Once the root cause is identified, the fix goes to the charm/Juju (not the tutorial), and the test passes again.

This closes the feedback loop: tutorials act as integration tests for the product itself, not just documentation correctness checks.

## References

- [Spread documentation](https://github.com/canonical/spread)
- [STAT repository](https://github.com/canonical/stat)
- Production usage: [kafka-operator/tests/tutorial](https://github.com/canonical/kafka-operator/tree/main/tests/tutorial), [spark-k8s-bundle/python/tests/tutorial](https://github.com/canonical/spark-k8s-bundle/tree/main/python/tests/tutorial)
