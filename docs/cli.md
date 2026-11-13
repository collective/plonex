# CLI command structure

Use `plonex RESOURCE ACTION [options]`. The command line, interactive shell,
completion, project aliases, and `options` previews share this grammar.
Each built-in operation has one spelling. A bare resource displays help and
performs no operation, including outside an initialized project.

| Resource       | Actions                                                                                                                        | Purpose                                |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------- |
| `project`      | `init`, `compile`, `describe`, `doctor`, `snapshot`, `inspect-legacy`, `edit`                                                  | Project configuration and reports      |
| `dependencies` | `install`, `sync`, `outdated`, `add`, `preview`                                                                                | Requirements and virtualenv management |
| `sources`      | `list`, `clone`, `update`, `missing`, `tainted`, `suggest`                                                                     | Source checkouts                       |
| `instance`     | `start`, `debug`, `console`, `run`, `add-user`, `upgrade`                                                                      | Plone instances                        |
| `supervisor`   | `status`, `start`, `stop`, `restart`, `graceful`, `reread`, `update`                                                           | Background services                    |
| `db`           | `start`, `backup`, `restore`, `pack`                                                                                           | The ZEO database                       |
| `test`         | `pytest`, `zope`, `robot`, `robot-server`, `sources`                                                                           | Tests and test services                |
| `cron`         | `list`, `run`, `enqueue`, `history`, `logs`, `configure`, `daemon`, `status`, `queue`, `inspect`, `retry`, `revoke`, `restore` | Scheduled jobs                         |

`shell` opens the project prompt. `options COMMAND ...` previews a command's
resolved service options. These direct operations do not need an action word.

```sh
plonex project init myproject
cd myproject
plonex sources clone
plonex dependencies install
plonex instance debug --port 8081
plonex test pytest my.package -k login --pdb
plonex options instance debug --port 8081
```

`instance start`, `instance debug`, and `db start` run in the foreground.
`supervisor start` manages configured programs in the background.
`instance console` opens the interactive Zope console; scripts use
`instance run -- task.py --flag value`.

For an editor debugger, install `debugpy` in the project and use
`plonex instance debug --debugpy 5678`; the debugger listens only on
`127.0.0.1`. Add `--wait-for-debugger` to wait for an attachment before the
instance starts.

Global target selection goes before the resource:

```sh
plonex --target /path/to/project dependencies sync --update-sources
```

Action-specific options go after the action. `--verbose` and `--quiet` are
accepted before the resource, between resource and action, or after the action.
Test-runner arguments retain their normal forwarding rules: everything after
the package in `test pytest PACKAGE ...` goes to pytest.

## Project reports

`project describe` produces a complete report. Select a section to avoid unrelated
probes and focus the output:

```sh
plonex project describe overview
plonex project describe sources
plonex project describe dependencies
plonex project describe services
plonex project describe runtime
plonex project describe jobs
plonex project describe queue
plonex project describe preparation
plonex project describe files
plonex project describe profiles
plonex project describe environment
plonex project describe configuration --key http_port
plonex project describe analytics
```

Use a real command after `configuration` or `analytics` to explain its own defaults,
service-specific files, and CLI overrides:

```sh
plonex project describe configuration --key http_port instance debug --port 8081
plonex project describe analytics instance debug
plonex project describe configuration --key sources dependencies install
```

Reports export responsive, searchable HTML, Markdown, and JSON under
`var/plonex_description/`. Complete reports use `index.*`; focused reports use the
section name and do not overwrite the complete report.

```sh
plonex project describe --format html --browse
plonex project describe configuration --format json --key http_port
plonex project describe sources --format markdown
```

`--format terminal|markdown|html|json` controls stdout. HTML output prints the
file URI; `--browse` opens that file. Inspection does not install packages,
compile configuration, export environment variables, or start services. Loading
an explicitly configured remote Git profile can still fetch that profile.
Conventional sensitive fields and derived secrets are redacted in exports.

## Project doctor

