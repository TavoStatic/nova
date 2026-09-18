# Knowledge

This directory is the optional home for local knowledge resources used by Nova.

The directory is part of the core installation contract even when no knowledge resources are installed. Keeping it present allows fresh-install diagnostics and local resource discovery to behave consistently.

Knowledge resources should be provider-neutral, reviewable, and scoped to the capabilities declared by their owning module. Runtime state, credentials, generated artifacts, and private source data do not belong here.
