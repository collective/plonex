# Project decisions

This document records the boundaries used by the CLI, interactive shell, job
control, and service inspection. It describes the implementation rather than a
replacement framework.

## Keep the service lifecycle

Services remain keyword-only dataclasses derived from `BaseService`. Defaults
belong in `options_defaults`; configuration merging remains in `BaseService`.
Existing services can prepare directories and template objects in `__post_init__`.
Entering a service exports its configured environment and runs pre-services;
`run()` performs its operation; exiting runs post-services.

The CLI still owns command-specific operations such as `supervisor status`,
`db pack`, and dependency persistence. A service factory does not choose which
operation to run.

## One registry and one argument binding

`ServiceRegistry` in `services/registry.py` owns the service catalog shared with
declarative dependencies. Command mappings such as `fg` → `RunWSGI`, `run` →
`ZConsole`, and `dependencies` → `InstallService` are explicit.

`ServiceInvocation` in `services/invocation.py` translates an already-parsed
argparse namespace into service constructor arguments. CLI execution and option
previews use that same binding. Runtime names, extra configuration files, host
and port overrides, foreground debug settings, and test arguments therefore
have one interpretation. CLI flags used by service methods are retained as
command parameters in inspection reports.

Existing CLI service import/mock points remain usable through the invocation's
optional constructor override. Parser registration and command handlers remain
explicit; services are not discovered through import side effects or metaclasses.

When adding a command:

1. Keep or introduce its `BaseService` dataclass.
1. Add the service to the registry if it is new, and an explicit command mapping
   if the command name differs from the service name.
1. Register its parser and bind its constructor arguments in `ServiceInvocation`.
1. Keep the execution method in the CLI handler and construct through the invocation.
1. Test execution and inspection against the same flags.

## Separate the shell session from jobs and presentation

`ShellSession` owns prompt input, help, parsing, alias-aware CLI routing, and
error recovery. `run_shell()` remains a small compatibility entry point.
Commands execute in fresh CLI processes so their environment and configuration
state do not leak into later commands.

`ShellJobs` owns the job collection and terminal attachment. `ShellJob` owns one
process, PTY, output reader, log, and lifecycle. Ctrl-Z detaches without sending a
stop signal: a WSGI instance must keep answering requests while an upgrade runs.
Ctrl-C is forwarded through the job's terminal. Exiting the session cleans up
the processes it owns. Supervisor-managed services have a separate owner and
are not adopted into this job collection.

`JobPresenter` turns job state into rows. `MarkdownTable` renders those rows using
Rich's pipe-style box and typed colour spans, or exports portable Markdown.
Process control does not contain table layout logic. User command labels are
literal text, not Rich markup. `NO_COLOR` and terminal capabilities remain under
Rich's normal control; Markdown export contains no colour escape sequences.

## Current previews and recorded startup state are different

`plonex options COMMAND ...` creates the same service as execution and reads its
resolved options without entering or running it. This includes the service's own
defaults and normal precedence. Existing constructors may create directories;
previews do not install packages, export service environment variables, execute
service dependencies, or render runtime files. Normal configuration loading may
fetch remote Git profiles, just as it does for execution. Inspection never evaluates a `command`
property merely to display options: some command properties have side effects.

For shell jobs, the launcher supplies a snapshot path and the expected service
identity. At the start of `BaseService.__enter__`, the matching service records
its actual options, constructor arguments, invocation parameters, and configuration
file locations. The invocation marks the actual CLI service instance; the
launcher also checks implementation class and service name. Dependency services
and template pre-services cannot overwrite the main report, even if a helper
has the same class and name. Command parameters come from the child process's
own parsed invocation.

The snapshot is published atomically alongside the job log with owner-only
permissions. The shell reads it for `options %1`; it never recreates a service
from today's YAML and calls that the running job's state. Snapshots remain useful
after exit. A service that has not reached its entry point has no snapshot yet;
help/version commands have no service snapshot. Editing YAML affects future
commands and previews, not recorded startup state. Reports are not remote Python
debuggers and do not track changes a service makes after startup.

Inspection masks conventional password, token, and secret keys, recognized
credential arguments, and URL passwords before writing snapshots or presenting
previews. This is intentionally separate from process logs, which preserve the
program's original output. No global configuration is rewritten by inspection.

