from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from spongebob.ui import theme


class ExportOverwriteModal(ModalScreen[bool]):
    """Explicit confirmation dialog before overwriting an existing export file."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("y", "confirm", "Overwrite"),
        Binding("n", "cancel", "Cancel"),
    ]

    CSS = f"""
    ExportOverwriteModal {{
        align: center middle;
        background: {theme.BG};
    }}
    #overwrite-box {{
        width: 58;
        height: auto;
        border: solid {theme.SIGNAL_GREEN};
        padding: 1 2;
        background: {theme.BG};
    }}
    #overwrite-title {{
        text-style: bold;
        background: {theme.BANNER_BLUE};
        color: {theme.CREAM};
        padding: 0 1;
        margin-bottom: 1;
    }}
    #overwrite-body {{
        color: {theme.CREAM};
        margin-bottom: 1;
    }}
    #overwrite-actions {{
        height: auto;
    }}
    #overwrite-actions Button {{
        margin-right: 1;
    }}
    """

    def __init__(self, target_path: str) -> None:
        super().__init__()
        self._target_path = target_path

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="overwrite-box"):
                yield Static("OVERWRITE EXISTING FILE?", id="overwrite-title")
                yield Static(
                    f"File already exists:\n{self._target_path}\n\nOverwrite it?",
                    id="overwrite-body",
                )
                with Horizontal(id="overwrite-actions"):
                    yield Button("Overwrite [Y]", id="btn-overwrite-yes", variant="primary")
                    yield Button("Cancel [N]", id="btn-overwrite-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-overwrite-yes":
            self.dismiss(True)
        elif event.button.id == "btn-overwrite-no":
            self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class DiagnoseExportModal(ModalScreen[str | None]):
    """Modal dialog prefilled with the default Downloads export path."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS = f"""
    DiagnoseExportModal {{
        align: center middle;
        background: {theme.BG};
    }}
    #diag-export-box {{
        width: 72;
        height: auto;
        border: solid {theme.SIGNAL_GREEN};
        padding: 1 2;
        background: {theme.BG};
    }}
    #diag-export-title {{
        text-style: bold;
        background: {theme.BANNER_BLUE};
        color: {theme.CREAM};
        padding: 0 1;
        margin-bottom: 1;
    }}
    #diag-export-note {{
        color: {theme.CREAM};
        margin-bottom: 1;
    }}
    #diag-export-warning {{
        color: {theme.WARN_AMBER};
        margin-bottom: 1;
    }}
    #modal-export-path {{
        margin-bottom: 1;
    }}
    #diag-export-actions {{
        height: auto;
    }}
    #diag-export-actions Button {{
        margin-right: 1;
    }}
    """

    def __init__(self, initial_path: str, warning: str | None = None) -> None:
        super().__init__()
        self._initial_path = initial_path
        self._warning = warning

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="diag-export-box"):
                yield Static("EXPORT DIAGNOSE REPORT", id="diag-export-title")
                yield Static(
                    "Review or edit the export path (.md, .json, or .csv). Nothing is saved until you press Save.",
                    id="diag-export-note",
                )
                if self._warning:
                    yield Static(self._warning, id="diag-export-warning")
                yield Input(
                    self._initial_path,
                    placeholder="Enter full export path (.md / .json / .csv)",
                    id="modal-export-path",
                )
                with Horizontal(id="diag-export-actions"):
                    yield Button("Save", id="btn-export-save", variant="primary")
                    yield Button("Cancel", id="btn-export-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-export-save":
            chosen = self.query_one("#modal-export-path", Input).value.strip()
            self.dismiss(chosen or None)
        elif event.button.id == "btn-export-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
