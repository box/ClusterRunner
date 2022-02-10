#!/usr/bin/env bats

load ../all

@test "assert should pass with successful command" {
  set +e
  assert "true"
  status=$?
  set -e

  test $status = 0
}

@test "assert should fail for failed commands" {
  set +e
  assert "false"
  status=$?
  set -e

  test $status = 1
}

@test "assert should emit failure message for failed commands" {
  set +e
  stderr=$( { assert "false"; } 2>&1 )
  set -e

  test "$stderr" = "failed: false"
}
