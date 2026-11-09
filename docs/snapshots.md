# Project snapshots

A snapshot records the observed target Python/platform, installed distribution
versions and direct sources, configured checkout commits and dirty state, and
hashes of project/profile configuration, dependency fragments, and the cached
base constraints. It does not contain configuration values or URL credentials.

```sh
plonex project snapshot create --output deployment.json
plonex project snapshot compare deployment.json
plonex project snapshot compare deployment.json --format json
plonex project snapshot prepare deployment.json --to /path/to/new-venv
```

Create writes a new private file and refuses to overwrite one. Without `--output`
it prints JSON. Compare is read-only and exits 1 when the recorded evidence differs.
Source entries record uncommitted/untracked state, but not the contents of those
changes. Snapshot `issues` identify dirty or uninspectable checkouts and other
inputs that prevent preparation.

Prepare verifies the captured project and profile input hashes, constraint cache,
source revisions and cleanliness, Python version, operating system, and machine
architecture before creating a **new** virtualenv. It refuses an existing path,
installs the recorded versions using uv, and checks the resulting installed
versions. Sources installed from a clean configured checkout inside the project
are supported; other direct sources are reported as unsupported. Use `--python`
to select a matching interpreter. A failed preparation leaves its new directory
for inspection. It does not start services or replace the project's environment.

The snapshot records package versions and source locations, not distribution
artifact hashes or build dependencies. Different index contents or build
conditions can therefore produce different bytes at the same version. Treat
this as a version-level reconstruction, not a cryptographic lockfile. Nested
requirement or constraint includes in fragments and base constraints are flagged as uncaptured;
preparation refuses such snapshots until the inputs have been made explicit.
Git-ignored files are not captured by a clean-checkout test; keep build inputs in
version control or otherwise control them during reconstruction.
No repository checkout or remote constraint download is performed by capture or
compare. Prepare may download packages through uv.
