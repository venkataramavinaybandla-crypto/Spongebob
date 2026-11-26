from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, Label, Static

from spongebob.ui import theme


class SettingsScreen(Screen[None]):
    """Session settings and explicit data-only plugin folder loader."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
    ]

    CSS = f"""
    SettingsScreen {{
        layout: vertical;
        background: {theme.BG};
        color: {theme.CREAM};
    }}
    #settings-body {{
        height: 1fr;
        padding: 1;
    }}
    #plugin-box {{
        border: solid {theme.SIGNAL_GREEN};
        padding: 1;
        height: auto;
        margin-bottom: 1;
    }}
    .section-title {{
        text-style: bold;
        color: {theme.SIGNAL_GREEN};
        margin-bottom: 1;
    }}
    #plugin-row {{
        height: auto;
        margin-bottom: 1;
    }}
    #plugin-dir-input {{
        width: 1fr;
        margin-right: 1;
    }}
    #plugin-status {{
        color: {theme.CREAM};
    }}
    """

    def compose(self) -> ComposeResult:
        yield theme.make_top_title("SETTINGS & PLUGINS")
        yield theme.RedTopRule(classes="red-rule")
        yield Static("SETTINGS — EXPLICIT PLUGIN FOLDER (DATA-ONLY)", classes="screen-banner")
        with Vertical(id="settings-body"):
            with Vertical(id="plugin-box"):
                yield Static("PLUGIN FOLDER", classes="section-title")
                yield Label("Type a folder path containing plugin.toml (or subfolders):")
                with Horizontal(id="plugin-row"):
                    yield Input("", placeholder="e.g. ./my-plugins", id="plugin-dir-input")
                    yield Button("Load Plugins", id="btn-load-plugins", variant="primary")
                yield Static("No plugins loaded.", id="plugin-status")
        yield Static(theme.format_status_line("SETTINGS READY", 1.0), classes="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._render_registry()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-load-plugins":
            path = self.query_one("#plugin-dir-input", Input).value.strip()
            if not path:
                self.query_one("#plugin-status", Static).update("Enter a plugin folder path.")
                return
            self.app.load_plugins_folder(path)  # type: ignore[attr-defined]
            self._render_registry()

    def _render_registry(self) -> None:
        reg = getattr(self.app, "plugin_registry", None)
        status = self.query_one("#plugin-status", Static)
        if reg is None or (not reg.plugins and not reg.errors):
            status.update("No plugins loaded.")
            return
        lines: list[str] = []
        for p in reg.plugins:
            m = p.manifest
            if m.kind == "scenarios":
                cnt = f"{len(p.scenarios)} scenarios"
            elif m.kind == "jokes":
                cnt = f"{sum(len(v) for v in p.finding_jokes.values()) + sum(len(v) for v in p.drop_jokes.values())} jokes"
            else:
                cnt = f"{len(p.theme_colors)} colors"
            lines.append(f"Loaded {m.name} ({m.version}) [{m.kind}]: {cnt}")
        for pname, err in reg.errors:
            lines.append(f"Skipped {pname}: {err}")
        status.update("\n".join(lines))

    def action_go_back(self) -> None:
        self.app.pop_screen()
