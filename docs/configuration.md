# Project configuration

Plonex reads YAML files from the project and its profiles. Use `plonex project describe configuration` to inspect resolved values and their origins.

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
plone_version: 6.2.0
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

By default, `deprecation_warnings` is `default` when debug mode is on and
`ignore` when debug mode is off.
Set it to one of these strings to override the default:

- `"default"`: show each warning once per location.
- `"ignore"`: suppress warnings.
- `"always"`, `"module"`, `"once"`, or `"error"`: use the corresponding Python
  warning action.

Invalid or non-string values are ignored with a warning.

## Base Constraints

`plonex` generates a merged `var/constraints.txt` for installation.

By default it starts from the Plone release constraints selected by
`plone_version`. The generated `etc/plonex.yml` does not include a
`plonex_base_constraint` entry unless you decide to add one.

Default behavior:

```yaml
plone_version: 6.2.0
```

This means the base constraint is effectively:

```yaml
https://dist.plone.org/release/{{ plone_version }}/constraints.txt
```

If you want to override that base, add
`plonex_base_constraint`.

Supported values are:

- remote URLs
- local files relative to the project root
- `resource://package:path` references

Examples:

```yaml
plonex_base_constraint: https://example.org/constraints/base.txt
```

```yaml
plonex_base_constraint: etc/constraints/base.txt
```

```yaml
plonex_base_constraint: resource://my.package:constraints/base.txt
```

Use a plain URL in YAML, without Markdown link syntax. For GitHub files, copy the
**Raw** URL from `raw.githubusercontent.com`, rather than the `/blob/` page URL.
Remote constraints, including nested `-c` and `-r` references, are merged into
`var/constraints.txt`. Local pins override remote pins, and packages installed in
editable mode are excluded. HTML responses and invalid remote requirements cause
a warning and stop generation, preserving the previous constraints file.

Generated package names use lowercase and replace runs of dots, underscores, or
hyphens with a single hyphen: `zope.sendmail==7.2` becomes
`zope-sendmail==7.2`. This also applies to suggested and saved pins, added packages,
and direct `pip_requirements`. Versions, environment markers, paths, and URLs keep
their original spelling.

> [!NOTE]
> If an old `etc/constraints.d/000-plonex.txt` file still exists, `plonex` warns
> that it is ignored and suggests removing it. For compatibility, if neither
> `plone_version` nor `plonex_base_constraint` is configured, `plonex` still tries
> to infer `plone_version` from that legacy file.

## Default actions

You can configure commands to run when `plonex` is invoked without an action.

Single action examples:

```yaml
default_action: project describe
```

```yaml
default_action: instance start
```

Equivalent list form:

```yaml
default_action:
  - instance start
```

If you want to run multiple commands in sequence, use `default_actions`:

```yaml
default_actions:
  - supervisor start
  - instance start
```

This is useful when you want plain `plonex` to bootstrap a common local
workflow, for example starting Supervisor first and then bringing up the client.

Notes:

- `default_actions` runs in order.
- each action can be written as a shell-like string or a list of tokens.
- command-line global options such as `-v` and `-q` still apply.

## Precedence and runtime settings

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
- `zeo_address`: socket/host used by runtime services and `db pack`
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
- `etc/plonex-runwsgi.yml`: runwsgi-only adjustments.

Because these files are merged with precedence, you can keep common settings in
one place and make only small targeted overrides where needed.

### Project environment variables

Before running a command, plonex reads the optional `.env` and `.env.local` files
in the project root (the directory containing `etc/plonex.yml`). Both supply
variables to plonex and the services it starts, including Supervisor and its
child processes. `.env.local` overrides `.env`, so it can hold machine-specific
values. Other names, such as `.env.production`, are not loaded automatically.

Each file contains one `NAME=value` assignment per line. Empty lines, comments,
optional `export`, and shell-style single or double quotes are supported. Quote
values containing spaces or `#`. Values are literal: variable expansion, command
substitution, and multiline values are not supported. Either file may be absent.

When the same variable is defined in multiple places, the highest applicable
setting wins:

1. A job's `environment` settings, for that job. A managed process may also
   define its own environment settings.
1. The service's resolved `environment_vars` in YAML or configuration overrides.
   YAML files and `-c/--config` follow the configuration precedence above.
1. Variables already exported in the shell that starts plonex (including an
   explicitly exported empty value).
1. The project root `.env.local`.
1. The project root `.env`.

For example, start with these files in the project root:

`.env`:

```dotenv
COLOR=blue
TZ=Europe/Rome
```

`.env.local`:

```dotenv
COLOR=green
```

With no other definition of `COLOR`, a service receives `COLOR=green` and
`TZ=Europe/Rome`. Remove `COLOR` from `.env.local` and the service receives
`COLOR=blue`. To override both files for one command, run:

```shell
COLOR=red plonex instance start
```

The service now receives `COLOR=red`. To override it for a particular service,
add the following to `etc/plonex-runwsgi.yml`:

```yaml
environment_vars:
  COLOR: purple
```

