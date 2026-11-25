from __future__ import annotations

from typing import Sequence

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Footer, Header, Static

from spongebob.analyzer import Finding
from spongebob.bus import EventBus
from spongebob.engine.models import Event, Hop
from spongebob.narrator import MASCOT_NAME, Line
from spongebob.ui.canvas import BrailleCanvas, detect_truecolor, rgb_to_ansi256
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

    CSS = """
    VisualizeScreen {
        layout: vertical;
    }
    #viz-main {
        height: 1fr;
    }
    #pipe-pane {
        width: 1fr;
        height: 1fr;
        padding: 0 1;
        background: #060b14;
    }
    #side-readout {
        width: 30;
        height: 1fr;
        padding: 1;
        border-left: solid #1e293b;
        background: #0f172a;
    }
    #too-small {
        width: 100%;
        height: 100%;
        content-align: center middle;
        color: #facc15;
        text-style: bold;
        display: none;
    }
    """

    def __init__(
        self,
        path: Sequence[Hop],
        events: Sequence[Event],
        findings: Sequence[Finding],
        narrator_lines: Sequence[Line] = (),
        narrator_enabled: bool = True,
    ) -> None:
        super().__init__()
        self._path = list(path)
        self._hop_names = [h.name for h in self._path]
        self._events = list(events)
        self._findings = list(findings)
        self._narrator_lines = list(narrator_lines)
        self._narrator_enabled = narrator_enabled
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
        yield Header(show_clock=False)
        yield Static("Enlarge terminal (minimum 50x16 required).", id="too-small")
        with Horizontal(id="viz-main"):
            yield Static("", id="pipe-pane")
            with Vertical(id="side-readout"):
                yield Static("", id="readout-text")
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

    def _color_style(self, rgb: tuple[int, int, int]) -> Style:
        if self._truecolor:
            return Style(color=f"rgb({rgb[0]},{rgb[1]},{rgb[2]})")
        return Style(color=f"color({rgb_to_ansi256(*rgb)})")

    def _render_frame(self) -> None:
        pipe_pane = self.query_one("#pipe-pane", Static)
        cols = max(16, pipe_pane.size.width - 2)
        rows = max(8, pipe_pane.size.height - 2)
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

        # Draw living pipe walls (narrowing at bandwidth-capped hops)
        for x in range(2, pw - 2):
            x_norm = x / max(1, pw - 1)
            hop_idx = min(num_hops - 1, int(x_norm * num_hops))
            hop = self._path[hop_idx]
            half_h = max(2, pipe_half // 2) if hop.bandwidth_kbps is not None else pipe_half
            wall_color = (56, 189, 248) if hop.bandwidth_kbps is None else (245, 158, 11)
            canvas.set_pixel(x, mid_y - half_h, wall_color)
            canvas.set_pixel(x, mid_y + half_h, wall_color)

        # Draw hop nodes and queued packet stacks
        for i, hop in enumerate(self._path):
            hx = int(((i + 0.5) / num_hops) * (pw - 6)) + 3
            node_color = (148, 163, 184)
            if (
                self._pulse_active
                and not self._pulse_target.all_clear
                and self._pulse_target.hop_index == i
                and self._pulse_ticks % 6 < 3
            ):
                node_color = (248, 113, 113)
            canvas.draw_circle(hx, mid_y, 2, node_color)

            q_depth = state.queue_depths.get(hop.name, 0)
            for q in range(min(q_depth, 8)):
                qx = max(2, hx - 4 - (q * 2))
                qy = mid_y - pipe_half - 2 - (q % 3)
                canvas.set_pixel(qx, qy, (251, 191, 36))

        # Draw moving packet particles
        for p in state.particles:
            px = int(p.x_norm * (pw - 6)) + 3
            py = int(mid_y + p.jitter_offset * 4)
            canvas.draw_circle(px, py, 1, (52, 211, 153))
            canvas.set_pixel(px - 2, py, (16, 185, 129))

        # Draw drop shatter effects distinct by reason
        for d in state.drops:
            hx = int(((d.hop_index + 0.5) / num_hops) * (pw - 6)) + 3
            spread = int((d.age_ms / 220.0) * 6) + 1
            if d.reason == "queue_full":
                color = (239, 68, 68)
                for s in range(1, spread + 1):
                    canvas.set_pixel(hx - s, mid_y - s, color)
                    canvas.set_pixel(hx + s, mid_y - s, color)
            elif d.reason == "burst":
                color = (232, 121, 249)
                for s in range(-spread, spread + 1):
                    canvas.set_pixel(hx, mid_y + s, color)
            else:
                color = (251, 146, 60)
                canvas.set_pixel(hx - spread, mid_y - spread, color)
                canvas.set_pixel(hx + spread, mid_y + spread, color)
                canvas.set_pixel(hx - spread, mid_y + spread, color)
                canvas.set_pixel(hx + spread, mid_y - spread, color)

        # Draw diagnostic pulse wave
        if self._pulse_active:
            pulse_px = int(self._pulse_x * (pw - 6)) + 3
            pulse_color = (34, 211, 238) if self._pulse_target.all_clear else (248, 113, 113)
            canvas.draw_line(pulse_px, 1, pulse_px, ph - 2, pulse_color)

        rich_text = Text()
        for r_idx, row in enumerate(canvas.iter_rows()):
            for ch, rgb in row:
                if rgb is None:
                    rich_text.append(ch)
                else:
                    rich_text.append(ch, style=self._color_style(rgb))
            if r_idx < canvas.rows - 1:
                rich_text.append("\n")

        # Callout line at bottom of pipe pane
        callout = self._callout_text()
        if callout:
            rich_text.append(f"\n{callout}", style=Style(bold=True, color="bright_white"))
        pipe_pane.update(rich_text)

        # Update side readout
        lat_str = f"{state.latency_avg_ms:.1f} ms" if state.latency_avg_ms is not None else "N/A"
        jit_str = f"{state.jitter_ms:.1f} ms" if state.jitter_ms is not None else "N/A"
        q_lines = "\n".join(f"  {name}: {state.queue_depths.get(name, 0)}" for name in self._hop_names)
        readout = (
            f"LIVE TELEMETRY\n"
            f"t = {state.time_ms:.0f} / {self._max_time_ms:.0f} ms\n"
            f"Speed: {SPEED_STEPS[self._speed_idx]}x"
            f"{' [PAUSED]' if self._paused else ''}\n\n"
            f"Sent:      {state.sent}\n"
            f"Delivered: {state.delivered}\n"
            f"Lost:      {state.lost} ({state.loss_pct:.1f}%)\n"
            f"Latency:   {lat_str}\n"
            f"Jitter:    {jit_str}\n"
            f"Reordered: {state.reordered}\n\n"
            f"Queue Depth:\n{q_lines}"
        )
        self.query_one("#readout-text", Static).update(readout)

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
