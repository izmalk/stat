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

<!-- test:await-idle --timeout 900 -->

## Deploy the application

```shell
juju deploy my-app --channel=latest/stable
```

<!-- test:await-idle --timeout 600 --allow-blocked my-app -->

## Verify deployment

<!-- test:assert
juju status --format json | jq -e '.applications."my-app".application-status.current == "active"'
-->

## Skip an optional step

The next block is skipped during testing (e.g. a browser-only command):

<!-- test:skip -->

```shell
open https://dashboard.example.com
```

## Run hidden setup commands

Sometimes tests need extra commands not shown to readers:

<!-- test:run
juju config my-app debug-mode=true
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

## Long-running operation with timeout

<!-- test:run-with-timeout --seconds 120 -->

```shell
my-app rebuild-index
```

## Retry a flaky command

<!-- test:retry --timeout 600 --interval 60 --description "wait for endpoint" -- curl -sf http://localhost:8080/health -->
