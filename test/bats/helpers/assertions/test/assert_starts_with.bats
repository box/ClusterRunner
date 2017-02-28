#!/usr/bin/env bats

load ../all

@test "assert_starts_with should pass when it matches" {
  set +e
  assert_starts_with foobar foo
  status=$?
  set -e

  test $status = 0
}

@test "assert_starts_with should fail when it doesn't match" {
  set +e
  assert_starts_with foo bar
  status=$?
  set -e

  test $status = 1
}

@test "assert_starts_with should emit error message when fails" {
  set +e
  stderr=$( { assert_starts_with foo bar; } 2>&1 )
  set -e

  test "$stderr" = $'expected: foo\nto start with: bar'
}

@test "assert_starts_with should not match empty string" {
  set +e
  assert_starts_with foo ""
  status=$?
  set -e

  test $status = 1
}

@test "assert_starts_with should match original string" {
  set +e
  assert_starts_with foo foo
  status=$?
  set -e

  test $status = 0
}
