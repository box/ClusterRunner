#!/usr/bin/env bats

load ../all

setup() {
  status=0
  output="good job"
}

@test "assert_success should pass on 0 \$status" {
  set +e
  assert_success
  status=$?
  set -e

  test $status = 0
}

@test "assert_success should fail on non-zero \$status" {
  status=1

  set +e
  assert_success
  status=$?
  set -e

  test $status = 1
}

@test "assert_success should emit message on failure" {
  status=7
  output="my bad"

  set +e
  stderr=$( { assert_success; } 2>&1 )
  set -e

  test "$stderr" = $'command failed with exit status 7\noutput: my bad'
}

@test "assert_success should pass when output matches argument" {
  set +e
  assert_success "good job"
  status=$?
  set -e

  test $status = 0
}

@test "assert_success should fail when output doesn't match argument" {
  set +e
  stderr=$( { assert_success "my bad"; } 2>&1 )
  status=$?
  set -e

  test $status = 1
  test "$stderr" = $'expected: my bad\nactual:   good job'
}
