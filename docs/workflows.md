# Operating Plonex

## Local development

```sh
plonex project init .
plonex supervisor start
plonex shell
```

What happens:

- `init` creates project skeleton and base config.
- `init` creates `.venv` and installs the configured dependencies.
- `supervisor start` starts the configured ZEO and WSGI services in the background.
- `shell` opens a prompt for project commands. Use `supervisor status` there to
  check managed services. `jobs` lists processes launched by the current shell;
  Supervisor services are managed separately.

## Running maintenance tasks

```sh
plonex db pack --days N
plonex db backup
```

What happens:

- `db pack` reads `zeo_address` from merged options and calls `zeopack`.
- `db backup` runs `repozo` against the project Data.fs location.

## Working with supervisor

```sh
plonex supervisor start
plonex supervisor status
plonex supervisor restart
plonex supervisor graceful --interval 2.0
```

What happens:

- `plonex` generates `tmp/supervisor/etc/supervisord.conf` and service templates if needed.
- it runs `supervisord` and `supervisorctl` from your project virtualenv.
- `plonex supervisor graceful` restarts each configured service one by one in the
  order reported by `supervisorctl status`.
- `--interval` controls the pause between service restarts. The default interval is `1` second.

You can also set the default interval in YAML:

```yaml
supervisor_graceful_interval: 10
```

Put that in `etc/plonex.yml` or another merged plonex config file.
The CLI flag
still wins over YAML when both are provided.

## Commands

## Setup and info

`shell [--target PATH]`

- Open the interactive project shell, including aliases, completion, job control,
  logs, and startup option inspection. See [Interactive shell](shell.md).

`options [--markdown] <command> [arguments ...]`

- Preview effective service arguments and options without running the service.
- In the interactive shell, `options [JOB]` inspects a recorded job snapshot;
  omitting the job ID selects the most recent running job.

`project init [target]`

- Initialize project folders and base config.
- If `target` is omitted, `plonex` prompts for a folder and suggests the current directory as the default.

`project compile`

- Compile merged configuration into `var/plonex.yml`.
- If `sources` is configured, compile also generates `var/gitman.yml`.
- The default checkout location is `src` when `sources_location` is omitted.

Example:

```yaml
sources:
  my.package:
    repo: https://github.com/example/my.package.git
    rev: main
```

`project describe`

- Render a project description from current configuration.
- Always export responsive HTML, Markdown, and JSON under `var/plonex_description/`.
- Select a section: `overview`, `configuration`, `analytics`, `profiles`,
  `environment`, `sources`, `dependencies`, `services`, `runtime`, `files`, `jobs`, or `preparation`.
- `--format terminal|markdown|html|json` controls stdout; `--browse` opens HTML.
- `configuration --key OPTION [COMMAND ...]` explains definitions and overrides.
- Inspection does not compile configuration, install packages, or start services.

`dependencies {install|sync|outdated} [options]`

- Install from merged requirements/constraints.
- `sync`: compile requirements/constraints and run `uv pip sync` using the compiled requirements file as positional input.
- `outdated`: run `uv pip list --outdated`. Use this explicit action instead of an installation flag.
- `-p, --persist`: save auto-detected missing constraints into the project's `etc/constraints.d/`.
- `--persist-local`: save auto-detected missing constraints into a local (git-ignored) `etc/constraints.d/999-autoinstalled.local.txt`.
- `--persist-profile`: save auto-detected missing constraints into the first configured profile's `etc/constraints.d/`.
- `--update-sources`: update sources before installing dependencies (uses Gitman under the hood).

Dependency installation prints only package changes and relevant diagnostics:

```text
Added my-package==1.0
Upgraded zope-sendmail: 7.2 → 7.3
Removed unused-package==2.0
```

An unchanged environment prints `No package changes.` Reinstalls, downgrades,
and source changes are reported as well. Use `--verbose` to see full uv output.
The internal package inventory used for checking pins is captured silently;
missing-pin suggestions and resolver/build failures remain visible.

To enable source updates by default in project configuration:

```yaml
sources_update_before_dependencies: true
sources:
  my.package:
    repo: https://github.com/example/my.package.git
    rev: main
```

To install a checkout in the project virtualenv, set `install: true`. Installs
are editable by default, so Python code changes are available without reinstalling:

```yaml
sources:
  ploneintranet:
    repo: git@github.com:quaive/ploneintranet.git
    rev: master
    install: true
    extras: [test]
  pas.plugins.oidc:
    repo: git@github.com:collective/pas.plugins.oidc.git
    install: true
  reference.package:
    repo: https://github.com/example/reference.package.git
    install: false
```

Run `plonex sources clone` followed by `plonex dependencies install`, or use
`plonex dependencies install --update-sources` to update checkouts and install in one step.
`plonex dependencies sync` also supports these selections. Source declarations
without `install: true` remain checkout only. `sources list` shows each source's
installation selection alongside checkout health; it does not inspect the virtualenv.

Each selected source also accepts:

- `extras: [test, debug]`: optional dependency extras, with canonical package naming.
- `editable: false`: build and install the local project normally; rerun dependencies
  after changing its code.
- `path: vendor/my-checkout`: override the checkout path, relative to the project
  (an absolute path is also supported). Otherwise use `sources_location`, default `src`.
- `subdirectory: packages/backend`: install a Python project inside a repository.
  This must be a relative path within the checkout.

