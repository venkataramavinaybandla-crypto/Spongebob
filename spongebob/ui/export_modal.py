from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

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