That service receives `COLOR=purple`, even when `COLOR=red` is exported in the
shell. Other services use their own resolved configuration. To override a YAML
setting for one invocation, create `etc/one-off.yml`:

```yaml
environment_vars:
  COLOR: yellow
```

Then run `plonex instance start --config etc/one-off.yml`; that invocation
receives `COLOR=yellow`.

A scheduled job can override the service value for its own process. For example,
in the applicable cron configuration:

```yaml
cron_jobs:
  example:
    schedule: "*/15 * * * *"
    command: ["/usr/bin/env"]
    environment:
      COLOR: orange
```

This job receives `COLOR=orange`. Other jobs retain their own resolved values.

The environment files supply process environment variables; they do not
substitute values into YAML options. YAML `environment_vars` is an option mapping:
a higher-priority definition normally replaces the mapping, while `+environment_vars` can extend it in profile and additional project
configuration files that support `+` merges.
Plonex does not automatically load separate service-specific `.env` files.
Services may implement their own environment handling.

Keep files containing secrets out of version control and give them appropriate
permissions; plonex does not create or configure the project's ignore rules.
Restart running processes to pick up changes. The interactive shell reloads the
files for each command.

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
      source_path: resource://plonex.services.supervisor.templates:program.conf.j2
      target_path: tmp/supervisor/etc/supervisor/runwsgi.conf
      options:
        program: runwsgi
        command: plonex instance start
        process_name: runwsgi
        directory: "{{ target }}"
        priority: 2
```

In this example:

- the template is rendered only when running a command mapped to `supervisor`,
- the rendered file is prepared before `supervisord`/`supervisorctl` is called,
- and the dependency is fully controlled from YAML.

`run_for` accepts either a string or a list of command names:

```yaml
services:
  - template:
      run_for: [supervisor, runwsgi]
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

More examples:

- Add extra ZCML includes for runtime services:

```yaml
zcml_additional:
  - etc/zcml/010-my-package-meta.zcml
  - etc/zcml/020-my-package-configure.zcml
  - etc/zcml/030-my-package-overrides.zcml
```

These files are rendered or copied into `tmp/runwsgi/etc/package-includes/`
before `plonex instance start ...` runs. File names matter: `plonex` expects the
usual `-meta.zcml`, `-configure.zcml`, or `-overrides.zcml` suffixes.

- Add extra `zope.conf` snippets for runtime services:

```yaml
zope_conf_additional:
  - etc/zopeconf/cache.j2
  - etc/zopeconf/instancesettings.conf
```

For example, `etc/zopeconf/cache.j2` could contain:

```text
<product-config my.package>
  some-setting value
</product-config>
```

Each listed file is appended to the generated runtime `zope.conf` file.
Jinja templates can use the current service context.

- Generate a Supervisor program for an auxiliary service such as a websocket
  worker, Celery worker, or custom script:

```yaml
services:
  - template:
      run_for: supervisor
      source_path: resource://plonex.services.supervisor.templates:program.conf.j2
      target_path: tmp/supervisor/etc/supervisor/worker.conf
      options:
        program: worker
        command: .venv/bin/python -m mypackage.worker
        process_name: worker
        directory: "{{ target }}"
        priority: 20
```

That way `plonex supervisor start` manages not only `zeoserver` and
`runwsgi`, but also your additional long-running process.

- Combine service dependencies and runtime extras in the same project:

```yaml
zcml_additional:
  - etc/zcml/020-my-package-configure.zcml

zope_conf_additional:
  - etc/zopeconf/cache.j2

services:
  - template:
      run_for: supervisor
      source: etc/templates/worker.conf.j2
      target: tmp/supervisor/etc/supervisor/worker.conf
```

This keeps all project-specific runtime wiring in `etc/plonex.yml` while still
letting the generated files live under `tmp/`.

## Inspecting where a value came from

For a practical explanation of precedence, inspect a value both generally and in
the context of a command:

```sh
plonex project describe configuration --key http_port
plonex project describe configuration --key http_port instance debug --port 8081
plonex options instance debug --port 8081
```

The configuration report shows definitions and their origins. `options` shows
the constructed service's resolved values. Command options can change the
result shown by either command.

```{mermaid}
flowchart LR
    D[Service defaults] --> P[Profiles]
    P --> Y[Project YAML files]
    Y --> S[Service-specific YAML files]
    S --> E[Explicit config files]
    E --> C[Command-line options]
```

Read the diagram from lower to higher precedence. See the numbered precedence
list above for the ordering within project and service files.

| Need                    | Setting or location                         | Example                      |
| ----------------------- | ------------------------------------------- | ---------------------------- |
| Shared defaults         | `etc/plonex.yml` or a profile               | `http_port: 8080`            |
| Machine-specific values | `etc/plonex.local.yml`                      | Local socket or port         |
| One service's settings  | `etc/plonex-runwsgi.yml`                    | WSGI-specific settings       |
| One invocation          | Command-line option                         | `instance debug --port 8081` |
| Additional packages     | `pip_requirements` or `etc/requirements.d/` | Add an add-on requirement    |
| Package version pins    | `etc/constraints.d/`                        | Pin a dependency version     |
