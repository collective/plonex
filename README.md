# plonex

Plone deployment CLI.

`plonex` is a helper tool designed to simplify everyday project operations with Plone.

> [!NOTE]
> `plonex` At the moment `plonex` is in early development and may have breaking changes. Use with caution and report issues.

## Quickstart

If you just want to test `plonex`, you can initialize a new project and run the ZEO server and client with these commands:

```sh
plonex init myproject
cd myproject
plonex supervisor start
```

This is enough to get a ZEO server running in the background and a ZEO client in the foreground, with all configuration generated for you.

Your site will be available at `http://localhost:8080`.

## The magic behind the scenes

When you run a command, `plonex` does more than simply spawn a process:

- it finds the correct project root (a parent folder containing a file named `etc/plonex.yml`)
- it loads and merges configuration from all supported files
- it prepares temporary/generated config files when needed
- it exports environment variables defined in configuration
- it runs the appropriate executable from your virtualenv

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

If you run `plonex` without a command, it displays the help message unless a
default action is configured in `etc/plonex.yml`.

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

## Default actions

You can configure what happens when you run `plonex` with no explicit command.

By default, `plonex` shows the command help.

If you want a different behavior, set either `default_action` or
`default_actions` in `etc/plonex.yml`.

## Profiles

You can extend a project from one or more profiles declared in `etc/plonex.yml`.

Example:

```yaml
profiles:
  - /path/to/plonex-profile
  - https://github.com/example/plonex-profile.git

http_port: 8081
```

Profile configuration is loaded before the local project configuration, so the
local `etc/plonex.yml` remains the highest-precedence place for site-specific
overrides such as ports, hostnames, and service settings.

Profiles can themselves declare `profiles`, which allows a profile to extend
another profile before the local project overrides both.

Relative profile paths in the project `etc/plonex.yml` are resolved from the
project root. Relative profile paths declared inside a profile are resolved from
that profile root.

One practical way to organize profiles inside a repository is:

```text
myproject/
├── etc/
│   └── plonex.yml
└── profiles/
    ├── default/
    │   └── etc/
    │       └── plonex.yml
    ├── production/
    │   └── etc/
    │       └── plonex.yml
    └── development/
        └── etc/
            └── plonex.yml
```

For example, `profiles/default/etc/plonex.yml` can hold shared defaults used by
every environment:

```yaml
plone_version: 6.1.4
http_address: 0.0.0.0
zeo_address: var/zeo.sock
environment_vars:
  TZ: Europe/Rome
```

Then `profiles/production/etc/plonex.yml` can extend `default` and add
production-specific values:

```yaml
profiles:
  - ../default

http_port: 8080
debug_mode: false
```

And `profiles/development/etc/plonex.yml` can also extend `default` but keep
more developer-friendly settings:

```yaml
profiles:
  - ../default

http_port: 8081
debug_mode: true
log_level: debug
```

Finally, the project `etc/plonex.yml` chooses which profile to inherit from and
keeps the final local overrides:

```yaml
profiles:
  - profiles/development

http_port: 8082
```

In this example the resulting `http_port` is `8082`, because the local
`etc/plonex.yml` overrides `profiles/development`, which overrides
`profiles/default`.

Single action examples:

```yaml
default_action: describe
```

```yaml
default_action: zeoclient fg
```

Equivalent list form:

```yaml
default_action:
  - zeoclient
  - fg
```

If you want to run multiple commands in sequence, use `default_actions`:

```yaml
default_actions:
  - supervisor start
  - zeoclient fg
```

This is useful when you want plain `plonex` to bootstrap a common local
workflow, for example starting Supervisor first and then bringing up the client.

Notes:

- `default_actions` runs in order.
- each action can be written as a shell-like string or a list of tokens.
- command-line global options such as `-v` and `-q` still apply.

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
plonex db pack --days N
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
- If `target` is omitted, `plonex` prompts for a folder and suggests the current directory as the default.

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
1. Profiles declared by `etc/plonex.yml` and nested profile `plonex.yml` files
1. Service defaults

Why this matters:

- you can keep sane defaults in `etc/plonex.yml`,
- inherit shared defaults from one or more profiles,
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

## Dependency-driven services

`plonex` supports declarative helper services in `etc/plonex.yml`.
These services are not intended to be run directly as a top-level command.
Instead, they run automatically as dependencies of runtime commands.

This is useful when a command needs generated files before execution, for
example Supervisor program snippets or other rendered templates.

Example:

```yaml
services:
  - template:
      run_for: supervisor
      source_path: resource://plonex.supervisor.templates:program.conf.j2
      target_path: tmp/supervisor/etc/supervisor/zeoclient.conf
      options:
        name: zeoclient
        command: tmp/zeoclient/bin/instance fg
        autostart: false
```

In this example:

- the template is rendered only when running a command mapped to `supervisor`,
- the rendered file is prepared before `supervisord`/`supervisorctl` is called,
- and the dependency is fully controlled from YAML.

`run_for` accepts either a string or a list of command names:

```yaml
services:
  - template:
      run_for: [supervisor, zeoclient]
      source: etc/templates/runtime.conf.j2
      target: tmp/runtime.conf
```

Notes:

- service entries must be a list of single-key mappings,
- unknown service names raise a configuration error,
- relative `source`/`target` paths are resolved from the project target folder,
- `resource://...` template sources are supported.

Recommended pattern:

- keep long-lived defaults in `etc/plonex.yml`,
- keep machine-specific path overrides in `etc/plonex.local.yml`,
- add `run_for` only where generation must be scoped to specific commands.

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
