# Development workflow and next steps

Source declarations now express which checkouts belong in `.venv`:

```yaml
sources:
  my.package:
    repo: https://github.com/example/my.package.git
    install: true
    extras: [test]
```

Use `sources list` to inspect selection and checkout health, `sources clone`
to obtain missing code, and `dependencies install` to install it. Editable installation
avoids reinstalling after ordinary Python edits; dependency or extra changes still
require `dependencies install`. Restart the application when its imports or configuration
need refreshing. Use the existing shell's Ctrl-Z detachment, `instance upgrade`, and `fg`
attachment when the application needs to keep running during an upgrade.

## Current reporting and scheduling

`project describe` now compares declarations with installed metadata and explains
configuration provenance, Jinja references, profile locations, file freshness,
service/template wiring, runtime health, and job history. Its HTML report is
searchable and responsive; focused sections also export JSON and Markdown.

`cron` adds manual and scheduled jobs through a Supervisor-managed Huey consumer.
See the [job guide](jobs.md) and [development FAQ](appendix.md).

Supervisor startup now uses an incremental preparation graph. `supervisor start --plan` and `project describe preparation` explain required work; see the
[preparation guide](preparation.md). Extending the graph to other command families
should preserve their explicit mutation and restart policies.

`project doctor` checks the target virtualenv, selected source installation
locations and modes, direct requirements, generated constraints, preparation,
and local services. It suggests next steps without changing the project. See the
[doctor reference](cli.md#project-doctor) for the checks and their limits.

Selected sources can provide `test_command`; use `test sources` to run those
commands, including forwarded runner arguments. `dependencies preview` produces
temporary proposed inputs and invokes uv in dry-run mode. `instance debug --debugpy`
starts a loopback-only debugger, and `supervisor restart PROGRAM` targets a named
service. See the [CLI reference](cli.md).

## Further work

1. **Deeper dependency diagnosis.** Extend doctor checks to nested requirement files
   and resolver output. Requested extras are not recorded in Python distribution
   metadata, so report their direct dependencies and explain what remains unknown.
1. **Source-aware runtime impact.** Associate running instances with selected
   sources and propose precise restart targets after code or dependency changes.

These remaining proposals build on the shared source plan, configuration trace,
report sections, and job runner. Automatic reloads and database upgrades remain
explicit future choices, rather than side effects of inspection or scheduling.
