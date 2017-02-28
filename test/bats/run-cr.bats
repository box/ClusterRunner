#!/usr/bin/env bats

load test_helper

@test "'run-cr' script displays help." {
	run ./run-cr
	assert_contains "$output" "Usage:"
}

@test "CR-BIN: Help msg displayed by image built from binary." {
	run ./run-cr bin -h
	assert_contains "$output" "usage: clusterrunner"
}

@test "CR-SRC: Help msg displayed by image built from source." {
	run ./run-cr src -h
	assert_contains "$output" "usage: main.py"
}
