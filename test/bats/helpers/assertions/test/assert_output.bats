#!/usr/bin/env bats

load ../all

setup() {
  output=foo
}

@test "assert_output should pass when it matches" {
  set +e
  assert_output foo
  status=$?
  set -e

  test $status = 0
}

@test "assert_output should fail when it doesn't match" {
  set +e
  assert_output bar
  status=$?
  set -e

  test $status = 1
}

@test "assert_output should emit error message when fails" {
  set +e
  stderr=$( { assert_output bar; } 2>&1 )
  set -e

  test "$stderr" = $'expected: bar\nactual:   foo'
}

@test "assert_output can take argument from STDIN" {
  set +e
  stderr=$( { echo bar | assert_output; } 2>&1 )
  status=$?
  set -e

  test $status = 1
  test "$stderr" = $'expected: bar\nactual:   foo'
}
