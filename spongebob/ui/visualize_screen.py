from __future__ import annotations

from typing import Sequence

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Footer, Static

from spongebob.analyzer import Finding, LatencyKind
from spongebob.bus import EventBus
from spongebob.engine.models import Event, Hop
from spongebob.narrator import MASCOT_NAME, Line
from spongebob.ui import theme
from spongebob.ui.canvas import BrailleCanvas, detect_truecolor
from spongebob.ui.replay import compute_replay_state, select_pulse_target

MIN_WIDTH = 50
MIN_HEIGHT = 16
SPEED_STEPS = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)


class VisualizeScreen(Screen[None]):
    """Full-terminal living-pipe visualizer replaying events via EventBus."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("space", "toggle_pause", "Pause/Resume"),
        Binding("plus", "speed_up", "Speed +"),
        Binding("equal", "speed_up", "Speed +", show=False),
        Binding("minus", "speed_down", "Speed -"),
        Binding("r", "restart", "Restart"),
        Binding("p", "trigger_pulse", "Pulse"),
    ]

    CSS = f"""
    VisualizeScreen {{
        layout: vertical;
        background: {theme.BG};
        color: {theme.CREAM};
    }}
    #viz-main {{
        height: 1fr;
    }}
    #pipe-pane {{
        width: 1fr;
        height: 1fr;
        padding: 0 1;
        background: {theme.BG};
        border: solid {theme.SIGNAL_GREEN};
    }}
    #side-readout {{
        width: 32;
        height: 1fr;
        padding: 0 1;
        border: solid {theme.SIGNAL_GREEN};
        background: {theme.BG};
        margin-left: 1;
    }}
    #readout-title {{
        color: {theme.SIGNAL_GREEN};
        text-style: bold;
    }}
    #readout-text {{
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

    def __init__(
        self,
        path: Sequence[Hop],
        events: Sequence[Event],
        findings: Sequence[Finding],
        narrator_lines: Sequence[Line] = (),
        narrator_enabled: bool = True,
        latency_kind: LatencyKind = "one_way",
    ) -> None:
        super().__init__()
        self._path = list(path)
        self._hop_names = [h.name for h in self._path]
        self._events = list(events)
        self._findings = list(findings)
        self._narrator_lines = list(narrator_lines)
        self._narrator_enabled = narrator_enabled
        self._latency_kind: LatencyKind = latency_kind
        self._max_time_ms = max((e.time_ms for e in self._events), default=0.0)
        self._pulse_target = select_pulse_target(self._findings, self._hop_names)
        self._truecolor = detect_truecolor()

        self._bus = EventBus()
        self._replayed_events: list[Event] = []
        self._next_event_idx = 0

        self._t_ms = 0.0
        self._paused = False
        self._speed_idx = 2  # 1.0x
        self._pulse_active = False
        self._pulse_x = 0.0
        self._pulse_ticks = 0
        self._canvas: BrailleCanvas | None = None
        self._timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield theme.make_top_title("VISUALIZE")
        yield theme.RedTopRule(id="viz-red-rule", classes="red-rule")
        banner_label = (
            "VISUALIZE — LIVE RTT PIPE"
            if self._latency_kind == "rtt"
            else "VISUALIZE — LIVE SIMULATION PIPE"
        )
        yield Static(banner_label, classes="screen-banner")
        yield Static("Enlarge terminal (minimum 50x16 required).", id="too-small")
        with Horizontal(id="viz-main"):
            yield Static("", id="pipe-pane")
            with Vertical(id="side-readout"):
                yield Static("LIVE TELEMETRY", id="readout-title")
                yield Static("", id="readout-text")
        yield Static(theme.format_status_line("REPLAY READY", 0.0), id="viz-status", classes="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._reset_bus()
        self._timer = self.set_interval(1.0 / 30.0, self._on_tick)
        self._check_size_and_render()

    def on_resize(self) -> None:
        self._canvas = None
        self._check_size_and_render()

    def _reset_bus(self) -> None:
        self._bus = EventBus()
        self._replayed_events = []
        self._next_event_idx = 0
        self._bus.subscribe("*", lambda ev: self._replayed_events.append(ev))

    def _advance_bus_to(self, t_ms: float) -> None:
        while (
            self._next_event_idx < len(self._events)
            and self._events[self._next_event_idx].time_ms <= t_ms
        ):
            self._bus.publish(self._events[self._next_event_idx])
            self._next_event_idx += 1

    def _on_tick(self) -> None:
        if not self._paused:
            speed = SPEED_STEPS[self._speed_idx]
            dt_ms = (1000.0 / 30.0) * speed
            if self._t_ms < self._max_time_ms:
                self._t_ms = min(self._max_time_ms, self._t_ms + dt_ms)
                self._advance_bus_to(self._t_ms)
                if self._t_ms >= self._max_time_ms:
                    self._pulse_active = True
                    self._pulse_x = 0.0
                    self._pulse_ticks = 0
            elif self._pulse_active:
                self._pulse_ticks += 1
                target_x = (
                    (self._pulse_target.hop_index + 0.5) / max(1, len(self._hop_names))
                    if self._pulse_target.hop_index is not None
                    else 1.0
                )
                if self._pulse_x < target_x:
                    self._pulse_x = min(target_x, self._pulse_x + 0.03)
        self._check_size_and_render()

    def _check_size_and_render(self) -> None:
        w, h = self.size.width, self.size.height
        too_small = self.query_one("#too-small", Static)
        viz_main = self.query_one("#viz-main", Horizontal)
        if w < MIN_WIDTH or h < MIN_HEIGHT:
            too_small.styles.display = "block"
            viz_main.styles.display = "none"
            return
        too_small.styles.display = "none"
        viz_main.styles.display = "block"
        self._render_frame()

    def _update_red_rule(self) -> None:
        rule_widget = self.query_one("#viz-red-rule", theme.RedTopRule)
        w = max(20, rule_widget.size.width or 80)
        if self._pulse_active:
            marker_pos = max(0, min(w - 1, int(self._pulse_x * (w - 1))))
            chars = ["━"] * w
            chars[marker_pos] = "▼"
            rule_widget.update("".join(chars))
        else:
            rule_widget.update("━" * w)

    def _render_frame(self) -> None:
        self._update_red_rule()
        pipe_pane = self.query_one("#pipe-pane", Static)
        cols = max(16, pipe_pane.size.width - 4)
        rows = max(8, pipe_pane.size.height - 5)
        if cols < 16 or rows < 8:
            return

        if self._canvas is None or self._canvas.cols != cols or self._canvas.rows != rows:
            self._canvas = BrailleCanvas(cols, rows)

        canvas = self._canvas
        canvas.fade(0.72)

        pw = canvas.pixel_width
        ph = canvas.pixel_height
        mid_y = ph // 2
        pipe_half = max(4, ph // 5)
        num_hops = max(1, len(self._path))

        state = compute_replay_state(self._replayed_events, self._hop_names, self._t_ms)
        is_rtt = self._latency_kind == "rtt"

        # Deterministic signal-band stripe field inside the pipe
        band_rows = theme.generate_signal_bands(max(1, pw - 4), 5, seed=42)
        for b_idx, b_row in enumerate(band_rows):
            by = mid_y - 2 + b_idx
            if 1 <= by < ph - 1:
                for x_off, (ch, rgb) in enumerate(b_row):
                    if ch != " " and x_off % 3 == 0:
                        dim_rgb = (rgb[0] // 3, rgb[1] // 3, rgb[2] // 3)
                        canvas.set_pixel(2 + x_off, by, dim_rgb)

        # Draw living pipe walls (narrowing at bandwidth-capped hops in simulation mode)
        for x in range(2, pw - 2):
            x_norm = x / max(1, pw - 1)
            hop_idx = min(num_hops - 1, int(x_norm * num_hops))
            hop = self._path[hop_idx]
            show_bw = (not is_rtt) and (hop.bandwidth_kbps is not None)
            half_h = max(2, pipe_half // 2) if show_bw else pipe_half
            wall_color = theme.WARN_AMBER_RGB if show_bw else theme.SIGNAL_GREEN_RGB
            canvas.set_pixel(x, mid_y - half_h, wall_color)
            canvas.set_pixel(x, mid_y + half_h, wall_color)

        # Draw hop nodes and queued packet stacks
        for i, hop in enumerate(self._path):
            hx = int(((i + 0.5) / num_hops) * (pw - 6)) + 3
            node_color = theme.TEAL_LIGHT_RGB
            if (
                self._pulse_active
                and not self._pulse_target.all_clear
                and self._pulse_target.hop_index == i
                and self._pulse_ticks % 6 < 3
            ):
                node_color = theme.CRIT_RED_RGB
            canvas.draw_circle(hx, mid_y, 2, node_color)

            if not is_rtt:
                q_depth = state.queue_depths.get(hop.name, 0)
                for q in range(min(q_depth, 8)):
                    qx = max(2, hx - 4 - (q * 2))
                    qy = mid_y - pipe_half - 2 - (q % 3)
                    canvas.set_pixel(qx, qy, theme.WARN_AMBER_RGB)

        # Draw moving packet particles
        for p in state.particles:
            px = int(p.x_norm * (pw - 6)) + 3
            py = int(mid_y + p.jitter_offset * 4)
            canvas.draw_circle(px, py, 1, theme.CREAM_RGB)
            canvas.set_pixel(px - 2, py, theme.TEAL_MID_RGB)

        # Draw drop effects distinct by reason
        for d in state.drops:
            hx = int(((d.hop_index + 0.5) / num_hops) * (pw - 6)) + 3
            spread = int((d.age_ms / 220.0) * 6) + 1
            if d.reason == "timeout":
                # Silent fade-out with no shatter: reads as "never came back"
                fade = max(0.0, 1.0 - (d.age_ms / 220.0))
                color = (
                    int(theme.TEAL_MID_RGB[0] * fade + theme.BG_RGB[0]),
                    int(theme.TEAL_MID_RGB[1] * fade + theme.BG_RGB[1]),
                    int(theme.TEAL_MID_RGB[2] * fade + theme.BG_RGB[2]),
                )
                canvas.set_pixel(hx, mid_y, color)
                canvas.set_pixel(hx + 1, mid_y, color)
            elif d.reason == "queue_full":
                color = theme.CRIT_RED_RGB
                for s in range(1, spread + 1):
                    canvas.set_pixel(hx - s, mid_y - s, color)
                    canvas.set_pixel(hx + s, mid_y - s, color)
            elif d.reason == "burst":
                color = theme.RED_RULE_RGB
                for s in range(-spread, spread + 1):
                    canvas.set_pixel(hx, mid_y + s, color)
            else:
                color = theme.WARN_AMBER_RGB
                canvas.set_pixel(hx - spread, mid_y - spread, color)
                canvas.set_pixel(hx + spread, mid_y + spread, color)
                canvas.set_pixel(hx - spread, mid_y + spread, color)
                canvas.set_pixel(hx + spread, mid_y - spread, color)

        # Draw diagnostic pulse wave
        if self._pulse_active:
            pulse_px = int(self._pulse_x * (pw - 6)) + 3
            pulse_color = theme.TEAL_LIGHT_RGB if self._pulse_target.all_clear else theme.RED_RULE_RGB
            canvas.draw_line(pulse_px, 1, pulse_px, ph - 2, pulse_color)

        rich_text = Text()
        # Hop name labels aligned along the pipe
        label_row = [" "] * cols
        for i, name in enumerate(self._hop_names):
            cx = int(((i + 0.5) / num_hops) * cols)
            tag = name.upper()[: max(3, cols // max(1, num_hops) - 1)]
            start_c = max(0, min(cols - len(tag), cx - len(tag) // 2))
            for idx_c, ch in enumerate(tag):
                label_row[start_c + idx_c] = ch
        rich_text.append("".join(label_row) + "\n", style=Style(bold=True, color=theme.SIGNAL_GREEN))

        for r_idx, row in enumerate(canvas.iter_rows()):
            for ch, rgb in row:
                if rgb is None:
                    rich_text.append(ch)
                else:
                    rich_text.append(ch, style=theme.color_style(rgb, truecolor=self._truecolor))
            if r_idx < canvas.rows - 1:
                rich_text.append("\n")

        callout = self._callout_text()
        if callout:
            rich_text.append(f"\n{callout}", style=Style(bold=True, color=theme.CREAM))
        pipe_pane.update(rich_text)

        # Update outlined telemetry readout
        lat_str = f"{state.latency_avg_ms:.1f} ms" if state.latency_avg_ms is not None else "N/A"
        jit_str = f"{state.jitter_ms:.1f} ms" if state.jitter_ms is not None else "N/A"
        lat_label = "RTT:      " if is_rtt else "Latency:  "
        readout = (
            f"Time:     {state.time_ms:>5.0f}/{self._max_time_ms:<5.0f}ms\n"
            f"Speed:    {SPEED_STEPS[self._speed_idx]}x"
            f"{' [PAUSED]' if self._paused else ''}\n\n"
            f"Sent:     {state.sent:>5}\n"
            f"Delivered:{state.delivered:>5}\n"
            f"Lost:     {state.lost:>5} ({state.loss_pct:.1f}%)\n"
            f"{lat_label}{lat_str}\n"
            f"Jitter:   {jit_str}\n"
        )
        if not is_rtt:
            q_lines = "\n".join(
                f"  {name:<8} {state.queue_depths.get(name, 0):>3}" for name in self._hop_names
            )
            readout += f"Reordered:{state.reordered:>5}\n\nQueue Depth:\n{q_lines}"
        self.query_one("#readout-text", Static).update(readout)

        frac = (self._t_ms / self._max_time_ms) if self._max_time_ms > 0 else 1.0
        status_label = "PULSE STALLED" if (self._pulse_active and not self._pulse_target.all_clear) else "REPLAYING"
        self.query_one("#viz-status", Static).update(
            theme.format_status_line(status_label, frac)
        )

    def _callout_text(self) -> str:
        hops_bar = "  ->  ".join(self._hop_names)
        if not self._pulse_active:
            return f"Path: {hops_bar}"
        mascot_line = ""
        if self._narrator_enabled and self._narrator_lines:
            if self._pulse_target.hop_name is not None:
                matched = next(
                    (l.text for l in self._narrator_lines if l.hop == self._pulse_target.hop_name),
                    self._narrator_lines[0].text,
                )
            else:
                matched = self._narrator_lines[0].text
            mascot_line = f"\n{MASCOT_NAME}: {matched}"
        if self._pulse_target.all_clear:
            return f"PULSE ALL CLEAR  |  Path: {hops_bar}{mascot_line}"
        f = self._pulse_target.finding
        if f is None:
            return f"Path: {hops_bar}{mascot_line}"
        loc = self._pulse_target.hop_name or "path"
        return f"PULSE STALLED @ {loc}: [{f.severity.upper()}] {f.code} = {f.value:.2f}{mascot_line}"

    def action_toggle_pause(self) -> None:
        self._paused = not self._paused

    def action_speed_up(self) -> None:
        if self._speed_idx < len(SPEED_STEPS) - 1:
            self._speed_idx += 1

    def action_speed_down(self) -> None:
        if self._speed_idx > 0:
            self._speed_idx -= 1

    def action_restart(self) -> None:
        self._t_ms = 0.0
        self._paused = False
        self._pulse_active = False
        self._pulse_x = 0.0
        self._pulse_ticks = 0
        self._reset_bus()
        if self._canvas is not None:
            self._canvas.clear()

    def action_trigger_pulse(self) -> None:
        self._pulse_active = True
        self._pulse_x = 0.0
        self._pulse_ticks = 0

    def action_go_back(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        self.app.pop_screen()
