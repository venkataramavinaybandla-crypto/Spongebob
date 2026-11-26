from __future__ import annotations

from pathlib import Path

import pytest

from spongebob.__main__ import main as cli_main
from spongebob.narrator import MASCOT_NAME
from spongebob.scenarios import (
    MAX_HOPS,
    MAX_PACKETS,
    MAX_SCENARIO_BYTES,
    dump_scenario,
    list_builtin_scenarios,
    load_builtin_scenario,
    load_scenario,
    loads_scenario,
    run_scenario,
)


def test_dump_and_load_round_trip(tmp_path: Path) -> None:
    for name in list_builtin_scenarios():
        original = load_builtin_scenario(name)
        dumped = dump_scenario(original)
        reloaded = loads_scenario(dumped)
        assert reloaded == original

        file_path = tmp_path / f"{name}.toml"
        file_path.write_text(dumped, encoding="utf-8")
        from_disk = load_scenario(file_path)
        assert from_disk == original


@pytest.mark.parametrize(
    ("toml_text", "expected_fragment"),
    [
        (
            """
extra_top = 1
[scenario]
name = "A"
description = "B"
[flow]
packets = 10
interval_ms = 10.0
size_bytes = 64
[[hop]]
name = "h1"
delay_ms = 1.0
jitter_ms = 0.0
loss_pct = 0.0
""",
            "extra_top",
        ),
        (
            """
[scenario]
name = "A"
description = "B"
author = "nobody"
[flow]
packets = 10
interval_ms = 10.0
size_bytes = 64
[[hop]]
name = "h1"
delay_ms = 1.0
jitter_ms = 0.0
loss_pct = 0.0
""",
            "author",
        ),
        (
            """
[scenario]
name = "A"
description = "B"
[flow]
packets = 10
interval_ms = 10.0
size_bytes = 64
protocol = "udp"
[[hop]]
name = "h1"
delay_ms = 1.0
jitter_ms = 0.0
loss_pct = 0.0
""",
            "protocol",
        ),
        (
            """
[scenario]
name = "A"
description = "B"
[flow]
packets = 10
interval_ms = 10.0
size_bytes = 64
[[hop]]
name = "h1"
delay_ms = 1.0
jitter_ms = 0.0
loss_pct = 0.0
mtu = 1500
""",
            "mtu",
        ),
    ],
)
def test_unknown_keys_rejected_with_key_name(
    toml_text: str, expected_fragment: str
) -> None:
    with pytest.raises(ValueError, match=expected_fragment):
        loads_scenario(toml_text)


@pytest.mark.parametrize(
    ("toml_text", "missing_key"),
    [
        (
            """
[scenario]
name = "A"
[flow]
packets = 10
interval_ms = 10.0
size_bytes = 64
[[hop]]
name = "h1"
delay_ms = 1.0
jitter_ms = 0.0
loss_pct = 0.0
""",
            "description",
        ),
        (
            """
[scenario]
name = "A"
description = "B"
[flow]
packets = 10
interval_ms = 10.0
[[hop]]
name = "h1"
delay_ms = 1.0
jitter_ms = 0.0
loss_pct = 0.0
""",
            "size_bytes",
        ),
        (
            """
[scenario]
name = "A"
description = "B"
[flow]
packets = 10
interval_ms = 10.0
size_bytes = 64
[[hop]]
name = "h1"
delay_ms = 1.0
jitter_ms = 0.0
""",
            "loss_pct",
        ),
    ],
)
def test_missing_required_keys_rejected(toml_text: str, missing_key: str) -> None:
    with pytest.raises(ValueError, match=missing_key):
        loads_scenario(toml_text)


