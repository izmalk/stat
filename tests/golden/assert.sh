#!/bin/bash
# Extracted from : tests/fixtures/assert.md
# Regenerate with: python3 extract_commands.py tests/fixtures/assert.md <output.sh>
#
# Only ```shell fences are extracted; use any other tag to naturally exclude a block.

set -euo pipefail

# Load shared helpers (wait_idle, retry_until_success, etc.).
HELPERS="${SPREAD_PATH:-$(cd "$(dirname "$0")" && pwd)}/helpers.sh"
. "$HELPERS"

# --- Test assertion ---
juju status --format json | jq -e '.applications."my-app".application-status.current == "active"'
