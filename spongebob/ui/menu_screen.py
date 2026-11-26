from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Static

from spongebob.ui import theme


class MenuScreen(Screen[None]):
    """Keyboard-first main menu screen."""

    BINDINGS = [
        Binding("s", "open_simulate", "Simulate"),
        Binding("v", "open_visualize", "Visualize"),
        Binding("d", "open_diagnose", "Diagnose"),
        Binding("p", "open_settings", "Plugins/Settings"),
        Binding("n", "toggle_narrator", "Narrator On/Off"),
        Binding("q", "quit_app", "Quit"),
    ]

    CSS = f"""
    MenuScreen {{
        layout: vertical;
        background: {theme.BG};
        color: {theme.CREAM};
    }}
    #menu-center {{
        height: 1fr;
        align: center middle;
    }}
    #menu-box {{
        width: 56;
        height: auto;
        padding: 0 1;
        background: {theme.BG};
    }}
    #menu-banner {{
        background: {theme.BANNER_BLUE};
        color: {theme.CREAM};
        border: solid {theme.SIGNAL_GREEN};
        padding: 1 2;
        margin-bottom: 1;
        text-align: center;
    }}
    #menu-mode-box {{
        border: solid {theme.SIGNAL_GREEN};
        padding: 0 1;
        background: {theme.BG};
        height: auto;
    }}
    #menu-mode-label {{
        color: {theme.SIGNAL_GREEN};
        text-style: bold;
        margin-bottom: 1;
    }}
    #menu-mode-box Button {{
        width: 100%;
        margin-bottom: 0;
        content-align: left middle;
        padding: 0 1;
    }}
    #too-small {{
        width: 100%;
        height: 1fr;
        content-align: center middle;
        color: {theme.WARN_AMBER};
        text-style: bold;
        display: none;
    }}
    """

    def compose(self) -> ComposeResult:
        yield theme.make_top_title("MAIN MENU")
        yield theme.RedTopRule(classes="red-rule")
        yield Static("Enlarge terminal (minimum 50x16 required).", id="too-small")
        with Center(id="menu-center"):
            with Vertical(id="menu-box"):
                yield Static("", id="menu-banner")
                with Vertical(id="menu-mode-box"):
                    yield Static("SELECT MODE", id="menu-mode-label")
                    yield Button("[S]  Simulate   (Delay, Jitter, Loss)", id="btn-simulate", variant="primary")
                    yield Button("[V]  Visualize  (Live Pipe Replay)", id="btn-visualize")
                    yield Button("[D]  Diagnose   (Live Target Probe)", id="btn-diagnose")
                    yield Button("[P]  Plugins & Settings", id="btn-settings")
                    yield Button("[N]  Settings: Narrator ON", id="btn-narrator-toggle")
                    yield Button("[Q]  Quit", id="btn-quit", variant="error")
        yield Static(theme.format_status_line("SYSTEM READY", 1.0), id="menu-status", classes="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._render_banner()
        self._sync_narrator_label()
        self._check_size()

    def on_resize(self) -> None:
        self._check_size()

    def _check_size(self) -> None:
        too_small = self.query_one("#too-small", Static)
        center = self.query_one("#menu-center", Center)
        if self.size.width < 50 or self.size.height < 16:
            too_small.styles.display = "block"
            center.styles.display = "none"
        else:
            too_small.styles.display = "none"
            center.styles.display = "block"

    def _render_banner(self) -> None:
        banner = Text()
        word_style = theme.color_style(theme.CREAM_RGB, bg_rgb=theme.BANNER_BLUE_RGB)
        sub_style = theme.color_style(theme.TEAL_LIGHT_RGB, bg_rgb=theme.BANNER_BLUE_RGB)
        for line in theme.WORDMARK_LINES:
            banner.append(line + "\n", style=word_style)
        banner.append(theme.SUBTITLE + "\n", style=sub_style)
        banner.append(theme.render_signal_band_text(48, 3, seed=42))
        self.query_one("#menu-banner", Static).update(banner)

    def _sync_narrator_label(self) -> None:
        enabled = getattr(self.app, "narrator_enabled", True)
        state = "ON" if enabled else "OFF"
        self.query_one("#btn-narrator-toggle", Button).label = f"[N]  Settings: Narrator {state}"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-simulate":
            self.action_open_simulate()
        elif btn_id == "btn-visualize":
            self.action_open_visualize()
        elif btn_id == "btn-diagnose":
            self.action_open_diagnose()
        elif btn_id == "btn-settings":
            self.action_open_settings()
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

    def action_open_settings(self) -> None:
        self.app.open_settings()  # type: ignore[attr-defined]

    def action_quit_app(self) -> None:
        self.app.exit()
