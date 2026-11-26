from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path

import pytest

from spongebob import __version__
from spongebob.__main__ import main as cli_main
from spongebob.diagnose import Sample, samples_to_events
from spongebob.engine import Flow, Hop, simulate
from spongebob.export import ExportPayload, export_report
from spongebob.meter import measure
from spongebob.narrator import MASCOT_NAME, narrate
from spongebob.scenarios import load_builtin_scenario, run_scenario


def test_json_export_matches_meter_and_events_flag(tmp_path: Path) -> None:
    sc = load_builtin_scenario("flaky-last-mile")
    res = run_scenario(sc)

    no_ev_path = tmp_path / "report.json"
    with_ev_path = tmp_path / "report_events.json"

    cli_main(["run", "flaky-last-mile", "--export", str(no_ev_path)])
    cli_main(["run", "flaky-last-mile", "--export", str(with_ev_path), "--events"])

    data = json.loads(no_ev_path.read_text(encoding="utf-8"))
    assert data["schema"] == 1
    assert data["spongebob_version"] == __version__
    assert data["source"] == "simulation"
    assert data["scenario"]["name"] == sc.name
    assert "events" not in data

    m = data["metrics"]
    assert m["sent"] == res.metrics.sent
    assert m["delivered"] == res.metrics.delivered
    assert m["lost"] == res.metrics.lost
    assert m["loss_pct"] == res.metrics.loss_pct
    assert m["jitter_ms"] == res.metrics.jitter_ms
    assert m["reordered"] == res.metrics.reordered
    assert m["throughput_kbps"] == res.metrics.throughput_kbps
    assert res.metrics.latency_ms is not None
    assert m["latency_ms"]["avg"] == res.metrics.latency_ms.avg

    data_ev = json.loads(with_ev_path.read_text(encoding="utf-8"))
    assert len(data_ev["events"]) == len(res.events)


def test_csv_export_rows_drops_and_formula_escaping(tmp_path: Path) -> None:
    path = [Hop(name="=SUM(1+1)", delay_ms=5.0, jitter_ms=0.0, loss_pct=50.0)]
    flow = Flow(packet_count=20, interval_ms=10.0, size_bytes=64)
    events = simulate(flow, path=path, seed=42)
    metrics = measure(events, packet_size_bytes=flow.size_bytes)

    csv_path = tmp_path / "packets.csv"
    payload = ExportPayload(
        source="simulation",
        metrics=metrics,
        findings=[],
        events=events,
    )
    export_report(payload, csv_path)

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))

    assert rows[0] == ["seq", "send_time_ms", "outcome", "latency_ms", "drop_hop", "drop_reason"]
    assert len(rows) == 1 + flow.packet_count

    dropped_rows = [r for r in rows[1:] if r[2] == "dropped"]
    assert dropped_rows
    for r in dropped_rows:
        assert r[4] == "'=SUM(1+1)"
        assert r[5] == "random"


def test_markdown_simulation_and_diagnose_reports_and_no_narrator(tmp_path: Path) -> None:
    sim_md = tmp_path / "sim.md"
    cli_main(["run", "flaky-last-mile", "--export", str(sim_md)])
    sim_txt = sim_md.read_text(encoding="utf-8")
    assert "## Configured vs Measured" in sim_txt
    assert "DELAY" in sim_txt
    assert "JITTER" in sim_txt
    assert "LOSS" in sim_txt
    assert MASCOT_NAME in sim_txt

    sim_no_narr = tmp_path / "sim_quiet.md"
    cli_main(["run", "flaky-last-mile", "--no-narrator", "--export", str(sim_no_narr)])
    assert MASCOT_NAME not in sim_no_narr.read_text(encoding="utf-8")

    # Diagnose JSON + MD
    samples = [
        Sample(seq=0, sent_at_ms=0.0, rtt_ms=15.0, outcome="ok"),
        Sample(seq=1, sent_at_ms=200.0, rtt_ms=None, outcome="timeout"),
    ]
    adapted = samples_to_events({"tcp:127.0.0.1:443": samples})
    diag_metrics = measure(adapted.events, packet_size_bytes=0)
    diag_lines = narrate([], diag_metrics, adapted.events, seed=1, mode="diagnose")

    diag_json = tmp_path / "diag.json"
    diag_md = tmp_path / "diag.md"
    diag_payload = ExportPayload(
        source="diagnose",
        metrics=diag_metrics,
        findings=[],
        events=adapted.events,
        narrator_lines=tuple(diag_lines),
        latency_kind="rtt",
        target_host="127.0.0.1",
        target_port=443,
    )
    export_report(diag_payload, diag_json)
    export_report(diag_payload, diag_md)

    dj = json.loads(diag_json.read_text(encoding="utf-8"))
    assert dj["latency_kind"] == "rtt"
    assert dj["target"] == {"host": "127.0.0.1", "port": 443}

    dm = diag_md.read_text(encoding="utf-8")
    assert "round-trip time" in dm
    assert "timeouts approximate packet loss" in dm
    assert "n/a" in dm


def test_no_export_creates_zero_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    rc = cli_main(["run", "control-line"])
    assert rc == 0
    assert list(tmp_path.iterdir()) == []


def test_export_safety_existing_missing_parent_and_bad_extension(tmp_path: Path) -> None:
    sc = load_builtin_scenario("control-line")
    res = run_scenario(sc)
    payload = ExportPayload(
        source="simulation",
        metrics=res.metrics,
        findings=res.findings,
        events=res.events,
        scenario=sc,
    )

    # Bad extension
    with pytest.raises(ValueError, match="Unsupported export format"):
        export_report(payload, tmp_path / "bad.txt")

    # Missing parent directory (never created)
    missing_parent = tmp_path / "nonexistent_dir" / "out.json"
    with pytest.raises(FileNotFoundError):
        export_report(payload, missing_parent)
    assert not (tmp_path / "nonexistent_dir").exists()

    # Existing file refused without --force, untouched; overwritten with --force
    existing = tmp_path / "keep.json"
    existing.write_text("original", encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_report(payload, existing, force=False)
    assert existing.read_text(encoding="utf-8") == "original"

    export_report(payload, existing, force=True)
    assert json.loads(existing.read_text(encoding="utf-8"))["schema"] == 1


def test_determinism_byte_identical_across_all_formats(tmp_path: Path) -> None:
    for ext in (".json", ".csv", ".md"):
        p1 = tmp_path / f"a{ext}"
        p2 = tmp_path / f"b{ext}"
        cli_main(["run", "crowded-wifi", "--seed", "42", "--export", str(p1)])
        cli_main(["run", "crowded-wifi", "--seed", "42", "--export", str(p2)])
        assert p1.read_bytes() == p2.read_bytes()


def test_atomic_write_failure_leaves_no_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sc = load_builtin_scenario("control-line")
    res = run_scenario(sc)
    payload = ExportPayload(
        source="simulation",
        metrics=res.metrics,
        findings=res.findings,
        events=res.events,
        scenario=sc,
    )

    def fail_replace(_src: object, _dst: object) -> None:
        raise OSError("simulated disk error")

    monkeypatch.setattr(os, "replace", fail_replace)
    target = tmp_path / "atomic.json"
    with pytest.raises(OSError, match="simulated disk error"):
        export_report(payload, target)

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_diagnose_cli_export_still_requires_consent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_file = tmp_path / "diag.json"
    monkeypatch.setattr("sys.stdin", io.StringIO("n\n"))
    rc = cli_main(["diagnose", "127.0.0.1", "--count", "2", "--interval-ms", "100", "--export", str(out_file)])
    assert rc == 0
    assert not out_file.exists()
