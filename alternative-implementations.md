# Alternative `wait_idle` implementations: analysis

STAT's `wait_idle` helper (defined in `helpers.sh`, emitted by `<!-- test:await-idle -->` annotations) polls `juju status` until every Juju unit in the model is `active/idle`. This document analyses three implementations of that helper and is **intentionally conclusion-free** — it presents trade-offs, problems, and workarounds so you can decide which to use (or A/B test) for your environment.

The three implementations:

| Implementation | File | Mechanism |
|---|---|---|
| **shell** (classic, default) | `wait-shell.sh` | Polls `juju status --format=json` on a fixed interval; embedded Python checks every unit's workload + agent status. |
| **jubilant** | `wait-jubilant.sh` | Uses the [Jubilant](https://canonical.com/juju/docs/jubilant/) Python library's `Juju.wait()` with a custom readiness predicate. |
| **wait-for** | `wait-juju-waitfor.sh` | Uses the native `juju wait-for application` subcommand (Juju 3.6 only) which streams status deltas. |

Select at runtime via `STAT_WAIT_IMPL=shell|jubilant|waitfor` (default: `shell`). See the README for usage.

---

## Summary parity table

| Feature | `shell` | `jubilant` | `wait-for` |
|---|:---:|:---:|:---:|
| `--timeout` | ✅ | ✅ | ✅ |
| `--interval` | ✅ | ✅ | ❌ |
| `--allow-blocked` | ✅ | ✅ | ⚠️ workaround |
| All-units check | ✅ | ✅ | ⚠️ workaround |
| Provisioning (no units yet) | ✅ | ✅ | ✅ |
| Progress output | ✅ detailed | ✅ logged | ✅ streamed |
| Error detection (fail fast) | ❌ gap | ✅ bonus | ✅ bonus |
| Subordinate units | ❌ gap | ✅ | ✅ |
| Exit code (0/1) | ✅ | ✅ wrapper | ✅ wrapper |
| Juju 3.6 | ✅ | ✅ | ✅ |
| Juju 4.0 | ✅ | ✅ | ❌ removed |

---

## Detailed breakdown

### `--timeout` — overall wait timeout

**Status**: shell ✅ · jubilant ✅ · wait-for ✅

**Problem**: None for shell/jubilant. For `wait-for`, the `--timeout` flag applies to a *single* `wait-for application <app>` call, but `wait_idle` must wait for *all* apps. A naive per-app loop would let total wall time exceed the user's `--timeout`.

**Impact**: A 10-minute timeout could silently become 30 minutes if three apps each take the full per-app timeout.

**Workaround**: Track elapsed time across per-app calls and pass `--timeout=<remaining_seconds>` to each `wait-for` invocation. If remaining time drops to zero, abort with timeout. This preserves the user's overall timeout budget.

**Notes**: Shell and Jubilant handle this natively (single wait call with one timeout).

---

### `--interval` — poll interval between status checks

**Status**: shell ✅ · jubilant ✅ · wait-for ❌

**Problem**: `juju wait-for` uses **delta streaming** — the server pushes status changes as they happen, so there is no polling interval. The `--interval` argument has no equivalent.

**Impact**: Users who tune `--interval` to reduce API load (e.g. `--interval 60` on loaded controllers) cannot throttle `wait-for`. Conversely, delta streaming is *more* efficient than polling, so the absence is usually a net win.

**Workaround**: Accept `--interval` for API compatibility but ignore it, emitting a one-line warning: `--interval ignored by wait-for implementation (uses delta streaming)`. No functional impact — the wait still completes when ready.

**Notes**: Jubilant maps `--interval` to its `delay` parameter (seconds between `juju status` fetches). Shell uses `sleep $interval`. If API-load throttling is critical, use `shell` or `jubilant`.

---

### `--allow-blocked APP1,APP2` — permit blocked/idle units for listed apps

**Status**: shell ✅ · jubilant ✅ · wait-for ⚠️ (workaround)

**Problem**: `juju wait-for application <app>` waits for a single app via a DSL query. Expressing "active/idle OR (blocked/idle AND app in allow-list)" across multiple apps in one call is complex and the DSL syntax for OR-conditions needs runtime verification. Worse, `wait-for` operates per-app, so the allow-list must be applied per-app anyway.

**Impact**: Without a workaround, `wait-for` would hang forever on an allow-blocked app (it never reaches active).

**Workaround (option A — skip and verify)**: **Skip** allow-blocked apps from the `wait-for` loop entirely — don't call `wait-for` on them. After all non-blocked apps are ready, run a final `juju status --format=json` check to verify each allow-blocked app is actually `blocked/idle` (not `error`). If any allow-blocked app is in `error`, fail. Simpler and more robust than fighting the DSL.

**Workaround (option B — DSL query)**: Construct a per-app DSL query that accepts `active` or `blocked` for allow-listed apps, e.g. `juju wait-for application <app> --query='... status == "active" or status == "blocked" ...'`. Requires verifying the exact DSL syntax at runtime against Juju 3.6; if the DSL can't express it, fall back to option A.

**Notes**: Shell checks `ws == "blocked" and js == "idle" and app_name in allowed` inline. Jubilant expresses the same in a custom `ready(status)` lambda. Both are clean.

---

### All-units check — wait for every unit in the model to settle

**Status**: shell ✅ · jubilant ✅ · wait-for ⚠️ (workaround)

**Problem**: `juju wait-for application <app>` waits for ONE application. There is no `wait-for all-applications` primitive. `wait-for model` waits for model-level conditions (e.g. model status) but does **not** verify per-unit `active/idle`.

**Impact**: Must enumerate apps and loop. Apps deployed *during* the wait (race) won't be caught. Subordinate apps may not be directly enumerable.

**Workaround**: Enumerate applications once from `juju status --format=json` at the start of `wait_idle`, then loop `wait-for application <app>` over each. For tutorials this is safe — apps are deployed *before* `<!-- test:await-idle -->` is emitted, so the app set is stable. For subordinate apps: they appear as entries in `applications`, so enumeration includes them.

**Notes**: Shell iterates `data["applications"][*]["units"][*]` in one pass. Jubilant's custom lambda iterates `status.apps` and units. Both are single-pass and race-free for the common case.

---

### Provisioning — no units exist yet (model still bootstrapping)

**Status**: shell ✅ · jubilant ✅ · wait-for ✅

**Problem**: None significant. When no units exist yet, the wait must not falsely report success.

**Impact**: A naive "zero units = done" check would return success prematurely.

**Workaround**: None needed.
- Shell: prints `"provisioning"` and keeps polling when `total_units == 0`.
- Jubilant: custom `ready(status)` returns `False` when no units exist.
- `wait-for`: naturally blocks until the named app exists and has units; no special handling required.

**Notes**: This case is rare in tutorials (apps are deployed before await-idle), but the implementations handle it correctly.

---

### Progress output — visibility into what's being waited on

**Status**: shell ✅ (detailed) · jubilant ✅ (logged) · wait-for ✅ (streamed)

**Problem**: Output formats differ across implementations. Tooling that greps logs for specific patterns (e.g. `"N unit(s) not yet active/idle"`) will not work across implementations.

**Impact**: Log analysis and CI dashboards may need per-implementation parsing. The final `juju status` print is consistent across all three.

**Workaround**: None needed for functionality. For log normalization, either accept different formats or wrap output. Jubilant's logging is configurable: `logging.getLogger('jubilant.wait').setLevel('WARNING')` silences it; default is INFO.

**Notes**: Shell is the most verbose (per-poll counts with elapsed time). Jubilant logs the full status object on change. `wait-for` streams delta updates in its own format. All print a final `juju status` on success and on timeout.

---

### Error detection — fail fast when a unit enters `error` status

**Status**: shell ❌ (gap) · jubilant ✅ (bonus) · wait-for ✅ (bonus)

**Problem**: Shell `wait_idle` does **not** detect `error` status — it keeps polling until `--timeout` expires, wasting time on a doomed wait. This is a classic limitation, not an alternative limitation.

**Impact**: On a charm that goes into `error`, shell burns the full timeout (e.g. 20 minutes) before failing. Alternatives fail in seconds.

**Workaround (for shell)**: Could be added as an enhancement to `wait-shell.sh` (treat `error` workload status as immediate failure). Out of scope for the alternatives work, but worth noting for A/B fairness.

**Workaround (for alternatives)**: Jubilant uses `error=jubilant.any_error` to raise `WaitError` immediately. `wait-for` can express error conditions in its DSL, or the wrapper detects non-zero exit.

**Notes**: This is a **bonus feature** of the alternatives, not a gap. For reliability/speed testing, this makes alternatives faster on failure cases — a real advantage to measure.

---

### Subordinate units — charms deployed under a principal unit

**Status**: shell ❌ (gap) · jubilant ✅ · wait-for ✅

**Problem**: Shell `wait_idle` iterates `app["units"].values()` — this is **top-level units only**. Subordinate units (nested under `unit["subordinates"]`) are **not checked**. A subordinate stuck in `waiting` would not block shell `wait_idle`.

**Impact**: Shell may report "all active/idle" while a subordinate is not yet settled. For tutorials that depend on subordinates (e.g. logging via a subordinate charm), this can cause flaky downstream failures.

**Workaround (for shell)**: Could enhance `wait-shell.sh` to recurse into `subordinates`. Out of scope for alternatives work, but worth noting.

**Workaround (for alternatives)**: Jubilant's `status.get_units(app)` includes subordinate units — use it in the `ready` lambda to match shell's gap (iterate top-level only) OR to improve on shell (include subordinates). `wait-for application <subordinate-app>` works because subordinates appear in `applications`.

**Notes**: For fair A/B comparison, decide whether to match shell's gap (ignore subordinates) or fix it (check subordinates). Open question — see "Further considerations".

---

### Exit code semantics — consistent 0/1 return

**Status**: shell ✅ · jubilant ✅ (wrapper) · wait-for ✅ (wrapper)

**Problem**: Each implementation signals success/failure differently. Shell returns 0/1. Jubilant raises `TimeoutError`/`WaitError`. `wait-for` exits non-zero on timeout/failure.

**Impact**: Generated scripts use `set -e` and rely on `wait_idle` returning non-zero on failure to abort the task. Inconsistent exit codes would break this.

**Workaround**: Wrapper functions in `wait-jubilant.sh` and `wait-juju-waitfor.sh` catch exceptions/non-zero exits and `return 0` on success, `return 1` on timeout/error. This normalizes all three to the shell contract.

**Notes**: Already part of the implementation — no extra work.

---

### Juju version compatibility

**Status**: shell ✅ (all) · jubilant ✅ (3.x, 4.x) · wait-for ❌ (3.6 only)

**Problem**: `juju wait-for` and its subcommands (`wait-for model|application|machine|unit`) are **removed in Juju 4.0**. Confirmed via the Juju 4.0 release notes and the 3.6→4.0 upgrade guide.

**Impact**: Any test using `STAT_WAIT_IMPL=waitfor` will fail on Juju 4.0 with "command not found". Scripts that hardcode `waitfor` break on upgrade.

**Workaround**: Use `shell` or `jubilant` for Juju 4.0. The `wait-juju-waitfor.sh` implementation detects the Juju version at the top and either falls back to `shell` with a warning, or fails fast with a clear message: `juju wait-for is not available in Juju 4.0; use STAT_WAIT_IMPL=shell or jubilant`.

**Notes**: This is the **most significant limitation** of `wait-for`. Document prominently. For long-term maintainability, `jubilant` is the forward-compatible choice.

---

## Further considerations (open questions)

These are deliberately left unanswered — they depend on your environment, charm mix, and A/B testing results.

1. **Jubilant `successes` parameter**: Default is 3 (requires 3 consecutive stable checks). The implementation sets `successes=1` to match shell's "return on first success". For reliability testing, you may want to try `successes=3` — easily changed in `wait-jubilant.sh`. Which value gives the fairest comparison?

2. **`juju wait-for` DSL for allow-blocked**: Can the DSL express OR-conditions cleanly (option B above), or is the skip-and-verify workaround (option A) necessary? Needs runtime testing against Juju 3.6.

3. **Subordinate units — match the gap or fix it?** Shell ignores subordinates. Should the alternatives match that gap (for fair comparison) or fix it (check subordinates too)? Matching gives fairer timing data; fixing gives more correct behavior but skews the comparison.

4. **Multi-file copy instructions**: Users now copy `helpers.sh` + `wait-*.sh` (4 files) instead of 1. Is the modularity worth the extra copy step? Alternatively, a single `helpers.sh` with all 3 implementations embedded (~500 lines) is possible but harder to delete cleanly.

5. **Which implementation is best for which scenario?** This document does not answer that. Run A/B tests with `make test`, `make test-jubilant`, and `make test-waitfor` against your real tutorials and compare reliability + speed. The answer likely depends on your charm mix, model size, and Juju version.