```sh
plonex project doctor
plonex project doctor --format json
plonex project doctor --strict
```

The doctor checks configuration, the project Python, installed direct requirements,
selected source installations, available base constraints, installed versions
against already-generated constraints, and the Supervisor preparation plan. It
also attempts to connect to the local ZEO endpoint and inspect existing Supervisor
status. Findings include a severity, a code, evidence, and a suggested next step.
JSON output has the same findings and a count per severity.

Errors produce exit status 1; warnings produce status 0 unless `--strict` is set.
The doctor does not install packages, fetch URLs or remote profiles, write project
files, or start services. It only probes Unix sockets and loopback TCP addresses for
ZEO; other addresses are reported as unchecked. A listening endpoint does not
establish database health. A denied connection is reported as an unavailable check.

The version checks use direct YAML requirements and parseable entries in the
existing generated constraints file, which may itself be stale. They are not a
dependency resolver and do not fully inspect nested files or remote inputs. Python
metadata does not record which extras were requested: the doctor can check direct
extra dependencies, but reports the selection itself as unverified.

## Dependencies and sources

`project snapshot create`, `compare`, and `prepare` capture installed versions and
source revisions, compare the current project, and reconstruct supported versions
in a new virtualenv. See [project snapshots](snapshots.md) for reproducibility
limits. `project inspect-legacy --format json` inventories local mxdev and Buildout
configuration without executing recipes or changing either tool's files. This
inspection also works in a directory that has no `etc/plonex.yml`.

For an mxdev project, you can run mxdev explicitly and point Plonex at its generated
files, for example:

```yaml
plonex_base_constraint: constraints-mxdev.txt
pip_requirements:
  - "-r requirements-mxdev.txt"
```

Adjust the paths to match `mx.ini`. mxdev remains responsible for generating those
files and managing its checkouts; Plonex installs the resulting inputs. Avoid also
selecting the same checkout in Plonex's `sources` configuration. Legacy inspection
reports possible mappings; Buildout recipes and configuration interpolation require
manual review and are not executed or converted.

Configured selected sources can declare an argv-list `test_command`:

```yaml
sources:
  my.addon:
    repo: https://github.com/example/my.addon.git
    install: true
    test_command: [python, -m, pytest, tests]
```

For a checkout whose packaging metadata computes the distribution name dynamically,
set `distribution: my-addon` explicitly. Plonex normalizes the name and uses it
when reconciling installed metadata and constraints.

Run all selected sources that have commands with `plonex test sources`, or choose
one and forward runner arguments with `plonex test sources my.addon -- -k login`.
Commands run from the source project directory with the target virtualenv on PATH.
All requested declarations are validated before any command starts.

`dependencies install` installs requirements and selected sources. `dependencies sync` compiles and synchronizes the environment, including removal of packages
that are no longer needed. Both accept `--update-sources` and exactly one of
`--persist`, `--persist-local`, and `--persist-profile`. `dependencies add SPEC ...`
records specifications and then installs dependencies. `dependencies outdated`
only lists available upgrades.

`plonex dependencies preview` generates proposed inputs and a copy of the installed
distribution metadata in a temporary environment, shows constraint changes, and
asks uv for an offline dry-run plan. It does not install into the project virtualenv
or rewrite generated project files. uv may run source build backends for metadata;
those backends can write to their source checkouts. uv may also update its cache.
The temporary inventory copies `.dist-info` metadata; legacy installations known
only through external `.egg-info` or editable path hooks may not be represented.
Remote constraint snapshots must already be cached;
use `--online` if uv needs to query indexes or remote requirements. An offline plan
can fail when required packages are not in the uv cache. `--format json` provides
the same results for tools.

Output summarizes actual additions, removals, upgrades, downgrades, reinstalls,
and source changes. An unchanged environment prints `No package changes.`
Internal inventory checks stay silent. Warnings and failure diagnostics remain
visible; `--verbose` shows full uv output.

