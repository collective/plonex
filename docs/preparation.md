# Incremental preparation

`plonex supervisor start` prepares the project before starting Supervisor. Plonex
uses an embedded [doit](https://pydoit.org/extending.html) task runner; projects do
not need a Makefile or `dodo.py`. The normal plonex CLI remains the entry point.

Preview the work without installing packages, rendering outputs, starting services,
or downloading constraints:

```sh
plonex supervisor start --plan
plonex project describe preparation
plonex project describe preparation --format json
```

The report includes the same task graph, freshness decisions, prerequisites, and
potentially affected services. A plan does not create preparation state. An
uncached remote Git profile must first be resolved with `project compile`, or
replaced with a local checkout; planning never clones it.

## What startup prepares

```{mermaid}
flowchart TD
    D[Generate requirements and constraints] --> E[Ensure virtualenv dependencies]
    E --> H[Configured Supervisor helper services]
    E --> S[Supervisor configuration and directories]
    H --> R[Runtime templates for managed Plonex instances]
    E --> C[Scheduled job program]
    R --> F[Validate generated outputs]
    S --> F
    C --> F
    F --> START[Start Supervisor]
```

Each task checks its own inputs and outputs after its prerequisites finish.
Prerequisites shared by multiple tasks execute once. A prerequisite that needs
work does not automatically force all downstream work: unchanged outputs can leave
downstream tasks current. The plan labels uncertain downstream checks as
`check after prerequisites`.

Supervisor programs invoking `plonex instance start`, `plonex instance debug`, or
`plonex db start` have their runtime templates prepared too. Normal runtime names,
configuration files, and command-line overrides apply. Non-Plonex executables
remain Supervisor's responsibility.

`services[].run_for: supervisor` templates participate in the graph. Their declared
order is preserved. Other helper services are explicit hooks without a reliable
freshness contract, so they run on every startup preparation; the plan identifies
them as always evaluated.

## When work becomes stale

| Change                                                    | Preparation                                             |
| --------------------------------------------------------- | ------------------------------------------------------- |
| Add, edit, or remove a requirement/constraint fragment    | Regenerate dependency inputs and reconcile installation |
| Change a nested `-r` or `-c` input                        | Reconcile affected dependency inputs                    |
| Change an effective dependency option or source selection | Reconcile installation                                  |
| Edit ordinary Python code in an editable selected source  | Skip installation                                       |
| Change a selected source's project metadata or extras     | Reinstall that source and reconcile dependencies        |
| Edit a regularly installed selected source                | Reinstall that source                                   |
| Change an instance port or a runtime template             | Render affected outputs; skip dependency installation   |
| Change a Jinja include                                    | Render affected outputs                                 |
| Remove or edit a generated output                         | Recreate it from its declared template                  |
| Change installed distribution metadata outside plonex     | Reconcile the virtualenv                                |
| No relevant change                                        | Skip preparation                                        |

A constraint limits a package version; it does not request installation of that
package. Automatic preparation uses installation, not synchronization. Removed
requirements can therefore leave unused packages installed. Use the explicit
`plonex dependencies sync` command to remove packages no longer required.

Dependency checks include local profiles, fragment membership, nested local inputs,
selected source paths and metadata, configured Python, and conventional build
settings such as `UV_*`, `PIP_*`, and compiler flags. Runtime-only settings do not
invalidate installation. Arbitrary application environment variables are not
assumed to influence package builds.

Configured jobs add the matching `plonex` project runtime and Huey with its
statistics extension to the target environment's dependency inputs. Manual-only jobs also request the
runtime; their Supervisor worker consumes explicitly enqueued work.

The virtualenv check observes interpreter identity and installed distribution
metadata. It is not a full integrity scan of every installed Python file.
Configuring a different Python version stops startup and asks you to recreate the
virtualenv explicitly; preparation does not replace it.

Source metadata discovery covers `pyproject.toml`, `setup.cfg`, `setup.py`, and conventional
requirements files. Projects whose build configuration reads additional arbitrary
files should use an explicit dependency installation when those files change.

## Remote inputs and reproducibility

Remote constraints are validated and cached under the configured
`var_folder/cache/constraints/`. Startup uses these snapshots and downloads missing
ones, including nested constraints. A moving URL does not silently change the
project on every startup.

An explicit `plonex dependencies install` or `plonex dependencies sync` refreshes
remote constraints. A failed download or an HTML response stops preparation and
preserves the previous constraints output. Remote requirement URLs still follow
uv's fetching behavior when installation runs; prefer immutable URLs and pinned
requirements for deployments.

Remote Git profiles have stable checkouts under `var/cache/profiles/` in the
project. They are reused across configuration loads. `project describe profiles`
shows their paths. Update a cached checkout explicitly, for example with
`git -C PATH pull --ff-only`, or manage the profile as your own local checkout.
Startup never updates source repositories implicitly, including projects setting
`sources_update_before_dependencies: true` for interactive dependency commands.

## Successful work, failures, and concurrent commands

Preparation records content fingerprints rather than relying on modification
times. Generated files are replaced atomically, and identical content preserves
its timestamp. Jinja includes are evaluated afresh, including when a file's
modification time was preserved.

Receipts live under the configured `var_folder/preparation/`, with private
permissions. They contain digests and paths rather than raw configuration values
or credentials. Only successful tasks receive current receipts. Failed tasks
block startup and are retried on the next invocation. Prior output ownership is
retained separately during failures so cleanup can be retried safely.

A project lock serializes preparation and explicit dependency-install contexts.
Freshness is checked after acquiring the lock, so concurrent commands can reuse
each other's completed work. Configuration edits while a prepared graph is
waiting or running require retrying the command.

When a template declaration is removed, preparation removes its previously tracked,
unchanged output. Unmanaged files are preserved. If an obsolete generated file was
edited manually, preparation stops and asks you to move or remove it. Put lasting
changes in source templates.

## Prepared files and running processes

`supervisor start` ensures prerequisites even if Supervisor is already running.
It reports affected services when preparation changed their dependencies or
configuration. It does not restart those services automatically. Use the explicit
Supervisor commands to apply the intended change:

```sh
plonex supervisor update
plonex supervisor restart
```

`update` applies changed Supervisor program declarations; `restart` restarts the
existing managed programs. Plone database upgrades remain explicit through
`plonex instance upgrade`.

This first graph covers Supervisor startup. `supervisor status` and `supervisor stop`
perform no preparation. Other command families retain their existing behavior;
`dependencies install` and `dependencies sync` record successful installation so
startup can reuse it.
