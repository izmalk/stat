---
myst:
  html_meta:
    description: "Sample tutorial page demonstrating STAT annotations."
---

<!-- test:spread
priority: 100
kill-timeout: 20m
-->

# Set up the environment

This tutorial page demonstrates all available STAT annotations.

## Install dependencies

The following `shell` block will be extracted and executed:

```shell
sudo snap install juju --channel=3/stable
```

This `text` block is **not** extracted (only `shell` fences are):

```text
This is just example output — it won't be executed.
```

## Bootstrap Juju

<!-- test:wait --seconds 5 -->

```shell
juju bootstrap localhost overlord
```

<!-- test:await-idle --timeout 900 --interval 15 -->

## Deploy the application

```shell
juju deploy my-app --channel=latest/stable
```

<!-- test:await-idle --timeout 600 --allow-blocked my-app -->

## Verify deployment

<!-- test:assert
juju status --format json | jq -e '.applications."my-app".application-status.current == "active"'
-->

Structured checks are more robust with inline Python than with grep:

<!-- test:assert
juju status --format=json | python3 -c '
import json, sys
data = json.load(sys.stdin)
units = data["applications"]["my-app"]["units"]
assert len(units) == 1, f"expected 1 unit, got {len(units)}"
for name, unit in units.items():
    ws = unit["workload-status"]["current"]
    assert ws == "active", f"{name} is {ws}, not active"
print("all units active")
'
-->

## Skip an optional step

The next block is skipped during testing (e.g. a browser-only command):

<!-- test:skip -->

```shell
open https://dashboard.example.com
```

## Run hidden setup commands

Sometimes tests need extra commands not shown to readers — e.g. a
non-interactive variant of a command the docs show interactively:

<!-- test:run
juju config my-app debug-mode=true
-->

Hidden blocks can also materialise data files the docs only show as fenced
content:

<!-- test:run
cat > bulk-data.json << 'EOF'
{"album": "Abbey Road", "year": 1969}
EOF
-->

## Extract credentials

<!-- test:set-variables
command: juju run my-app/leader get-credentials
MY_USER: username
MY_PASS: password
-->

Use the credentials to connect:

```shell
my-cli login --user <username> --password <password>
```

Multi-line values (e.g. a CA certificate) can be sliced out of the command
output in a hidden block and written to a file:

<!-- test:run
MY_CA=$(echo "$_CMD_OUTPUT" | sed -n '/ca-cert:/,/username:/{ /ca-cert:/d; /username:/d; p }' | sed 's/^    //')
echo "$MY_CA" > demo-ca.pem
-->

## Long-running operation with timeout

<!-- test:run-with-timeout --seconds 120 -->

```shell
my-app rebuild-index
```

## Retry a flaky command

<!-- test:retry --timeout 600 --interval 60 --description "wait for endpoint" -- curl -sf http://localhost:8080/health -->

Commands with pipes or redirects need `--shell` (by default every token is
quoted, so the command runs as a single argv):

<!-- test:retry --shell --timeout 600 --interval 30 --description "endpoint reports ok" -- curl -sf http://localhost:8080/health | grep -q ok -->

## Remove a unit

The docs show the interactive form; the test runs the non-interactive
variant in a hidden block:

```shell
juju remove-unit my-app/1
```

<!-- test:run
juju remove-unit my-app/1 --no-prompt
-->

<!-- test:await-idle --timeout 600 -->
