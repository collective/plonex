# Migrating from Buildout or mxdev

This guide helps you move an existing Plone project to Plonex. It covers projects
using `buildout.cfg`, `mx.ini`, or both. Plonex can inventory their local
configuration, but it does not convert Buildout recipes, resolve Buildout
interpolation, or run mxdev for you. Review the project's behavior and test the
result on a copy before changing a running deployment.

## 1. Inventory the existing project

From an environment with Plonex installed, inspect the existing project even if
it does not yet have `etc/plonex.yml`:

```sh
plonex --target /path/to/old-project project inspect-legacy
plonex --target /path/to/old-project project inspect-legacy --format json
```

The inspector reads `buildout.cfg` and `mx.ini` in that directory. It reports
common settings, source declarations, and recipe names. It does not follow
Buildout `extends`, execute recipes, resolve interpolation, inspect included
files, or change the project. Review the included files and generated
configuration yourself, especially custom recipes and scripts.

Record the working Python and Plone versions, requirements and effective pins,
source revisions and local changes, enabled add-ons and ZCML, environment
variables, ports, database and blob locations, scheduled jobs, and process
manager configuration. Save the current deployment and recovery procedure so you
can return to it if needed.

## 2. Create a staging project

Use a separate directory and a compatible Python environment for the migration:

```sh
plonex project init /path/to/plonex-staging
cd /path/to/plonex-staging
```

`init` writes a starter `etc/plonex.yml`, creates a virtualenv, and installs its
starter dependencies. It uses a Plone 6.2 default: this is not a detection of
your existing project's version. It may initialize and commit a Git repository
in a directory that does not already contain one. Inspect and adjust the
starter configuration, constraints, and dependencies before using it for your
application. Do not assume an older Plone application is compatible with that
default or with the selected Python version.

Keep staging's database, blob storage, ports, and process manager separate from
production. In particular, do not start a second ZEO server against a live
FileStorage. If staging must connect to an existing ZEO server, agree on access
and shared blob-storage semantics first; use a copy for upgrade experiments.

## 3. Move requirements and source checkouts

Choose **one owner per checkout**. Either continue using mxdev to generate the
inputs and manage its sources, or declare those sources in Plonex. Mixing both
owners for the same checkout can produce conflicting installs.

### Keep mxdev temporarily

Run mxdev using your existing project procedure. Set Plonex to consume its
actual generated files; the following names are examples, not mxdev defaults:

```yaml
# etc/plonex.yml
plonex_base_constraint: constraints-mxdev.txt
pip_requirements:
  - "-r requirements-mxdev.txt"
```

Keep the starter requirements your project needs as well. Set paths relative to
the Plonex project or use appropriate absolute paths, and ensure files referenced
from those generated inputs are accessible. Inspect the generated files for
editable paths and nested includes before installing. Run mxdev again when its
inputs change; Plonex does not generate these files or update mxdev's checkouts.
Remove duplicate Plonex source selections for those same packages. See
[dependency and constraint configuration](configuration.md#base-constraints).

### Move source ownership to Plonex

Translate each selected repository, revision, extras, and install mode after
reviewing its original declaration. For example, a Buildout `[sources]` Git
entry or an mxdev section with a Git URL and branch might become:

```yaml
# etc/plonex.yml
sources:
  my.addon:
    repo: https://github.com/example/my.addon.git
    rev: main  # Replace with the branch, tag, or commit you actually use.
    install: true
    extras: [test]
```

`install: true` selects the checkout for installation; selected sources are
editable by default. Use `editable: false` for a regular installation, and
`path` or `subdirectory` where the checkout layout requires them. Entries
without `install: true` are checkout-only. Plonex manages these checkouts through
Gitman, so review non-Git sources and custom checkout behavior separately.

Remove the corresponding old editable requirements and stop mxdev from
selecting the same packages. Move normal distribution requirements to
`pip_requirements` or `etc/requirements.d/`, and version pins to
`etc/constraints.d/` or a suitable base constraints file. Buildout version
sections, constraints, and Python package metadata are not identical; check the
resulting resolver inputs rather than copying syntax mechanically.

```sh
plonex sources clone
plonex sources list
plonex dependencies install
plonex project describe sources
plonex project describe dependencies
```

The clone and install commands change the staging project and can access
repositories or package indexes. `dependencies install` does not remove unrelated
installed distributions; `dependencies sync` does, so use sync only after
reviewing the complete intended requirements.

## 4. Translate runtime and operations

| Existing concern                             | Where to review it in Plonex                                                    |
| -------------------------------------------- | ------------------------------------------------------------------------------- |
| ZEO server and connection                    | `plonex db start`, `zeo_address`, and the configured blob storage               |
| Zope/Plone instances                         | `plonex instance start`, `http_address`, `http_port`, and runtime configuration |
| Package requirements and versions            | `pip_requirements`, requirement and constraint fragments, and base constraints  |
| `mr.developer` or mxdev Git sources          | `sources` with an explicit `repo`, `rev`, and installation selection            |
| Supervisor parts                             | `services` templates and `plonex supervisor` commands                           |
| Cron jobs                                    | `cron_jobs` and `plonex cron` commands                                          |
| ZCML and custom Zope configuration           | `zcml_additional`, `zope_conf_additional`, or custom templates                  |
| Backup recipes                               | The existing recovery procedure and [Plonex backup and recovery](recovery.md)   |
| Other recipes, scripts, and deployment hooks | Review and migrate their behavior manually                                      |

These are areas to compare, not one-to-one recipe conversions. Check effective
configuration before starting processes:

```sh
plonex project describe configuration
plonex project describe configuration --key zeo_address db start
plonex project doctor
plonex supervisor start --plan
```

The `--plan` command previews preparation without starting Supervisor. The
[configuration guide](configuration.md) explains profiles, environment variables,
and generated templates; [scheduled jobs](jobs.md) describes the job runtime.
Review each scheduled task before enabling it in the new environment, so it does
not run twice during migration.

## 5. Test data and cut over

1. Make and verify a backup using the **existing** deployment's procedure. Include
   the matching blob storage and any additional databases or external data.
1. Restore a consistent copy into isolated staging storage and confirm its paths,
   ownership, and permissions. Coordinate all writers when taking the copy. A
   `Data.fs` file alone does not contain blob data.
1. Start the staging services with `plonex supervisor start`; inspect
   `plonex supervisor status` and the application logs. Test add-ons, login,
   ZCML, URLs, background jobs, integrations, and representative content.
1. If the application requires upgrades, test them against the staging copy and
   check the results. Plonex's `db upgrade` uses `collective.ftw.upgrade`; install
   and enable it first. A successful environment install does not run application
   upgrade steps automatically.
1. Plan the final cutover with a maintenance window: stop or otherwise coordinate
   all writers, take a fresh consistent backup, rehearse recovery, move the final
   data and blobs according to your storage setup, and start the intended services.
   Keep the old configuration and verified backup until the new deployment is
   accepted. Do not let old and new deployments write independently to divergent
   copies of the database.

[Plonex backup and recovery](recovery.md) documents its own offline snapshot
format and limitations. Existing repozo backups are not automatically converted
into that format; restore them with the original procedure and separately managed
blob backups. After cutover, establish and test the new backup schedule.
