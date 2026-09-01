#!/bin/bash
# Extracted from : tests/fixtures/heading-in-fence.md
# Regenerate with: python3 extract_commands.py tests/fixtures/heading-in-fence.md <output.sh>
#
# Only ```shell fences are extracted; use any other tag to naturally exclude a block.

set -euo pipefail

# Load shared helpers (wait_idle, retry_until_success, etc.).
HELPERS="${SPREAD_PATH:-$(cd "$(dirname "$0")" && pwd)}/helpers.sh"
. "$HELPERS"

echo done
