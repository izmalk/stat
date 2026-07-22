#!/bin/bash
# juju wait-for based implementation of wait_idle.
#
# Uses the native `juju wait-for application` subcommand (Juju 3.6 only) to
# stream status deltas until each application is ready. Because wait-for
# operates on a single application, this implementation enumerates apps and
# loops, tracking an aggregate timeout budget.
#
# Select with:  STAT_WAIT_IMPL=waitfor
# Sourced by helpers.sh; not intended to be sourced directly.
# See alternative-implementations.md for feature comparison, gaps, and
# workarounds (notably: --interval is ignored, --allow-blocked uses a
# skip-and-verify workaround, and this requires Juju 3.6).

# ---------------------------------------------------------------------------
# wait_idle – wait until every Juju unit in the model is active/idle, using
# `juju wait-for application` per app.
#
# Usage (identical to the shell implementation):
#   wait_idle [--timeout SECONDS] [--interval SECONDS]
#             [--allow-blocked APP1,APP2,...]
#
# Defaults:
#   --timeout  600   (10 minutes, aggregate across all apps)
#   --interval  30   (IGNORED — wait-for uses delta streaming; a warning is
#                     emitted if a non-default value is passed)
#
# Returns 0 when all units are active/idle, 1 on timeout or error.
# ---------------------------------------------------------------------------
wait_idle() {
    local timeout=600
    local interval=30
    local allow_blocked=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --timeout)       timeout="$2";       shift 2 ;;
            --interval)      interval="$2";      shift 2 ;;
            --allow-blocked) allow_blocked="$2"; shift 2 ;;
            *) echo "wait_idle: unknown option: $1" >&2; return 1 ;;
        esac
    done

    # --interval has no effect with wait-for (delta streaming). Warn if the
    # user passed a non-default value so they are not surprised.
    if [[ "$interval" -ne 30 ]]; then
        echo "wait_idle (wait-for): --interval=${interval}s ignored (wait-for uses delta streaming)" >&2
    fi

    # Juju version guard: wait-for is removed in Juju 4.0.
    local juju_version
    juju_version=$(juju version 2>/dev/null | head -n1 | cut -d. -f1)
    if [[ -z "$juju_version" ]]; then
        echo "wait_idle (wait-for): could not determine Juju version" >&2
        return 1
    fi
    if [[ "$juju_version" -ge 4 ]]; then
        echo "wait_idle (wait-for): juju wait-for is removed in Juju 4.0; use STAT_WAIT_IMPL=shell or jubilant" >&2
        return 1
    fi

    echo "Waiting for all Juju units to be active/idle via juju wait-for (timeout=${timeout}s aggregate)…"

    # Enumerate applications from juju status. Subordinates appear in
    # `applications`, so they are included.
    local apps_json
    apps_json=$(juju status --format=json 2>/dev/null)
    if [[ -z "$apps_json" ]]; then
        echo "wait_idle (wait-for): failed to fetch juju status" >&2
        return 1
    fi

    # Build the list of apps to wait for (exclude allow-blocked apps — they
    # are expected to be blocked, so waiting for them to reach active would
    # hang forever). We verify their blocked state at the end.
    local apps_to_wait
    apps_to_wait=$(export ALLOW_BLOCKED="$allow_blocked"; \
        echo "$apps_json" | python3 -c '
import json, sys, os
data = json.load(sys.stdin)
allowed = set(os.environ.get("ALLOW_BLOCKED", "").split(",")) - {""}
apps = [name for name in data.get("applications", {}) if name not in allowed]
for a in apps:
    print(a)
')
    if [[ -z "$apps_to_wait" ]]; then
        echo "No applications to wait for (all allow-blocked or empty model)."
        juju status
        return 0
    fi

    local start_time
    start_time=$(date +%s)

    # Wait for each app in turn, passing the remaining timeout budget.
    local app
    while IFS= read -r app; do
        [[ -z "$app" ]] && continue
        local now elapsed remaining
        now=$(date +%s)
        elapsed=$(( now - start_time ))
        remaining=$(( timeout - elapsed ))
        if [[ "$remaining" -le 0 ]]; then
            echo "Timed out after ${timeout}s (aggregate). Final status:"
            juju status
            return 1
        fi
        echo "  → waiting for application '${app}' (remaining budget: ${remaining}s)…"
        if ! juju wait-for application "$app" --timeout="${remaining}s" 2>&1; then
            echo "wait_idle (wait-for): 'juju wait-for application ${app}' failed" >&2
            juju status
            return 1
        fi
    done <<< "$apps_to_wait"

    # Verify allow-blocked apps are actually blocked/idle (not error).
    if [[ -n "$allow_blocked" ]]; then
        echo "Verifying allow-blocked apps are blocked/idle…"
        if ! ALLOW_BLOCKED="$allow_blocked" bash -c '
            juju status --format=json 2>/dev/null | python3 -c "
import json, sys, os
data = json.load(sys.stdin)
allowed = set(os.environ.get(\"ALLOW_BLOCKED\", \"\").split(\",\")) - {\"\"}
bad = []
for app_name in allowed:
    app = data.get(\"applications\", {}).get(app_name)
    if app is None:
        bad.append(f\"{app_name}: not found\")
        continue
    for unit_name, unit in app.get(\"units\", {}).items():
        ws = unit.get(\"workload-status\", {}).get(\"current\", \"\")
        js = unit.get(\"juju-status\", {}).get(\"current\", \"\")
        if ws == \"error\":
            bad.append(f\"{unit_name}: error\")
        elif not (ws == \"blocked\" and js == \"idle\"):
            bad.append(f\"{unit_name}: {ws}/{js} (expected blocked/idle)\")
if bad:
    for b in bad:
        print(f\"  X {b}\", file=sys.stderr)
    sys.exit(1)
"
        '; then
            echo "wait_idle (wait-for): allow-blocked verification failed" >&2
            juju status
            return 1
        fi
    fi

    echo "All units active/idle (juju wait-for) after $(( $(date +%s) - start_time ))s."
    juju status
    return 0
}
