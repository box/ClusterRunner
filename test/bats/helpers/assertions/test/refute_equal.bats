#!/usr/bin/env bats

load ../all

@test "refute_equal should fail when equal" {
  set +e
  refute_equal foo foo
  status=$?
  set -e

  test $status = 1
}

@test "refute_equal should pass when not equal" {
  set +e
  refute_equal foo bar
  status=$?
  set -e

  test $status = 0
}

@test "refute_equal should emit message on failure" {
  set +e
  stderr=$( { refute_equal foo foo; } 2>&1 )
  set -e

  test "$stderr" = $'unexpectedly equal: foo'
}
