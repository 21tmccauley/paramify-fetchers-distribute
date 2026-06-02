"""Modal dialogs for the manifest editor.

Each follows the Bagels write-path idiom (reimplemented, not copied): a
ModalScreen that collects input and returns a result via dismiss(), which the
caller's push_screen callback maps onto framework.api mutators.

  FormModal    -> dict of {group: {key: value}}   (edit entry / add target / platform)
  PickerModal  -> str (the chosen option id) or None
  ConfirmModal -> bool
  PreviewModal -> None (read-only YAML view)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from framework.tui.components.forms import FieldRow


class FormModal(ModalScreen[dict]):
    """Render grouped field specs; return {group: {key: typed value}} on save.

    Empty optional fields are omitted from the result (so we never write blanks);
    booleans are always included.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
    ]

    def __init__(self, title: str, groups: Dict[str, List[dict]], subtitle: str = "") -> None:
        super().__init__()
        self._title = title
        self._subtitle = subtitle
        self._groups = groups

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-card"):
            yield Label(self._title, id="modal-title")
            if self._subtitle:
                yield Label(self._subtitle, id="modal-subtitle")
            with VerticalScroll(id="modal-body"):
                any_fields = False
                for gname, fields in self._groups.items():
                    if not fields:
                        continue
                    any_fields = True
                    yield Label(gname, classes="group-label")
                    for spec in fields:
                        yield FieldRow(spec, group=gname)
                if not any_fields:
                    yield Static("Nothing to configure for this fetcher.", classes="dim")
            with Horizontal(id="modal-buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        first = self.query(FieldRow).first()
        if first is not None:
            first.query_one("#field-input").focus()

    @on(Button.Pressed, "#save")
    def action_save(self) -> None:
        result: Dict[str, dict] = {}
        for row in self.query(FieldRow):
            value = row.get_value()
            if value is None:
                continue
            result.setdefault(row.group, {})[row.spec["key"]] = value
        self.dismiss(result)

    @on(Button.Pressed, "#cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)


class PickerModal(ModalScreen[str]):
    """A filterable single-choice list. Returns the chosen option id, or None."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, options: List[Tuple[str, str]], subtitle: str = "") -> None:
        # options: list of (id, label)
        super().__init__()
        self._title = title
        self._subtitle = subtitle
        self._options = options

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-card"):
            yield Label(self._title, id="modal-title")
            if self._subtitle:
                yield Label(self._subtitle, id="modal-subtitle")
            yield Input(placeholder="filter…", id="picker-filter")
            yield OptionList(id="picker-list")

    def on_mount(self) -> None:
        self._populate("")
        self.query_one("#picker-filter", Input).focus()

    def _populate(self, flt: str) -> None:
        ol = self.query_one("#picker-list", OptionList)
        ol.clear_options()
        flt = flt.strip().lower()
        matches = [(oid, label) for oid, label in self._options if not flt or flt in label.lower()]
        if matches:
            ol.add_options([Option(label, id=oid) for oid, label in matches])
        else:
            ol.add_option(Option("no matches", disabled=True))

    @on(Input.Changed, "#picker-filter")
    def _filter(self, event: Input.Changed) -> None:
        self._populate(event.value)

    @on(OptionList.OptionSelected, "#picker-list")
    def _choose(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option_id)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmModal(ModalScreen[bool]):
    """A yes/no confirmation. Returns True on confirm, False otherwise."""

    BINDINGS = [
        Binding("escape", "no", "No"),
        Binding("n", "no", "No"),
        Binding("y", "yes", "Yes"),
    ]

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-card", classes="confirm"):
            yield Label(self._message, id="modal-title")
            with Horizontal(id="modal-buttons"):
                yield Button("Yes", variant="error", id="yes")
                yield Button("No", variant="primary", id="no")

    @on(Button.Pressed, "#yes")
    def action_yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no")
    def action_no(self) -> None:
        self.dismiss(False)


class PreviewModal(ModalScreen[None]):
    """Read-only scrollable view of the manifest YAML."""

    BINDINGS = [Binding("escape,q,p", "close", "Close")]

    def __init__(self, text: str, title: str = "manifest preview") -> None:
        super().__init__()
        self._text = text
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-card", classes="wide"):
            yield Label(self._title, id="modal-title")
            with VerticalScroll(id="modal-body"):
                yield Static(self._text, id="preview-text")

    def action_close(self) -> None:
        self.dismiss(None)
