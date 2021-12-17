# Enable second expansion of the prerequisites for all targets defined in the
# Makefile. This feature is used by "release" target so that the RPM file name
# can be dynamically calculated before the prerequisite is evaluated.
#
# See https://www.gnu.org/software/make/manual/html_node/Secondary-Expansion.html
.SECONDEXPANSION:

.PHONY: all lint test init pylint pep8 test-unit test-unit-via-clusterrunner test-functional
.PHONY: clean wheels pex

DIST_DIR := ./dist
CR_BIN   := $(DIST_DIR)/clusterrunner
CR_CONF  := ./conf/default_clusterrunner.conf
CR_UNK_VERSION := 0.0.0   # Default CR version used when git repo is missing.

# ## Python defines
PY_EGG_INFO_DIR := ./clusterrunner.egg-info
PY_PKG_INFO     := $(PY_EGG_INFO_DIR)/PKG-INFO
# TODO: Use platform flag to build multi-platform pex (requires platform wheels).
#       --platform=macosx-10.12-x86_64
#       --platform=linux_x86_64
#       --platform=win64_amd
PY_WHEEL_CACHE := $(PWD)/$(DIST_DIR)/wheels
# Pex will source all wheel dependencies from the PY_WHEEL_CACHE. It is necessary
# to set the Cache TTL to 0 so that pex will accept any matching wheel,
# regardless of its timestamp.
PEX_ARGS := -v --no-pypi --cache-dir=$(PY_WHEEL_CACHE) --cache-ttl=0

# ## RPM defines
RPM_BASE_DIR       := /var/lib/clusterrunner
RPM_CR_CONF        := $(RPM_BASE_DIR)/clusterrunner.conf
RPM_DEPENDS        := python34u git
RPM_USER           := jenkins
RPM_GROUP          := engineering
# Auto-detect packaging info from PKG-INFO
RPM_DESCRIPTION = $(call pkg_info,summary)
RPM_LICENSE     = $(call pkg_info,license)
RPM_NAME        = $(call pkg_info,name)
RPM_URL         = $(call pkg_info,home-page)
RPM_VENDOR      = $(call pkg_info,author)
RPM_VERSION     = $(call pkg_info,version)
# Currently unused but consider adjusting value for snapshost releases.
RPM_RELEASE     = 1
RPM_FILE        = clusterrunner-$(subst -,_,$(RPM_VERSION))-$(RPM_RELEASE).x86_64.rpm
RPM_PATH        = $(DIST_DIR)/$(RPM_FILE)

# ## FPM Defines
# Collect all package info fields into fpm args
FPM_INFO_ARGS = --name "$(RPM_NAME)" \
                --version "$(RPM_VERSION)" \
                --iteration "$(RPM_RELEASE)" \
                --license "$(RPM_LICENSE)" \
                --description "$(RPM_DESCRIPTION)" \
                --vendor "$(RPM_VENDOR)" \
                --maintainer "$(RPM_VENDOR)" \
                --url "$(RPM_URL)"
# Expand all dependencies into fpm args
FPM_DEPEND_ARGS = $(addprefix --depends , $(RPM_DEPENDS))

# ## Docker defines
DOCKER_TAG := productivity/clusterrunner

# ## Artifactory defines
# Select the release repo based on if version string is an "official" release
# (i.e. N.N.N) or "snapshot".
ARTIFACTORY_REPO = \
	$(shell grep --quiet --extended-regexp '^[0-9]+\.[0-9]+\.[0-9]+$$' <<< $(RPM_VERSION) && \
	echo productivity || \
	echo productivity-snapshots)
ARTIFACTORY_URL = https://box.jfrog.io/box/$(ARTIFACTORY_REPO)/com/box/clusterrunner


# Macro for printing a colored message to stdout
print_msg = @printf "\n\033[1;34m***%s***\033[0m\n" "$(1)"

# Macro for extracting key values from PKG-INFO.
# IMPORTANT: $(PY_PKG_INFO) must be a dependency of any targets that use this macro.
pkg_info = $(strip $(shell egrep -i "^$(1): " $(PY_PKG_INFO) | sed 's/[^:]*://'))


all: lint test
lint: pep8 pylint
test: test-unit test-integration test-functional

.PHONY: .pre-init
.pre-init:
	pip install --upgrade pip
	@# Constrain setuptools because pylint is not compatible with newer versions.
	pip install setuptools==33.1.1
	pip install --upgrade pip-tools

init: .pre-init
	$(call print_msg, Installing requirements... )
	pip-sync requirements.txt

init-dev: .pre-init
	$(call print_msg, Installing dev requirements... )
	pip-sync requirements.txt dev-requirements.txt

deps:
	pip-compile requirements.in
	pip-compile dev-requirements.in

deps-upgrade:
	pip-compile -U requirements.in
	pip-compile -U dev-requirements.in

pylint:
	$(call print_msg, Running pylint... )
	PYTHONPATH=.:$(PYTHONPATH) pylint --load-plugins=test.framework.pylint app

pep8:
	$(call print_msg, Running pep8... )
	pep8 --max-line-length=145 app

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

test-unit-via-clusterrunner: $(CR_BIN)
	$(call print_msg, Running unit tests via ClusterRunner... )
	python $(CR_BIN) build --job-name Unit
	python $(CR_BIN) stop

test-functional:
	$(call print_msg, Running functional tests... )
	nosetests -s -v test/functional

