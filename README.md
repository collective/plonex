# plonex

Plone deployment CLI.

`plonex` is a helper tool designed to simplify everyday project operations with Plone.

> [!NOTE]
> At the moment `plonex` is in early development and may have breaking changes. Use with caution and report issues.

## Quickstart

If you just want to test `plonex`, you can initialize a new project and run the ZEO server and client with these commands:

```sh
plonex project init myproject
cd myproject
plonex supervisor start
```

The generated configuration starts ZEO and the WSGI client under Supervisor in
the background. Use `plonex supervisor status` to check them. Runtime files are
generated from your YAML configuration.

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

## Command layout

Use `plonex RESOURCE ACTION [options]` across the CLI:

```sh
plonex project compile
plonex sources list
plonex sources update
plonex dependencies install --update-sources
plonex dependencies sync
plonex instance debug
plonex db backup
plonex test pytest my.package -k login
```

`project`, `dependencies`, `sources`, `instance`, `supervisor`, `db`, `cron`, and `test`
provide command families. `shell` and `options` provide interactive access and
inspection. Each operation has one built-in spelling. Removed shortcuts and flags are listed
in the [CLI structure and migration guide](docs/cli.md). Bare command families show help.

## Autocomplete

Add this to your shell startup file:

```sh
eval "$(register-python-argcomplete plonex)"
```

## Interactive shell

Start a prompt for your current project with `plonex shell`, or choose a project:

```sh
plonex shell --target /path/to/project
```

Enter the same commands and arguments you use at the command line, without the
`plonex` prefix:

```text
plonex[myproject]> supervisor status
plonex[myproject]> dependencies sync
plonex[myproject]> sources list "plone.*"
plonex[myproject]> test robot tests/robot/example.robot --test "Login works"
plonex[myproject]> help dependencies
plonex[myproject]> exit
```

- Tab completes commands, subcommands, flags, and paths when readline is available.
- Up/Down recall commands from this project's current and previous sessions.
- `history` lists remembered commands. History is stored in
  `var/plonex-shell-history` under the target project with owner-only permissions.
  Commands with recognizable credentials are omitted, but avoid placing secrets
  in command arguments: detection cannot recognize every possible secret.
- `help` lists commands; `help COMMAND` and `COMMAND --help` show command help.
- `exit`, `quit`, or Ctrl-D leave the shell. Ctrl-C cancels the current input or
  interrupts a running command and returns to the prompt.
- In an interactive terminal, Ctrl-Z returns to the prompt **without stopping the
  current command**. The server stays available for requests and upgrades.
- Blank lines and lines beginning with `#` are ignored.
- Quoting, escaped spaces, and `--` work as they do in the CLI. Arguments are
  passed directly to plonex; pipes, redirects, variable expansion, and wildcard
  expansion are not interpreted by this prompt.

The shell uses the selected project as its working directory. Each command runs
in a fresh process using the same Python installation as plonex, so configuration
is reloaded and command-specific environment variables do not leak into later
commands. Errors leave the prompt open.

Startup `--verbose` or `--quiet` flags become session defaults. An explicit `-v`
or `-q` on a command overrides those defaults for that command. To run a command
against another project without changing the session target, use
`--target /other/project COMMAND`. The optional `plonex` prefix is also accepted.

### Keeping a foreground instance running

You can return to the prompt to run an upgrade, then reconnect to the same
instance:

```text
plonex[myproject]> instance debug
... instance starts; press Ctrl-Z ...
plonex[myproject]> instance upgrade
plonex[myproject]> fg
... back to the same instance and its live output ...
```

The shell keeps detached commands running and records their output under
`var/log/shell/` (or your configured `var_folder`). Background logs do not print
over the prompt. On reconnect, the shell shows up to 64 KiB of output you missed,
then streams live output. Full logs remain on disk.

- `jobs`: show a Markdown-style table of job IDs, service names, coloured states,
  process IDs, commands, and log locations. Running jobs are green, successful
  exits cyan, failures red, and signal exits yellow. Terminal colour settings,
  including `NO_COLOR`, are respected.
