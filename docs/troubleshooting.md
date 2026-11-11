# Troubleshooting

## Plonex cannot find the project configuration

Commands look for `etc/plonex.yml` by walking up from the current directory.
Run the command inside an initialized project or use `--target`:

```sh
plonex --target /path/to/project supervisor status
```

## A command uses unexpected configuration

Use `plonex options COMMAND ...` to inspect the resolved service options. Check
whether a service-specific file, local override, profile, or command line value
has higher precedence than the value you expected. The [configuration guide](configuration.md)
explains the layers.

## Runtime binaries are missing

Install or update the project environment's dependencies:

```sh
plonex dependencies install
```

## ZEO connection or database problems

Check the configured `zeo_address` and confirm that the ZEO service is running.
For safe data recovery steps, follow [Database backup and recovery](recovery.md).
