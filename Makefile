.PHONY: all
all: .venv/bin/uv requirements.txt constraints.txt
	.venv/bin/uv pip install -r requirements.txt -c constraints.txt

.venv/bin/python3:
	python3 -m venv .venv

.venv/bin/uv: .venv/bin/python3
	.venv/bin/pip install uv

.PHONY: test
test: all
	.venv/bin/mypy src/plonex
	find src/plonex -type d -name __pycache__ -exec rm -rf {} \; 2>/dev/null || true
	.venv/bin/pytest -s --cov=plonex --cov-report=html
