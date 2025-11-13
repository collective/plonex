.PHONY: all
all: help

.PHONY: test
test: install  ## Run the tests
	.venv/bin/mypy src/plonex
	find src/plonex -type d -name __pycache__ -exec rm -rf {} \; 2>/dev/null || true
	mkdir -p tmp/tests
	TMPDIR=$(shell pwd)/tmp/tests .venv/bin/pytest -s --cov=plonex --cov-report=html

htmlcov: test
	@echo "HTML coverage report generated at htmlcov/index.html"

.PHONY: browse-coverage
browse-coverage: htmlcov ## Open the coverage report in a web browser
	xdg-open htmlcov/index.html

.PHONY: install
install: .venv/bin/uv requirements.txt constraints.txt
	.venv/bin/uv pip install -r requirements.txt -c constraints.txt

.venv/bin/python3:
	python3 -m venv .venv

.venv/bin/uv: .venv/bin/python3
	.venv/bin/pip install uv

.PHONY: pre-commit
pre-commit: all  ## Install pre-commit hooks
	pre-commit install

.PHONY: clean
clean:  ## Remove all generated files
	rm -rf .coverage .venv tmp var


.PHONY: help
help:  ## Show this help message
	@gawk -vG=$$(tput setaf 2) -vR=$$(tput sgr0) ' \
	  match($$0, "^(([^#:]*[^ :]) *:)?([^#]*)##([^#].+|)$$",a) { \
	   if (a[2] != "") { printf "    make %s%-18s%s %s\n", G, a[2], R, a[4]; next }\
	    if (a[3] == "") { print a[4]; next }\
	    printf "\n%-36s %s\n","",a[4]\
	  }' $(MAKEFILE_LIST)