## Keep reports and public behavior testable

Presentation tests force terminal colour to verify state styling, check literal
text handling, and verify Markdown escaping and absence of ANSI codes. Service
tests exercise defaults, profiles, extra files, CLI overrides, redaction, and
previews without execution. PTY integration tests verify detach/upgrade/reattach,
job cleanup, debugger input, and startup snapshots surviving YAML edits and exit.

Service and invocation tests preserve configuration identities and argument
forwarding. Public parser tests explicitly reject removed command spellings;
configuration examples, shell tests, and generated deployment commands use the
canonical forms.

## Source selection belongs to a shared installation plan

`SourceInstallPlan` resolves selected checkouts from the calling service's merged
options. `SourceInstallation` owns the project path, extras, installation mode,
and generated requirement. Both source listing and dependency installation use
this model and the same checkout path calculation. New source metadata is not
forwarded as Gitman options.

Sources remain checkout only unless `install: true` is explicit. Selected sources
are editable by default; ordinary requirements and existing editable requirement
files keep working. Paths are emitted as file URIs, so spaces survive requirement
parsing. uv currently fails on editable paths containing `#` or `?`; validation
explains how to move the checkout or select a regular installation. Metadata
names and extras use packaging's
canonicalization, while checkout keys, file paths, and Python import names retain
their spelling. Reading metadata never executes a checkout's setup script.

Dependency installation validates selected Python project directories before uv
runs. Updating sources happens before final dependency generation, so metadata from
new or updated checkouts determines which release pins to remove. Both editable
and regular local installations override base and local pins and are excluded from
suggested release constraints. Source updates receive the install service's resolved
source options, including CLI overrides, rather than independently reloading a
different selection.

Installation selection describes intent, not observed virtualenv state. Listing
it must not install packages or mutate checkouts. A future environment doctor can
compare this shared plan with actual installed metadata without overloading listing
or creating another interpretation of source configuration.

## Public commands use resource and action families

The CLI uses `RESOURCE ACTION` for project configuration, dependencies, sources,
instances, supervisor, database operations, tests, and scheduled jobs. Direct
operations such as `shell` and `options` remain direct. Built-in aliases and legacy
mode flags are removed: every operation has one spelling. Bare families display
help and perform no operation, including in configured default-action lists.

`cli/commands.py` binds canonical leaves to existing service identities using
argparse parents, then removes the flat implementation spellings from the public
parser. Nested help is rebased to canonical paths. `ServiceInvocation`, snapshots,
`run_for` hooks, and service-specific configuration retain their identities.
Dependencies use explicit install, sync, outdated, and add actions; installation
options belong to the action. The shell's `fg` only reattaches jobs.

Source inspection uses `execute_command(capture_output=True)` to retrieve Git
metadata without echoing stdout or stderr. Capture is independent of quiet mode
and a service's streaming default; failures retain their diagnostics on the
exception. Listing presents configured and unmanaged checkouts in one table,
then renders suggestions as highlighted YAML in a panel. The same name filter
applies to rows and suggested entries.

Dependency reports consume uv's installation events, so they describe actual
operations, including same-version reinstalls. `DependencyReport` owns event
classification and presentation; installation owns process execution. stdout
from compilation and internal freeze probes is captured. stderr is collected
through an explicit callback, parsed after successful execution, and retained for
complete failure diagnostics. Routine timing/progress messages stay hidden in
normal mode; warnings and unrecognized diagnostics remain visible. Unknown event
formats with installer activity never produce a misleading no-changes message.
Verbose mode preserves raw uv output; internal freeze output stays silent in all
modes. The general command runner retains its normal output behavior.

## Record configuration provenance at the merge boundary

`TrackedOptions` is an internal mapping with definition history. YAML loading
attaches file identity; actual merges preserve replacement, append, and removal
operations without mutating earlier layers. Explicit files and CLI overrides add
their own layers. The public options dictionary remains an ordinary dictionary.
The final trace holds raw pre-interpolation definitions and resolved, normalized
values. Zope's derived storage defaults are attributed explicitly.

