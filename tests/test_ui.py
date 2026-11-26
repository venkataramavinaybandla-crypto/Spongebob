import pytest

from spongebob.analyzer import Finding
from spongebob.engine import Flow, Hop, simulate
from spongebob.ui.app import SimulatorApp
from spongebob.ui.canvas import BrailleCanvas
from spongebob.ui.menu_screen import MenuScreen
from spongebob.ui.replay import compute_replay_state, select_pulse_target
from spongebob.ui.simulate_screen import SimulateScreen
from spongebob.ui.visualize_screen import VisualizeScreen
from tests.conftest import wait_for_screen, wait_until


def test_braille_canvas_set_clear_bounds_and_fade() -> None:
    canvas = BrailleCanvas(cols=4, rows=2)

    # Top-left dot (0, 0) -> U+2801; (1, 3) -> 0x80 => 0x2881
    canvas.set_pixel(0, 0, (200, 100, 50))
    assert canvas.get_char(0, 0) == "\u2801"
    canvas.set_pixel(1, 3, (200, 100, 50))
    assert canvas.get_char(0, 0) == "\u2881"

    canvas.clear_pixel(0, 0)
    assert canvas.get_char(0, 0) == "\u2880"
    canvas.clear_pixel(1, 3)
    assert canvas.get_char(0, 0) == "\u2800"
    assert canvas.get_color(0, 0) is None

    # Bounds safety
    canvas.set_pixel(-1, -1, (255, 255, 255))
    canvas.set_pixel(100, 100, (255, 255, 255))
    canvas.clear_pixel(-1, 0)
    canvas.clear_pixel(999, 999)
    assert canvas.get_char(-1, 0) == "\u2800"
    assert canvas.get_color(99, 99) is None

    # Monotonic fade
    canvas.set_pixel(2, 2, (200, 160, 120))
    prev = canvas.get_color(1, 0)
    assert prev is not None
    for _ in range(5):
        canvas.fade(0.7, cutoff=5)
        nxt = canvas.get_color(1, 0)
        if nxt is not None:
            assert nxt[0] <= prev[0] and nxt[1] <= prev[1] and nxt[2] <= prev[2]
            prev = nxt


def test_replay_state_determinism_drops_queues_and_overtaking() -> None:
    # Overtaking test: packet 0 gets large delay, packet 1 gets small delay
    path = [Hop(name="jittery", delay_ms=50.0, jitter_ms=45.0)]
    flow = Flow(packet_count=30, interval_ms=1.0, size_bytes=64)
    events = simulate(flow, path=path, seed=17)

    s1 = compute_replay_state(events, ["jittery"], t_ms=25.0)
    s2 = compute_replay_state(events, ["jittery"], t_ms=25.0)
    assert s1 == s2

    # Find a time where a later seq has overtaken an earlier seq in x_norm
    overtaken = False
    for t in range(5, 100, 2):
        st = compute_replay_state(events, ["jittery"], t_ms=float(t))
        by_seq = sorted(st.particles, key=lambda p: p.seq)
        for i in range(len(by_seq) - 1):
            if by_seq[i].x_norm < by_seq[i + 1].x_norm:
                overtaken = True
                break
        if overtaken:
            break
    assert overtaken

    # Queue depth and drops exposed
    bw_path = [Hop(name="tight", bandwidth_kbps=200.0, queue_limit_packets=2)]
    bw_events = simulate(Flow(packet_count=40, interval_ms=5.0, size_bytes=1000), path=bw_path, seed=1)
    bw_state = compute_replay_state(bw_events, ["tight"], t_ms=50.0)
    assert bw_state.queue_depths["tight"] >= 0
    assert bw_state.sent > 0


def test_pulse_target_selection() -> None:
    hops = ["client", "router", "isp", "server"]
    clear_target = select_pulse_target([], hops)
    assert clear_target.all_clear is True
    assert clear_target.hop_name is None
    assert clear_target.finding is None

    findings = [
        Finding("HIGH_JITTER", "warn", "router", 40.0, 30.0),
        Finding("PACKET_LOSS", "critical", "isp", 12.0, 5.0),
    ]
    target = select_pulse_target(findings, hops)
    assert target.all_clear is False
    assert target.hop_name == "isp"
    assert target.hop_index == 2
    assert target.finding is not None and target.finding.code == "PACKET_LOSS"


@pytest.mark.asyncio
async def test_textual_pilot_navigation_validation_run_and_visualize() -> None:
    app = SimulatorApp()
    async with app.run_test(size=(100, 40)) as pilot:
        assert isinstance(app.screen, MenuScreen)

        # Navigate to Simulate
        app.screen.query_one("#btn-simulate").press()
        await wait_for_screen(pilot, app, SimulateScreen)

        # Bad input validation disables Run button and shows error
        packets_input = app.screen.query_one("#flow-packets")
        packets_input.value = "-5"
        await wait_until(
            pilot,
            lambda: app.screen.query_one("#btn-run").disabled is True,
            message="Expected #btn-run disabled on invalid packets",
        )
        assert "Invalid input" in str(app.screen.query_one("#validation-error").render())

        # Fix input and run simulation
        packets_input.value = "30"
        await wait_until(
            pilot,
            lambda: app.screen.query_one("#btn-run").disabled is False,
            message="Expected #btn-run enabled after fixing packets",
        )
        app.screen.query_one("#btn-run").press()
        await wait_until(
            pilot,
            lambda: app.last_run is not None
            and app.screen.query_one("#btn-open-visualize").disabled is False,
            message="Expected simulation results and enabled #btn-open-visualize",
        )

        # Open Visualize from Simulate
        app.screen.query_one("#btn-open-visualize").press()
        await wait_until(
            pilot,
            lambda: isinstance(app.screen, VisualizeScreen),
            message="Expected VisualizeScreen",
        )

        # Controls work without error
        await pilot.press("space")
        await pilot.press("plus")
        await pilot.press("p")
        await pilot.pause()

        # Esc returns to Simulate
        await pilot.press("escape")
        await wait_until(
            pilot,
            lambda: isinstance(app.screen, SimulateScreen),
            message="Expected return to SimulateScreen",
        )

        # Esc returns to Menu
        await pilot.press("escape")
        await wait_until(
            pilot,
            lambda: isinstance(app.screen, MenuScreen),
            message="Expected return to MenuScreen",
        )
