#!/bin/bash
# Extracted from : tests/fixtures/set-variables.md
# Regenerate with: python3 extract_commands.py tests/fixtures/set-variables.md <output.sh>
#
# Only ```shell fences are extracted; use any other tag to naturally exclude a block.

set -euo pipefail

# Load shared helpers (wait_idle, retry_until_success, etc.).
HELPERS="${SPREAD_PATH:-$(cd "$(dirname "$0")" && pwd)}/helpers.sh"
. "$HELPERS"

_CMD_OUTPUT=$(juju run my-app/leader get-credentials)
MY_USER=$(echo "$_CMD_OUTPUT" | grep 'username:' | awk '{print $2}')
MY_PASS=$(echo "$_CMD_OUTPUT" | grep 'password:' | awk '{print $2}')

my-cli login --user ${MY_USER} --password ${MY_PASS}
