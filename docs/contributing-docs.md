# Writing and building the documentation

The handbook uses Markdown with MyST directives and Sphinx. Existing pages live
under `docs/`, and `index.md` defines the navigation. Add a page to a `toctree`
when creating it so readers can find it.

Install the documentation tools into the project's virtual environment and build:

```sh
python3 -m venv .venv  # omit if the environment already exists
.venv/bin/python -m pip install -r docs/requirements.txt
make docs
```

Open `docs/_build/html/index.html` in a browser. For a local server that rebuilds
after changes, run `make docs-live`. The generated `_build` directory is ignored
by Git.

## Diagrams and links

Use a MyST directive for Mermaid diagrams so Sphinx renders them:

````markdown
```{mermaid}
flowchart LR
    A[Edit configuration] --> B[Inspect options]
    B --> C[Run command]
```
````

Link to another page with a relative Markdown link such as
`[configuration](configuration.md)`. Use descriptive link text and test examples
against the current CLI. Keep command output illustrative unless it is guaranteed
by the implementation.

## Read the Docs

The repository's `.readthedocs.yaml` installs `docs/requirements.txt` and builds
`docs/conf.py`. Import the repository in Read the Docs and select the desired
versions in the project settings. Subsequent builds use the configuration from
the selected repository revision.
