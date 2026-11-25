from __future__ import annotations

import re
from pathlib import Path

import pytest
from textual.widgets import Input, Static

from spongebob import __version__
from spongebob.ui import theme
from spongebob.ui.app import SimulatorApp
from spongebob.ui.diagnose_screen import DiagnoseScreen
from spongebob.ui.menu_screen import MenuScreen
from spongebob.ui.simulate_screen import SimulateScreen
from spongebob.ui.visualize_screen import VisualizeScreen


@pytest.mark.asyncio
async def test_simulate_core_inputs_visible_without_scrolling_at_100x30() -> None:
    app = SimulatorApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.click("#btn-simulate")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SimulateScreen)

        # No validation error on first show
        assert str(screen.query_one("#validation-error", Static).render()).strip() == ""

        # All 4 hops' delay/jitter/loss inputs visible within first 30 rows without scrolling
        for hop in ("client", "router", "isp", "server"):
            for metric in ("delay", "jitter", "loss"):
                inp = screen.query_one(f"#hop-{hop}-{metric}", Input)
                assert inp.region.height >= 1
                assert inp.region.y >= 0
                assert inp.region.y + inp.region.height <= 30


@pytest.mark.asyncio
async def test_diagnose_no_error_on_mount() -> None:
    app = SimulatorApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.click("#btn-diagnose")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, DiagnoseScreen)
        assert str(screen.query_one("#validation-error", Static).render()).strip() == ""


def test_no_hardcoded_hex_in_screen_files() -> None:
    hex_pattern = re.compile(r"#[0-9a-fA-F]{3,8}\b")
    ui_dir = Path("spongebob", "ui")
    for filename in (
        "app.py",
        "menu_screen.py",
        "simulate_screen.py",
        "visualize_screen.py",
        "diagnose_screen.py",
    ):
        src = (ui_dir / filename).read_text(encoding="utf-8")
        matches = hex_pattern.findall(src)
        assert not matches, f"Hardcoded hex {matches} found in {filename}"


def test_signal_bands_deterministic_and_version() -> None:
    assert __version__ == "0.2.1"
    b1 = theme.generate_signal_bands(40, 4, seed=42)
    b2 = theme.generate_signal_bands(40, 4, seed=42)
    assert b1 == b2
    assert theme.segmented_bar(0.5, width=10) == "[█████░░░░░]"


@pytest.mark.asyncio
async def test_all_screens_open_and_esc_returns() -> None:
    app = SimulatorApp()
    async with app.run_test(size=(100, 35)) as pilot:
        assert isinstance(app.screen, MenuScreen)

        for btn_id, screen_cls in (
            ("#btn-simulate", SimulateScreen),
            ("#btn-visualize", VisualizeScreen),
            ("#btn-diagnose", DiagnoseScreen),
        ):
            await pilot.click(btn_id)
            await pilot.pause()
            assert isinstance(app.screen, screen_cls)
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, MenuScreen)