# Build the clusterrunnner testing docker image from only the builder stage and run tests in it.
.PHONY: docker-test
docker-test:
	$(call print_msg, Building ClusterRunner docker image to run tests in... )
	docker build --target builder -t $(DOCKER_TAG)-tests -f Dockerfile .
	docker run --rm $(DOCKER_TAG)-tests make test

# INFO: The use of multiple targets (before the :) in the next sections enable
#       a technique for setting some targets to "phony" so they will always
#       run, while allowing other targets to remain conditional based on the
#       dependencies (after the :).

# TODO: Consider using "pip download --platform" when direct downloading of
#       cross-platform wheels is supported.
.INTERMEDIATE: $(PY_WHEEL_CACHE)
wheels $(PY_WHEEL_CACHE): requirements.txt
	$(call print_msg, Creating wheels cache... )
	mkdir -p $(PY_WHEEL_CACHE)
	pip wheel -r requirements.txt --wheel-dir $(PY_WHEEL_CACHE)

pex $(CR_BIN): $(PY_WHEEL_CACHE)
	$(call print_msg, Running pex... )
	@# Do not cache the ClusterRunner build.
	rm -f $(PY_WHEEL_CACHE)/clusterrunner*
	./setup.py bdist_pex --bdist-all --pex-args="$(PEX_ARGS)"

$(PY_PKG_INFO):
	$(call print_msg, Creating Python egg-info data... )
	./setup.py egg_info

.PHONY: rpm
rpm: $(CR_BIN) $(PY_PKG_INFO)
	$(call print_msg, Creating ClusterRunner RPM... )
	$(if $(filter $(RPM_VERSION), $(CR_UNK_VERSION)), $(error version cannot be $(CR_UNK_VERSION)))
	fpm -s dir -t rpm $(FPM_INFO_ARGS) $(FPM_DEPEND_ARGS) \
		--package $(DIST_DIR) \
		--config-files $(RPM_CR_CONF) \
		--rpm-tag "Requires(pre): shadow-utils" \
		--directories $(RPM_BASE_DIR) \
		--rpm-attr 0600,$(RPM_USER),$(RPM_GROUP):$(RPM_CR_CONF) \
		--rpm-attr -,$(RPM_USER),$(RPM_GROUP):$(RPM_BASE_DIR) \
		$(CR_BIN)=/usr/bin/ \
		$(CR_CONF)=$(RPM_CR_CONF) \
		bin/=$(RPM_BASE_DIR)/bin/

# Use a docker container to build the clusterrunnner RPM and copy it to the local directory.
# Additionally extract the PKG-INFO file so the final "release-signed" target can run without a
# local Python environment.
.PHONY: docker-rpm
docker-rpm:
	$(call print_msg, Running ClusterRunner Docker RPM builder... )
	docker build -t $(DOCKER_TAG) -f Dockerfile .
	mkdir -p $(DIST_DIR) $(PY_EGG_INFO_DIR)
	@# Docker cp does not support globing, so the path to the RPM file must be
	@# detected with a query. The order of the commands are important and they
	@# must all be run in the same "shell" for the variables to be available to
	@# the final "docker cp" command.
	DOCKER_RPM_PATH=$$(docker run $(DOCKER_TAG) sh -c "ls /root/$(DIST_DIR)/*.rpm") && \
	CONTAINER_ID=$$(docker ps -alq) && \
	docker cp $$CONTAINER_ID:$$DOCKER_RPM_PATH $(DIST_DIR) && \
	docker cp $$CONTAINER_ID:/root/$(PY_PKG_INFO) $(PY_EGG_INFO_DIR) && \
	docker rm $$CONTAINER_ID

# RPM_PATH is set as a target dependency to potentially warn users in the event
# that the RPM file does not exist. It is added as a convenience to the user.
# Generation of RPM_PATH requires Python (or the PKG_INFO output file) and makes
# use of Make's SECONDEXPANSION feature so that it is not resolved until the
# PY_PKG_INFO prerequisite is resolved. Additionally, RPM_PATH is not defined as
# a target because only prerequisites are supported by SECONDEXPANSION.
#
# The RPM can manually be created with the "docker-rpm" or "rpm" targets.
.PHONY: release
release: $(PY_PKG_INFO) $$($$RPM_PATH)
	curl -u $(ARTIFACTORY) -X PUT $(ARTIFACTORY_URL)/$(RPM_VERSION)-$(RPM_RELEASE)/$(RPM_FILE) -T $(RPM_PATH)

# Run the "release" target in the Docker container. Technically this is not
# required, but guarantees that a release can be made without a working Python
# environment.
.PHONY: docker-release
docker-release: docker-rpm
	docker run --rm -e ARTIFACTORY=$(ARTIFACTORY) $(DOCKER_TAG) /usr/bin/make release

# See "release" target. The major difference is that this target uses the Box custom
# rpm-to-artifactory tooling that is made available for signing and uploading rpms.
.PHONY: release-signed
release-signed: $(PY_PKG_INFO) $$($$RPM_PATH)
	REPO_NAME="$(ARTIFACTORY_REPO)" \
	REPO_PATH="com/box" \
	SERVICE_KIND="clusterrunner" \
	SERVICE_VERSION="$(RPM_VERSION)-$(RPM_RELEASE)" \
	rpm-to-artifactory $(RPM_PATH)

clean:
	$(call print_msg, Removing intermediate build files... )
	@# Remove to prevent caching of setup.py and MANIFEST.in
	rm -rf $(PY_EGG_INFO_DIR) build/ .hypothesis/
	rm -rf $(WHEEL_CACHE) $(CR_BIN)
	rm -rf $(DIST_DIR)/*.rpm
