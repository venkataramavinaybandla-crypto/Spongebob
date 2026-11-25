from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

from spongebob.analyzer import Finding, analyze
from spongebob.engine import Flow, Hop, default_path, simulate
from spongebob.meter import Metrics, measure
from spongebob.narrator import MASCOT_NAME


class SimulateScreen(Screen[None]):
    """Configure flow and per-hop impairments, validate live, and inspect results."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("v", "open_visualize", "Visualize"),
    ]

    CSS = """
    SimulateScreen {
        layout: vertical;
    }
    #sim-layout {
        height: 1fr;
    }
    #config-pane {
        width: 58%;
        padding: 1;
        border-right: solid #334155;
    }
    #config-scroll {
        height: 1fr;
    }
    #results-pane {
        width: 42%;
        padding: 1;
    }
    .section-title {
        text-style: bold;
        color: #38bdf8;
        margin-top: 1;
        margin-bottom: 1;
    }
    .hop-card {
        border: round #334155;
        padding: 0 1;
        margin-bottom: 1;
    }
    .hop-header {
        text-style: bold;
        color: #e2e8f0;
    }
    .row {
        height: auto;
        margin-bottom: 0;
    }
    .field {
        width: 1fr;
        margin-right: 1;
    }
    .field-label {
        color: #94a3b8;
    }
    #validation-error {
        color: #f87171;
        text-style: bold;
        min-height: 1;
        margin-top: 1;
    }
    #actions-row {
        height: auto;
        margin-top: 1;
    }
    #actions-row Button {
        margin-right: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._has_results = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="sim-layout"):
            with Vertical(id="config-pane"):
                with VerticalScroll(id="config-scroll"):
                    yield Static("Flow Settings", classes="section-title")
                    with Horizontal(classes="row"):
                        with Vertical(classes="field"):
                            yield Label("Packets", classes="field-label")
                            yield Input("100", id="flow-packets")
                        with Vertical(classes="field"):
                            yield Label("Interval (ms)", classes="field-label")
                            yield Input("10.0", id="flow-interval")
                        with Vertical(classes="field"):
                            yield Label("Size (bytes)", classes="field-label")
                            yield Input("64", id="flow-size")
                        with Vertical(classes="field"):
                            yield Label("Seed", classes="field-label")
                            yield Input("42", id="flow-seed")

                    yield Static("Core Hop Settings (Delay, Jitter, Loss)", classes="section-title")
                    default_delays = {"client": "5", "router": "15", "isp": "25", "server": "5"}
                    default_jitters = {"client": "1", "router": "5", "isp": "8", "server": "1"}
                    default_losses = {"client": "0", "router": "1", "isp": "2", "server": "0"}

                    for hop_name in [h.name for h in default_path()]:
                        with Vertical(classes="hop-card"):
                            yield Static(f"Hop: {hop_name}", classes="hop-header")
                            with Horizontal(classes="row"):
                                with Vertical(classes="field"):
                                    yield Label("Delay (ms)", classes="field-label")
                                    yield Input(default_delays[hop_name], id=f"hop-{hop_name}-delay")
                                with Vertical(classes="field"):
                                    yield Label("Jitter (ms)", classes="field-label")
                                    yield Input(default_jitters[hop_name], id=f"hop-{hop_name}-jitter")
                                with Vertical(classes="field"):
                                    yield Label("Loss (%)", classes="field-label")
                                    yield Input(default_losses[hop_name], id=f"hop-{hop_name}-loss")

                    yield Static("Secondary Settings (Bandwidth Cap & Bursty Loss)", classes="section-title")
                    for hop_name in [h.name for h in default_path()]:
                        with Vertical(classes="hop-card"):
                            yield Static(f"Advanced: {hop_name}", classes="hop-header")
                            with Horizontal(classes="row"):
                                with Vertical(classes="field"):
                                    yield Label("BW kbps (blank=off)", classes="field-label")
                                    yield Input("", id=f"hop-{hop_name}-bw")
                                with Vertical(classes="field"):
                                    yield Label("Queue limit", classes="field-label")
                                    yield Input("", id=f"hop-{hop_name}-qlim")
                                with Vertical(classes="field"):
                                    yield Label("Loss model", classes="field-label")
                                    yield Select(
                                        [("random", "random"), ("gilbert", "gilbert")],
                                        value="random",
                                        id=f"hop-{hop_name}-lmodel",
                                    )
                            with Horizontal(classes="row"):
                                with Vertical(classes="field"):
                                    yield Label("p_g2b (0-1)", classes="field-label")
                                    yield Input("0.0", id=f"hop-{hop_name}-pg2b")
                                with Vertical(classes="field"):
                                    yield Label("p_b2g (0-1)", classes="field-label")
                                    yield Input("0.0", id=f"hop-{hop_name}-pb2g")
                                with Vertical(classes="field"):
                                    yield Label("loss_bad (%)", classes="field-label")
                                    yield Input("100.0", id=f"hop-{hop_name}-lbad")

                yield Static("", id="validation-error")
                with Horizontal(id="actions-row"):
                    yield Button("Run Simulation", id="btn-run", variant="primary")
                    yield Button("Visualize (V)", id="btn-open-visualize", disabled=True)

            with VerticalScroll(id="results-pane"):
                yield Static("Metrics", classes="section-title")
                yield Static("Run a simulation to view metrics.", id="metrics-output")
                yield Static("Findings", classes="section-title")
                yield Static("No findings yet.", id="findings-output")
                yield Static(MASCOT_NAME, classes="section-title")
                yield Static("Narrator ready.", id="narrator-output")
        yield Footer()

    def _parse_config(self) -> tuple[Flow, list[Hop], int | None]:
        packets = int(self.query_one("#flow-packets", Input).value.strip())
        interval = float(self.query_one("#flow-interval", Input).value.strip())
        size_bytes = int(self.query_one("#flow-size", Input).value.strip())
        seed_raw = self.query_one("#flow-seed", Input).value.strip()
        seed = int(seed_raw) if seed_raw else None
        flow = Flow(packet_count=packets, interval_ms=interval, size_bytes=size_bytes)

        hops: list[Hop] = []
        for hop_name in [h.name for h in default_path()]:
            delay = float(self.query_one(f"#hop-{hop_name}-delay", Input).value.strip())
            jitter = float(self.query_one(f"#hop-{hop_name}-jitter", Input).value.strip())
            loss = float(self.query_one(f"#hop-{hop_name}-loss", Input).value.strip())

            bw_raw = self.query_one(f"#hop-{hop_name}-bw", Input).value.strip()
            bw = float(bw_raw) if bw_raw else None

            qlim_raw = self.query_one(f"#hop-{hop_name}-qlim", Input).value.strip()
            qlim = int(qlim_raw) if qlim_raw else None

            lmodel_val = self.query_one(f"#hop-{hop_name}-lmodel", Select).value
            lmodel = str(lmodel_val) if lmodel_val is not None else "random"

            pg2b = float(self.query_one(f"#hop-{hop_name}-pg2b", Input).value.strip())
            pb2g = float(self.query_one(f"#hop-{hop_name}-pb2g", Input).value.strip())
            lbad = float(self.query_one(f"#hop-{hop_name}-lbad", Input).value.strip())

            hops.append(
                Hop(
                    name=hop_name,
                    delay_ms=delay,
                    jitter_ms=jitter,
                    loss_pct=loss,
                    bandwidth_kbps=bw,
                    queue_limit_packets=qlim,
                    loss_model=lmodel,  # type: ignore[arg-type]
                    p_good_to_bad=pg2b,
                    p_bad_to_good=pb2g,
                    loss_bad=lbad,
                )
            )
        return flow, hops, seed

    def _validate_live(self) -> tuple[Flow, list[Hop], int | None] | None:
        err_widget = self.query_one("#validation-error", Static)
        run_btn = self.query_one("#btn-run", Button)
        try:
            parsed = self._parse_config()
            err_widget.update("")
            run_btn.disabled = False
            return parsed
        except (ValueError, TypeError) as exc:
            err_widget.update(f"Invalid input: {exc}")
            run_btn.disabled = True
            return None

    def on_input_changed(self, _: Input.Changed) -> None:
        self._validate_live()

    def on_select_changed(self, _: Select.Changed) -> None:
        self._validate_live()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-run":
            self._run_simulation()
        elif event.button.id == "btn-open-visualize":
            self.action_open_visualize()

    def _run_simulation(self) -> None:
        parsed = self._validate_live()
        if parsed is None:
            return
        flow, path, seed = parsed
        events = simulate(flow=flow, path=path, seed=seed)
        metrics = measure(events, packet_size_bytes=flow.size_bytes)
        findings = analyze(events, path)

        self.app.last_run = (path, events, metrics, findings)  # type: ignore[attr-defined]
        self._has_results = True
        self.query_one("#btn-open-visualize", Button).disabled = False

        self._render_metrics(metrics)
        self._render_findings(findings)
        self._render_narrator(findings, metrics, events, seed)

    def _render_metrics(self, metrics: Metrics) -> None:
        if metrics.latency_ms is not None:
            lat_text = (
                f"min={metrics.latency_ms.min:.2f}ms  "
                f"avg={metrics.latency_ms.avg:.2f}ms  "
                f"max={metrics.latency_ms.max:.2f}ms  "
                f"p95={metrics.latency_ms.p95:.2f}ms"
            )
        else:
            lat_text = "N/A"
        jit_text = f"{metrics.jitter_ms:.2f}ms" if metrics.jitter_ms is not None else "N/A"
        text = (
            f"Sent: {metrics.sent}  Delivered: {metrics.delivered}  "
            f"Lost: {metrics.lost} ({metrics.loss_pct:.2f}%)\n"
            f"Latency: {lat_text}\n"
            f"Jitter (RFC3550): {jit_text}\n"
            f"Reordered: {metrics.reordered}  "
            f"Throughput: {metrics.throughput_kbps:.2f} kbps\n"
            f"Loss by hop: {metrics.loss_by_hop or 'none'}"
        )
        self.query_one("#metrics-output", Static).update(text)

    def _render_findings(self, findings: list[Finding]) -> None:
        if not findings:
            self.query_one("#findings-output", Static).update("[green]All clear: no findings.[/green]")
            return

        color_map = {"critical": "red", "warn": "yellow", "info": "cyan"}
        lines = []
        for f in findings:
            color = color_map.get(f.severity, "white")
            hop_label = f.hop if f.hop is not None else "path"
            lines.append(
                f"[{color}][{f.severity.upper()}][/{color}] {f.code} "
                f"({hop_label}): {f.value:.2f} > {f.threshold:.2f}"
            )
        self.query_one("#findings-output", Static).update("\n".join(lines))

    def _render_narrator(
        self, findings: list[Finding], metrics: Metrics, events: list, seed: int | None
    ) -> None:
        output = self.query_one("#narrator-output", Static)
        if not getattr(self.app, "narrator_enabled", True):
            output.update("[dim]Narrator is off.[/dim]")
            return
        lines = self.app.narrator.narrate(findings, metrics, events, seed=seed)  # type: ignore[attr-defined]
        output.update("\n".join(f"• {line.text}" for line in lines))

    def action_open_visualize(self) -> None:
        if self._has_results:
            self.app.open_visualize()  # type: ignore[attr-defined]

    def action_go_back(self) -> None:
        self.app.pop_screen()
