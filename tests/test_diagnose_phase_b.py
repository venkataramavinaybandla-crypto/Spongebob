from __future__ import annotations

import asyncio
import io
import socket
import threading

import pytest

from spongebob.__main__ import main as cli_main
from spongebob.analyzer import THRESHOLDS, Finding, analyze
from spongebob.diagnose import Sample, samples_to_events
from spongebob.engine import Event, Hop
from spongebob.meter import measure
from spongebob.narrator import (
    DIAGNOSE_SUMMARY_POOL,
    DROP_REASON_POOLS,
    MASCOT_NAME,
    narrate,
)
from tests.test_phase5 import BANNED_NAMES


def test_adapter_hand_computed_metrics_and_rfc3550_jitter() -> None:
    samples = [
        Sample(seq=0, sent_at_ms=0.0, rtt_ms=10.0, outcome="ok"),
        Sample(seq=1, sent_at_ms=200.0, rtt_ms=26.0, outcome="ok"),
        Sample(seq=2, sent_at_ms=400.0, rtt_ms=None, outcome="timeout"),
        Sample(seq=3, sent_at_ms=600.0, rtt_ms=42.0, outcome="ok"),
    ]
    adapted = samples_to_events({"tcp:127.0.0.1:443": samples})

    assert [h.name for h in adapted.path] == ["you", "tcp:127.0.0.1:443"]
    assert adapted.latency_kind == "rtt"
    assert adapted.errors == {}
    assert adapted.size_bytes == 0

    metrics = measure(adapted.events, packet_size_bytes=adapted.size_bytes)
    assert metrics.sent == 4
    assert metrics.delivered == 3
    assert metrics.lost == 1
    assert metrics.loss_pct == pytest.approx(25.0)
    assert metrics.loss_by_hop == {"tcp:127.0.0.1:443": 1}
    assert metrics.latency_ms is not None
    assert metrics.latency_ms.min == pytest.approx(10.0)
    assert metrics.latency_ms.avg == pytest.approx(26.0)
    assert metrics.latency_ms.max == pytest.approx(42.0)

    # RFC 3550 jitter: J_0 = 0; |26-10|=16 -> J_1 = 1.0; |42-26|=16 -> J_2 = 1.0 + (16-1)/16 = 1.9375
    assert metrics.jitter_ms == pytest.approx(1.9375)
    assert metrics.throughput_kbps is None


def test_adapter_timeouts_vs_errors_and_empty_inputs() -> None:
    samples = [
        Sample(seq=0, sent_at_ms=0.0, rtt_ms=12.0, outcome="ok"),
        Sample(seq=1, sent_at_ms=200.0, rtt_ms=None, outcome="timeout"),
        Sample(seq=2, sent_at_ms=400.0, rtt_ms=None, outcome="refused"),
        Sample(seq=3, sent_at_ms=600.0, rtt_ms=None, outcome="unreachable"),
    ]
    adapted = samples_to_events({"tcp:127.0.0.1:443": samples})
    drops = [e for e in adapted.events if e.type == "packet_dropped"]
    assert len(drops) == 1
    assert drops[0].reason == "timeout"
    assert adapted.errors is not None
    assert len(adapted.errors["tcp:127.0.0.1:443"]) == 2

    metrics = measure(adapted.events, packet_size_bytes=0)
    assert metrics.sent == 2
    assert metrics.delivered == 1
    assert metrics.lost == 1
    assert metrics.loss_pct == pytest.approx(50.0)

    empty = samples_to_events({})
    assert [h.name for h in empty.path] == ["you"]
    assert empty.events == []
    assert measure(empty.events, packet_size_bytes=0).throughput_kbps is None
    assert analyze(empty.events, empty.path, latency_kind="rtt") == []

    all_errors = samples_to_events(
        {"dns": [Sample(seq=0, sent_at_ms=0.0, rtt_ms=None, outcome="dns_error")]}
    )
    assert all_errors.events == []
    assert all_errors.errors is not None and len(all_errors.errors["dns"]) == 1
    assert analyze(all_errors.events, all_errors.path, latency_kind="rtt") == []


def test_adapter_three_consecutive_timeouts_triggers_burst_loss_pinned_to_segment() -> None:
    samples = [
        Sample(seq=0, sent_at_ms=0.0, rtt_ms=10.0, outcome="ok"),
        Sample(seq=1, sent_at_ms=200.0, rtt_ms=None, outcome="timeout"),
        Sample(seq=2, sent_at_ms=400.0, rtt_ms=None, outcome="timeout"),
        Sample(seq=3, sent_at_ms=600.0, rtt_ms=None, outcome="timeout"),
        Sample(seq=4, sent_at_ms=800.0, rtt_ms=12.0, outcome="ok"),
    ]
    adapted = samples_to_events({"tcp:example:443": samples})
    findings = analyze(adapted.events, adapted.path, latency_kind="rtt")

    burst = [f for f in findings if f.code == "BURST_LOSS"]
    assert len(burst) == 1
    assert burst[0].severity == "warn"
    assert burst[0].hop == "tcp:example:443"
    assert burst[0].value == pytest.approx(3.0)


