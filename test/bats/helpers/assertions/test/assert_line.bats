#!/usr/bin/env bats

load ../all

setup() {
  lines=('one fish' 'two fish' 'red fish' 'blue fish')
}

@test "assert_line should pass when the given line is found" {
  set +e
  assert_line "red fish"
  status=$?
  set -e

  test $status = 0
}

@test "assert_line should fail when the given line isn't found" {
  set +e
  assert_line "green eggs and ham"
  status=$?
  set -e

  test $status = 1
}

@test "assert_line should emit error message when it fails" {
  set +e
  stderr=$( { assert_line "green eggs and ham"; } 2>&1 )
  set -e

  test "$stderr" = $'expected line: green eggs and ham\nto be found in:\none fish\ntwo fish\nred fish\nblue fish'
}

@test "assert_line can match against a given line index" {
  # success
  set +e
  assert_line 2 "red fish"
  status=$?
  set -e

  test $status = 0

  # failure
  set +e
  stderr=$( { assert_line 0 "red fish"; } 2>&1 )
  status=$?
  set -e

  test $status = 1
  test "$stderr" = $'expected: red fish\nactual:   one fish'
}
