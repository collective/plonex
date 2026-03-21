# plonex

Plone deployment CLI.

`plonex` is designed to make everyday project operations predictable.
Instead of asking you to remember many low-level commands and file locations,
it gives you one consistent entry point for setup, runtime, database operations,
and test helpers.

When you run a command, `plonex` does more than simply spawn a process:

- it finds the correct project root (`etc/plonex.yml`),
- it loads and merges configuration from all supported files,
- it prepares temporary/generated config files when needed,
- it exports environment variables defined in config,
- and finally it runs the appropriate executable from your virtualenv.

This means commands are reproducible and configuration-driven.
You change behavior in YAML files (or CLI flags), and `plonex` applies that
consistently across services.

## Autocomplete

Add this to your shell startup file:

```sh
eval "$(register-python-argcomplete plonex)"
```

## Global options

All commands accept these options:

```text
plonex [--target PATH] [--verbose] [--quiet] [--version] <command> ...
```

- `-t, --target`: target project folder (defaults to current directory).
- `-v, --verbose`: set log level to `DEBUG`.
- `-q, --quiet`: reduce log output (`WARNING` and above).
- `-V, --version`: print installed plonex version.

For all commands except `init`, `plonex` resolves the target by walking upward until it finds `etc/plonex.yml`.

## Quick start

If you are new to `plonex`, think about this flow:

1. `init`: create a valid project structure.
1. `dependencies`: create/update `.venv` and install project requirements.
1. `zeoserver` / `zeoclient`: run your services.
1. `db` commands: maintain your Data.fs.
1. `zopetest` / `robottest`: run test suites.

In practice, you can keep using the same high-level commands while changing
only configuration values per environment (local, CI, staging, production).

Initialize a project:

```sh
plonex init myproject
```

Install/update dependencies:

```sh
plonex dependencies
```

Start ZEO server:

```sh
plonex zeoserver
```

Start ZEO client in foreground:

```sh
plonex zeoclient fg
```

## How to think about plonex

`plonex` separates intent from implementation.
You declare intent with simple commands such as `plonex zeoclient fg` or
`plonex db pack`, and `plonex` translates that into the correct low-level command,
with the correct paths, environment variables, and generated configuration files.

This approach has a few practical benefits:

- You do not need to remember long binary paths or many flags.
- Team members can share the same commands while keeping local overrides in YAML.
- Automation in CI can reuse exactly the same command set used locally.

In other words, `plonex` behaves like an orchestration layer over project runtime
tools, while still letting you control details through configuration.

## Typical workflows

### Local development

```sh
plonex init .
plonex dependencies
plonex zeoserver
plonex zeoclient fg
```

What happens:

- `init` creates project skeleton and base config.
- `dependencies` ensures `.venv` exists and installs pinned dependencies.
- `zeoserver` starts ZEO using generated config in `tmp/zeoserver`.
- `zeoclient fg` renders instance config in `tmp/zeoclient` and starts in foreground.

### Running maintenance tasks

```sh
plonex db pack --days 7
plonex db backup
```

What happens:

- `db pack` reads `zeo_address` from merged options and calls `zeopack`.
- `db backup` runs `repozo` against the project Data.fs location.

### Working with supervisor

```sh
plonex supervisor start
plonex supervisor status
plonex supervisor restart
```

What happens:

- `plonex` generates `etc/supervisord.conf` and service templates if needed.
- it runs `supervisord` and `supervisorctl` from your project virtualenv.
- status/restart actions use the same generated config file, so behavior is consistent.

## Commands

### Setup and info

`init [target]`

- Initialize project folders and base config.

`compile`

- Compile merged configuration into `var/plonex.yml`.

`describe`

- Render a project description from current configuration.

`dependencies [--persist]`

- Install from merged requirements/constraints.
- `-p, --persist`: save auto-detected missing constraints.

`install <package> [<package> ...]`

- Add one or more packages and run dependency installation.

`upgrade`

- Run Plone upgrade steps.

### Runtime

`zeoserver`

- Start ZEO server.

`zeoclient [options] [action]`

- Options:
  - `-n, --name`: client name (default: `zeoclient`)
  - `-c, --config`: extra config file (repeatable)
  - `-p, --port`: HTTP port
  - `--host`: HTTP host
- Actions:
  - `console` (default)
  - `fg`
  - `start`
  - `stop`
  - `status`
  - `debug`

`run [args ...]`

- Run an instance script through the ZEO client wrapper.

`adduser [-c FILE] <username> [password]`

- Create a Zope user (password can be omitted to auto-generate one).

`supervisor [status|start|stop|restart|graceful]`

- Manage supervisord for project services.

### Database

`db backup`

- Run Data.fs backup.

`db pack [--days DAYS]`

- Pack ZODB revisions older than `DAYS` (default: `7`).
- Uses merged `zeo_address` from your config files.

`db restore`

- Placeholder (not implemented yet).

### Tests

`zopetest <package> [-t TEST]`

- Run `zope-testrunner` for a package.

`robotserver [--layer LAYER]`

- Start robot test server.

