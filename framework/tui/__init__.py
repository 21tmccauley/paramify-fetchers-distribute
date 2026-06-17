"""Terminal UI for the fetcher framework.

A Textual front-end over framework.api — the SAME facade the CLI uses.
It never re-implements discovery, validation, manifest editing, or execution; it
only renders the JSON-able values the facade returns. Launch via:

    python -m framework.tui            # full-screen terminal app

Implemented: a catalog browser, manifest editor, run console, and evidence
browser. The architecture is modeled on the Bagels TUI (design inspiration
only; no Bagels source is copied — Bagels is GPL-3.0).
"""

from framework.tui.app import FetcherApp

__all__ = ["FetcherApp"]
