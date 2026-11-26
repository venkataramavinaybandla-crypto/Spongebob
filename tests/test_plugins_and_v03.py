from __future__ import annotations

import json
from pathlib import Path

import pytest
from textual.widgets import Button, Input, Select, Static

from spongebob.__main__ import main as cli_main
from spongebob.meter import LatencyStats, Metrics
from spongebob.narrator import FINDING_POOLS, Narrator, narrate
from spongebob.plugins import (
    MAX_PLUGIN_FILE_BYTES,
    MAX_PLUGIN_FILES,
    load_plugin,
    load_plugins_from_dir,
)
from spongebob.ui.app import SimulatorApp
from spongebob.ui.export_modal import ExportOverwriteModal
from spongebob.ui.menu_screen import MenuScreen
from spongebob.ui.settings_screen import SettingsScreen
from spongebob.ui.simulate_screen import SimulateScreen
from tests.conftest import wait_for_screen, wait_until


def _write_manifest(folder: Path, name: str, kind: str, extra: str = "") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "plugin.toml").write_text(
        f'name = "{name}"\nversion = "0.1.0"\nkind = "{kind}"\ndescription = "Test pack"\n{extra}',
        encoding="utf-8",
    )


def test_plugins_valid_packs_of_all_three_kinds_and_never_executes_py(tmp_path: Path) -> None:
    # 1. Scenarios plugin (also containing a .py file that must NEVER execute)
    scen_dir = tmp_path / "lab-scenarios"
    _write_manifest(scen_dir, "lab-scenarios", "scenarios")
    marker = tmp_path / "executed.marker"
    (scen_dir / "evil.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('pwned')\n",
        encoding="utf-8",
    )
    (scen_dir / "amber-link.toml").write_text(
        """
[scenario]
name = "Amber Link"
description = "Custom lab link"
[flow]
packets = 20
interval_ms = 10.0
size_bytes = 64
seed = 5
[[hop]]
name = "router"
delay_ms = 22.0
jitter_ms = 4.0
loss_pct = 1.0
""",
        encoding="utf-8",
    )

    # 2. Jokes plugin
    jokes_dir = tmp_path / "reef-jokes"
    _write_manifest(jokes_dir, "reef-jokes", "jokes")
    (jokes_dir / "jokes.toml").write_text(
        '[findings]\n"HIGH_DELAY.warn" = ["Extra tide lag at {hop}: {value} ms!"]\n'
        '[drop_reasons]\n"timeout" = ["Extra silent wait at {hop} ({value})!"]\n',
        encoding="utf-8",
    )

    # 3. Theme plugin
    theme_dir = tmp_path / "deep-theme"
    _write_manifest(theme_dir, "deep-theme", "theme")
    (theme_dir / "theme.toml").write_text(
        '[colors]\nbg = "#010203"\ncream = "#f5f5f5"\nsignal_green = "#22ee77"\n',
        encoding="utf-8",
    )

    reg = load_plugins_from_dir(tmp_path)
    assert reg.errors == ()
    assert len(reg.plugins) == 3
    assert "lab-scenarios/amber-link" in reg.scenarios
    assert ("HIGH_DELAY", "warn") in reg.finding_jokes
    assert "timeout" in reg.drop_jokes
    assert reg.theme_colors["bg"] == "#010203"
    assert not marker.exists()

    # Jokes pack adds lines without shrinking built-in pools; same seed deterministic
    assert len(FINDING_POOLS[("HIGH_DELAY", "warn")]) >= 8
    n1 = Narrator(extra_finding_pools=reg.finding_jokes, extra_drop_pools=reg.drop_jokes)
    n2 = Narrator(extra_finding_pools=reg.finding_jokes, extra_drop_pools=reg.drop_jokes)
    metrics = Metrics(10, 10, 0, 0.0, {}, LatencyStats(10, 10, 10, 10), 0.0, 0.0, 0, 10.0)
    assert n1.narrate([], metrics, [], seed=7) == n2.narrate([], metrics, [], seed=7)


