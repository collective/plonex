from __future__ import annotations

project = "Plonex"
author = "Plonex contributors"
copyright = "2026, Plonex contributors"

extensions = ["myst_parser", "sphinxcontrib.mermaid"]
source_suffix = {
    ".md": "markdown",
    ".rst": "restructuredtext",
}
root_doc = "index"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_static_path: list = []
myst_heading_anchors = 3

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "linkify",
    "strikethrough",
    "tasklist",
]