Reports consume that trace rather than replaying a different merge algorithm.
Per-key history is authoritative, including nested profiles and replacement of
mapping children. Jinja references explain derived configuration values. Sensitive
keys, credential URLs, conventional credential arguments, and derived secrets are
redacted before export. Configuration dependencies are distinct from Python imports
or the package resolver's dependency graph.

## Description reports are structured evidence, not terminal screenshots

`ProjectReport` builds lazy section data. Selecting configuration provenance does
not probe Git or the installed interpreter. All outputs share the section model.
HTML uses an escaped, self-contained responsive template, semantic tables, navigation,
search, expandable definition histories, and file links. JSON stdout uses soft wrapping
to preserve machine-readable strings. Focused exports do not overwrite `index.*`.

Description no longer compiles the project, enters installation services, exports
environment variables, or starts Supervisor. Runtime health reads existing
Supervisor configuration. Normal configuration loading can still resolve explicitly
configured remote profiles. Generated artifacts are owner-readable only.

## Scheduled jobs are trusted, isolated application work

`JobSet` validates declarations; `JobRunner` owns subprocesses, POSIX file locks,
timeouts, private logs, and SQLite history. Huey owns the persistent queue and
minute-based scheduling. A private daemon lock prevents duplicate schedulers.
Per-job timezones convert Huey's UTC timestamps before applying the cron matcher.
Supervisor owns daemon startup, restart, log rotation, and group termination.

Each Plone invocation renders unique runtime files and calls a standalone script
through the project's zconsole interpreter. The script sets the site, adopts an
explicit existing user, invokes the configured domain callable, commits on success,
and aborts on failure. It never calls a browser view or disables CSRF. Environment
values are passed to child processes rather than mutated from worker threads.
A browser view may share the domain callable while keeping its permission, POST,
and authenticator checks. Queue retries are opt-in because external side effects
cannot be rolled back or guaranteed exactly once.

## Make startup preparation an explicit dependency graph

`preparation.engine` uses doit for prerequisite scheduling, deduplication, and
failure propagation. Plonex owns task definitions and freshness receipts, allowing
read-only plans and execution to use the same checks. Doit's internal dependency
store is ephemeral; content-based receipts are the sole durable success state.

`DependencyTasks` tracks effective dependency configuration, fragment membership,
nested inputs, selected source metadata, cached remote constraints, and the observed
virtualenv. `SupervisorPreparation` adds declared helper templates, runtime templates
for managed Plonex programs, required directories, the cron program, and output
ownership. Opaque configured helpers remain explicit always-run tasks.

Successful receipts contain input/output fingerprints and completion timestamps.
A failure invalidates success before work starts and retains previous ownership in
a separate journal. Atomic writes preserve unchanged output timestamps. Project
locks coordinate automatic preparation with explicit installation. Runtime state
and loaded application versions are separate from generated-file freshness.

`supervisor start --plan` performs no preparation and does not clone uncached remote
profiles. Remote profiles now use stable project caches instead of new temporary
clones on every load; updating those checkouts is explicit. The first graph covers
Supervisor startup, with a report section for its current state. Other command
families can adopt the same graph when their preparation policies are defined.

## Project workers own queue dependencies

The install service injects Huey and an unpinned `plonex` runtime requirement into
the target virtualenv when jobs are configured. Projects can declare an editable
source explicitly. The preparation graph tracks the worker requirements.

The CLI delegates queue operations through the target interpreter using an isolated
Python invocation and a versioned JSON protocol. Configuration overrides travel
through stdin or the daemon's environment rather than command arguments. Supervisor
starts the target worker entry point directly. Configuration validation and basic
history/log inspection remain usable without Huey in the CLI environment.

`QueueRuntime` owns task registration, producers, and the consumer. Existing Huey
registry names are preserved for pending messages. Huey task IDs correlate retries
with separate execution attempts and logs. The run-history schema upgrades older
rows in place. Huey's statistics recorder captures producer and consumer events
without arguments. JSON monitoring and the static report share the runtime API;
a Plone control panel is a later consumer of that API.

Manual-only jobs disable periodic scheduling while retaining a Supervisor consumer.
Task revocation affects future execution; it does not terminate running jobs.
Application producers must account for ZODB commit boundaries, and applications
requiring durable publication need an outbox. `collective.taskqueue2` is deferred.
