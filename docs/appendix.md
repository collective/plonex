# Appendix: How can I…?

These recipes answer common questions. Run commands from your project directory, or provide `--target /path/to/project` before the command. Replace example names and paths with your own.

## How do I start a new project?

```sh
plonex project init myproject
cd myproject
plonex supervisor start
plonex supervisor status
```

Supervisor starts the generated ZEO and WSGI programs in the background. For
interactive development, the shell workflow below gives direct debugger input.

## How do I run Plone with a debugger and still run commands?

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

## How do I develop an add-on from a checkout?

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

## Why do Python changes not appear in the application?

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

## How do I update dependencies and remove obsolete packages?

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

## Where should additional requirements and pins go?

Use `pip_requirements` or `etc/requirements.d/*.txt` for requirements and
`etc/constraints.d/*.txt` for pins. These can also come from profiles.
When constraint fragments in the same directory pin the same package, the first
filename in alphabetical order takes precedence. Project constraints take
precedence over profile constraints.
`dependencies add 'my-addon[test]'` records a requirement and installs it.
Save missing pins with `dependencies install --persist-local`; the local pin file
stays separate from shared constraints. Use a raw text URL for
`plonex_base_constraint`, rather than a GitHub `/blob/` HTML page.

## Which file set this option, and why did it change?

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

## How do I keep personal settings out of a shared profile?

Put machine-specific overrides in `etc/plonex.local.yml`. Mappings and lists
normally replace earlier values. `+sources` adds or replaces complete source
entries, and `+pip_requirements` appends requirements. A source entry is itself
replaced, so include its repository and other settings when overriding it.
Use `project describe configuration --key sources` to inspect the result.

## How do I open a useful project report?

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

## Why is my project not working as expected?

```sh
plonex project doctor
plonex project doctor --format json
plonex supervisor start --plan
```

The doctor reports configuration, virtualenv, source installation, constraint,
preparation, and local service problems with suggested next steps. It does not
install packages or change the project. Use `--strict` to make warnings fail a CI
check. See the [doctor reference](cli.md#project-doctor) for its scope and
limitations.

## How do I compare or recreate an environment?

```sh
plonex project snapshot create --output deployment.json
plonex project snapshot compare deployment.json
plonex project snapshot prepare deployment.json --to /path/to/new-venv
```

Snapshots capture installed versions, source revisions, and dependency inputs.
Preparation verifies supported inputs before creating a separate environment.
See [project snapshots](snapshots.md) for limitations and reproducibility.

## Can I inspect an existing mxdev or Buildout project?

Run `plonex --target /path/to/project project inspect-legacy`. The report reads
local configuration without running recipes or modifying the project. The
[CLI reference](cli.md#dependencies-and-sources) shows how to consume mxdev's
generated files while leaving mxdev in charge of generating them.

## How do I run tests and stop in a failing test?

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

## How do I run a script or inspect the ZODB?

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

## How do I run upgrade steps?

Keep the configured application running, then run `plonex instance upgrade`.
Install and enable `collective.ftw.upgrade` in the target project and site. Set
`upgrade_tempfile_auth: true` in YAML and restart the instance to enable private
temporary-file authentication for the same OS account. The default instance URL
uses the configured HTTP port; select another running instance with
`plonex instance upgrade --url http://127.0.0.1:8081/`. Alternatively configure
the upgrade tool's authentication and URL environment variables explicitly.
In the shell, detach the instance with Ctrl-Z, run the upgrade, and reattach.
Review and back up the database before planned deployment upgrades.

## Why does Supervisor startup prepare dependencies and templates?

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
See [incremental preparation](preparation.md) for caching, failures, and
remote profile behavior.

## How do I apply Supervisor configuration changes?

```sh
plonex supervisor reread
plonex supervisor update
plonex supervisor status
```

`update` applies changed program declarations. `restart` restarts all managed
programs; `graceful --interval 2` restarts them sequentially. Neither should be
confused with editing the currently running process's configuration in memory.
`options %JOB` reports a shell job's startup snapshot even after YAML changes.

## How can I schedule work without a curl password or a CSRF exemption?

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

Plonex installs the matching job runtime and Huey into the target virtualenv
when jobs are configured. Supervisor launches
the target interpreter directly. Manual-only job declarations still keep a worker
for explicitly queued tasks.

A protected browser view can call the same function after POST and authenticator
checks. The job runs through a dedicated ZEO client and owns its transaction;
it does not invoke the browser view or disable CSRF. See the
[complete scheduled-job guide](jobs.md), including a protected view example.

## How do I check scheduling times, failures, and overlap?

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

## How do I inspect or retry queued work?

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
See the [queue guide](jobs.md#queue-monitoring-and-controls).

## What changed in the command names?

There are no built-in synonyms such as both `--sync` and `sync`. Use
`dependencies sync`, `dependencies outdated`, `instance debug`, and
`project describe`. Update aliases, default command lists, deployment scripts,
and Supervisor `command` values from older projects. Configuration identities
such as `run_for: fg` and `etc/plonex-runwsgi.yml` retain their meaning.
The [CLI migration table](cli.md#breaking-migration) lists every removed form.

## How can I back up before an upgrade?

Stop Supervisor and coordinate any other processes that write to the database or
blob storage, then create a snapshot:

```sh
plonex supervisor stop
plonex db backup
```

The backup is offline and applies to the configured local FileStorage and blob
storage. Follow [backup and recovery](recovery.md) for verification, limitations,
and a restore into a separate directory before relying on the backup.

## How can I recover without replacing the live database?

Choose a new destination and restore into it:

```sh
plonex db restore --to /path/to/new-recovery-directory
plonex db restore --from /path/to/snapshot --to /path/to/another-new-directory
```

Inspect and validate the recovered data using the procedure in
[Database backup and recovery](recovery.md) before considering a cutover.

## How can I run another instance on a different port?

With the project's ZEO server already running, start another foreground instance
and inspect its effective settings:

```sh
plonex options instance debug --port 8081
plonex instance debug --port 8081
```

Use `plonex shell` if you need to detach and reattach the process while running
other commands. See [Interactive shell](shell.md) for job control and cleanup.

## How can I identify what Supervisor will change before startup?

```sh
plonex supervisor start --plan
plonex project describe preparation --format json
```

The plan explains stale inputs and prerequisites. See
[Incremental preparation](preparation.md) for remote profiles and the difference
between preparing files and applying changes to running processes.

## How can I investigate a failure systematically?

| Symptom                  | First action                                                    | More detail                           |
| ------------------------ | --------------------------------------------------------------- | ------------------------------------- |
| Project cannot be found  | Check `--target` and `etc/plonex.yml`                           | [Troubleshooting](troubleshooting.md) |
| Unexpected setting       | `plonex options instance debug`                                 | [Configuration](configuration.md)     |
| Services are not running | `plonex supervisor status`                                      | [Operating Plonex](workflows.md)      |
| Setup is inconsistent    | `plonex project doctor`                                         | [Doctor](cli.md#project-doctor)       |
| Scheduled job failed     | `plonex cron history JOB` and `plonex cron logs JOB --tail 100` | [Scheduled jobs](jobs.md)             |
| Environment differs      | `plonex project snapshot compare deployment.json`               | [Snapshots](snapshots.md)             |
