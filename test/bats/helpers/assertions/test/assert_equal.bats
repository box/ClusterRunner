#!/usr/bin/env bats

load ../all

@test "assert_equal should pass when equal" {
  set +e
  assert_equal foo foo
  status=$?
  set -e

  test $status = 0
}

@test "assert_equal should fail when not equal" {
  set +e
  assert_equal foo bar
  status=$?
  set -e

  test $status = 1
}

@test "assert_equal should emit message on failure" {
  set +e
  stderr=$( { assert_equal foo bar; } 2>&1 )
  set -e

  test "$stderr" = $'expected: foo\nactual:   bar'
}
