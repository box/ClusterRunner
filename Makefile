.PHONY: all lint test init pylint pep8 test-unit test-unit-via-clusterrunner test-functional
.PHONY: clean wheels pex

DIST_DIR := ./dist
CR_BIN   := $(DIST_DIR)/clusterrunner
CR_CONF  := ./conf/default_clusterrunner.conf
CR_UNK_VERSION := 0.0   # Default CR version when git repo is missing.

EGG_INFO_DIR := ./clusterrunner.egg-info
PKG_INFO     := $(EGG_INFO_DIR)/PKG-INFO

# Macro for printing a colored message to stdout
print_msg = @printf "\n\033[1;34m***%s***\033[0m\n" "$(1)"

# Macro for extracting key values from PKG-INFO.
# IMPORTANT: $(PKG_INFO) must be a dependency of any targets that use this macro.
pkg_info = $(strip $(shell egrep -i "^$(1): " $(PKG_INFO) | sed 's/[^:]*://'))

all: lint test
lint: pep8 pylint
test: test-unit test-integration test-functional

.PHONY: .pre-init
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

# TODO: Use platform flag to build multi-platform pex (requires platform wheels).
#       --platform=macosx-10.12-x86_64
#       --platform=linux_x86_64
#       --platform=win64_amd
WHEEL_CACHE := $(PWD)/$(DIST_DIR)/wheels

# Pex will source all wheel dependencies from the WHEEL_CACHE. It is necessary
# to set the Cache TTL to 0 so that pex will accept any matching wheel,
# regardless of its timestamp.
PEX_ARGS    := -v --no-pypi --cache-dir=$(WHEEL_CACHE) --cache-ttl=0

# INFO: The use of multiple targets (before the :) in the next sections enable
#       a technique for setting some targets to "phony" so they will always
#       run, while allowing other targets to remain conditional based on the
#       dependencies (after the :).

# TODO: Consider using "pip download --platform" when direct downloading of
#       cross-platform wheels is supported.
.INTERMEDIATE: $(WHEEL_CACHE)
wheels $(WHEEL_CACHE): requirements.txt
	$(call print_msg, Creating wheels cache... )
	mkdir -p $(WHEEL_CACHE)
	pip wheel -r requirements.txt --wheel-dir $(WHEEL_CACHE)

pex $(CR_BIN): $(WHEEL_CACHE)
	$(call print_msg, Running pex... )
	@# Do not cache the ClusterRunner build.
	rm -f $(WHEEL_CACHE)/clusterrunner*
	./setup.py bdist_pex --bdist-all --pex-args="$(PEX_ARGS)"

$(PKG_INFO):
	$(call print_msg, Creating Python egg-info data... )
	./setup.py egg_info

# RPM package defaults
RPM_BASE_DIR    := /var/lib/clusterrunner
RPM_CR_CONF     := $(RPM_BASE_DIR)/clusterrunner.conf
RPM_DEPENDS     := python34u git
RPM_USER        := jenkins
RPM_GROUP       := engineering
RPM_PREINSTALL  := conf/preinstall.rpm

# Auto-detect packaging info from PKG-INFO
RPM_DESCRIPTION = $(call pkg_info,summary)
RPM_LICENSE     = $(call pkg_info,license)
RPM_NAME        = $(call pkg_info,name)
RPM_URL         = $(call pkg_info,home-page)
RPM_VENDOR      = $(call pkg_info,author)
RPM_VERSION     = $(call pkg_info,version)
# Collect all package info fields into fpm args
FPM_INFO_ARGS   = --name "$(RPM_NAME)" --version "$(RPM_VERSION)" \
	--license "$(RPM_LICENSE)" --description "$(RPM_DESCRIPTION)" \
	--vendor "$(RPM_VENDOR)" --maintainer "$(RPM_VENDOR)" --url "$(RPM_URL)"
# Expand all dependencies into fpm args
FPM_DEPEND_ARGS = $(addprefix --depends , $(RPM_DEPENDS))

.PHONY: rpm
rpm: $(CR_BIN) $(PKG_INFO)
	$(call print_msg, Creating ClusterRunner RPM... )
	$(if $(filter $(RPM_VERSION), $(CR_UNK_VERSION)), $(error version cannot be $(CR_UNK_VERSION)))
	fpm -s dir -t rpm $(FPM_INFO_ARGS) $(FPM_DEPEND_ARGS) \
		--package $(DIST_DIR) \
		--config-files $(RPM_CR_CONF) \
		--rpm-tag "Requires(pre): shadow-utils" \
		--pre-install $(RPM_PREINSTALL) \
		--directories $(RPM_BASE_DIR) \
		--rpm-attr 0600,$(RPM_USER),$(RPM_GROUP):$(RPM_CR_CONF) \
		--rpm-attr -,$(RPM_USER),$(RPM_GROUP):$(RPM_BASE_DIR) \
		$(CR_BIN)=/usr/bin/ \
		$(CR_CONF)=$(RPM_CR_CONF) \
		conf/clusterrunner-master=/etc/init.d/

.PHONY: docker-rpm
docker-rpm:
	$(call print_msg, Running ClusterRunner Docker RPM builder... )
	$(eval TAG := productivity/clusterrunner)
	mkdir -p $(DIST_DIR)
	docker build -t $(TAG) -f Dockerfile .
	@# Docker cp does not support globing, so detect the path to the RPM file.
	$(eval RPM_PATH := $(shell docker run $(TAG) sh -c "ls /root/$(DIST_DIR)/*.rpm"))
	@# Docker "run" must be called before the next steps.
	$(eval CONTAINER_ID := $(shell docker ps -alq))
	docker cp $(CONTAINER_ID):$(RPM_PATH) dist/

clean:
	$(call print_msg, Removing intermediate build files... )
	@# Remove to prevent caching of setup.py and MANIFEST.in
	rm -rf $(EGG_INFO_DIR) build
	rm -rf $(WHEEL_CACHE) $(CR_BIN)
