#!/bin/bash
# Extracted from : tests/fixtures/multi-annotation-page.md
# Regenerate with: python3 extract_commands.py tests/fixtures/multi-annotation-page.md <output.sh>
#
# Only ```shell fences are extracted; use any other tag to naturally exclude a block.

set -euo pipefail

# Load shared helpers (wait_idle, retry_until_success, etc.).
HELPERS="${SPREAD_PATH:-$(cd "$(dirname "$0")" && pwd)}/helpers.sh"
. "$HELPERS"

sleep 10

echo first

wait_idle --timeout 900 --interval 30

echo hidden

# --- Test assertion ---
test -f /tmp/done

echo last