@pytest.mark.parametrize(
    ("avg_ms", "expected_rtt_sev", "expected_one_way_sev"),
    [
        (250.0, None, "warn"),
        (350.0, "warn", "warn"),
        (900.0, "critical", "critical"),
    ],
)
def test_analyzer_rtt_vs_one_way_delay_thresholds(
    avg_ms: float, expected_rtt_sev: str | None, expected_one_way_sev: str
) -> None:
    assert THRESHOLDS["HIGH_DELAY_RTT"] == {"warn": 300.0, "critical": 800.0}
    path = [Hop(name="you"), Hop(name="tcp:target:443")]
    events = [
        Event("packet_sent", 0, 0.0, "you"),
        Event("packet_delivered", 0, avg_ms, "tcp:target:443", delay_ms=avg_ms, total_latency_ms=avg_ms),
    ]

    rtt_findings = [f for f in analyze(events, path, latency_kind="rtt") if f.code == "HIGH_DELAY"]
    if expected_rtt_sev is None:
        assert rtt_findings == []
    else:
        assert len(rtt_findings) == 1
        assert rtt_findings[0].severity == expected_rtt_sev

    ow_findings = [f for f in analyze(events, path, latency_kind="one_way") if f.code == "HIGH_DELAY"]
    assert len(ow_findings) == 1
    assert ow_findings[0].severity == expected_one_way_sev


def test_analyzer_rtt_mode_skips_bandwidth_choke_and_reordering() -> None:
    path = [Hop(name="you"), Hop(name="tcp:target:443")]
    events = [
        Event("packet_sent", 0, 0.0, "you"),
        Event("packet_sent", 1, 10.0, "you"),
        Event("packet_delivered", 1, 20.0, "tcp:target:443", delay_ms=10.0, total_latency_ms=10.0, queue_depth=50),
        Event("packet_delivered", 0, 30.0, "tcp:target:443", delay_ms=30.0, total_latency_ms=30.0, queue_depth=50),
        Event("packet_dropped", 2, 40.0, "tcp:target:443", reason="queue_full"),
    ]
    findings = analyze(events, path, latency_kind="rtt")
    codes = {f.code for f in findings}
    assert "BANDWIDTH_CHOKE" not in codes
    assert "REORDERING" not in codes


def test_narrator_timeout_and_diagnose_summary_pools_and_output() -> None:
    timeout_pool = DROP_REASON_POOLS["timeout"]
    assert len(timeout_pool) >= 8
    assert len(set(timeout_pool)) == len(timeout_pool)
    assert len(DIAGNOSE_SUMMARY_POOL) >= 6
    assert len(set(DIAGNOSE_SUMMARY_POOL)) == len(DIAGNOSE_SUMMARY_POOL)

    for tmpl in (*timeout_pool, *DIAGNOSE_SUMMARY_POOL):
        rendered = tmpl.format(hop="tcp:host:443", value="5")
        assert "{hop}" not in rendered and "{value}" not in rendered
        lowered = tmpl.lower()
        for banned in BANNED_NAMES:
            assert banned not in lowered

    samples = [
        Sample(seq=0, sent_at_ms=0.0, rtt_ms=900.0, outcome="ok"),
        Sample(seq=1, sent_at_ms=200.0, rtt_ms=10.0, outcome="ok"),
        Sample(seq=2, sent_at_ms=400.0, rtt_ms=None, outcome="timeout"),
        Sample(seq=3, sent_at_ms=600.0, rtt_ms=None, outcome="timeout"),
        Sample(seq=4, sent_at_ms=800.0, rtt_ms=None, outcome="timeout"),
    ]
    adapted = samples_to_events({"tcp:host:443": samples})
    metrics = measure(adapted.events, packet_size_bytes=0)
    findings = analyze(adapted.events, adapted.path, latency_kind="rtt")
    lines = narrate(findings, metrics, adapted.events, seed=7, mode="diagnose")

    assert any(line.tone == "chaotic" for line in lines)
    assert any(line.tone == "upbeat" for line in lines)
    assert len(lines) >= len(findings) + 2


def test_cli_diagnose_end_to_end_and_consent_abort(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ready = threading.Event()
    stop_event = threading.Event()
    port_holder: list[int] = []

    def serve() -> None:
        async def _run() -> None:
            async def _handle(_r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
                w.close()
                await w.wait_closed()

            server = await asyncio.start_server(_handle, "127.0.0.1", 0)
            port_holder.append(server.sockets[0].getsockname()[1])
            ready.set()
            try:
                while not stop_event.is_set():
                    await asyncio.sleep(0.05)
            finally:
                server.close()
                await server.wait_closed()

        asyncio.run(_run())

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    assert ready.wait(timeout=5.0)
    port = port_holder[0]

    try:
        # Consent = "y"
        monkeypatch.setattr("sys.stdin", io.StringIO("y\n"))
        rc = cli_main(["diagnose", "127.0.0.1", "--port", str(port), "--count", "3", "--interval-ms", "100"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "round-trip time" in out
        assert "timeouts approximate packet loss" in out
        assert "throughput=n/a" in out
        assert MASCOT_NAME in out

        # Consent = "n"
        called = False

        async def fail_if_called(*_args: object, **_kwargs: object) -> list[Sample]:
            nonlocal called
            called = True
            return []

        monkeypatch.setattr("spongebob.diagnose.probe_tcp", fail_if_called)
        monkeypatch.setattr("sys.stdin", io.StringIO("n\n"))
        rc_abort = cli_main(["diagnose", "127.0.0.1", "--port", str(port), "--count", "3", "--interval-ms", "100"])
        assert rc_abort == 0
        assert called is False
        assert "Aborted." in capsys.readouterr().out
    finally:
        stop_event.set()
        thread.join(timeout=5.0)


def test_cli_no_args_opens_menu_app(monkeypatch: pytest.MonkeyPatch) -> None:
    ran = False

    def fake_run(self: object) -> None:
        nonlocal ran
        ran = True

    monkeypatch.setattr("spongebob.ui.app.SimulatorApp.run", fake_run)
    rc = cli_main([])
    assert rc == 0
    assert ran is True
