all: .venv/bin/uv requirements.txt constraints.txt
	.venv/bin/uv pip install -r requirements.txt -c constraints.txt

.venv/bin/python3:
	python3 -m venv .venv

.venv/bin/uv: .venv/bin/python3
	.venv/bin/pip install uv
