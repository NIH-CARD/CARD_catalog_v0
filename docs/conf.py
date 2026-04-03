import os
import sys

# Make project modules importable for autodoc
sys.path.insert(0, os.path.abspath(".."))

# ---------------------------------------------------------------------------
# Project info
# ---------------------------------------------------------------------------
project = "CARD Catalog"
author = "DataTecnica / NIH CARD"
release = "1.0"

# ---------------------------------------------------------------------------
# Extensions
# ---------------------------------------------------------------------------
extensions = [
    "myst_parser",              # render .md files
    "sphinx.ext.autodoc",       # pull docstrings from Python modules
    "sphinx.ext.napoleon",      # Google/NumPy docstring style
    "sphinx.ext.viewcode",      # links to source code
    "sphinx.ext.intersphinx",   # cross-project links
]

# ---------------------------------------------------------------------------
# Source files
# ---------------------------------------------------------------------------
source_suffix = {
    ".rst": "restructuredtext",
    ".md":  "markdown",
}

myst_enable_extensions = [
    "colon_fence",      # ::: directive syntax in markdown
    "deflist",          # definition lists
    "tasklist",         # - [x] checkboxes
]

# ---------------------------------------------------------------------------
# HTML output
# ---------------------------------------------------------------------------
html_theme = "sphinx_rtd_theme"
html_theme_options = {
    "navigation_depth": 3,
    "titles_only": False,
}

# ---------------------------------------------------------------------------
# autodoc settings
# ---------------------------------------------------------------------------
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}
autodoc_typehints = "description"

# ---------------------------------------------------------------------------
# intersphinx
# ---------------------------------------------------------------------------
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pandas": ("https://pandas.pydata.org/docs", None),
}