- `jobs --markdown`: export a plain Markdown table without ANSI colour codes.
- `fg` or `attach`: reconnect to the most recent running job.
- `fg %1` or `attach %1`: reconnect to a specific job.
- `logs %1`: show that job's latest output without reconnecting.
- `options %1`: inspect the resolved service options captured when that job started.
- `bg %1`: leave or resume a job in the background.
- `kill %1`: stop the job and its foreground process group.
- `instance debug &`: start an instance directly in the background. A trailing, unquoted
  `&` preceded by a space works with other plonex commands too.

Job IDs also accept plain numbers. Commands that take a job ID default to the
most recent running job. `instance debug --port 8081` starts another instance.
Ctrl-C while attached stops the foreground command; Ctrl-Z detaches it.
Exiting the shell stops jobs it owns, including detached instances. Job control
requires an interactive terminal; piped shell commands retain their usual behavior.

### Inspecting service and job options

Preview a service using the same defaults, merged configuration, aliases, and
argument handling as normal execution:

```sh
plonex options instance debug --port 8081
plonex options instance start --name worker --config etc/worker.yml
plonex options test pytest my.package -k login
plonex options --markdown dependencies sync
```

The report includes service constructor arguments, command flags, configuration
file locations, and resolved options, including nested environment settings.
The service is constructed but not entered or run: inspection does not launch
the service, install dependencies, or render runtime files. Existing constructors
may create directories, and normal configuration resolution still applies,
including fetching remote Git profiles when configured.

In the shell, use a job ID to see its **startup snapshot**, or a command to
preview **current configuration**:

```text
plonex[myproject]> jobs
plonex[myproject]> options %1
plonex[myproject]> options %1 --markdown
plonex[myproject]> options instance debug --port 8082
```

Job snapshots are captured by the service process before it exports environment
variables or runs helper services. They remain available after the job exits and
do not change when YAML files are edited. A snapshot may be unavailable while a
job is starting, or if it fails before entering its service. Help/version jobs
do not have service options.

Inspection masks conventional password, token, and secret keys, known credential
arguments, and passwords in URLs. Snapshots are stored with owner-only file
permissions next to job logs. Ordinary process output in log files is unchanged.

## Project aliases

Define shortcuts in `etc/plonex.yml`:

```yaml
aliases:
  start: supervisor start
  stop: supervisor stop
  test_whatever: pytest my.package
  test_unit: [pytest, my.package, -k, "not integration"]
```

Then run them as ordinary commands:

```sh
plonex start
plonex test_whatever -k login -x
plonex --target /path/to/project test_unit -q
```

An alias is one command, expressed as a quoted command string or a list of
argument tokens. Extra arguments are appended to its expansion. In the examples,
`test_whatever -k login -x` runs `pytest my.package -k login -x`. Values may
optionally start with `plonex`. Quotes preserve arguments containing spaces;
commands are not evaluated as shell code.

Aliases can refer to other aliases, but loops produce an error. Built-in command
names and shell commands such as `help`, `history`, `exit`, `jobs`, and `attach` cannot be replaced.
Aliases appear in project help and Tab completion, work in `plonex shell`, and can
be used by `default_action` or `default_actions`. Edits take effect on the next
shell command or completion.

Aliases use the same profile and local configuration precedence as other
options. To extend or override individual aliases inherited from a profile, use
the existing `+` mapping syntax:

```yaml
+aliases:
  test_whatever: pytest my.other_package
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
You declare intent with simple commands such as `plonex instance start` or
`plonex db pack`, and `plonex` translates that into the correct low-level command,
with the correct paths, environment variables, and generated configuration files.

This approach has a few practical benefits:

- You do not need to remember long binary paths or many flags.
- Team members can share the same commands while keeping local overrides in YAML.
- Automation in CI can reuse exactly the same command set used locally.

In other words, `plonex` behaves like an orchestration layer over project runtime
tools, while still letting you control details through configuration.

You can still see what happens when you run a command passing the `-v/--verbose` flag or setting `log_level: debug` in YAML.
This is useful for troubleshooting and understanding the underlying behavior.

## Default actions

You can configure what happens when you run `plonex` with no explicit command.

By default, `plonex` shows the command help.

If you want a different behavior, set either `default_action` or
`default_actions` in `etc/plonex.yml`.

For example, to ensure supervisor is started and then run WSGI client is run in the foreground, you can set:

```yaml
default_actions:
  - supervisor start
  - supervisor status
  - instance debug
