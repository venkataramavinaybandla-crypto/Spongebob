from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Checkbox, Footer, Input, Label, Static
from textual.worker import Worker

from spongebob.analyzer import Finding, analyze
from spongebob.diagnose import Sample, probe_dns, probe_tcp, samples_to_events
from spongebob.diagnose.models import (
    validate_port,
    validate_probe_params,
    validate_target,
)
from spongebob.export import ExportPayload, export_report
from spongebob.meter import Metrics, measure
from spongebob.narrator import MASCOT_NAME
from spongebob.ui import theme
from spongebob.ui.export_modal import ExportOverwriteModal


class DiagnoseConfirmModal(ModalScreen[bool]):
    """Explicit consent dialog shown before any network probe is sent."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("y", "confirm", "Confirm"),
        Binding("n", "cancel", "Cancel"),
    ]

    CSS = f"""
    DiagnoseConfirmModal {{
        align: center middle;
        background: {theme.BG};
    }}
    #confirm-box {{
        width: 58;
        height: auto;
        border: solid {theme.SIGNAL_GREEN};
        padding: 1 2;
        background: {theme.BG};
    }}
    #confirm-title {{
        text-style: bold;
        background: {theme.BANNER_BLUE};
        color: {theme.CREAM};
        padding: 0 1;
        margin-bottom: 1;
    }}
    #confirm-body {{
        color: {theme.CREAM};
        margin-bottom: 1;
    }}
    #confirm-actions {{
        height: auto;
    }}
    #confirm-actions Button {{
        margin-right: 1;
    }}
    """

    def __init__(self, host: str, port: int, count: int) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._count = count

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="confirm-box"):
                yield Static("CONFIRM LIVE PROBE", id="confirm-title")
                yield Static(
                    f"This will contact {self._host}:{self._port} {self._count} times.\n"
                    "Nothing is saved to disk.",
                    id="confirm-body",
                )
                with Horizontal(id="confirm-actions"):
                    yield Button("Confirm [Y]", id="btn-confirm-yes", variant="primary")
                    yield Button("Cancel [N]", id="btn-confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-confirm-yes":
            self.dismiss(True)
        elif event.button.id == "btn-confirm-no":
            self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class DiagnoseScreen(Screen[None]):
    """Configure bounded live probes, confirm consent, and inspect RTT findings."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("v", "open_visualize", "Visualize"),
    ]

    CSS = f"""
    DiagnoseScreen {{
        layout: vertical;
        background: {theme.BG};
        color: {theme.CREAM};
    }}
    #diag-layout {{
        height: 1fr;
    }}
    #diag-config-pane {{
        width: 48%;
        padding: 0 1;
        border: solid {theme.SIGNAL_GREEN};
        margin-right: 1;
    }}
    #diag-config-scroll {{
        height: 1fr;
    }}
    #diag-results-pane {{
        width: 52%;
        padding: 0 1;
        border: solid {theme.SIGNAL_GREEN};
    }}
    .section-title {{
        text-style: bold;
        color: {theme.SIGNAL_GREEN};
        margin-top: 1;
        margin-bottom: 0;
    }}
    .row {{
        height: auto;
        margin-bottom: 1;
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
    #progress-output {{
        color: {theme.TEAL_LIGHT};
        min-height: 1;
    }}
    #actions-row {{
        height: auto;
        margin-top: 1;
        margin-bottom: 1;
    }}
    #actions-row Button {{
        margin-right: 1;
    }}
    #export-path {{
        width: 1fr;
        margin-right: 1;
    }}
    #metrics-output, #findings-output, #narrator-output {{
        margin-bottom: 1;
        color: {theme.CREAM};
    }}
    #errors-output {{
        color: {theme.WARN_AMBER};
        margin-bottom: 1;
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
        self._active_worker: Worker[Any] | None = None
        self._dirty = False
        self._initial_values: dict[str | None, str] = {}
        self._last_export_data: tuple[str, int, list, Metrics, list[Finding], list] | None = None

    def compose(self) -> ComposeResult:
        yield theme.make_top_title("DIAGNOSE")
        yield theme.RedTopRule(classes="red-rule")
        yield Static("DIAGNOSE — LIVE TARGET PROBE (RTT & TIMEOUTS)", classes="screen-banner")
        yield Static("Enlarge terminal (minimum 50x16 required).", id="too-small")
        with Horizontal(id="diag-layout"):
            with Vertical(id="diag-config-pane"):
                with VerticalScroll(id="diag-config-scroll"):
                    yield Static("TARGET PARAMETERS", classes="section-title")
                    with Horizontal(classes="row"):
                        with Vertical(classes="field"):
                            yield Label("HOST", classes="field-label")
                            yield Input("", placeholder="e.g. 127.0.0.1", id="diag-host")
                        with Vertical(classes="field"):
                            yield Label("PORT (1-65535)", classes="field-label")
                            yield Input("443", id="diag-port")
                    with Horizontal(classes="row"):
                        with Vertical(classes="field"):
                            yield Label("COUNT (1-200)", classes="field-label")
                            yield Input("20", id="diag-count")
                        with Vertical(classes="field"):
                            yield Label("INTERVAL MS (MIN 100)", classes="field-label")
                            yield Input("200", id="diag-interval")

                    yield Checkbox("Probe system DNS resolution first", value=False, id="diag-dns")
                yield Static("", id="validation-error")
                yield Static("Idle.", id="progress-output")
                with Horizontal(id="actions-row"):
                    yield Button("Start", id="btn-start", variant="primary")
                    yield Button("Visualize (V)", id="btn-open-visualize", disabled=True)

            with VerticalScroll(id="diag-results-pane"):
                yield Static("METRICS", classes="section-title")
                yield Static("Run a probe to view metrics.", id="metrics-output")
                yield Static("FINDINGS", classes="section-title")
                yield Static("No findings yet.", id="findings-output")
                yield Static(MASCOT_NAME.upper(), classes="section-title")
                yield Static("Narrator ready.", id="narrator-output")
                yield Static("COULD NOT PROBE", classes="section-title")
                yield Static("None.", id="errors-output")
                yield Static("EXPORT REPORT", classes="section-title")
                with Horizontal(classes="row"):
                    yield Input("", placeholder="diag.json / .csv / .md", id="export-path")
                    yield Button("Export", id="btn-export", disabled=True)
                yield Static("", id="export-status")
        yield Static(theme.format_status_line("DIAGNOSE READY", 0.0), id="diag-status", classes="status-bar")
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
        layout = self.query_one("#diag-layout", Horizontal)
        if self.size.width < 50 or self.size.height < 16:
            too_small.styles.display = "block"
            layout.styles.display = "none"
        else:
            too_small.styles.display = "none"
            layout.styles.display = "block"

    def _parse_config(self) -> tuple[str, int, int, float, bool]:
        host = validate_target(self.query_one("#diag-host", Input).value, "host")
        port_raw = self.query_one("#diag-port", Input).value.strip()
        count_raw = self.query_one("#diag-count", Input).value.strip()
        interval_raw = self.query_one("#diag-interval", Input).value.strip()

        port = validate_port(int(port_raw))
        count, interval_ms, _ = validate_probe_params(
            int(count_raw), float(interval_raw), 1000.0
        )
        include_dns = self.query_one("#diag-dns", Checkbox).value
        return host, port, count, interval_ms, include_dns

    def _validate_live(self) -> tuple[str, int, int, float, bool] | None:
        err_widget = self.query_one("#validation-error", Static)
        start_btn = self.query_one("#btn-start", Button)
        try:
            parsed = self._parse_config()
            err_widget.update("")
            start_btn.disabled = False
            return parsed
        except (ValueError, TypeError) as exc:
            err_widget.update(f"Invalid input: {exc}")
            start_btn.disabled = True
            return None

    def on_input_changed(self, event: Input.Changed) -> None:
        if not self._dirty and event.value == self._initial_values.get(event.input.id):
            return
        self._dirty = True
        self._validate_live()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-start":
            self._prompt_and_start()
        elif event.button.id == "btn-open-visualize":
            self.action_open_visualize()
        elif event.button.id == "btn-export":
            self._handle_export()

    def _handle_export(self) -> None:
        if self._last_export_data is None:
            return
        raw_path = self.query_one("#export-path", Input).value.strip()
        status = self.query_one("#export-status", Static)
        if not raw_path:
            status.update("Enter an export path (.json, .csv, .md).")
            return
        host, port, events, metrics, findings, narr_lines = self._last_export_data
        payload = ExportPayload(
            source="diagnose",
            metrics=metrics,
            findings=findings,
            events=events,
            narrator_lines=tuple(narr_lines),
            latency_kind="rtt",
            target_host=host,
            target_port=port,
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

    def _prompt_and_start(self) -> None:
        parsed = self._validate_live()
        if parsed is None:
            return
        host, port, count, interval_ms, include_dns = parsed

        def _on_confirm(confirmed: bool | None) -> None:
            if not confirmed:
                if self.is_mounted:
                    self.query_one("#progress-output", Static).update("Cancelled.")
                return
            self._start_worker(host, port, count, interval_ms, include_dns)

        self.app.push_screen(DiagnoseConfirmModal(host, port, count), _on_confirm)

    def _start_worker(
        self,
        host: str,
        port: int,
        count: int,
        interval_ms: float,
        include_dns: bool,
    ) -> None:
        self.query_one("#btn-start", Button).disabled = True
        self.query_one("#progress-output", Static).update(
            f"Probing {host}:{port} — sent: 0/{count}, ok: 0, timeouts: 0"
        )
        self.query_one("#diag-status", Static).update(
            theme.format_status_line(f"PROBING {host}:{port}", 0.25)
        )
        self._active_worker = self.run_worker(
            self._probe_worker(host, port, count, interval_ms, include_dns),
            exclusive=True,
        )

    async def _probe_worker(
        self,
        host: str,
        port: int,
        count: int,
        interval_ms: float,
        include_dns: bool,
    ) -> None:
        try:
            results: dict[str, list[Sample]] = {}
            if include_dns:
                results["dns"] = await probe_dns(
                    host, count=count, interval_ms=interval_ms, timeout_ms=1000.0
                )
            results[f"tcp:{host}:{port}"] = await probe_tcp(
                host, port=port, count=count, interval_ms=interval_ms, timeout_ms=1000.0
            )

            if not self.is_mounted:
                return

            all_samples = [s for seg in results.values() for s in seg]
            sent_n = len(all_samples)
            ok_n = sum(1 for s in all_samples if s.outcome == "ok")
            timeout_n = sum(1 for s in all_samples if s.outcome == "timeout")
            self.query_one("#progress-output", Static).update(
                f"Done — sent: {sent_n}, ok: {ok_n}, timeouts: {timeout_n}"
            )
            self.query_one("#diag-status", Static).update(
                theme.format_status_line("PROBE COMPLETE", 1.0)
            )

            adapted = samples_to_events(results)
            metrics = measure(adapted.events, packet_size_bytes=adapted.size_bytes)
            findings = analyze(adapted.events, adapted.path, latency_kind=adapted.latency_kind)

            self.app.last_run = (adapted.path, adapted.events, metrics, findings)  # type: ignore[attr-defined]
            self.app.last_run_latency_kind = "rtt"  # type: ignore[attr-defined]
            self._has_results = True
            self.query_one("#btn-open-visualize", Button).disabled = False
            self.query_one("#btn-export", Button).disabled = False

            narr_lines = (
                self.app.narrator.narrate(  # type: ignore[attr-defined]
                    findings, metrics, adapted.events, mode="diagnose"
                )
                if getattr(self.app, "narrator_enabled", True)
                else []
            )
            self._last_export_data = (
                host,
                port,
                adapted.events,
                metrics,
                findings,
                narr_lines,
            )

            self._render_metrics(metrics)
            self._render_findings(findings)
            self._render_narrator(findings, metrics, adapted.events)
            self._render_errors(adapted.errors or {})
        except asyncio.CancelledError:
            return
        finally:
            if self.is_mounted:
                self.query_one("#btn-start", Button).disabled = False

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
            f"Lost: {metrics.lost} ({metrics.loss_pct:.2f}% — timeouts approximate packet loss)\n"
            f"Round-trip time: {lat_text}\n"
            f"Jitter (RFC3550): {jit_text}\n"
            f"Throughput: n/a\n"
            f"Loss by segment: {metrics.loss_by_hop or 'none'}"
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
        self, findings: list[Finding], metrics: Metrics, events: list[Any]
    ) -> None:
        output = self.query_one("#narrator-output", Static)
        if not getattr(self.app, "narrator_enabled", True):
            output.update(f"[{theme.DIM_TEXT}]Narrator is off.[/{theme.DIM_TEXT}]")
            return
        lines = self.app.narrator.narrate(  # type: ignore[attr-defined]
            findings, metrics, events, mode="diagnose"
        )
        output.update("\n".join(f"• {line.text}" for line in lines))

    def _render_errors(self, errors: dict[str, list[Sample]]) -> None:
        output = self.query_one("#errors-output", Static)
        if not errors:
            output.update("None.")
            return
        parts = []
        for seg, err_samples in errors.items():
            outcomes = ", ".join(sorted({s.outcome for s in err_samples}))
            parts.append(f"{seg}: {len(err_samples)} ({outcomes})")
        output.update("\n".join(parts))

    def action_open_visualize(self) -> None:
        if self._has_results:
            self.app.open_visualize()  # type: ignore[attr-defined]

    def action_go_back(self) -> None:
        if self._active_worker is not None and not self._active_worker.is_finished:
            self._active_worker.cancel()
        self.app.pop_screen()
