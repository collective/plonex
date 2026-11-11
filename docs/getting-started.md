# Getting started

## Install

Install Plonex in the Python environment you want to use for project management:

```sh
pip install plonex
```

For development, clone the repository and install its development requirements:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

See [Development](development.md) for the project workflow.

## Create and start a project

```sh
plonex project init myproject
cd myproject
plonex supervisor start
plonex supervisor status
```

The generated project configuration describes the Plone runtime and services.
Supervisor starts the configured ZEO server and WSGI client in the background.
The site is normally available at <http://localhost:8080>.

Stop services with `plonex supervisor stop`. Run `plonex` from within the
project directory (or provide `--target /path/to/myproject`) so it can find
`etc/plonex.yml`.

## Next steps

- Read [Configuration](configuration.md) to understand YAML settings, profiles,
  and precedence.
- Browse the [CLI reference](cli.md) for available command families.
- See [Database backup and recovery](recovery.md) before handling production data.
- For interactive development, see the shell and job control details in
  [Interactive shell and command options](shell.md).
