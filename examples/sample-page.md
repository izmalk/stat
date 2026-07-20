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

This tutorial page demonstrates all available STAT annotations using the
`self-signed-certificates` charm — a real, simple charm available on Charmhub.

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

Deploy the `self-signed-certificates` charm from Charmhub:

```shell
juju deploy self-signed-certificates --channel=latest/stable
```

<!-- test:await-idle --timeout 600 -->

## Verify deployment

<!-- test:assert
juju status --format json | jq -e '.applications."self-signed-certificates".application-status.current == "active"'
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
juju config self-signed-certificates ca-common-name="stat-test"
-->

## Long-running operation with timeout

<!-- test:run-with-timeout --seconds 10 -->

```shell
juju debug-log --replay --tail
```

## Retry a flaky command

<!-- test:retry --timeout 60 --interval 5 --description "juju status responds" -- juju status --format=oneline -->

