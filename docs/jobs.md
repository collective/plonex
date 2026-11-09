# Scheduled jobs

Plonex uses a local Huey scheduler with a persistent SQLite queue. No Redis server
or system crontab is required. Jobs can be run manually, queued, or scheduled;
all execution paths share history, logs, timeouts, and file locks. The scheduler
runs under Supervisor. See the [Huey guide](https://huey.readthedocs.io/en/latest/guide.html#periodic-tasks)
for the underlying periodic-task model.

Huey belongs to the target project's virtualenv. The base plonex CLI does not
require it. When `cron_jobs` contains any jobs, dependency generation adds the
matching `plonex[jobs]` runtime, including `huey[stats]`. `dependencies install`,
`dependencies sync`, and Supervisor startup preparation install that runtime with
the project's interpreter and constraints. An editable CLI checkout supplies an
editable project runtime from the same source; packaged releases request the
matching plonex version.

`plonex cron daemon` replaces its launcher with the target interpreter running
`plonex.services.cron.runtime`. Supervisor uses that entry point directly. The
worker and each Plone job therefore use the target environment. The worker itself
does not need a permanent ZODB connection; each Plone callable still runs through
a fresh target-venv `zconsole` subprocess.

`cron run`, `cron enqueue`, and `cron daemon` prepare missing runtime dependencies.
Read-only inspection commands report a missing runtime without installing it.
Use `plonex dependencies install` to prepare explicitly. Constraints must permit
Huey 3.5 or newer, below 4; incompatible pins cause a normal resolver error.

## A Plone job without HTTP credentials

Move the work into a trusted Python function installed in the project virtualenv:

```python
# my.addon/jobs.py
import logging

logger = logging.getLogger(__name__)


def store_session_stats(context, days=1):
    # Perform the application's work here, using context and normal Plone APIs.
    # Do not commit here: the job runner owns the transaction.
    count = update_statistics(context, days=days)
    logger.info("Stored statistics for %s sessions", count)
    return {"sessions": count}
```

`update_statistics` represents your existing domain implementation. The runner
calls the configured function with the traversed context and keyword arguments.
The function must not require a browser request or an HTTP authenticator.

Declare the job:

```yaml
cron_timezone: Europe/Rome
cron_workers: 1
cron_jobs:
  StoreSessionStats:
    schedule: "15 2 * * *"
    callable: my.addon.jobs:store_session_stats
    site: /Plone
    context: sectors
    user: scheduler
    runtime: cron
    kwargs:
      days: 1
    timeout: 900
    lock: zope
    lock_timeout: 300
    enabled: false
```

Create the named `scheduler` user in Plone and give it the roles the work requires.
The job does not need that user's password. It opens a dedicated ZEO client through
`zconsole`, sets the Plone site hook, adopts the named user using `plone.api`, and
commits on success. Exceptions abort the transaction; the user and site context
are restored. ZODB connections are isolated in a fresh subprocess for each run.
The project must have Plone, its add-on, and `zconsole` installed, and ZEO must be
available. Normal Zope configuration, ZCML additions, blob paths, and environment
settings apply. `runtime: cron` selects `etc/plonex-cron.yml` overrides.

This is trusted server-side code running as the deployment OS account. Naming a
Plone user provides the application security context; it is not a sandbox for
untrusted Python code.

## Keep the browser view protected

The browser view can call the same domain function after checking its normal
permissions, HTTP method, and authenticator:

```python
from Products.Five.browser import BrowserView
from plone.protect import CheckAuthenticator, PostOnly
from my.addon.jobs import store_session_stats


class StoreSessionStats(BrowserView):
    # Register with an appropriate permission in ZCML.
    def __call__(self):
        PostOnly(self.request)
        CheckAuthenticator(self.request)
        return str(store_session_stats(self.context))
```

Test it from an authenticated browser form using POST and an authenticator token.
The scheduled job invokes the function, not the view. It does not disable CSRF,
store Basic Auth passwords, or manufacture authentication cookies. Plone accepts
an authenticator form field or `X-CSRF-TOKEN` header for browser requests; see
[Plone's CSRF documentation](https://6.docs.plone.org/classic-ui/csrf.html).

## Test, enable, and deploy

`enabled: false` disables the periodic schedule while allowing explicit manual
runs and enqueues. It does not cancel work already stored in the queue:

```sh
plonex cron list
plonex cron run StoreSessionStats
plonex cron logs StoreSessionStats
plonex cron history StoreSessionStats
```

After verifying the result, set `enabled: true` and run:

```sh
plonex cron configure
plonex supervisor start
```

If Supervisor is already running, use `plonex supervisor update` to apply the
new program. The worker program is rendered whenever Supervisor configuration is
prepared and jobs are configured. Manual-only jobs (`enabled: false`) still need a
consumer for explicitly queued work, so they keep the Supervisor worker. Removing
all job declarations removes `plonex-cron.conf`; apply that change with
`supervisor update`.
Job definition changes require restarting the daemon, for example with
`supervisor restart`. This restarts all managed programs, so plan it accordingly.

For foreground development:

```sh
plonex cron daemon --workers 1
```

To queue an immediate run for the daemon:

```sh
plonex cron enqueue StoreSessionStats
```

Enqueuing does not start a daemon. The persistent queue waits until a consumer is
running. Only one scheduler daemon may own a project's daemon lock. Workers run
job subprocesses; each job's timeout bounds its execution. Normal daemon shutdown
terminates active subprocess groups and records their outcomes.

## Queue monitoring and controls

```sh
plonex cron status
plonex cron queue
plonex cron inspect TASK_ID
plonex cron retry TASK_ID
plonex cron revoke TASK_ID
plonex cron restore TASK_ID
```

`status` shows consumer state, queue depths, and execution statistics. Consumer
state is checked through the daemon lock rather than assuming a recorded PID is
still alive. `queue` lists pending and scheduled work, including its task IDs,
due times, revocation flags, and whether the job definition still exists.

`inspect` joins queue metadata, Huey events, and execution attempts. Huey's task ID
is retained across automatic retries; each attempt has its own run ID, attempt
number, exit status, and private log. A manual retry creates a new task ID and uses
the current job definition. An automatic retry already waiting in the queue or
schedule must finish or be handled before a manual retry is accepted.

`revoke` prevents future execution of that task ID. It does not terminate a running
job or immediately remove the queue entry. `restore` removes that revocation.
Pausing a periodic job uses `enabled: false` and a daemon restart. Keep a job's
definition until its queued work has drained; removing it leaves unregistered tasks
that the consumer cannot execute.

All monitoring/control commands accept `--format json`; `status` and `queue` accept
`--limit` up to 1000. Full execution history is also available as JSON:

```sh
plonex cron status --format json
plonex cron queue --limit 100 --format json
plonex cron inspect TASK_ID --format json
plonex cron history --format json
plonex project describe queue
```

The same project-runtime API backs these commands, the report, and the optional
Plone control panel described below. No separate web service is needed.

## Plone queue control panel

Set `cron_control_panel: true` in the project YAML, install dependencies, and
restart the Plone instance. The option enables the queue view and supplies the
project path to the instance. It also requests `plonex[jobs]` even if no jobs have
been declared yet.

Users with the **Manage portal** permission can visit `/Plone/@@plonex-queue`
to inspect the worker, queue and recent attempts, and enqueue, retry, revoke, or
restore tasks. Changes use POST with Plone's authenticator check. Revocation
prevents future execution and does not terminate a running task. The page does not
install runtime dependencies; run `plonex dependencies install` explicitly if
the runtime is unavailable.

To add a link in Site Setup, apply the GenericSetup profile
`profile-plonex.services.cron:queue-control-panel` to each site. For example, run
a trusted Zope script with `plonex instance run -- SCRIPT.py`:

```python
import transaction
from zope.component.hooks import setSite

site = app["Plone"]
setSite(site)
site.portal_setup.runAllImportStepsFromProfile(
    "profile-plonex.services.cron:queue-control-panel"
)
transaction.commit()
```

Monitoring uses [Huey's statistics extension](https://huey.readthedocs.io/en/latest/contrib.html#task-statistics),
the recorder behind its Django and Flask dashboards. It is enabled in producers
and consumers. Arguments are not captured. Events are buffered briefly and retained
for 48 hours, up to 2000 events per queue, using Huey's defaults. In-flight records
are last-observed execution state: an abruptly killed worker can leave them until
retention cleanup. They are shown separately from whether a worker is actually
running. Job logs retain the program's original output and may contain values the
job prints.

## Producing work from application code

The target runtime exposes `QueueRuntime` for application producers:

```python
from pathlib import Path
from plonex.services.cron import CronService
from plonex.services.cron.runtime import QueueRuntime

with QueueRuntime(CronService(target=Path("/path/to/project"))) as queue:
    receipt = queue.enqueue("StoreSessionStats")
    task_id = receipt["task_id"]
```

Use one project queue per process and close short-lived producer instances so
buffered statistics are flushed. In a Plone request, publish only after a
successful ZODB commit, for example through a transaction after-commit hook that
checks its success argument. Publishing and the ZODB commit are separate operations;
applications needing durable publication should use a persistent outbox and
idempotent processing. Queue arguments should contain identifiers or paths rather
than persistent objects. The configured job controls callable and execution user.

## Other commands and execution controls

A job must choose exactly one of `callable` or an argv-list `command`:

```yaml
cron_jobs:
  maintenance:
    schedule: "*/15 * * * *"
    command:
      - /absolute/path/to/.venv/bin/python
      - -m
      - mypackage.maintenance
    environment:
      MODE: development
    timeout: 120
```

Commands run from the project root without a shell and with stdin closed. The
target virtualenv's `bin` directory leads `PATH`, and `VIRTUAL_ENV` identifies it.
Configured runtime environment values apply, with per-job `environment` values
taking precedence. Shell operators, redirects, pipes, and variable expansion are
not interpreted. Output goes to a private log.
Plone jobs default to the shared `plone` lock; command jobs default to a lock named
after the job. Set a common `lock` to serialize related jobs. A busy lock skips the
run after `lock_timeout` seconds; `0` means skip immediately. Locks release when
the owning process exits, including after crashes.

Schedules have five fields: minute, hour, day of month, month, weekday. Timezones
are IANA names; the default is UTC, independent of the machine's timezone. Huey's
cron matcher requires all specified fields to match, including day and weekday.
Schedules are checked once per minute. Missed schedules are not replayed after
an outage. Local DST transitions can skip or repeat wall-clock times.

`retries` defaults to zero. Optional `retries` and `retry_delay` configure queue
retries on failed runs; manual `cron run` executes once. Write idempotent jobs,
especially when they send mail or call external systems. ZODB rollback cannot
undo external side effects, and abrupt process termination is not an exactly-once
execution guarantee.

State is under the configured `var_folder`:

- `cron/queue.sqlite3`: persistent Huey queue.
- `cron/history.sqlite3`: task IDs, execution attempts, exit codes, timestamps, and log paths.
- `cron/stats.sqlite3`: Huey lifecycle events and in-flight statistics.
- `cron/daemon.json`: identity of the lock-owning worker while it runs.
- `cron/logs/`: per-run stdout/stderr logs.
- `cron/locks/`: process-safe lock files.
- `log/cron.log`: the Supervisor daemon log, with rotation.

Queue, history, payloads, and per-run logs are created with owner-only file
permissions. Temporary Plone payloads and runtime directories are removed after
the run. Logs retain the program's original output; avoid printing secrets in
job code. Reports show job declarations and recent log links without displaying
job output. Use `project describe jobs --browse` to inspect scheduling state.
Execution history and per-run logs have no automatic retention policy yet; include
them in your deployment's storage monitoring and archive policy.
