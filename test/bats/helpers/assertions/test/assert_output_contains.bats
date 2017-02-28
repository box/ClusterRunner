#!/usr/bin/env bats

load ../all

setup() {
  output=foobar
}

@test "assert_output_contains should pass when true" {
  set +e
  assert_output_contains bar
  status=$?
  set -e

  test $status = 0
}

@test "assert_output_contains should fail when it doesn't match" {
  set +e
  assert_output_contains baz
  status=$?
  set -e

  test $status = 1
}

@test "assert_output_contains should emit error message when fails" {
  set +e
  stderr=$( { assert_output_contains baz; } 2>&1 )
  set -e

  test "$stderr" = $'expected:   foobar\nto contain: baz'
}

@test "assert_output_contains can take argument from STDIN" {
  set +e
  stderr=$( { echo baz | assert_output_contains; } 2>&1 )
  status=$?
  set -e

  test $status = 1
  test "$stderr" = $'expected:   foobar\nto contain: baz'
}
