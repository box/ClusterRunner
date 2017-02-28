#!/usr/bin/env bats

load ../all

@test "flunk returns status code of 1" {
  set +e
  flunk msg
  status=$?
  set -e

  test $status = 1
}

@test "flunk emits the given message to STDERR" {
  set +e
  stderr=$( { flunk message; } 2>&1 )
  set -e

  test "$stderr" = "message"
}

@test "flunk accepts error message on STDIN" {
  set +e
  stderr=$( { echo message | flunk; } 2>&1 )
  set -e

  test "$stderr" = "message"
}

@test "flunk replaces \$BATS_TMPDIR" {
  set +e
  stderr=$( { flunk "bats tmpdir: $BATS_TMPDIR"; } 2>&1 )
  set -e

  test "$stderr" = "bats tmpdir: \${BATS_TMPDIR}"
}
