#!/bin/bash
# Shared helpers for tutorial spread tests.
#
# Source this file at the top of every generated script (done automatically
# by extract_commands.py):
#   . "$SPREAD_PATH/helpers.sh"
#
# NOTE: The functions below (wait_idle, retry_until_success) are designed for
# Juju-based Charmed Operator tutorials. If your tutorial does not use Juju,
# replace or extend this file with your own helpers.

# Spread SSHs in as root but does not always set HOME=/root, which causes the
# Juju client to fail looking up its config in $HOME/.local/share/juju.
export HOME=/root

# ---------------------------------------------------------------------------
# wait_idle implementation dispatcher
#
# Selects which wait_idle implementation to use based on the STAT_WAIT_IMPL
# environment variable:
#
#   STAT_WAIT_IMPL=shell    (default)  Poll juju status on a fixed interval
#   STAT_WAIT_IMPL=jubilant            Use the Jubilant Python library
#   STAT_WAIT_IMPL=waitfor             Use `juju wait-for` (Juju 3.6 only)
#
# Each implementation lives in its own file (wait-shell.sh, wait-jubilant.sh,
# wait-juju-waitfor.sh) and defines a wait_idle() function with the same
# signature. See alternative-implementations.md for a feature comparison.
# ---------------------------------------------------------------------------
_HELPERS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAT_WAIT_IMPL="${STAT_WAIT_IMPL:-shell}"

case "$STAT_WAIT_IMPL" in
    shell)
        . "$_HELPERS_DIR/wait-shell.sh"
        ;;
    jubilant)
        . "$_HELPERS_DIR/wait-jubilant.sh"
        ;;
    waitfor)
        . "$_HELPERS_DIR/wait-juju-waitfor.sh"
        ;;
    *)
        echo "helpers.sh: unknown STAT_WAIT_IMPL='$STAT_WAIT_IMPL'" >&2
        echo "Valid values: shell (default), jubilant, waitfor" >&2
        return 1 2>/dev/null || exit 1
        ;;
esac

# ---------------------------------------------------------------------------
# retry_until_success – retry a command with a fixed interval until it
# succeeds or the timeout is reached.
#
# Usage:
#   retry_until_success [--timeout SECONDS] [--interval SECONDS]
#                       [--description TEXT] -- COMMAND [ARGS...]
#
# Defaults:
#   --timeout   1200  (20 minutes)
#   --interval   120  (retry every 2 minutes)
#
# Everything after the ``--`` separator is executed as a command on each
# attempt.  If the command exits 0, the function returns 0 immediately.
# If all attempts are exhausted, returns 1.
# ---------------------------------------------------------------------------
retry_until_success() {
    local timeout=1200
    local interval=120
    local description="command"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --timeout)     timeout="$2";     shift 2 ;;
            --interval)    interval="$2";    shift 2 ;;
            --description) description="$2"; shift 2 ;;
            --)            shift; break ;;
            *) echo "retry_until_success: unknown option: $1" >&2; return 1 ;;
        esac
    done

    if [[ $# -eq 0 ]]; then
        echo "retry_until_success: no command specified after --" >&2
        return 1
    fi

    local elapsed=0
    echo "Retrying ${description} (timeout=${timeout}s, interval=${interval}s)…"

    while [[ "$elapsed" -lt "$timeout" ]]; do
        if "$@" 2>&1; then
            echo "${description} succeeded after ${elapsed}s."
            return 0
        fi
        echo "[${elapsed}s elapsed] ${description} failed – retrying in ${interval}s…"
        sleep "$interval"
        elapsed=$(( elapsed + interval ))
    done

    echo "ERROR: ${description} did not succeed within ${timeout}s"
    return 1
}
