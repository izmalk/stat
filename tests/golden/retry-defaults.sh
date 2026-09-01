#!/bin/bash
# Extracted from : tests/fixtures/retry-defaults.md
# Regenerate with: python3 extract_commands.py tests/fixtures/retry-defaults.md <output.sh>
#
# Only ```shell fences are extracted; use any other tag to naturally exclude a block.

set -euo pipefail

# Load shared helpers (wait_idle, retry_until_success, etc.).
HELPERS="${SPREAD_PATH:-$(cd "$(dirname "$0")" && pwd)}/helpers.sh"
. "$HELPERS"

retry_until_success --timeout 1200 --interval 120 --description command -- curl -sf http://localhost:8080/health
