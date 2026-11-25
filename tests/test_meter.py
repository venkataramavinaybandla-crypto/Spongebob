import math

from spongebob.engine import Flow, Hop, default_path, simulate
from spongebob.meter import measure


def test_no_impairments_zero_loss_latency_jitter() -> None:
    flow = Flow(packet_count=100, interval_ms=10.0, size_bytes=64)
    events = simulate(flow, path=default_path(), seed=1)
    metrics = measure(events, packet_size_bytes=flow.size_bytes)

    assert metrics.sent == 100
    assert metrics.delivered == 100
    assert metrics.lost == 0
    assert metrics.loss_pct == 0.0
    assert metrics.loss_by_hop == {}
    assert metrics.latency_ms is not None
    assert metrics.latency_ms.min == 0.0
    assert metrics.latency_ms.avg == 0.0
    assert metrics.latency_ms.max == 0.0
    assert metrics.latency_ms.p95 == 0.0
    assert metrics.jitter_ms == 0.0
    assert metrics.jitter_mean_abs_ms == 0.0
    assert metrics.reordered == 0


def test_fixed_100ms_path_exact_latency_and_zero_jitter() -> None:
    path = [
        Hop(name="client", delay_ms=10.0),
        Hop(name="router", delay_ms=25.0),
        Hop(name="isp", delay_ms=45.0),
        Hop(name="server", delay_ms=20.0),
    ]
    flow = Flow(packet_count=50, interval_ms=10.0, size_bytes=64)
    events = simulate(flow, path=path, seed=7)
    metrics = measure(events, packet_size_bytes=flow.size_bytes)

    expected = sum(h.delay_ms for h in path)
    assert metrics.latency_ms is not None
    assert math.isclose(metrics.latency_ms.min, expected, abs_tol=1e-9)
    assert math.isclose(metrics.latency_ms.avg, expected, abs_tol=1e-9)
    assert math.isclose(metrics.latency_ms.max, expected, abs_tol=1e-9)
    assert math.isclose(metrics.latency_ms.p95, expected, abs_tol=1e-9)
    assert metrics.jitter_ms == 0.0
    assert metrics.jitter_mean_abs_ms == 0.0
    assert metrics.reordered == 0


def test_uniform_20ms_jitter_bounds_and_mean_abs() -> None:
    delay = 50.0
    jitter = 20.0
    path = [Hop(name="single", delay_ms=delay, jitter_ms=jitter, jitter_model="uniform")]
    flow = Flow(packet_count=2000, interval_ms=100.0, size_bytes=64)
    events = simulate(flow, path=path, seed=123)
    metrics = measure(events, packet_size_bytes=flow.size_bytes)

    assert metrics.latency_ms is not None
    assert metrics.latency_ms.min >= delay - jitter
    assert metrics.latency_ms.max <= delay + jitter
    assert metrics.jitter_mean_abs_ms is not None
    assert metrics.jitter_ms is not None
    expected_mean_abs = 2.0 * jitter / 3.0
    assert abs(metrics.jitter_mean_abs_ms - expected_mean_abs) <= expected_mean_abs * 0.10


def test_loss_5_percent_10000_packets_pins_hop() -> None:
    path = [
        Hop(name="client", delay_ms=5.0, loss_pct=0.0),
        Hop(name="isp", delay_ms=15.0, loss_pct=5.0),
        Hop(name="server", delay_ms=5.0, loss_pct=0.0),
    ]
    flow = Flow(packet_count=10000, interval_ms=1.0, size_bytes=64)
    events = simulate(flow, path=path, seed=2026)
    metrics = measure(events, packet_size_bytes=flow.size_bytes)

    assert metrics.sent == 10000
    assert metrics.delivered + metrics.lost == 10000
    assert 4.0 <= metrics.loss_pct <= 6.0
    assert list(metrics.loss_by_hop.keys()) == ["isp"]
    assert metrics.loss_by_hop["isp"] == metrics.lost


def test_throughput_lossless_flow_matches_rate() -> None:
    path = [Hop(name="link", delay_ms=10.0)]
    flow = Flow(packet_count=200, interval_ms=10.0, size_bytes=128)
    events = simulate(flow, path=path, seed=5)
    metrics = measure(events, packet_size_bytes=flow.size_bytes)

    expected_kbps = (flow.size_bytes * 8.0) / flow.interval_ms
    assert abs(metrics.throughput_kbps - expected_kbps) <= expected_kbps * 0.02


def test_reordered_count_with_and_without_jitter() -> None:
    flow = Flow(packet_count=100, interval_ms=1.0, size_bytes=64)

    no_jitter_events = simulate(flow, path=[Hop(name="h", delay_ms=50.0, jitter_ms=0.0)], seed=17)
    no_jitter_metrics = measure(no_jitter_events, packet_size_bytes=flow.size_bytes)
    assert no_jitter_metrics.reordered == 0

    jitter_events = simulate(flow, path=[Hop(name="h", delay_ms=50.0, jitter_ms=45.0)], seed=17)
    jitter_metrics = measure(jitter_events, packet_size_bytes=flow.size_bytes)
    assert jitter_metrics.reordered > 0


def test_all_lost_flow_and_empty_input() -> None:
    empty_metrics = measure([])
    assert empty_metrics.sent == 0
    assert empty_metrics.delivered == 0
    assert empty_metrics.lost == 0
    assert empty_metrics.loss_pct == 0.0
    assert empty_metrics.loss_by_hop == {}
    assert empty_metrics.latency_ms is None
    assert empty_metrics.jitter_ms is None
    assert empty_metrics.jitter_mean_abs_ms is None
    assert empty_metrics.reordered == 0
    assert empty_metrics.throughput_kbps == 0.0

    flow = Flow(packet_count=25, interval_ms=5.0, size_bytes=64)
    all_lost_events = simulate(flow, path=[Hop(name="blackhole", loss_pct=100.0)], seed=9)
    all_lost_metrics = measure(all_lost_events, packet_size_bytes=flow.size_bytes)
    assert all_lost_metrics.sent == 25
    assert all_lost_metrics.delivered == 0
    assert all_lost_metrics.lost == 25
    assert all_lost_metrics.loss_pct == 100.0
    assert all_lost_metrics.loss_by_hop == {"blackhole": 25}
    assert all_lost_metrics.latency_ms is None
    assert all_lost_metrics.jitter_ms is None
    assert all_lost_metrics.jitter_mean_abs_ms is None
    assert all_lost_metrics.reordered == 0
    assert all_lost_metrics.throughput_kbps == 0.0