def test_plugin_rejections_and_skip_without_crash(tmp_path: Path) -> None:
    # Unknown key in manifest
    p1 = tmp_path / "bad-key"
    _write_manifest(p1, "bad-key", "jokes", extra='unknown_field = "x"\n')
    with pytest.raises(ValueError, match="unknown_field"):
        load_plugin(p1)

    # Bad name
    p2 = tmp_path / "bad-name"
    _write_manifest(p2, "Bad_Name!", "jokes")
    with pytest.raises(ValueError, match="Invalid plugin name"):
        load_plugin(p2)

    # Oversize file
    p3 = tmp_path / "oversize"
    _write_manifest(p3, "oversize-pack", "jokes")
    (p3 / "jokes.toml").write_bytes(b"#" * (MAX_PLUGIN_FILE_BYTES + 1))
    with pytest.raises(ValueError, match=str(MAX_PLUGIN_FILE_BYTES)):
        load_plugin(p3)

    # Too many files
    p4 = tmp_path / "too-many"
    _write_manifest(p4, "too-many", "jokes")
    for i in range(MAX_PLUGIN_FILES):
        (p4 / f"f{i}.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match=str(MAX_PLUGIN_FILES)):
        load_plugin(p4)

    # Bad hex
    p5 = tmp_path / "bad-hex"
    _write_manifest(p5, "bad-hex", "theme")
    (p5 / "theme.toml").write_text('[colors]\nbg = "not-hex"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid hex"):
        load_plugin(p5)

    # Low contrast
    p6 = tmp_path / "low-contrast"
    _write_manifest(p6, "low-contrast", "theme")
    (p6 / "theme.toml").write_text('[colors]\nbg = "#111111"\ncream = "#222222"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="contrast"):
        load_plugin(p6)

    # ANSI escape in joke line
    p7 = tmp_path / "ansi-joke"
    _write_manifest(p7, "ansi-joke", "jokes")
    (p7 / "jokes.toml").write_text('[findings]\n"HIGH_DELAY.warn" = ["\\u001b[31mred"]\n', encoding="utf-8")
    with pytest.raises(ValueError, match="control or escape"):
        load_plugin(p7)

    # Banned name in joke line
    p8 = tmp_path / "banned-joke"
    _write_manifest(p8, "banned-joke", "jokes")
    (p8 / "jokes.toml").write_text(
        '[findings]\n"HIGH_DELAY.warn" = ["Spongebob dropped {value} at {hop}!"]\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="banned name"):
        load_plugin(p8)

    # Disallowed {field} in joke line
    p9 = tmp_path / "bad-field"
    _write_manifest(p9, "bad-field", "jokes")
    (p9 / "jokes.toml").write_text(
        '[findings]\n"HIGH_DELAY.warn" = ["{secret} at {hop}!"]\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Disallowed placeholder"):
        load_plugin(p9)

    # Attempt to override built-in scenario
    p10 = tmp_path / "override-builtin"
    _write_manifest(p10, "override-pack", "scenarios")
    (p10 / "control-line.toml").write_text(
        """
[scenario]
name = "Hijack"
description = "Override attempt"
[flow]
packets = 10
interval_ms = 10.0
size_bytes = 64
[[hop]]
name = "client"
delay_ms = 1.0
jitter_ms = 0.0
loss_pct = 0.0
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="override built-in"):
        load_plugin(p10)

    # Loading the directory skips all invalid plugins without crashing
    reg = load_plugins_from_dir(tmp_path)
    assert len(reg.errors) == 10
    assert reg.plugins == ()


def test_no_auto_load_from_default_locations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    default_plug = fake_home / ".spongebob" / "plugins" / "auto-pack"
    _write_manifest(default_plug, "auto-pack", "jokes")
    (default_plug / "jokes.toml").write_text(
        '[findings]\n"HIGH_DELAY.warn" = ["Should not auto-load at {hop} ({value})"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))

    app = SimulatorApp()
    assert app.plugin_registry.plugins == ()

    # Narrator without plugins matches baseline
    m = Metrics(10, 10, 0, 0.0, {}, LatencyStats(10, 10, 10, 10), 0.0, 0.0, 0, 10.0)
    assert narrate([], m, [], seed=42) == app.narrator.narrate([], m, [], seed=42)


def test_cli_plugins_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "pack"
    _write_manifest(p, "pack-one", "jokes")
    (p / "jokes.toml").write_text(
        '[findings]\n"HIGH_DELAY.warn" = ["Slow swim at {hop}: {value} ms!"]\n',
        encoding="utf-8",
    )
    rc = cli_main(["plugins", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "pack-one" in out
    assert "[jokes]" in out
    assert "1 joke lines" in out


@pytest.mark.asyncio
async def test_ui_load_scenario_export_overwrite_and_settings_plugins(tmp_path: Path) -> None:
    # Prepare a valid plugin pack
    plug_dir = tmp_path / "plugs" / "ui-pack"
    _write_manifest(plug_dir, "ui-pack", "jokes")
    (plug_dir / "jokes.toml").write_text(
        '[findings]\n"HIGH_DELAY.warn" = ["UI plugin line at {hop}: {value}!"]\n',
        encoding="utf-8",
    )

    app = SimulatorApp()
    async with app.run_test(size=(110, 42)) as pilot:
        # 1. Settings screen loads plugins from typed path
        app.screen.query_one("#btn-settings", Button).press()
        await wait_for_screen(pilot, app, SettingsScreen)
        app.screen.query_one("#plugin-dir-input", Input).value = str(tmp_path / "plugs")
        app.screen.query_one("#btn-load-plugins", Button).press()
        await wait_until(
            pilot,
            lambda: "ui-pack" in str(app.screen.query_one("#plugin-status", Static).render()),
            message="Expected ui-pack in #plugin-status",
        )
        status_txt = str(app.screen.query_one("#plugin-status", Static).render())
        assert "ui-pack" in status_txt
        assert "1 jokes" in status_txt
        await pilot.press("escape")
        await wait_for_screen(pilot, app, MenuScreen)

        # 2. Simulate: Load scenario fills hop rows, then Run + Export + Overwrite confirm
        app.screen.query_one("#btn-simulate", Button).press()
        await wait_for_screen(pilot, app, SimulateScreen)

        app.screen.query_one("#scenario-select", Select).value = "flaky-last-mile"
        await wait_until(
            pilot,
            lambda: app.screen.query_one("#hop-client-loss", Input).value == "8.0",
            message="Expected hop-client-loss to be filled with 8.0",
        )

        app.screen.query_one("#btn-run", Button).press()
        await wait_until(
            pilot,
            lambda: app.screen.query_one("#btn-export", Button).disabled is False,
            message="Expected #btn-export to be enabled after run",
        )

        out_file = tmp_path / "ui_report.json"
        app.screen.query_one("#export-path", Input).value = str(out_file)
        app.screen.query_one("#btn-export", Button).press()
        await wait_until(
            pilot,
            lambda: out_file.is_file(),
            message="Expected initial export file to be written",
        )
        assert json.loads(out_file.read_text(encoding="utf-8"))["schema"] == 1

        # Second export to existing file opens overwrite modal; Esc cancels
        out_file.write_text("sentinel", encoding="utf-8")
        app.screen.query_one("#btn-export", Button).press()
        await wait_for_screen(pilot, app, ExportOverwriteModal)
        await pilot.press("escape")
        await wait_for_screen(pilot, app, SimulateScreen)
        assert out_file.read_text(encoding="utf-8") == "sentinel"

        # Confirm overwrite replaces file
        app.screen.query_one("#btn-export", Button).press()
        await wait_for_screen(pilot, app, ExportOverwriteModal)
        app.screen.query_one("#btn-overwrite-yes", Button).press()
        await wait_until(
            pilot,
            lambda: out_file.read_text(encoding="utf-8") != "sentinel",
            message="Expected overwrite to replace sentinel file",
        )
        assert json.loads(out_file.read_text(encoding="utf-8"))["schema"] == 1