def test_bad_ranges_oversize_and_too_many_hops(tmp_path: Path) -> None:
    # Bad loss > 100
    with pytest.raises(ValueError, match="loss_pct"):
        loads_scenario(
            """
[scenario]
name = "A"
description = "B"
[flow]
packets = 10
interval_ms = 10.0
size_bytes = 64
[[hop]]
name = "h1"
delay_ms = 1.0
jitter_ms = 0.0
loss_pct = 150.0
"""
        )

    # Packets > 100000
    with pytest.raises(ValueError, match=str(MAX_PACKETS)):
        loads_scenario(
            f"""
[scenario]
name = "A"
description = "B"
[flow]
packets = {MAX_PACKETS + 1}
interval_ms = 10.0
size_bytes = 64
[[hop]]
name = "h1"
delay_ms = 1.0
jitter_ms = 0.0
loss_pct = 0.0
"""
        )

    # Too many hops (> 12)
    hops_block = "\n".join(
        f'[[hop]]\nname = "h{i}"\ndelay_ms = 1.0\njitter_ms = 0.0\nloss_pct = 0.0'
        for i in range(MAX_HOPS + 1)
    )
    with pytest.raises(ValueError, match=str(MAX_HOPS)):
        loads_scenario(
            f"""
[scenario]
name = "A"
description = "B"
[flow]
packets = 10
interval_ms = 10.0
size_bytes = 64
{hops_block}
"""
        )

    # Oversize file (> 64 KB)
    big_file = tmp_path / "huge.toml"
    big_file.write_bytes(b"# " + b"x" * MAX_SCENARIO_BYTES)
    with pytest.raises(ValueError, match=str(MAX_SCENARIO_BYTES)):
        load_scenario(big_file)


@pytest.mark.parametrize(
    ("builtin_name", "expected_code", "expected_hop"),
    [
        ("control-line", None, None),
        ("crowded-wifi", "HIGH_JITTER", "router"),
        ("tunnel-burst", "BURST_LOSS", "isp"),
        ("long-haul-orbit", "HIGH_DELAY", None),
        ("overloaded-uplink", "BANDWIDTH_CHOKE", "router"),
        ("flaky-last-mile", "PACKET_LOSS", "client"),
    ],
)
def test_builtin_scenarios_produce_intended_findings(
    builtin_name: str, expected_code: str | None, expected_hop: str | None
) -> None:
    sc = load_builtin_scenario(builtin_name)
    res = run_scenario(sc)
    if expected_code is None:
        assert res.findings == []
    else:
        matched = [f for f in res.findings if f.code == expected_code]
        assert matched, f"{builtin_name} did not emit {expected_code}; got {res.findings}"
        if expected_hop is not None:
            assert any(f.hop == expected_hop for f in matched)


def test_seed_determinism_and_override() -> None:
    sc = load_builtin_scenario("flaky-last-mile")
    r1 = run_scenario(sc)
    r2 = run_scenario(sc)
    assert r1.events == r2.events
    assert r1.metrics == r2.metrics

    r3 = run_scenario(sc, seed=999)
    assert r3.events != r1.events


def test_cli_scenarios_and_run_file_and_builtin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc_list = cli_main(["scenarios"])
    assert rc_list == 0
    list_out = capsys.readouterr().out
    for name in (
        "control-line",
        "crowded-wifi",
        "tunnel-burst",
        "long-haul-orbit",
        "overloaded-uplink",
        "flaky-last-mile",
    ):
        assert name in list_out

    # Built-in run with --seed override
    rc_builtin = cli_main(["run", "flaky-last-mile", "--seed", "77"])
    assert rc_builtin == 0
    out_builtin = capsys.readouterr().out
    assert "Scenario: Flaky Last Mile" in out_builtin
    assert "PACKET_LOSS" in out_builtin
    assert MASCOT_NAME in out_builtin

    # File run
    sc_file = tmp_path / "custom.toml"
    sc_file.write_text(dump_scenario(load_builtin_scenario("control-line")), encoding="utf-8")
    rc_file = cli_main(["run", str(sc_file)])
    assert rc_file == 0
    out_file = capsys.readouterr().out
    assert "Scenario: Clean Control Line" in out_file
    assert "Findings: none" in out_file


def test_cli_no_args_menu_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    ran = False

    def fake_run(self: object) -> None:
        nonlocal ran
        ran = True

    monkeypatch.setattr("spongebob.ui.app.SimulatorApp.run", fake_run)
    assert cli_main([]) == 0
    assert ran is True