`robottest <paths...> [--browser BROWSER] [-t TEST]`

- Run Robot Framework tests.

`test`

- Placeholder command.

## Configuration and option precedence

Options are merged in this order (higher wins):

1. CLI options
1. Files passed with `-c/--config`
1. `etc/plonex-<service>.*.yml`
1. `etc/plonex-<service>.yml`
1. `etc/plonex.*.yml` (alphabetical precedence)
1. `etc/plonex.yml`
1. Service defaults

Why this matters:

- you can keep sane defaults in `etc/plonex.yml`,
- add machine- or developer-specific overrides in `etc/plonex.local.yml`,
- and still force one-off values from the command line when needed.

This is especially useful for paths like `zeo_address`, ports, or feature flags
that can vary by environment.

Useful settings include:

- `log_level`: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- `environment_vars`: environment variables exported before service execution
- `zeo_address`: socket/host used by ZEO client and `db pack`
- `blobstorage`: blob storage path
- `http_port`, `http_address`

Example:

```yaml
zeo_address: /srv/components/zeo/var/zeo.socket
blobstorage: /srv/components/zeo/var/blobstorage
environment_vars:
  TZ: Europe/Rome
```

Service-specific overrides are useful when one command needs different settings.
For example:

- `etc/plonex.yml`: shared defaults.
- `etc/plonex.local.yml`: local machine overrides (socket paths, local ports).
- `etc/plonex-zeoclient.yml`: zeoclient-only adjustments.

Because these files are merged with precedence, you can keep common settings in
one place and make only small targeted overrides where needed.

## Under the hood

`plonex` is a wrapper around executables inside your virtualenv. Paths are resolved from the project target (typically `.venv/bin/...`).

Most commands follow the same lifecycle:

1. Resolve target folder.
1. Merge options from config files and CLI.
1. Generate required runtime files under `tmp/` and/or `etc/`.
1. Execute the real binary from `.venv/bin/...`.

So when you type a short command like `plonex db pack`, `plonex` still applies your
configuration first (for example `zeo_address`) and only then calls `zeopack`.
That is why changing config files can change command behavior without changing
the command itself.

Common command mappings:

- `plonex zeoserver`

```sh
.venv/bin/runzeo -C tmp/zeoserver/etc/zeo.conf
```

- `plonex zeoclient fg` (and other zeoclient actions)

```sh
tmp/zeoclient/bin/instance fg
```

- `plonex run path/to/script.py`

```sh
tmp/zeoclient/bin/instance run path/to/script.py
```

- `plonex adduser admin secret`

```sh
.venv/bin/addzopeuser -c tmp/zeoclient/etc/zope.conf admin secret
```

- `plonex db pack --days 7`

```sh
.venv/bin/zeopack -u <zeo_address> -d 7
```

`<zeo_address>` is read from merged `plonex` configuration, not hardcoded.

- `plonex db backup`

```sh
.venv/bin/repozo -Bv -r var/backup -f var/filestorage/Data.fs
```

- `plonex supervisor start`

```sh
.venv/bin/supervisord -c etc/supervisord.conf
```

- `plonex supervisor status`

```sh
.venv/bin/supervisorctl -c etc/supervisord.conf status
```

- `plonex dependencies`

```sh
.venv/bin/uv pip install -r var/requirements.txt -c var/constraints.txt
```

- `plonex robottest tests/acceptance/*.robot`

```sh
.venv/bin/robot --variable BROWSER:firefox tests/acceptance/*.robot
```

- `plonex robotserver`

```sh
.venv/bin/robot-server --debug-mode --verbose Products.CMFPlone.testing.PRODUCTS_CMFPLONE_ROBOT_TESTING
```

- `plonex zopetest plone.api -t test_get`

```sh
.venv/bin/zope-testrunner --all --quiet -pvc --path <package_path> -t test_get
```

Note: plonex also renders temporary config files under `tmp/` before running several services (for example `tmp/zeoclient/etc/zope.conf`).

## Troubleshooting

### "Could not find etc/plonex.yml"

`plonex` looks for `etc/plonex.yml` by walking up from the target directory.
Use one of these approaches:

- run commands from inside your project tree,
- pass `--target /path/to/project`,
- or initialize a project first with `plonex init`.

### Command uses unexpected values

Run `plonex compile` and inspect `var/plonex.yml`.
That file shows the final merged options and helps verify which file/flag won.

Typical causes:

- a higher-priority config file overrides your value,
- a command-line option is overriding YAML,
- or a service-specific file exists and takes precedence for that service.

### `db pack` cannot connect to ZEO

Check `zeo_address` in your merged config and ensure the socket/host exists.
If needed, set it in `etc/plonex.local.yml` for machine-specific environments.

### Missing binaries in `.venv/bin`

If commands fail because binaries are missing, run:

```sh
plonex dependencies
```

This recreates or updates environment-installed tooling used by runtime commands.

## Current limitations

- `db restore` is not implemented yet.
- `test` is currently a placeholder command.

These commands are listed for interface completeness but do not provide full behavior yet.
