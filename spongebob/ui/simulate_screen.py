from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, Label, Select, Static

from spongebob.analyzer import Finding, analyze
from spongebob.engine import Flow, Hop, default_path, simulate
from spongebob.export import ExportPayload, export_report
from spongebob.meter import Metrics, measure
from spongebob.narrator import MASCOT_NAME
from spongebob.scenarios import (
    Scenario,
    list_builtin_scenarios,
    load_builtin_scenario,
    load_scenario,
)
from spongebob.ui import theme
from spongebob.ui.export_modal import ExportOverwriteModal


class SimulateScreen(Screen[None]):
    """Configure flow and per-hop impairments, validate live, and inspect results."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("v", "open_visualize", "Visualize"),
    ]

    CSS = f"""
    SimulateScreen {{
        layout: vertical;
        background: {theme.BG};
        color: {theme.CREAM};
    }}
    #sim-layout {{
        height: 1fr;
    }}
    #config-pane {{
        width: 58%;
        padding: 0 1;
    }}
    #path-impairment-box {{
        border: solid {theme.SIGNAL_GREEN};
        background: {theme.BG};
        padding: 0 1;
        height: auto;
        margin-bottom: 1;
    }}
    #core-header-row {{
        height: 1;
        color: {theme.SIGNAL_GREEN};
        text-style: bold;
    }}
    .core-hop-row {{
        height: 1;
    }}
    .core-hop-name {{
        width: 10;
        height: 1;
        color: {theme.CREAM};
        text-style: bold;
    }}
    .core-col-hdr {{
        width: 1fr;
        height: 1;
        color: {theme.SIGNAL_GREEN};
        text-style: bold;
    }}
    .core-input {{
        width: 1fr;
        height: 1;
        border: none;
        padding: 0 1;
        background: {theme.BG};
        color: {theme.CREAM};
    }}
    .core-input:focus {{
        background: {theme.BANNER_BLUE};
        color: {theme.CREAM};
    }}
    #secondary-scroll {{
        height: 1fr;
        border: solid {theme.SIGNAL_GREEN};
        padding: 0 1;
    }}
    #results-pane {{
        width: 42%;
        padding: 0 1;
        border: solid {theme.SIGNAL_GREEN};
    }}
    .section-title {{
        text-style: bold;
        color: {theme.SIGNAL_GREEN};
        margin-top: 1;
        margin-bottom: 0;
    }}
    .hop-card {{
        border: solid {theme.TEAL_DARK};
        padding: 0 1;
        margin-bottom: 1;
        height: auto;
    }}
    .hop-header {{
        text-style: bold;
        color: {theme.TEAL_LIGHT};
    }}
    .row {{
        height: auto;
        margin-bottom: 0;
    }}
    .field {{
        width: 1fr;
        height: auto;
        margin-right: 1;
    }}
    .field-label {{
        color: {theme.SIGNAL_GREEN};
    }}
    #validation-error {{
        color: {theme.CRIT_RED};
        text-style: bold;
        min-height: 1;
    }}
    #actions-row {{
        height: auto;
        margin-top: 0;
    }}
    #actions-row Button {{
        margin-right: 1;
    }}
    #export-path, #scenario-path, #scenario-select {{
        width: 1fr;
        margin-right: 1;
    }}
    #metrics-output, #findings-output, #narrator-output {{
        margin-bottom: 1;
        color: {theme.CREAM};
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

    def __init__(self) -> None:
        super().__init__()
        self._has_results = False
        self._dirty = False
        self._initial_values: dict[str | None, str] = {}
        self._last_export_data: tuple[Scenario, list, Metrics, list[Finding], list] | None = None

    def compose(self) -> ComposeResult:
        yield theme.make_top_title("SIMULATE")
        yield theme.RedTopRule(classes="red-rule")
        yield Static("SIMULATE — CORE IMPAIRMENTS & FLOW", classes="screen-banner")
        yield Static("Enlarge terminal (minimum 50x16 required).", id="too-small")

        default_delays = {"client": "5", "router": "15", "isp": "25", "server": "5"}
        default_jitters = {"client": "1", "router": "5", "isp": "8", "server": "1"}
        default_losses = {"client": "0", "router": "1", "isp": "2", "server": "0"}
        hop_names = [h.name for h in default_path()]

        with Horizontal(id="sim-layout"):
            with Vertical(id="config-pane"):
                with Vertical(id="path-impairment-box"):
                    yield Static("PATH IMPAIRMENT", classes="box-title")
                    with Horizontal(id="core-header-row"):
                        yield Label("HOP", classes="core-hop-name")
                        yield Label("DELAY ms", classes="core-col-hdr")
                        yield Label("JITTER ms", classes="core-col-hdr")
                        yield Label("LOSS %", classes="core-col-hdr")
                    for hop_name in hop_names:
                        with Horizontal(classes="core-hop-row"):
                            yield Label(hop_name.upper(), classes="core-hop-name")
                            yield Input(
                                default_delays[hop_name],
                                id=f"hop-{hop_name}-delay",
                                classes="core-input",
                            )
                            yield Input(
                                default_jitters[hop_name],
                                id=f"hop-{hop_name}-jitter",
                                classes="core-input",
                            )
                            yield Input(
                                default_losses[hop_name],
                                id=f"hop-{hop_name}-loss",
                                classes="core-input",
                            )

                with VerticalScroll(id="secondary-scroll"):
                    yield Static("LOAD SCENARIO", classes="section-title")
                    scenario_options: list[tuple[str, str]] = [
                        (name, name) for name in list_builtin_scenarios()
                    ]
                    reg = getattr(self.app, "plugin_registry", None)
                    if reg is not None:
                        for pname in sorted(reg.scenarios):
                            scenario_options.append((pname, pname))
                    with Horizontal(classes="row"):
                        yield Select(
                            scenario_options,
                            prompt="Select built-in / plugin",
                            id="scenario-select",
                        )
                        yield Input("", placeholder="or type .toml path", id="scenario-path")
                        yield Button("Load", id="btn-load-scenario")

                    yield Static("FLOW SETTINGS", classes="section-title")
                    with Horizontal(classes="row"):
                        with Vertical(classes="field"):
                            yield Label("PACKETS", classes="field-label")
                            yield Input("100", id="flow-packets")
                        with Vertical(classes="field"):
                            yield Label("INTERVAL MS", classes="field-label")
                            yield Input("10.0", id="flow-interval")
                        with Vertical(classes="field"):
                            yield Label("SIZE BYTES", classes="field-label")
                            yield Input("64", id="flow-size")
                        with Vertical(classes="field"):
                            yield Label("SEED", classes="field-label")
                            yield Input("42", id="flow-seed")

                    yield Static("BANDWIDTH CAP & BURSTY LOSS", classes="section-title")
                    for hop_name in hop_names:
                        with Vertical(classes="hop-card"):
                            yield Static(f"HOP: {hop_name.upper()}", classes="hop-header")
                            with Horizontal(classes="row"):
                                with Vertical(classes="field"):
                                    yield Label("BW KBPS", classes="field-label")
                                    yield Input("", id=f"hop-{hop_name}-bw")
                                with Vertical(classes="field"):
                                    yield Label("QUEUE LIMIT", classes="field-label")
                                    yield Input("", id=f"hop-{hop_name}-qlim")
                                with Vertical(classes="field"):
                                    yield Label("LOSS MODEL", classes="field-label")
                                    yield Select(
                                        [("random", "random"), ("gilbert", "gilbert")],
                                        value="random",
                                        id=f"hop-{hop_name}-lmodel",
                                    )
                            with Horizontal(classes="row"):
                                with Vertical(classes="field"):
                                    yield Label("P_G2B (0-1)", classes="field-label")
                                    yield Input("0.0", id=f"hop-{hop_name}-pg2b")
                                with Vertical(classes="field"):
                                    yield Label("P_B2G (0-1)", classes="field-label")
                                    yield Input("0.0", id=f"hop-{hop_name}-pb2g")
                                with Vertical(classes="field"):
                                    yield Label("LOSS_BAD (%)", classes="field-label")
                                    yield Input("100.0", id=f"hop-{hop_name}-lbad")

                yield Static("", id="validation-error")
                with Horizontal(id="actions-row"):
                    yield Button("Run Simulation", id="btn-run", variant="primary")
                    yield Button("Visualize (V)", id="btn-open-visualize", disabled=True)

            with VerticalScroll(id="results-pane"):
                yield Static("METRICS", classes="section-title")
                yield Static("Run a simulation to view metrics.", id="metrics-output")
                yield Static("FINDINGS", classes="section-title")
                yield Static("No findings yet.", id="findings-output")
                yield Static(MASCOT_NAME.upper(), classes="section-title")
                yield Static("Narrator ready.", id="narrator-output")
                yield Static("EXPORT REPORT", classes="section-title")
                with Horizontal(classes="row"):
                    yield Input("", placeholder="report.json / .csv / .md", id="export-path")
                    yield Button("Export", id="btn-export", disabled=True)
                yield Static("", id="export-status")
        yield Static(theme.format_status_line("SIMULATE READY", 0.0), id="sim-status", classes="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._initial_values = {
            inp.id: inp.value for inp in self.query(Input)
        }
        self._check_size()

    def on_resize(self) -> None:
        self._check_size()

    def _check_size(self) -> None:
        too_small = self.query_one("#too-small", Static)
        layout = self.query_one("#sim-layout", Horizontal)
        if self.size.width < 50 or self.size.height < 16:
            too_small.styles.display = "block"
            layout.styles.display = "none"
        else:
            too_small.styles.display = "none"
            layout.styles.display = "block"

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

    def on_input_changed(self, event: Input.Changed) -> None:
        if not self._dirty and event.value == self._initial_values.get(event.input.id):
            return
        self._dirty = True
        self._validate_live()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "scenario-select" and event.value not in (None, Select.BLANK):
            self._load_named_scenario(str(event.value))
            return
        if self._initial_values:
            self._dirty = True
            self._validate_live()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-run":
            self._run_simulation()
        elif event.button.id == "btn-open-visualize":
            self.action_open_visualize()
        elif event.button.id == "btn-load-scenario":
            self._load_typed_scenario()
        elif event.button.id == "btn-export":
            self._handle_export()

    def _apply_scenario(self, scenario: Scenario) -> None:
        self.query_one("#flow-packets", Input).value = str(scenario.flow.packet_count)
        self.query_one("#flow-interval", Input).value = str(scenario.flow.interval_ms)
        self.query_one("#flow-size", Input).value = str(scenario.flow.size_bytes)
        self.query_one("#flow-seed", Input).value = (
            "" if scenario.seed is None else str(scenario.seed)
        )
        by_name = {h.name: h for h in scenario.hops}
        default_names = [h.name for h in default_path()]
        for idx, hop_name in enumerate(default_names):
            hop = by_name.get(hop_name)
            if hop is None and idx < len(scenario.hops):
                hop = scenario.hops[idx]
            if hop is None:
                continue
            self.query_one(f"#hop-{hop_name}-delay", Input).value = str(hop.delay_ms)
            self.query_one(f"#hop-{hop_name}-jitter", Input).value = str(hop.jitter_ms)
            self.query_one(f"#hop-{hop_name}-loss", Input).value = str(hop.loss_pct)
            self.query_one(f"#hop-{hop_name}-bw", Input).value = (
                "" if hop.bandwidth_kbps is None else str(hop.bandwidth_kbps)
            )
            self.query_one(f"#hop-{hop_name}-qlim", Input).value = (
                "" if hop.queue_limit_packets is None else str(hop.queue_limit_packets)
            )
            self.query_one(f"#hop-{hop_name}-lmodel", Select).value = hop.loss_model
            self.query_one(f"#hop-{hop_name}-pg2b", Input).value = str(hop.p_good_to_bad)
            self.query_one(f"#hop-{hop_name}-pb2g", Input).value = str(hop.p_bad_to_good)
            self.query_one(f"#hop-{hop_name}-lbad", Input).value = str(hop.loss_bad)
        self.query_one("#sim-status", Static).update(
            theme.format_status_line(f"LOADED {scenario.name.upper()}", 0.0)
        )

    def _load_named_scenario(self, name: str) -> None:
        reg = getattr(self.app, "plugin_registry", None)
        try:
            if reg is not None and name in reg.scenarios:
                sc = reg.scenarios[name]
            else:
                sc = load_builtin_scenario(name)
            self._apply_scenario(sc)
        except Exception as exc:
            self.query_one("#validation-error", Static).update(f"Scenario error: {exc}")

    def _load_typed_scenario(self) -> None:
        raw_path = self.query_one("#scenario-path", Input).value.strip()
        if not raw_path:
            self.query_one("#validation-error", Static).update("Enter a scenario .toml path.")
            return
        try:
            sc = load_scenario(raw_path)
            self._apply_scenario(sc)
            self.query_one("#validation-error", Static).update("")
        except Exception as exc:
            self.query_one("#validation-error", Static).update(f"Scenario error: {exc}")

    def _handle_export(self) -> None:
        if self._last_export_data is None:
            return
        raw_path = self.query_one("#export-path", Input).value.strip()
        status = self.query_one("#export-status", Static)
        if not raw_path:
            status.update("Enter an export path (.json, .csv, .md).")
            return
        sc, events, metrics, findings, narr_lines = self._last_export_data
        payload = ExportPayload(
            source="simulation",
            metrics=metrics,
            findings=findings,
            events=events,
            narrator_lines=tuple(narr_lines),
            scenario=sc,
            latency_kind="one_way",
            include_narrator=getattr(self.app, "narrator_enabled", True),
        )

        def _do_write(force: bool) -> None:
            try:
                out = export_report(payload, raw_path, force=force)
                status.update(f"Exported: {out}")
            except Exception as exc:
                status.update(f"Export failed: {exc}")

        if Path(raw_path).exists():
            self.app.push_screen(
                ExportOverwriteModal(raw_path),
                lambda ok: _do_write(True) if ok else status.update("Export cancelled."),
            )
        else:
            _do_write(False)

    def _run_simulation(self) -> None:
        parsed = self._validate_live()
        if parsed is None:
            return
        flow, path, seed = parsed
        status = self.query_one("#sim-status", Static)
        status.update(theme.format_status_line("RUNNING SIMULATION", 0.5))
        events = simulate(flow=flow, path=path, seed=seed)
        metrics = measure(events, packet_size_bytes=flow.size_bytes)
        findings = analyze(events, path)

        self.app.last_run = (path, events, metrics, findings)  # type: ignore[attr-defined]
        self.app.last_run_latency_kind = "one_way"  # type: ignore[attr-defined]
        self._has_results = True
        self.query_one("#btn-open-visualize", Button).disabled = False
        self.query_one("#btn-export", Button).disabled = False

        narr_lines = (
            self.app.narrator.narrate(findings, metrics, events, seed=seed)  # type: ignore[attr-defined]
            if getattr(self.app, "narrator_enabled", True)
            else []
        )
        sc_obj = Scenario(
            name="Interactive Simulation",
            description="Configured in Simulate screen.",
            flow=flow,
            hops=tuple(path),
            seed=seed,
        )
        self._last_export_data = (sc_obj, events, metrics, findings, narr_lines)

        self._render_metrics(metrics)
        self._render_findings(findings)
        self._render_narrator(findings, metrics, events, seed)
        status.update(theme.format_status_line("SIMULATION COMPLETE", 1.0))

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
        tp_text = (
            f"{metrics.throughput_kbps:.2f} kbps"
            if metrics.throughput_kbps is not None
            else "n/a"
        )
        text = (
            f"Sent: {metrics.sent}  Delivered: {metrics.delivered}  "
            f"Lost: {metrics.lost} ({metrics.loss_pct:.2f}%)\n"
            f"Latency: {lat_text}\n"
            f"Jitter (RFC3550): {jit_text}\n"
            f"Reordered: {metrics.reordered}  Throughput: {tp_text}\n"
            f"Loss by hop: {metrics.loss_by_hop or 'none'}"
        )
        self.query_one("#metrics-output", Static).update(text)

    def _render_findings(self, findings: list[Finding]) -> None:
        if not findings:
            self.query_one("#findings-output", Static).update(
                f"[{theme.SIGNAL_GREEN}]All clear: no findings.[/{theme.SIGNAL_GREEN}]"
            )
            return

        color_map = {"critical": theme.CRIT_RED, "warn": theme.WARN_AMBER, "info": theme.TEAL_LIGHT}
        lines = []
        for f in findings:
            color = color_map.get(f.severity, theme.CREAM)
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
            output.update(f"[{theme.DIM_TEXT}]Narrator is off.[/{theme.DIM_TEXT}]")
            return
        lines = self.app.narrator.narrate(findings, metrics, events, seed=seed)  # type: ignore[attr-defined]
        output.update("\n".join(f"• {line.text}" for line in lines))

    def action_open_visualize(self) -> None:
        if self._has_results:
            self.app.open_visualize()  # type: ignore[attr-defined]

    def action_go_back(self) -> None:
        self.app.pop_screen()
