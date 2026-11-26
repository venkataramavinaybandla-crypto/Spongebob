from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path

import pytest
from textual.widgets import Button, Input, Static

from spongebob import __version__
from spongebob.__main__ import main as cli_main
from spongebob.export import default_export_path
from spongebob.ui.app import SimulatorApp
from spongebob.ui.diagnose_screen import DiagnoseScreen
from spongebob.ui.export_modal import DiagnoseExportModal


@pytest.mark.parametrize(
    "hostile_target",
    [
        "../../x",
        "a/b\\c",
        "evil name:443",
        "x" * 120,
        "café.example.com",
        "...leading.dots",
    ],
)
def test_default_export_path_sanitizes_hostile_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hostile_target: str
) -> None:
    dl = tmp_path / "Downloads"
    dl.mkdir()
    monkeypatch.setattr("spongebob.export.exporter.get_downloads_dir", lambda: dl)

    out = default_export_path(kind="diagnose", target=hostile_target, fmt="md")
    assert out.parent == dl
    assert out.name.startswith("spongebob-diagnose-")
    assert out.suffix == ".md"
    assert ".." not in out.name
    assert "/" not in out.name and "\\" not in out.name
    # Sanitized target portion <= 60 chars and no leading dot
    target_part = out.stem[len("spongebob-diagnose-") :]
    assert 1 <= len(target_part) <= 60
    assert not target_part.startswith(".")


def test_default_export_path_collisions_and_missing_downloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dl = tmp_path / "Downloads"
    dl.mkdir()
    monkeypatch.setattr("spongebob.export.exporter.get_downloads_dir", lambda: dl)

    p1 = default_export_path(kind="diagnose", target="127.0.0.1", fmt="md")
    assert p1.name == "spongebob-diagnose-127.0.0.1.md"
    p1.write_text("keep-1", encoding="utf-8")

    p2 = default_export_path(kind="diagnose", target="127.0.0.1", fmt="md")
    assert p2.name == "spongebob-diagnose-127.0.0.1-2.md"
    p2.write_text("keep-2", encoding="utf-8")

    p3 = default_export_path(kind="diagnose", target="127.0.0.1", fmt="md")
    assert p3.name == "spongebob-diagnose-127.0.0.1-3.md"
    assert p1.read_text(encoding="utf-8") == "keep-1"
    assert p2.read_text(encoding="utf-8") == "keep-2"


def test_missing_downloads_raises_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    no_home = tmp_path / "NoHome"
    monkeypatch.setattr("spongebob.export.exporter.Path.home", lambda: no_home)
    monkeypatch.setattr("spongebob.export.exporter.sys.platform", "linux")
    with pytest.raises(FileNotFoundError, match="Downloads"):
        default_export_path(kind="diagnose", target="127.0.0.1", fmt="md")
    assert not no_home.exists()


@pytest.mark.asyncio
async def test_ui_diagnose_export_modal_prefill_esc_and_edited_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dl = tmp_path / "Downloads"
    dl.mkdir()
    monkeypatch.setattr("spongebob.export.exporter.get_downloads_dir", lambda: dl)

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
            screen.query_one("#diag-count", Input).value = "2"
            screen.query_one("#diag-interval", Input).value = "100"
            await pilot.pause()

            await pilot.click("#btn-start")
            await pilot.pause()
            await pilot.click("#btn-confirm-yes")
            await pilot.pause(0.6)

            # Open Export modal -> prefilled with Downloads path, Esc writes nothing
            screen.query_one("#btn-export", Button).scroll_visible()
            await pilot.pause()
            await pilot.click("#btn-export")
            await pilot.pause()
            assert isinstance(app.screen, DiagnoseExportModal)
            prefilled = app.screen.query_one("#modal-export-path", Input).value
            assert prefilled == str(dl / "spongebob-diagnose-127.0.0.1.md")

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, DiagnoseScreen)
            assert list(dl.iterdir()) == []

            # Re-open Export modal, edit path to .json, press Save -> writes edited path
            await pilot.click("#btn-export")
            await pilot.pause()
            assert isinstance(app.screen, DiagnoseExportModal)
            edited = dl / "custom-diag.json"
            app.screen.query_one("#modal-export-path", Input).value = str(edited)
            await pilot.click("#btn-export-save")
            await pilot.pause()
            assert edited.is_file()
            assert json.loads(edited.read_text(encoding="utf-8"))["source"] == "diagnose"
            status_txt = str(screen.query_one("#export-status", Static).render())
            assert str(edited) in status_txt
    finally:
        server.close()
        await server.wait_closed()


def test_cli_diagnose_export_downloads_and_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert __version__ == "0.3.2"
    dl = tmp_path / "Downloads"
    dl.mkdir()
    monkeypatch.setattr("spongebob.export.exporter.get_downloads_dir", lambda: dl)

    import threading

    ready = threading.Event()
    stop_ev = threading.Event()
    port_holder: list[int] = []

    def serve() -> None:
        async def _run() -> None:
            async def _h(_r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
                w.close()
                await w.wait_closed()

            srv = await asyncio.start_server(_h, "127.0.0.1", 0)
            port_holder.append(srv.sockets[0].getsockname()[1])
            ready.set()
            try:
                while not stop_ev.is_set():
                    await asyncio.sleep(0.05)
            finally:
                srv.close()
                await srv.wait_closed()

        asyncio.run(_run())

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    assert ready.wait(timeout=5.0)
    port = port_holder[0]

    try:
        # Without --export-downloads: nothing written
        monkeypatch.setattr("sys.stdin", io.StringIO("y\n"))
        rc1 = cli_main(["diagnose", "127.0.0.1", "--port", str(port), "--count", "2", "--interval-ms", "100"])
        assert rc1 == 0
        assert list(dl.iterdir()) == []
        capsys.readouterr()

        # With --export-downloads: writes one file and prints full path
        monkeypatch.setattr("sys.stdin", io.StringIO("y\n"))
        rc2 = cli_main(
            [
                "diagnose",
                "127.0.0.1",
                "--port",
                str(port),
                "--count",
                "2",
                "--interval-ms",
                "100",
                "--export-downloads",
            ]
        )
        assert rc2 == 0
        files = list(dl.iterdir())
        assert len(files) == 1
        assert files[0].name == "spongebob-diagnose-127.0.0.1.md"
        out = capsys.readouterr().out
        assert str(files[0]) in out
    finally:
        stop_ev.set()
        t.join(timeout=5.0)
