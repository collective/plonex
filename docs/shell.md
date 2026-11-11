# Interactive shell and command options

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

## Keeping a foreground instance running

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

## Inspecting service and job options

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
