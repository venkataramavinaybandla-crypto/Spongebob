from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static


class MenuScreen(Screen[None]):
    """Keyboard-first main menu screen."""

    BINDINGS = [
        Binding("s", "open_simulate", "Simulate"),
        Binding("v", "open_visualize", "Visualize"),
        Binding("d", "open_diagnose", "Diagnose"),
        Binding("n", "toggle_narrator", "Narrator On/Off"),
        Binding("q", "quit_app", "Quit"),
    ]

    CSS = """
    MenuScreen {
        align: center middle;
    }
    #menu-box {
        width: 48;
        height: auto;
        border: round #38bdf8;
        padding: 1 2;
        background: #0f172a;
    }
    #menu-title {
        text-align: center;
        text-style: bold;
        color: #38bdf8;
        margin-bottom: 1;
    }
    #menu-subtitle {
        text-align: center;
        color: #94a3b8;
        margin-bottom: 1;
    }
    Button {
        width: 100%;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Center():
            with Vertical(id="menu-box"):
                yield Static("Spongebob", id="menu-title")
                yield Static("Network Impairment Simulator — v0.2.0", id="menu-subtitle")
                yield Button("Simulate", id="btn-simulate", variant="primary")
                yield Button("Visualize", id="btn-visualize", variant="default")
                yield Button("Diagnose", id="btn-diagnose", variant="default")
                yield Button("Settings: Narrator ON", id="btn-narrator-toggle", variant="default")
                yield Button("Quit", id="btn-quit", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        self._sync_narrator_label()

    def _sync_narrator_label(self) -> None:
        enabled = getattr(self.app, "narrator_enabled", True)
        state = "ON" if enabled else "OFF"
        self.query_one("#btn-narrator-toggle", Button).label = f"Settings: Narrator {state}"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-simulate":
            self.action_open_simulate()
        elif btn_id == "btn-visualize":
            self.action_open_visualize()
        elif btn_id == "btn-diagnose":
            self.action_open_diagnose()
        elif btn_id == "btn-narrator-toggle":
            self.action_toggle_narrator()
        elif btn_id == "btn-quit":
            self.action_quit_app()

    def action_toggle_narrator(self) -> None:
        self.app.toggle_narrator()  # type: ignore[attr-defined]
        self._sync_narrator_label()

    def action_open_simulate(self) -> None:
        self.app.open_simulate()  # type: ignore[attr-defined]

    def action_open_visualize(self) -> None:
        self.app.open_visualize()  # type: ignore[attr-defined]

    def action_open_diagnose(self) -> None:
        self.app.open_diagnose()  # type: ignore[attr-defined]

    def action_quit_app(self) -> None:
        self.app.exit()
