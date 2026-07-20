#!/bin/bash
# Jubilant-based implementation of wait_idle.
#
# Uses the Jubilant Python library (https://canonical.com/juju/docs/jubilant/)
# and its Juju.wait() method with a custom readiness predicate that matches
# the classic shell semantics: every unit must be active/idle, with an
# optional allow-list for apps expected to be blocked/idle.
#
# Select with:  STAT_WAIT_IMPL=jubilant
# Sourced by helpers.sh; not intended to be sourced directly.
# See alternative-implementations.md for feature comparison and trade-offs.

# ---------------------------------------------------------------------------
# wait_idle – wait until every Juju unit in the model is active/idle, using
# Jubilant's Juju.wait().
#
# Usage (identical to the shell implementation):
#   wait_idle [--timeout SECONDS] [--interval SECONDS]
#             [--allow-blocked APP1,APP2,...]
#
# Defaults:
#   --timeout  600   (10 minutes)
#   --interval  30   (delay between status fetches, in seconds)
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

    # Ensure Jubilant is available. On Ubuntu 24.04 (PEP 668), system pip
    # install is blocked, so we use a dedicated venv at /root/.stat-venv.
    # If venv creation fails (python3-venv not installed), fall back to
    # pip install --break-system-packages as a last resort.
    local _stat_venv="/root/.stat-venv"
    local _stat_python="$_stat_venv/bin/python3"

    if ! "$_stat_python" -c "import jubilant" 2>/dev/null; then
        if python3 -m venv "$_stat_venv" 2>&1; then
            echo "Jubilant not found; installing into venv at $_stat_venv…"
            if ! "$_stat_venv/bin/pip" install --quiet jubilant 2>&1; then
                echo "wait_idle: failed to install jubilant into venv" >&2
                return 1
            fi
        else
            echo "venv creation failed (python3-venv not installed?); falling back to system pip --break-system-packages…" >&2
            if ! python3 -m pip install --quiet --break-system-packages jubilant 2>&1; then
                echo "wait_idle: failed to install jubilant" >&2
                return 1
            fi
            _stat_python="python3"
        fi
    fi

    echo "Waiting for all Juju units to be active/idle via Jubilant (timeout=${timeout}s, delay=${interval}s)…"

    # Export parameters for the embedded Python script.
    export _WAIT_TIMEOUT="$timeout"
    export _WAIT_DELAY="$interval"
    export _WAIT_ALLOW_BLOCKED="$allow_blocked"

    # Run the Jubilant wait in Python. We catch TimeoutError and WaitError
    # and translate them to shell return codes (0 success, 1 failure).
    if "$_stat_python" - <<'PYEOF'
import os
import sys

import jubilant

timeout = float(os.environ["_WAIT_TIMEOUT"])
delay = float(os.environ["_WAIT_DELAY"])
allow_blocked = {
    a.strip() for a in os.environ["_WAIT_ALLOW_BLOCKED"].split(",") if a.strip()
}


def ready(status: jubilant.Status) -> bool:
    """Return True when every unit is active/idle (or blocked/idle for
    allow-listed apps). Returns False if no units exist yet (provisioning)
    or if any unit is not yet settled."""
    total_units = 0
    for app_name, app in status.apps.items():
        units = status.get_units(app_name)
        for _unit_name, unit in units.items():
            total_units += 1
            ws = unit.workload_status.current
            js = unit.juju_status.current
            if ws == "active" and js == "idle":
                continue
            if ws == "blocked" and js == "idle" and app_name in allow_blocked:
                continue
            return False
    return total_units > 0


def on_error(status: jubilant.Status) -> bool:
    """Fail fast if any unit enters error status."""
    for app_name, app in status.apps.items():
        if app.app_status.current == "error":
            return True
        for _unit_name, unit in status.get_units(app_name).items():
            if unit.workload_status.current == "error":
                return True
    return False


juju = jubilant.Juju()
try:
    juju.wait(
        ready,
        timeout=timeout,
        delay=delay,
        successes=1,
        error=on_error,
    )
except (TimeoutError, jubilant.WaitError) as exc:
    print(f"wait_idle: {type(exc).__name__}: {exc}", file=sys.stderr)
    # Print final status for debugging.
    try:
        import subprocess
        subprocess.run(["juju", "status"])
    except Exception:
        pass
    sys.exit(1)

# Success — print final status (matches shell implementation output).
import subprocess
subprocess.run(["juju", "status"])
PYEOF
    then
        echo "All units active/idle (Jubilant)."
        return 0
    else
        return 1
    fi
}