`sources clone` clones missing checkouts. `sources update --force` retains its
confirmation prompt; add `--yes` to skip it. `sources suggest` accepts `--apply`,
`--apply-local`, and `--apply-profile`. Source selection remains explicit with
`install: true` in YAML.

## Incremental Supervisor startup

`supervisor start` first ensures dependencies and generated configuration are
current. Preview its dependency graph with `supervisor start --plan`; inspect the
same freshness information through `project describe preparation`. Plans explain
what changed, which prerequisites must finish, and which services may be affected.

Unchanged inputs and outputs skip their tasks. Dependency installation, template
rendering, remote constraint snapshots, failures, and concurrent invocations are
covered in [incremental preparation](preparation.md). Automatic preparation uses
installation rather than package-removing synchronization. Source updates and
Plone upgrades remain explicit operations.

`supervisor status` and `supervisor stop` do not prepare or rewrite configuration.
Other Supervisor actions retain their existing behavior. Already-running programs
need explicit updates/restarts to load changed dependencies or configuration.

Use `supervisor restart PROGRAM ...` for specific managed programs; omitting names
restarts all programs. A targeted restart requires an already-running Supervisor
and never starts it implicitly.

## Breaking migration

The following old forms are removed, rather than hidden aliases:

| Removed form                                     | Use                                                                   |
| ------------------------------------------------ | --------------------------------------------------------------------- |
| `init`, `compile`, `describe`, `edit`            | `project init`, `project compile`, `project describe`, `project edit` |
| Bare `dependencies`                              | `dependencies install`                                                |
| `dependencies --sync`                            | `dependencies sync`                                                   |
| `dependencies --outdated`                        | `dependencies outdated`                                               |
| `install SPEC ...`                               | `dependencies add SPEC ...`                                           |
| `runwsgi`, `fg`                                  | `instance start`, `instance debug`                                    |
| `zconsole`, `zconsole debug`                     | `instance console`                                                    |
| `run`, `zconsole run`                            | `instance run`                                                        |
| `adduser`, `upgrade`                             | `instance add-user`, `instance upgrade`                               |
| `zeoserver`                                      | `db start`                                                            |
| `pytest`, `zopetest`, `robottest`, `robotserver` | `test pytest`, `test zope`, `test robot`, `test robot-server`         |
| `sources clone-missing`                          | `sources clone`                                                       |
| `sources force-update`                           | `sources update --force`                                              |
| `sources suggest-existing`                       | `sources suggest`                                                     |
| `describe --html`                                | `project describe --format html`                                      |

Update aliases, `default_action` / `default_actions`, shell scripts, and Supervisor
`command` values in `services` templates. New project templates already use the
canonical forms. Existing generated Supervisor files should be regenerated from
updated declarations before restarting services.

Service identities are configuration names, not extra CLI spellings:
`instance debug` still uses `fg`, `instance start` still uses `runwsgi`, and
`services[].run_for: fg` still matches. Service-specific files such as
`etc/plonex-fg.yml` keep their meaning. Distribution names, Python import names,
and template paths are unaffected.

The interactive shell's `fg` only reattaches a job. Start an instance with
`instance debug`; use `jobs`, `attach`, `bg`, `logs`, and `kill` for shell jobs.
Scheduled jobs use the separate `cron` resource, avoiding that namespace collision.
See [scheduled jobs](jobs.md) and the [development FAQ](appendix.md).

## Project job runtime

Configured jobs add the `plonex` runtime and `huey[stats]` requirements
to the project. Huey runs in that target virtualenv. `cron daemon` delegates to its
interpreter; Supervisor launches that interpreter directly.

`cron status`, `cron queue`, and `cron inspect TASK_ID` show live queue state and
recorded events. `cron retry TASK_ID` creates a new task from a failed execution;
`cron revoke TASK_ID` prevents future execution and `cron restore TASK_ID` restores
it. All accept `--format json`; `cron history --format json` exports attempts and
log paths. See [queue monitoring](jobs.md#queue-monitoring-and-controls).
