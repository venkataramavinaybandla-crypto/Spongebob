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
from tests.conftest import wait_for_screen, wait_until


@pytest.mark.asyncio
async def test_menu_diagnose_enabled_and_opens_screen() -> None:
    app = SimulatorApp()
    async with app.run_test(size=(100, 40)) as pilot:
        assert __version__ == "0.3.2"
        assert isinstance(app.screen, MenuScreen)
        btn = app.screen.query_one("#btn-diagnose", Button)
        assert btn.disabled is False
        btn.press()
        await wait_until(
            pilot,
            lambda: isinstance(app.screen, DiagnoseScreen),
            message="Expected DiagnoseScreen",
        )


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
            screen.query_one("#btn-start", Button).press()
            await wait_for_screen(pilot, app, DiagnoseConfirmModal)
            app.screen.query_one("#btn-confirm-no", Button).press()
            await wait_for_screen(pilot, app, DiagnoseScreen)
            assert connections == 0

            # Click Start -> Esc
            screen.query_one("#btn-start", Button).press()
            await wait_for_screen(pilot, app, DiagnoseConfirmModal)
            await pilot.press("escape")
            await wait_for_screen(pilot, app, DiagnoseScreen)
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

            screen.query_one("#btn-start", Button).press()
            await wait_for_screen(pilot, app, DiagnoseConfirmModal)
            app.screen.query_one("#btn-confirm-yes", Button).press()
            await wait_until(
                pilot,
                lambda: "Round-trip time:" in str(screen.query_one("#metrics-output", Static).render()),
                message="Expected metrics output after diagnose run",
            )

            metrics_txt = str(screen.query_one("#metrics-output", Static).render())
            assert "Round-trip time:" in metrics_txt
            assert "Throughput: n/a" in metrics_txt
            assert "Sent: 3" in metrics_txt

            # Open Visualize from Diagnose results
            await pilot.press("v")
            await wait_until(
                pilot,
                lambda: isinstance(app.screen, VisualizeScreen)
                and "RTT:" in str(app.screen.query_one("#readout-text", Static).render()),
                message="Expected VisualizeScreen in RTT mode",
            )
            assert app.screen._latency_kind == "rtt"
            readout_txt = str(app.screen.query_one("#readout-text", Static).render())
            assert "RTT:" in readout_txt
            assert "Queue Depth:" not in readout_txt

            # Esc returns cleanly
            await pilot.press("escape")
            await wait_until(
                pilot,
                lambda: isinstance(app.screen, DiagnoseScreen),
                message="Expected return to DiagnoseScreen from VisualizeScreen",
            )
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

        screen.query_one("#btn-start", Button).press()
        await wait_for_screen(pilot, app, DiagnoseConfirmModal)
        app.screen.query_one("#btn-confirm-yes", Button).press()
        await wait_until(
            pilot,
            lambda: screen._active_worker is not None,
            message="Expected active worker to start",
        )

        worker = screen._active_worker
        assert worker is not None

        # Esc cancels mid-run and returns to Menu
        await pilot.press("escape")
        await wait_until(
            pilot,
            lambda: isinstance(app.screen, MenuScreen) and worker.is_finished,
            message="Expected MenuScreen and finished worker after Esc",
        )


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

        screen.query_one("#btn-start", Button).press()
        await wait_for_screen(pilot, app, DiagnoseConfirmModal)
        app.screen.query_one("#btn-confirm-yes", Button).press()
        await wait_until(
            pilot,
            lambda: "refused" in str(screen.query_one("#errors-output", Static).render()),
            message="Expected refused in #errors-output",
        )

        metrics_txt = str(screen.query_one("#metrics-output", Static).render())
        errors_txt = str(screen.query_one("#errors-output", Static).render())
        assert "Lost: 0 (0.00%" in metrics_txt
        assert "refused" in errors_txt
