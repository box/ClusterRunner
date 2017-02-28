#!/usr/bin/env bats

load ../all

setup() {
  lines=('one fish' 'two fish' 'red fish' 'blue fish')
}

@test "refute_line should fail when the given line is found" {
  set +e
  refute_line "red fish"
  status=$?
  set -e

  test $status = 1
}

@test "refute_line should pass when the given line isn't found" {
  set +e
  refute_line "green eggs and ham"
  status=$?
  set -e

  test $status = 0
}

@test "refute_line should emit error message when it fails" {
  set +e
  stderr=$( { refute_line "red fish"; } 2>&1 )
  set -e

  test "$stderr" = $'expected to not find line: red fish\nin:\none fish\ntwo fish\nred fish\nblue fish'
}

@test "refute_line can match against a given line index" {
  # success
  set +e
  refute_line 0 "red fish"
  status=$?
  set -e

  test $status = 0

  # failure
  set +e
  stderr=$( { refute_line 2 "red fish"; } 2>&1 )
  status=$?
  set -e

  test $status = 1
  test "$stderr" = $'unexpectedly equal: red fish'
}
