flunk() {
  { if [ "$#" -eq 0 ]; then cat -
    else echo "$@"
    fi
  } | sed "s:${BATS_TMPDIR}:\${BATS_TMPDIR}:g" >&2
  return 1
}

assert() {
  if ! "$@"; then
    flunk "failed: $@"
  fi
}

refute() {
  if "$@"; then
    flunk "expected to fail: $@"
  fi
}

assert_success() {
  if [ "$status" -ne 0 ]; then
    { echo "command failed with exit status $status"
      echo "output: $output"
    } | flunk
  elif [ "$#" -gt 0 ]; then
    assert_output "$1"
  fi
}

assert_failure() {
  if [ "$status" -eq 0 ]; then
    flunk "expected failed exit status"
  elif [ "$#" -gt 0 ]; then
    assert_output "$1"
  fi
}

assert_equal() {
  if [ "$1" != "$2" ]; then
    { echo "expected: $1"
      echo "actual:   $2"
    } | flunk
  fi
}

refute_equal() {
  if [ "$1" = "$2" ]; then
    flunk "unexpectedly equal: $1"
  fi
}

assert_not_equal() {
  refute_equal "$@"
}

assert_contains() {
  local haystack="$1"
  local needle="$2"
  echo "$haystack" | $(type -p ggrep grep | head -1) -F "$needle" >/dev/null || {
    { echo "expected:   $haystack"
      echo "to contain: $needle"
    } | flunk
  }
}

refute_contains() {
  local haystack="$1"
  local needle="$2"
  ! assert_contains "$haystack" "$needle" || {
    { echo "expected:       $haystack"
      echo "not to contain: $needle"
    } | flunk
  }
}

assert_starts_with() {
  if [ "$1" = "${1#${2}}" ]; then
    { echo "expected: $1"
      echo "to start with: $2"
    } | flunk
  fi
}

assert_output() {
  local expected
  if [ $# -eq 0 ]; then expected="$(cat -)"
  else expected="$1"
  fi
  assert_equal "$expected" "$output"
}

assert_output_contains() {
  local expected
  if [ $# -eq 0 ]; then expected="$(cat -)"
  else expected="$1"
  fi
  assert_contains "$output" "$expected"
}

refute_output_contains() {
  local expected
  if [ $# -eq 0 ]; then expected="$(cat -)"
  else expected="$1"
  fi
  refute_contains "$output" "$expected"
}

assert_line() {
  if [ "$1" -ge 0 ] 2>/dev/null; then
    assert_equal "$2" "${lines[$1]}"
  else
    local line
    for line in "${lines[@]}"; do
      if [ "$line" = "$1" ]; then return 0; fi
    done
    { echo "expected line: $1"
      echo "to be found in:"
      ( IFS=$'\n'; echo "${lines[*]}" )
    } | flunk
  fi
}

refute_line() {
  if [ "$1" -ge 0 ] 2>/dev/null; then
    refute_equal "$2" "${lines[$1]}"
  else
    local line
    for line in "${lines[@]}"; do
      if [ "$line" = "$1" ]; then
        { echo "expected to not find line: $line"
          echo "in:"
          ( IFS=$'\n'; echo "${lines[*]}" )
        } | flunk
        return $? # in case flunk didn't exit the loop
      fi
    done
  fi
}
