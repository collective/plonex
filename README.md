# Hello world

This is me!

## Autocomplete

Add something like this to your startup script:

```sh
eval "$(register-python-argcomplete plonex)"
```

## Initialize your project

You can initialize a new project with the `init` command:

```sh
$ plonex init foo
INFO     Creating foo/tmp
INFO     Creating foo/etc
INFO     Creating foo/var
INFO     Creating foo/var/blobstorage
INFO     Creating foo/var/cache
INFO     Creating foo/var/filestorage
INFO     Creating foo/var/log
INFO     Creating foo/etc/plonex.yml
INFO     Project initialized
```

## Install your packages

```sh
plonex dependencies
```

## Start your project

After initializing your project, you can find an `etc/supervisor` directory with a couple of example files:

```sh
$ ls etc/supervisor
zeoclient.conf.example
zeoserver.conf.example
```

You can use them to decide which services are managed by supervisor.

For example to start the `zeoserver` service when supervisor starts, you can just copy the example file:

```sh
cp etc/supervisor/zeoserver.conf.example etc/supervisor/zeoserver.conf
```

If you want you can modify the file to suit your needs.

All the files with the extension `.conf` in the `etc/supervisor` directory will be loaded by supervisor.

Once you are ready, you can start supervisor with:

```sh
plonex supervisor start
```

## Add an admin user

You can add an admin user with the `adduser` command, e.g.:

```sh
$ plonex adduser admin $ADMIN_PASSWORD
[ale@flo bar]$ plonex adduser admin admin
User admin created.
```

## Add a package

If you want to add a package to your project, you can use the `install` command:

```sh
$ plonex install collective.pdbpp
...
```

## Custom PyPI repository

If you want to use a custom PyPI repository, you can add in you `pyproject.toml` file the following snippet:

```toml
[tool.uv]
# Add command line parameters to the `pip` command, e.g.:
# index-strategy = "unsafe-best-match"

[[tool.uv.index]]
# You need to have this env variables set if you need to be authenticated:
# export UV_INDEX_PRIVATE_USERNAME=username
# export UV_INDEX_PRIVATE_PASSWORD=password
name = "private"
url = "https://pypi.acme.org/simple"


[[tool.uv.index]]
name = "pypi"
url = "https://pypi.org/simple"
```

```
--extra-index-url=https://pypi.acme.org/simple
```

## Setting options/variables

You can set options in multiple ways.

1. In the command line (max priority)
2. In config files
3. In some `etc/plonex.*.yml` file (if any of them exists, precedence is given by alphabetical order)
4. In the `etc/plonex.yml` file
5. In the class definition options_default (lowest priority)

### Log level

You can set the log level by setting the `log_level` variable, e.g.:

```yaml
log_level: INFO
```

Valid values are: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.

This value is ignored if you pass the `-v/--verbose` or the `-q/--quiet` option in the command line.

## Zope instance configuration

You can customize the Zope instance configuration by setting some options.

### Zope instance port

You can set the Zope default zope instance port by setting the `http_port` variable.

```yaml
http_port: 8080
```

### Zope instances environment variables

You can set environment variables for the Zope instances by setting the `environment_vars` variable.

Note in this example how you can reuse existing variables

```yaml
environment_vars:
  PTS_LANGUAGES: it
  TZ: Europe/Rome
  zope_i18n_allowed_languages: '{{ environment_vars["PTS_LANGUAGES"] }}'
  zope_i18n_compile_mo_files: true
```

### Zope instance additional zcml

If you want to load additional zcml files, you can set the `zcml_additional` variable.

```yaml
zcml_additional:
  - etc/extra.zcml
  - etc/extra-overrides.zcml
```

If the file ends in `-overrides.zcml`, it will be loaded after the default zcml files and override the existing configuration.

Your extra zcml files will be threated as jinja2 templates, so you can use any variable known to the instance to render them.
