#!/usr/bin/env bats

load ../all

@test "refute_contains should pass when needle isn't found" {
  set +e
  refute_contains foobar baz
  status=$?
  set -e

  test $status = 0
}

@test "refute_contains should fail when needle is found" {
  set +e
  refute_contains foobar bar
  status=$?
  set -e

  test $status = 1
}

@test "refute_contains should emit error message when fails" {
  set +e
  stderr=$( { refute_contains foobar bar; } 2>&1 )
  set -e

  test "$stderr" = $'expected:       foobar\nnot to contain: bar'
}
