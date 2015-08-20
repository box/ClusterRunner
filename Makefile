.PHONY: all lint test init pylint pep8 test-unit test-unit-via-clusterrunner test-functional freeze

# Macro for printing a colored message to stdout
print_msg = @printf "\n\033[1;34m***%s***\033[0m\n" "$(1)"

all: lint test
lint: pylint pep8
test: test-unit test-functional

init:
	$(call print_msg, Installing requirements... )
	pip install -r requirements.txt

pylint:
	$(call print_msg, Running pylint... )
	PYTHONPATH=.:${PYTHONPATH} pylint --load-plugins=test.framework.pylint app

pep8:
	$(call print_msg, Running pep8... )
	pep8 --max-line-length=160 app

test-unit:
	$(call print_msg, Running unit tests... )
	nosetests -v test/unit

test-unit-with-coverage:
	$(call print_msg, Running unit tests with coverage... )
	nosetests -v --with-xcoverage --cover-package=app test/unit

test-integration-with-coverage:
	$(call print_msg, Running unit tests with coverage... )
	nosetests -v --with-xcoverage --cover-package=app test/integration

test-unit-via-clusterrunner:
	$(call print_msg, Running unit tests via ClusterRunner... )
	./main.py build --job-name Unit
	./main.py stop

test-functional:
	$(call print_msg, Running functional tests... )
	nosetests -s -v test/functional

freeze:
	$(call print_msg, Freezing... )
	python setup.py build
