"""Terminal UI for the fetcher framework.

A Textual front-end over framework.api — the SAME facade the CLI and web UI use.
It never re-implements discovery, validation, manifest editing, or execution; it
only renders the JSON-able values the facade returns. Launch via:

    python -m framework.tui            # full-screen terminal app

Phase 1 (implemented): a read-only catalog browser. See docs/tui_design.md for
the full design and the Phase 2-4 plan (manifest editor, run console, evidence
browser). The architecture is modeled on the Bagels TUI (design inspiration
only; no Bagels source is copied — Bagels is GPL-3.0).
"""

from framework.tui.app import FetcherApp

__all__ = ["FetcherApp"]
