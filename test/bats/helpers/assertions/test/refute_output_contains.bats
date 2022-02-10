#!/usr/bin/env bats

load ../all

setup() {
  output=foobar
}

@test "refute_output_contains should pass when output doesn't contain needle" {
  set +e
  refute_output_contains baz
  status=$?
  set -e

  test $status = 0
}

@test "refute_output_contains should fail when output contains needle" {
  set +e
  refute_output_contains bar
  status=$?
  set -e

  test $status = 1
}

@test "refute_output_contains should emit error message when fails" {
  set +e
  stderr=$( { refute_output_contains bar; } 2>&1 )
  set -e

  test "$stderr" = $'expected:       foobar\nnot to contain: bar'
}

@test "refute_output_contains can take argument from STDIN" {
  set +e
  stderr=$( { echo bar | refute_output_contains; } 2>&1 )
  status=$?
  set -e

  test $status = 1
  test "$stderr" = $'expected:       foobar\nnot to contain: bar'
}