Package names come from static `pyproject.toml`, `setup.cfg`, or literal `setup.py`
metadata, falling back to the project directory name. Selected packages are removed
from both base and local constraints, so release pins cannot override the local
checkout. Missing checkouts and directories without `pyproject.toml` or `setup.py`
produce an actionable error before installation. Source updates regenerate the
dependency files after reading the updated metadata.
uv currently cannot resolve editable checkout paths containing `#` or `?`; move
the checkout or use `editable: false` in that case.

Put machine-specific selections in `etc/plonex.local.yml`. Configuration uses the
normal mapping replacement rules: if you override `sources`, include the entries
you want to keep; `+sources` adds or replaces complete source entries. Remove old
`-e src/...` entries from `pip_requirements` and `etc/requirements.d/` when migrating
to source declarations, including their extras. Those requirement mechanisms remain
supported. Disabling a source stops requesting it; use `dependencies sync` to
remove it if nothing else requires it.

See [development next steps](development.md) for proposed environment checks,
test selection, and debugging improvements.

`dependencies add <package> [<package> ...]`

- Add one or more packages and run dependency installation.

`sources {list|clone|update|missing|tainted|suggest} [options]`

- Manage configured source checkouts (uses Gitman under the hood).
- `update`: run a regular sources update (executed by Gitman).
- `update --force`: run a forced update (`--force`), asking for confirmation by
  default.
- `update --force --yes`: skip confirmation.
- `tainted`: list checkouts with local changes.
- `list`: show configured checkouts and whether each is clean, tainted, or missing.
- `missing`: show configured checkouts that are not present on disk.
- `clone`: clone missing configured checkouts (using `repo` and optional `rev`).
- `clone --yes`: skip confirmation prompt before cloning.
- `suggest`: inspect existing unmanaged checkouts and print a ready-to-paste
  YAML snippet for `etc/plonex.yml` with inferred `repo` and `rev`.
- `suggest --apply`: write inferred entries into `etc/plonex.yml`.
- `suggest --apply-local`: write inferred entries into
  `etc/plonex-sources.local.yml`.
- `suggest --apply-profile`: write inferred entries into
  the `etc/plonex.yml` of the first configured profile.

When unmanaged existing checkouts are detected, `sources list` and `sources tainted`
also print a suggested `sources` section to add into `etc/plonex.yml`.
`sources list` includes unmanaged checkouts in the table, marked `unmanaged` with
their branch, repository, and checkout health. The highlighted YAML suggestion
appears in a separate panel. Name filters apply to both rows and suggestions;
Git inspection output stays inside the report.

`db upgrade`

- Run Plone upgrade steps.

## Configuration editing

There is a dedicated `plonex project edit` command to help you edit the configuration files for your `plonex` project.
You can use `--all` to open all discovered config files in your editor, otherwise you can select which files to edit interactively.
The selected editor:

1. with the `--editor` option in the command line
1. with the `editor` option if specified in the `etc/plonex.yml` configuration file
1. can be configured with the `EDITOR` environment variable
1. use the `open` command as a fallback if none of the above is specified.

You can of course edit the configuration files manually, but `plonex project edit` helps you discover and open them quickly.

## Runtime

`db start`

- Start ZEO server.

`instance start [options] [args ...]`

- Options:
  - `-n, --name`: service name (default: `runwsgi`)
  - `-c, --config`: extra config file (repeatable)
  - `-p, --port`: HTTP port
  - `--host`: HTTP host

`instance console [options]`

- Options:
  - `-n, --name`: service name (default: `zconsole`)
  - `-c, --config`: extra config file (repeatable)
  - `-p, --port`: HTTP port
  - `--host`: HTTP host
- Open an interactive Zope console. Use `instance run` for scripts.

`instance run [args ...]`

- Run a script through `zconsole run` with generated runtime config.

`instance add-user [-c FILE] <username> [password]`

- Create a Zope user (password can be omitted to auto-generate one).

`supervisor {status|start|stop|restart|graceful|reread|update}`

- Manage supervisord for project services.
- `graceful` accepts `--interval SECONDS` and falls back to
  `supervisor_graceful_interval` from YAML, defaulting to `1.0`.
- `reread` detects changed program declarations; `update` applies them.
- `restart PROGRAM ...` restarts selected programs; omit names to restart all.

## Database

`db backup`

- Create a verified offline snapshot of FileStorage and blob storage.

`db pack [--days DAYS]`

- Pack ZODB revisions older than `DAYS` (default: `7`).
- Uses merged `zeo_address` from your config files.

`db restore --to NEW_DIRECTORY [--from SNAPSHOT_DIRECTORY]`

- Recover into a new directory without replacing the live database. See
  [database backup and recovery](recovery.md).

## Tests

`test pytest <package-or-path> [pytest arguments ...]`

- Runs `.venv/bin/python -m pytest --pyargs PACKAGE` in the target project, with
  its configured environment and pytest settings. Install pytest in that
  project's virtualenv first.
- Accepts importable Python package names, test directories, files, and node IDs.
- Arguments after the package are passed to pytest, including `-k`, `-m`, `-x`,
  `-q`, `-v`, and plugin flags. An optional `--` after the package is accepted.
- Put plonex logging flags before `pytest`; for example,
  `plonex -v test pytest my.package -q` enables plonex diagnostics and quiet pytest
  output. Test failures preserve pytest's exit status.

```sh
plonex test pytest my.package -k login -x
plonex test pytest src/my.package/tests -q
plonex test pytest tests/test_login.py::test_login -v
```

`test zope <package> [-t TEST]`

- Run `zope-testrunner` for a package.

`test robot-server [--layer LAYER]`

- Start robot test server.

`test robot <paths...> [--browser BROWSER] [-t TEST]`

- Run Robot Framework tests.
