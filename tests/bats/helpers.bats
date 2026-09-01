#!/usr/bin/env bats
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Functional tests for helpers.sh using a mocked juju binary.

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
HELPERS="$REPO_ROOT/helpers.sh"
MOCKS="$REPO_ROOT/tests/bats/mocks"

setup() {
    export PATH="$MOCKS:$PATH"
    # Reset the mock sequence counter between tests.
    rm -f "${BATS_TMPDIR:-/tmp}/juju-mock-counter"
}

# ---------------------------------------------------------------------------
# wait_idle
# ---------------------------------------------------------------------------

@test "wait_idle: returns 0 when all units are active/idle" {
    export JUJU_MOCK_STATE=all-idle
    run bash -c ". \"$HELPERS\" && wait_idle --timeout 5 --interval 1"
    [ "$status" -eq 0 ]
    [[ "$output" == *"All units active/idle"* ]]
}

@test "wait_idle: tolerates blocked/idle apps listed in --allow-blocked" {
    export JUJU_MOCK_STATE=blocked-idle
    run bash -c ". \"$HELPERS\" && wait_idle --timeout 5 --interval 1 --allow-blocked data-integrator"
    [ "$status" -eq 0 ]
}

@test "wait_idle: fails on blocked units without --allow-blocked" {
    export JUJU_MOCK_STATE=blocked-idle
    run bash -c ". \"$HELPERS\" && wait_idle --timeout 2 --interval 1"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Timed out"* ]]
}

@test "wait_idle: empty model reports provisioning then times out" {
    export JUJU_MOCK_STATE=empty
    run bash -c ". \"$HELPERS\" && wait_idle --timeout 2 --interval 1"
    [ "$status" -eq 1 ]
    [[ "$output" == *"still provisioning"* ]]
}

@test "wait_idle: malformed juju status is treated as provisioning" {
    export JUJU_MOCK_STATE=broken
    run bash -c ". \"$HELPERS\" && wait_idle --timeout 2 --interval 1"
    [ "$status" -eq 1 ]
    [[ "$output" == *"still provisioning"* ]]
}

@test "wait_idle: succeeds after units settle (state sequence)" {
    export JUJU_MOCK_SEQUENCE="empty,one-busy,all-idle"
    run bash -c ". \"$HELPERS\" && wait_idle --timeout 10 --interval 1"
    [ "$status" -eq 0 ]
    [[ "$output" == *"still provisioning"* ]]
    [[ "$output" == *"not yet active/idle"* ]]
    [[ "$output" == *"All units active/idle"* ]]
}

@test "wait_idle: unknown option returns 1" {
    run bash -c ". \"$HELPERS\" && wait_idle --bogus"
    [ "$status" -eq 1 ]
    [[ "$output" == *"unknown option"* ]]
}

# ---------------------------------------------------------------------------
# retry_until_success
# ---------------------------------------------------------------------------

@test "retry_until_success: succeeds on first try" {
    run bash -c ". \"$HELPERS\" && retry_until_success --timeout 5 --interval 1 -- true"
    [ "$status" -eq 0 ]
    [[ "$output" == *"succeeded after 0s"* ]]
}

@test "retry_until_success: succeeds after a failing command starts passing" {
    local flag="$BATS_TMPDIR/retry-flag"
    rm -f "$flag"
    # A command that fails until the flag file appears; created by a
    # background touch after one second.
    ( sleep 1 && touch "$flag" ) &
    run bash -c ". \"$HELPERS\" && retry_until_success --timeout 10 --interval 1 -- test -f '$flag'"
    [ "$status" -eq 0 ]
    rm -f "$flag"
}

@test "retry_until_success: times out when the command never succeeds" {
    run bash -c ". \"$HELPERS\" && retry_until_success --timeout 2 --interval 1 -- false"
    [ "$status" -eq 1 ]
    [[ "$output" == *"ERROR: command did not succeed"* ]]
}

@test "retry_until_success: no command after -- returns 1" {
    run bash -c ". \"$HELPERS\" && retry_until_success --timeout 1 --interval 1 --"
    [ "$status" -eq 1 ]
    [[ "$output" == *"no command specified"* ]]
}

@test "retry_until_success: unknown option returns 1" {
    run bash -c ". \"$HELPERS\" && retry_until_success --bogus -- true"
    [ "$status" -eq 1 ]
    [[ "$output" == *"unknown option"* ]]
}

# ---------------------------------------------------------------------------
# collect_diagnostics
# ---------------------------------------------------------------------------

@test "collect_diagnostics: succeeds without juju and writes host files" {
    local dir="$BATS_TMPDIR/diag-$$"
    run bash -c ". \"$HELPERS\" && collect_diagnostics --dir '$dir'"
    [ "$status" -eq 0 ]
    [ -f "$dir/free.txt" ]
    [ -f "$dir/df.txt" ]
    [ -f "$dir/sysctl.txt" ]
    rm -rf "$dir"
}

@test "collect_diagnostics: unknown option returns 1" {
    run bash -c ". \"$HELPERS\" && collect_diagnostics --bogus"
    [ "$status" -eq 1 ]
    [[ "$output" == *"unknown option"* ]]
}
