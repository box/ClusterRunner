#!/usr/bin/env bats

load ../all

@test "assert_contains should pass when it matches" {
  set +e
  assert_contains foobar bar
  status=$?
  set -e

  test $status = 0
}

@test "assert_contains should fail when it doesn't match" {
  set +e
  assert_contains foo bar
  status=$?
  set -e

  test $status = 1
}

@test "assert_contains should emit error message when fails" {
  set +e
  stderr=$( { assert_contains foo bar; } 2>&1 )
  set -e

  test "$stderr" = $'expected:   foo\nto contain: bar'
}
