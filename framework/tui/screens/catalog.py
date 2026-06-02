"""Catalog browser (Phase 1) — read-only view of every discovered fetcher.

Backed entirely by the App's cached `api.catalog(root)`. Left: a category ->
fetcher Tree with a live search filter. Right: the selected fetcher's contract
(version, description, secrets, config, target fields), rendered by tui.render.
"""

from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, Static, Tree

from framework.tui import render


class CatalogPage(Horizontal):
    """Two-pane fetcher catalog: tree on the left, contract detail on the right."""

    _filter: str = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="catalog-left"):
            yield Input(placeholder="search fetchers…", id="catalog-search")
            yield Tree("fetchers", id="catalog-tree")
        with VerticalScroll(id="catalog-detail-scroll"):
            yield Static(render.empty_detail(), id="catalog-detail")

    def on_mount(self) -> None:
        self.rebuild()

    # -- data ------------------------------------------------------------- #

    def rebuild(self) -> None:
        """Repopulate the tree from the App's cached catalog, applying the filter."""
        data = getattr(self.app, "catalog_data", None)
        tree = self.query_one("#catalog-tree", Tree)
        tree.clear()

        if not data:
            tree.root.label = "fetchers (none discovered)"
            return

        flt = self._filter.strip().lower()
        total = 0
        for cat in data["categories"]:
            matches = [f for f in cat["fetchers"] if _matches(f, flt)]
            if not matches:
                continue
            cat_node = tree.root.add(f"{cat['name']}  ({len(matches)})", expand=bool(flt))
            for fetcher in matches:
                cat_node.add_leaf(fetcher["name"], data=fetcher)
                total += 1

        tree.root.label = f"fetchers ({total})"
        tree.root.expand()

    # -- events ----------------------------------------------------------- #

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "catalog-search":
            self._filter = event.value
            self.rebuild()

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        self._show(event.node.data)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        self._show(event.node.data)

    # -- helpers ---------------------------------------------------------- #

    def _show(self, fetcher: Optional[dict]) -> None:
        detail = self.query_one("#catalog-detail", Static)
        detail.update(render.fetcher_detail(fetcher) if fetcher else render.empty_detail())

    def focus_search(self) -> None:
        self.query_one("#catalog-search", Input).focus()

    def focus_default(self) -> None:
        self.query_one("#catalog-tree").focus()


def _matches(fetcher: dict, flt: str) -> bool:
    if not flt:
        return True
    return flt in fetcher["name"].lower() or flt in (fetcher.get("description") or "").lower()