```

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

## Development FAQ

### How do I start a new project?

```sh
plonex project init myproject
cd myproject
plonex supervisor start
plonex supervisor status
```

Supervisor starts the generated ZEO and WSGI programs in the background. For
interactive development, the shell workflow below gives direct debugger input.

### How do I run Plone with a debugger and still run commands?

```text
plonex shell
plonex[myproject]> db start &
plonex[myproject]> instance debug
... press Ctrl-Z to return to the prompt ...
plonex[myproject]> options %2
plonex[myproject]> instance upgrade
plonex[myproject]> fg %2
```

Ctrl-Z detaches without stopping the server. `jobs` lists the actual IDs;
`logs %2` reads output and `kill %2` stops that job. `fg` only reattaches jobs;
start new instances with `instance debug`. Exiting the shell stops its jobs.
Use an already-running ZEO server instead of starting a second one when your
project is configured with a shared database.

### How do I develop an add-on from a checkout?

Declare its repository and editable installation together:

```yaml
sources:
  my.addon:
    repo: git@github.com:example/my.addon.git
    rev: main
    install: true
    extras: [test]
```

```sh
plonex sources clone
plonex dependencies install
plonex sources list
```

Editable installs use the checkout directly. A monorepo can add `subdirectory`;
`path` selects a custom checkout folder. Remove corresponding manual `-e` entries
when migrating. Distribution names such as `my-addon` are canonicalized, while
Python import names such as `my.addon` retain their dots.

### Why do Python changes not appear in the application?

Check both the declaration and actual installation:

```sh
plonex project describe sources
plonex project describe dependencies
```

The source should have `install: true`, and its installed metadata should identify
the expected checkout as editable. A running process can still hold imported
Python modules; restart the instance after code changes when required. Dependency,
extra, or packaging changes need another `dependencies install`. An ordinary
`editable: false` installation contains built code rather than live source files.

### How do I update dependencies and remove obsolete packages?

```sh
plonex sources update
plonex dependencies install
plonex dependencies sync
plonex dependencies outdated
```

`install` preserves unrelated installed packages. `sync` resolves the declared
requirements and removes packages outside that environment. To combine checkout
updates with installation, use `dependencies install --update-sources`.
Output reports actual changes; an unchanged run prints `No package changes.`

### Where should additional requirements and pins go?

Use `pip_requirements` or `etc/requirements.d/*.txt` for requirements and
`etc/constraints.d/*.txt` for pins. These can also come from profiles.
When constraint fragments in the same directory pin the same package, the first
filename in alphabetical order takes precedence. Project constraints take
precedence over profile constraints.
`dependencies add 'my-addon[test]'` records a requirement and installs it.
Save missing pins with `dependencies install --persist-local`; the local pin file
stays separate from shared constraints. Use a raw text URL for
`plonex_base_constraint`, rather than a GitHub `/blob/` HTML page.

### Which file set this option, and why did it change?

```sh
plonex project describe configuration --key http_port
plonex project describe configuration --key http_port instance debug --port 8081
plonex project describe analytics instance debug
plonex project describe profiles
```

The configuration report shows the resolved value, winning definition, earlier
values, and Jinja references. Adding a command inspects that command's defaults,
service-specific files, extra files, and CLI overrides. Analytics shows override
chains and configuration dependencies. Sensitive fields and derived secrets are
redacted. Use `--format json` for automation.

### How do I keep personal settings out of a shared profile?

Put machine-specific overrides in `etc/plonex.local.yml`. Mappings and lists
normally replace earlier values. `+sources` adds or replaces complete source
entries, and `+pip_requirements` appends requirements. A source entry is itself
replaced, so include its repository and other settings when overriding it.
Use `project describe configuration --key sources` to inspect the result.

### How do I open a useful project report?

```sh
plonex project describe --format html --browse
plonex project describe runtime --browse
plonex project describe jobs --browse
```

The complete report is `var/plonex_description/index.html`. It has responsive
layout, section navigation, search, file links, and definition history. Markdown
and JSON exports sit alongside it. Focused reports use their section name and
preserve the complete report. Existing file paths in the HTML report are clickable,
including configuration history. Open the report on the project host: browsers may
block local file links from a web server, and they decide whether to display or
download each file. Inspection does not install, compile, export the configured
environment, or start application services.

### Why is my project not working as expected?

```sh
plonex project doctor
plonex project doctor --format json
plonex supervisor start --plan
```

The doctor reports configuration, virtualenv, source installation, constraint,
preparation, and local service problems with suggested next steps. It does not
install packages or change the project. Use `--strict` to make warnings fail a CI
check. See the [doctor reference](docs/cli.md#project-doctor) for its scope and
limitations.

### How do I compare or recreate an environment?

```sh
plonex project snapshot create --output deployment.json
plonex project snapshot compare deployment.json
plonex project snapshot prepare deployment.json --to /path/to/new-venv
```

Snapshots capture installed versions, source revisions, and dependency inputs.
Preparation verifies supported inputs before creating a separate environment.
See [project snapshots](docs/snapshots.md) for limitations and reproducibility.

### Can I inspect an existing mxdev or Buildout project?

Run `plonex --target /path/to/project project inspect-legacy`. The report reads
local configuration without running recipes or modifying the project. The
[CLI reference](docs/cli.md#dependencies-and-sources) shows how to consume mxdev's
generated files while leaving mxdev in charge of generating them.

### How do I run tests and stop in a failing test?

```sh
plonex dependencies add pytest
plonex test pytest my.addon -k login -x --pdb
plonex test zope my.addon -t Login
plonex test robot tests/robot/login.robot --browser firefox
```

Install the add-on's testing extras and the runner it needs. Use Python import
names for package-based tests. Arguments after the package in `test pytest`
go to pytest, including `-k`, `-x`, and `--pdb`. The shell preserves terminal input
for interactive debugging.

### How do I run a script or inspect the ZODB?

```sh
plonex instance run -- scripts/maintenance.py --argument value
plonex instance console
```

The console provides `app`. To establish a Plone site context:

```python
from Testing.makerequest import makerequest
from zope.component.hooks import setSite
from zope.globalrequest import setRequest

app = makerequest(app)
setRequest(app.REQUEST)
site = app["Plone"]
setSite(site)
```

Use `plone.api.env.adopt_user(username="your-user")` for an explicit application
user context when needed. Commit intended database changes with
`transaction.commit()`; abort discarded changes with `transaction.abort()`.
See [Plone's console documentation](https://6.docs.plone.org/admin-guide/run-plone.html#run-a-debug-console).

### How do I run upgrade steps?

Keep the configured application running, then run `plonex instance upgrade`.
Install and enable `collective.ftw.upgrade` in the target project and site. Set
`upgrade_tempfile_auth: true` in YAML and restart the instance to enable private
temporary-file authentication for the same OS account. The default instance URL
uses the configured HTTP port; select another running instance with
`plonex instance upgrade --url http://127.0.0.1:8081/`. Alternatively configure
the upgrade tool's authentication and URL environment variables explicitly.
In the shell, detach the instance with Ctrl-Z, run the upgrade, and reattach.
Review and back up the database before planned deployment upgrades.

### Why does Supervisor startup prepare dependencies and templates?

`plonex supervisor start` ensures that declared dependencies and generated runtime
files are current before starting Supervisor. It skips unchanged work. Requirement
and constraint changes trigger installation checks; changing an HTTP port only
regenerates affected runtime files.

```sh
plonex supervisor start --plan
plonex project describe preparation
```

The plan explains stale tasks and their prerequisites without executing them.
Preparation never implicitly updates Git sources, removes unused packages, runs
Plone upgrades, or restarts existing instances. Use `dependencies sync` for package
removal and explicit Supervisor commands to apply changes to running services.
See [incremental preparation](docs/preparation.md) for caching, failures, and
remote profile behavior.

### How do I apply Supervisor configuration changes?

```sh
plonex supervisor reread
plonex supervisor update
plonex supervisor status
```

`update` applies changed program declarations. `restart` restarts all managed
programs; `graceful --interval 2` restarts them sequentially. Neither should be
confused with editing the currently running process's configuration in memory.
`options %JOB` reports a shell job's startup snapshot even after YAML changes.

### How can I schedule work without a curl password or a CSRF exemption?

```yaml
cron_timezone: Europe/Rome
cron_jobs:
  StoreSessionStats:
    schedule: "15 2 * * *"
    callable: my.addon.jobs:store_session_stats
    site: /Plone
    context: sectors
    user: scheduler
    timeout: 900
    lock: zope
    lock_timeout: 300
    enabled: false
```

Move the business logic into the callable, installed in the project virtualenv.
Create the named Plone user with the roles it needs; no password belongs in this
job declaration. Test with `cron run StoreSessionStats`, inspect `cron logs` and
`cron history`, then enable the schedule and apply Supervisor configuration.

Plonex installs the job runtime and Huey into the target virtualenv
when jobs are configured. Supervisor launches
the target interpreter directly. Manual-only job declarations still keep a worker
for explicitly queued tasks.

A protected browser view can call the same function after POST and authenticator
checks. The job runs through a dedicated ZEO client and owns its transaction;
it does not invoke the browser view or disable CSRF. See the
[complete scheduled-job guide](docs/jobs.md), including a protected view example.

### How do I check scheduling times, failures, and overlap?

```sh
plonex cron list
plonex cron status
plonex cron queue
plonex cron history StoreSessionStats
plonex cron logs StoreSessionStats --tail 100
plonex project describe jobs --browse
```

Schedules use explicit IANA timezones, defaulting to UTC. Common lock names
serialize related jobs; manual and daemon runs share those locks. Timeouts stop
the job subprocess group and record the outcome. Retries default to zero; enable
them only for work that tolerates repeating after a failure. The queue survives
restarts, but missed periodic schedules are not replayed.

### How do I inspect or retry queued work?

```sh
plonex cron status
plonex cron queue
plonex cron inspect TASK_ID
plonex cron retry TASK_ID
plonex cron revoke TASK_ID
plonex project describe queue
```

Monitoring uses Huey's statistics extension in the target environment. Task IDs
link events to individual attempts and logs. `retry` creates a new task using the
current definition; `revoke` prevents a queued execution and does not kill a
running process. Add `--format json` for complete task IDs and structured output.
See the [queue guide](docs/jobs.md#queue-monitoring-and-controls).

### What changed in the command names?

There are no built-in synonyms such as both `--sync` and `sync`. Use
`dependencies sync`, `dependencies outdated`, `instance debug`, and
`project describe`. Update aliases, default command lists, deployment scripts,
and Supervisor `command` values from older projects. Configuration identities
such as `run_for: fg` and `etc/plonex-runwsgi.yml` retain their meaning.
The [CLI migration table](docs/cli.md#breaking-migration) lists every removed form.

## Typical workflows

### Local development

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

### Setup and info

`shell [--target PATH]`

- Open the interactive project shell, including aliases, completion, job control,
  logs, and startup option inspection. See [Interactive shell](#interactive-shell).

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

See [development next steps](docs/development.md) for proposed environment checks,
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

`instance upgrade`

- Run Plone upgrade steps.

### Configuration editing

There is a dedicated `plonex project edit` command to help you edit the configuration files for your `plonex` project.
You can use `--all` to open all discovered config files in your editor, otherwise you can select which files to edit interactively.
The selected editor:

1. with the `--editor` option in the command line
1. with the `editor` option if specified in the `etc/plonex.yml` configuration file
1. can be configured with the `EDITOR` environment variable
1. use the `open` command as a fallback if none of the above is specified.

You can of course edit the configuration files manually, but `plonex project edit` helps you discover and open them quickly.

### Runtime

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

### Database

`db backup`

- Create a verified offline snapshot of FileStorage and blob storage.

`db pack [--days DAYS]`

- Pack ZODB revisions older than `DAYS` (default: `7`).
- Uses merged `zeo_address` from your config files.

`db restore --to NEW_DIRECTORY [--from SNAPSHOT_DIRECTORY]`

- Recover into a new directory without replacing the live database. See
  [database backup and recovery](docs/recovery.md).

### Tests

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

## Under the hood

Services remain dataclasses based on `BaseService`. Commands resolve the project,
merge configuration, enter the service (including helper services), then run the
appropriate executable from the project virtualenv.

| Command                            | Main service     | Execution                                                                                                          |
| ---------------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------ |
| `instance debug`, `instance start` | `RunWSGI`        | `.venv/bin/runwsgi tmp/<name>/etc/wsgi.ini`                                                                        |
| `instance console`, `instance run` | `ZConsole`       | `.venv/bin/zconsole ACTION tmp/<name>/etc/zope.conf ...`                                                           |
| `db start`                         | `ZeoServer`      | `.venv/bin/runzeo -C tmp/zeoserver/etc/zeo.conf`                                                                   |
| `supervisor start`                 | `Supervisor`     | `.venv/bin/supervisord -c tmp/supervisor/etc/supervisord.conf`                                                     |
| `supervisor status`                | `Supervisor`     | `.venv/bin/supervisorctl -c tmp/supervisor/etc/supervisord.conf status`                                            |
| `dependencies install`             | `InstallService` | `uv pip install -r var/requirements.txt -c var/constraints.txt`                                                    |
| `dependencies sync`                | `InstallService` | `uv pip compile ... --output-file var/compiled-requirements.txt`, then `uv pip sync var/compiled-requirements.txt` |
| `dependencies outdated`            | `InstallService` | `uv pip list --outdated`                                                                                           |
| `test pytest PACKAGE`              | `PytestService`  | `.venv/bin/python -m pytest --pyargs PACKAGE ...`                                                                  |
| `test zope PACKAGE`                | `ZopeTest`       | `.venv/bin/zope-testrunner --all --quiet -pvc --package PACKAGE --auto-path ...`                                   |
| `db pack`                          | `ZeoServer`      | `.venv/bin/zeopack -u <zeo_address> -d <days>`                                                                     |
| `options COMMAND`                  | Inspection       | Construct the same service and read its resolved options                                                           |

Paths shown above use default folder and service names. Dependency inspection
uses `uv pip freeze` with the target project's Python, so printed package names
are canonical. Runtime templates and configured helper services can add other
preparation steps.

The shared service registry and invocation binding are also used by inspection.
The shell owns terminal-backed jobs; services continue to run in isolated CLI
processes. Tables and inspection reports share a Markdown-capable presenter.
See [Project decisions](docs/decisions.md) for ownership boundaries, snapshot
semantics, and how to add commands while preserving these patterns.

## Troubleshooting

### "Could not find etc/plonex.yml"

`plonex` looks for `etc/plonex.yml` by walking up from the target directory.
Use one of these approaches:

- run commands from inside your project tree,
- pass `--target /path/to/project`,
- or initialize a project first with `plonex project init`.

### Command uses unexpected values

Use `plonex options COMMAND` with the same flags as the command you are
troubleshooting. For a running or completed shell job, `options %1` shows the
options it actually started with. Use `jobs` to find the job ID.

`plonex project compile` also writes merged configuration to `var/plonex.yml`, but that
file is not a substitute for inspecting a particular service and its CLI flags.

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
plonex dependencies install
```

This recreates or updates environment-installed tooling used by runtime commands.

## Current limitations

- Database snapshots require stopped FileStorage writers and a coordinated blob
  store; legacy repozo backups require their original restore procedure.
- Interactive job control requires a Unix terminal. Piped commands run without
  terminal job control.
- Jobs and snapshots belong to one shell session. Job logs and snapshots remain
  on disk, but a new shell does not adopt old processes or job IDs.
- Option previews construct services and may create directories; they do not run
  services. Startup snapshots are not live views into a process's Python state.

## AI Assistance

Parts of this project were developed with the assistance of AI-based tools.

All generated content was reviewed, tested, and modified by human maintainers
before inclusion in the repository.
