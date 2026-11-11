# Architecture and design

This section describes how Plonex resolves commands, configuration, and service
lifecycles. It is primarily for contributors and maintainers.

The [project decisions](decisions.md) document captures current ownership
boundaries and design constraints. It covers service lifecycles, command
registration and argument binding, shell jobs, service option inspection, and
snapshot behavior.

For the user-facing view of commands, see the [CLI guide](cli.md). For ongoing
implementation work, see [Development workflow](development.md).

## From command to running service

```{mermaid}
flowchart TD
    U[User or automation] --> CLI[CLI or interactive shell]
    CLI --> TARGET[Find project root]
    TARGET --> CONFIG[Merge profiles, project files and overrides]
    CONFIG --> SERVICE[Construct service]
    SERVICE --> PREP[Run required preparation and helper services]
    PREP --> RUN[Run target virtualenv executable]
    RUN --> RESULT[Output and exit status]
```

A command resolves its target project, merges configuration, constructs a
service and runs its lifecycle. Configuration and generated files let the same
commands work in local development and automation. The `options` command uses
service construction to preview values; see [interactive inspection](shell.md#inspecting-service-and-job-options)
for the limits of that preview.

| Component              | Responsibility                                  | Where to investigate                      |
| ---------------------- | ----------------------------------------------- | ----------------------------------------- |
| CLI                    | Parse commands, options and aliases             | [CLI guide](cli.md)                       |
| Configuration          | Merge profiles and project settings             | [Configuration](configuration.md)         |
| Services               | Prepare resources and run executables           | [Project decisions](decisions.md)         |
| Supervisor preparation | Reconcile dependency and generated inputs       | [Incremental preparation](preparation.md) |
| Shell jobs             | Manage terminal processes and startup snapshots | [Interactive shell](shell.md)             |
| Scheduled jobs         | Queue and run configured application work       | [Scheduled jobs](jobs.md)                 |
