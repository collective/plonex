all: .venv/bin/python3 requirements.txt
	.venv/bin/python3 -m pip install -r requirements.txt

.venv/bin/python3:
	python3 -m venv .venv
