.PHONY: all lint test init pylint pep8 test-unit test-unit-via-clusterrunner test-functional
.PHONY: clean wheels pex

BIN := dist/clusterrunner

# Macro for printing a colored message to stdout
print_msg = @printf "\n\033[1;34m***%s***\033[0m\n" "$(1)"

all: lint test
lint: pylint pep8
test: test-unit test-integration test-functional

.pre-init:
	pip install --upgrade pip
	@# Constrain setuptools because pylint is not compatible with newer versions.
	pip install setuptools==33.1.1

init: .pre-init
	$(call print_msg, Installing requirements... )
	pip install --upgrade -r requirements.txt

init-dev: .pre-init
	$(call print_msg, Installing dev requirements... )
	pip install --upgrade -r dev-requirements.txt

pylint:
	$(call print_msg, Running pylint... )
	PYTHONPATH=.:$(PYTHONPATH) pylint --load-plugins=test.framework.pylint app

pep8:
	$(call print_msg, Running pep8... )
	pep8 --max-line-length=160 app

test-unit:
	$(call print_msg, Running unit tests... )
	nosetests -v test/unit

test-unit-with-coverage:
	$(call print_msg, Running unit tests with coverage... )
	nosetests -v --with-xcoverage --cover-package=app test/unit

test-integration:
	$(call print_msg, Running unit tests... )
	nosetests -v test/integration

test-integration-with-coverage:
	$(call print_msg, Running unit tests with coverage... )
	nosetests -v --with-xcoverage --cover-package=app test/integration

test-unit-via-clusterrunner: $(BIN)
	$(call print_msg, Running unit tests via ClusterRunner... )
	python $(BIN) build --job-name Unit
	python $(BIN) stop

test-functional:
	$(call print_msg, Running functional tests... )
	nosetests -s -v test/functional

# Use platform flag to build multi-platform pex (requires platform wheels).
# --platform=macosx-10.12-x86_64 --platform=linux_x86_64 --platform=win64_amd
WHEEL_CACHE := $(PWD)/dist/wheels
PEX_ARGS    := -v --no-pypi --cache-dir=$(WHEEL_CACHE)

clean:
	rm -rf *.egg-info build      # Remove to prevent caching of setup.py and MANIFEST.in
	rm -rf $(WHEEL_CACHE) $(BIN)

# INFO: The use of multiple targets (before the :) in the next sections enable
#       a technique for setting some targets to "phony" so they will always
#       run, while allowing other targets to remain conditional based on the
#       dependencies (after the :).

# TODO: Consider using "pip download --platform" when direct downloading of
#       cross-platform wheels is supported.
wheels $(WHEEL_CACHE): requirements.txt
	$(call print_msg, Creating wheels cache... )
	mkdir -p $(WHEEL_CACHE)
	pip wheel -r requirements.txt --wheel-dir $(WHEEL_CACHE)

pex $(BIN): $(WHEEL_CACHE)
	$(call print_msg, Running pex... )
	@# Do not cache the ClusterRunner build.
	rm -f $(WHEEL_CACHE)/ClusterRunner*
	./setup.py bdist_pex --bdist-all --pex-args="$(PEX_ARGS)"
