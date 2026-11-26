from __future__ import annotations

import asyncio
import socket

import pytest
from textual.widgets import Button, Input, Static

from spongebob import __version__
from spongebob.diagnose import Sample
from spongebob.ui.app import SimulatorApp
from spongebob.ui.diagnose_screen import DiagnoseConfirmModal, DiagnoseScreen
from spongebob.ui.menu_screen import MenuScreen
from spongebob.ui.visualize_screen import VisualizeScreen


@pytest.mark.asyncio
async def test_menu_diagnose_enabled_and_opens_screen() -> None:
    app = SimulatorApp()
    async with app.run_test(size=(100, 40)) as pilot:
        assert __version__ == "0.3.1"
        assert isinstance(app.screen, MenuScreen)
        btn = app.screen.query_one("#btn-diagnose", Button)
        assert btn.disabled is False
        await pilot.click("#btn-diagnose")
        await pilot.pause()
        assert isinstance(app.screen, DiagnoseScreen)


@pytest.mark.asyncio
async def test_diagnose_validation_blocks_bad_inputs() -> None:
    app = SimulatorApp()
    async with app.run_test(size=(110, 42)) as pilot:
        await pilot.click("#btn-diagnose")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, DiagnoseScreen)

        screen.query_one("#diag-host", Input).value = "127.0.0.1"
        await pilot.pause()
        assert screen.query_one("#btn-start", Button).disabled is False

        # Bad count (201)
        screen.query_one("#diag-count", Input).value = "201"
        await pilot.pause()
        assert screen.query_one("#btn-start", Button).disabled is True
        assert "Invalid input" in str(screen.query_one("#validation-error", Static).render())

        # Bad interval (50)
        screen.query_one("#diag-count", Input).value = "5"
        screen.query_one("#diag-interval", Input).value = "50"
        await pilot.pause()
        assert screen.query_one("#btn-start", Button).disabled is True

        # Bad port (70000)
        screen.query_one("#diag-interval", Input).value = "100"
        screen.query_one("#diag-port", Input).value = "70000"
        await pilot.pause()
        assert screen.query_one("#btn-start", Button).disabled is True


@pytest.mark.asyncio
async def test_diagnose_consent_decline_and_esc_probe_nothing() -> None:
    connections = 0

    async def handle(_r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        nonlocal connections
        connections += 1
        w.close()
        await w.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        app = SimulatorApp()
        async with app.run_test(size=(110, 42)) as pilot:
            await pilot.click("#btn-diagnose")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, DiagnoseScreen)

            screen.query_one("#diag-host", Input).value = "127.0.0.1"
            screen.query_one("#diag-port", Input).value = str(port)
            screen.query_one("#diag-count", Input).value = "3"
            screen.query_one("#diag-interval", Input).value = "100"
            await pilot.pause()

            # Click Start -> Cancel
            await pilot.click("#btn-start")
            await pilot.pause()
            assert isinstance(app.screen, DiagnoseConfirmModal)
            await pilot.click("#btn-confirm-no")
            await pilot.pause()
            assert isinstance(app.screen, DiagnoseScreen)
            assert connections == 0

            # Click Start -> Esc
            await pilot.click("#btn-start")
            await pilot.pause()
            assert isinstance(app.screen, DiagnoseConfirmModal)
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, DiagnoseScreen)
            assert connections == 0
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_diagnose_local_server_full_run_and_visualize_rtt() -> None:
    async def handle(_r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        w.close()
        await w.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        app = SimulatorApp()
        async with app.run_test(size=(110, 42)) as pilot:
            await pilot.click("#btn-diagnose")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, DiagnoseScreen)

            screen.query_one("#diag-host", Input).value = "127.0.0.1"
            screen.query_one("#diag-port", Input).value = str(port)
            screen.query_one("#diag-count", Input).value = "3"
            screen.query_one("#diag-interval", Input).value = "100"
            await pilot.pause()

            await pilot.click("#btn-start")
            await pilot.pause()
            await pilot.click("#btn-confirm-yes")
            await pilot.pause(0.8)

            metrics_txt = str(screen.query_one("#metrics-output", Static).render())
            assert "Round-trip time:" in metrics_txt
            assert "Throughput: n/a" in metrics_txt
            assert "Sent: 3" in metrics_txt

            # Open Visualize from Diagnose results
            await pilot.press("v")
            await pilot.pause(0.2)
            assert isinstance(app.screen, VisualizeScreen)
            assert app.screen._latency_kind == "rtt"
            readout_txt = str(app.screen.query_one("#readout-text", Static).render())
            assert "RTT:" in readout_txt
            assert "Queue Depth:" not in readout_txt

            # Esc returns cleanly
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, DiagnoseScreen)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_diagnose_cancel_mid_run_leaves_no_running_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def slow_probe(*_args: object, **_kwargs: object) -> list[Sample]:
        await asyncio.sleep(5.0)
        return []

    monkeypatch.setattr("spongebob.ui.diagnose_screen.probe_tcp", slow_probe)

    app = SimulatorApp()
    async with app.run_test(size=(110, 42)) as pilot:
        await pilot.click("#btn-diagnose")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, DiagnoseScreen)

        screen.query_one("#diag-host", Input).value = "127.0.0.1"
        screen.query_one("#diag-count", Input).value = "5"
        screen.query_one("#diag-interval", Input).value = "100"
        await pilot.pause()

        await pilot.click("#btn-start")
        await pilot.pause()
        await pilot.click("#btn-confirm-yes")
        await pilot.pause(0.05)

        worker = screen._active_worker
        assert worker is not None

        # Esc cancels mid-run and returns to Menu
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert isinstance(app.screen, MenuScreen)
        assert worker.is_finished


@pytest.mark.asyncio
async def test_diagnose_refused_port_shows_errors_and_zero_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_refused(*_args: object, **_kwargs: object) -> list[Sample]:
        return [
            Sample(seq=0, sent_at_ms=0.0, rtt_ms=None, outcome="refused"),
            Sample(seq=1, sent_at_ms=100.0, rtt_ms=None, outcome="refused"),
            Sample(seq=2, sent_at_ms=200.0, rtt_ms=None, outcome="refused"),
        ]

    monkeypatch.setattr("spongebob.ui.diagnose_screen.probe_tcp", fake_refused)

    app = SimulatorApp()
    async with app.run_test(size=(110, 42)) as pilot:
        await pilot.click("#btn-diagnose")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, DiagnoseScreen)

        screen.query_one("#diag-host", Input).value = "127.0.0.1"
        screen.query_one("#diag-port", Input).value = "9999"
        screen.query_one("#diag-count", Input).value = "5"
        screen.query_one("#diag-interval", Input).value = "100"
        await pilot.pause()

        await pilot.click("#btn-start")
        await pilot.pause()
        await pilot.click("#btn-confirm-yes")
        await pilot.pause(0.2)

        metrics_txt = str(screen.query_one("#metrics-output", Static).render())
        errors_txt = str(screen.query_one("#errors-output", Static).render())
        assert "Lost: 0 (0.00%" in metrics_txt
        assert "refused" in errors_txt
