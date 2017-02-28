#!/usr/bin/env bats

load ../all

@test "refute should pass with failed command" {
  set +e
  refute "false"
  status=$?
  set -e

  test $status = 0
}

@test "refute should fail for successful commands" {
  set +e
  refute "true"
  status=$?
  set -e

  test $status = 1
}

@test "refute should emit failure message for successful commands" {
  set +e
  stderr=$( { refute "true"; } 2>&1 )
  set -e

  test "$stderr" = "succeeded: true"
}
