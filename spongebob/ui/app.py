from __future__ import annotations

from textual.app import App

from spongebob.analyzer import Finding, LatencyKind, analyze
from spongebob.engine import Flow, Hop, default_path, simulate
from spongebob.engine.models import Event
from spongebob.meter import Metrics, measure
from spongebob.narrator import Narrator
from spongebob.ui import theme
from spongebob.ui.diagnose_screen import DiagnoseScreen
from spongebob.ui.menu_screen import MenuScreen
from spongebob.ui.simulate_screen import SimulateScreen
from spongebob.ui.visualize_screen import VisualizeScreen


class SimulatorApp(App[None]):
    """Terminal UI application for Spongebob (Network Impairment Simulator)."""

    TITLE = "Spongebob"
    SUB_TITLE = "Network Impairment Simulator (v0.2.1)"
    CSS = theme.BASE_THEME_CSS

    def __init__(self) -> None:
        super().__init__()
        self.narrator_enabled: bool = True
        self.narrator = Narrator()
        self.last_run: tuple[list[Hop], list[Event], Metrics, list[Finding]] | None = None
        self.last_run_latency_kind: LatencyKind = "one_way"

    def on_mount(self) -> None:
        self.push_screen(MenuScreen())

    def toggle_narrator(self) -> bool:
        self.narrator_enabled = not self.narrator_enabled
        return self.narrator_enabled

    def open_simulate(self) -> None:
        self.push_screen(SimulateScreen())

    def open_diagnose(self) -> None:
        self.push_screen(DiagnoseScreen())

    def open_visualize(self) -> None:
        if self.last_run is None:
            path = default_path(delay_ms=15.0, jitter_ms=5.0, loss_pct=2.0)
            flow = Flow(packet_count=40, interval_ms=15.0, size_bytes=64)
            events = simulate(flow, path=path, seed=42)
            metrics = measure(events, packet_size_bytes=flow.size_bytes)
            findings = analyze(events, path)
            self.last_run = (path, events, metrics, findings)
            self.last_run_latency_kind = "one_way"
        path, events, metrics, findings = self.last_run
        mode = "diagnose" if self.last_run_latency_kind == "rtt" else "simulate"
        narrator_lines = (
            self.narrator.narrate(findings, metrics, events, mode=mode)
            if self.narrator_enabled
            else []
        )
        self.push_screen(
            VisualizeScreen(
                path=path,
                events=events,
                findings=findings,
                narrator_lines=narrator_lines,
                narrator_enabled=self.narrator_enabled,
                latency_kind=self.last_run_latency_kind,
            )
        )
