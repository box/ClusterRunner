#!/usr/bin/env bats

load test_helper

CR_SRC=yamaszone/clusterrunner:src
CR_DEMO_REPO=https://github.com/boxengservices/ClusterRunnerDemo.git

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

#slow-test
@test "CR-SRC: Image built from source can build job properly." {
	git clone $CR_DEMO_REPO /tmp/cr-demo
	cd /tmp/cr-demo
	run docker run --rm -v $PWD:/sut -w /sut $CR_SRC build --job-name Simple
	assert_contains "$output" "NO_FAILURES"
	cd -
	# Needs super user privilege as build artefacts are written as root
	sudo rm -rf /tmp/cr-demo
}
