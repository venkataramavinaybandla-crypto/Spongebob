import math
import pytest

from spongebob.engine import Flow, Hop, default_path, simulate


def test_zero_impairment_delivers_all_with_zero_latency() -> None:
    path = default_path()
    flow = Flow(packet_count=50, interval_ms=5.0, size_bytes=128)
    events = simulate(flow, path=path, seed=1)

    sent = [e for e in events if e.type == "packet_sent"]
    delivered = [e for e in events if e.type == "packet_delivered"]
    dropped = [e for e in events if e.type == "packet_dropped"]

    assert len(sent) == 50
    assert len(delivered) == 50
    assert len(dropped) == 0
    assert all(e.total_latency_ms == 0.0 for e in delivered)
    assert all(e.delay_ms == 0.0 for e in delivered)
    assert [e.time_ms for e in events] == sorted(e.time_ms for e in events)


def test_fixed_delay_100ms_across_path() -> None:
    path = [
        Hop(name="client", delay_ms=10.0),
        Hop(name="router", delay_ms=20.0),
        Hop(name="isp", delay_ms=55.0),
        Hop(name="server", delay_ms=15.0),
    ]
    flow = Flow(packet_count=20, interval_ms=10.0, size_bytes=64)
    events = simulate(flow, path=path, seed=7)

    delivered = [e for e in events if e.type == "packet_delivered"]
    assert len(delivered) == 20
    expected_total = sum(h.delay_ms for h in path)
    assert expected_total == 100.0
    for event in delivered:
        assert math.isclose(event.total_latency_ms, expected_total, rel_tol=0.0, abs_tol=1e-9)


def test_uniform_jitter_20ms_bounds_and_non_negative() -> None:
    path = [Hop(name="single", delay_ms=15.0, jitter_ms=20.0, jitter_model="uniform")]
    flow = Flow(packet_count=1000, interval_ms=1.0, size_bytes=64)
    events = simulate(flow, path=path, seed=123)

    delivered = [e for e in events if e.type == "packet_delivered"]
    assert len(delivered) == 1000
    latencies = [e.total_latency_ms for e in delivered]

    assert min(latencies) >= 0.0
    assert max(latencies) <= 35.0
    # Verify jitter actually spans both below and above base delay
    assert min(latencies) < 5.0
    assert max(latencies) > 30.0


def test_normal_jitter_clamped_at_zero() -> None:
    path = [Hop(name="single", delay_ms=5.0, jitter_ms=20.0, jitter_model="normal")]
    flow = Flow(packet_count=500, interval_ms=1.0, size_bytes=64)
    events = simulate(flow, path=path, seed=99)

    delivered = [e for e in events if e.type == "packet_delivered"]
    assert len(delivered) == 500
    assert all(e.total_latency_ms >= 0.0 for e in delivered)
    assert any(e.total_latency_ms == 0.0 for e in delivered)


def test_loss_5_percent_over_10000_packets() -> None:
    path = [Hop(name="lossy", delay_ms=10.0, jitter_ms=0.0, loss_pct=5.0)]
    flow = Flow(packet_count=10000, interval_ms=1.0, size_bytes=64)
    events = simulate(flow, path=path, seed=2026)

    dropped = [e for e in events if e.type == "packet_dropped"]
    delivered = [e for e in events if e.type == "packet_delivered"]
    assert len(dropped) + len(delivered) == 10000

    loss_rate = len(dropped) / 10000
    # 5% +/- 1% is ~4.6 standard deviations for n=10000, p=0.05
    assert 0.04 <= loss_rate <= 0.06


def test_seed_determinism_and_variation() -> None:
    path = default_path(delay_ms=20.0, jitter_ms=10.0, loss_pct=5.0)
    flow = Flow(packet_count=100, interval_ms=5.0, size_bytes=64)

    run1 = simulate(flow, path=path, seed=42)
    run2 = simulate(flow, path=path, seed=42)
    run3 = simulate(flow, path=path, seed=43)

    assert run1 == run2
    assert run1 != run3


def test_large_jitter_small_interval_causes_reordering() -> None:
    path = [Hop(name="jittery", delay_ms=50.0, jitter_ms=45.0, jitter_model="uniform")]
    flow = Flow(packet_count=100, interval_ms=1.0, size_bytes=64)
    events = simulate(flow, path=path, seed=17)

    delivered_seqs = [e.seq for e in events if e.type == "packet_delivered"]
    assert len(delivered_seqs) == 100
    assert delivered_seqs != sorted(delivered_seqs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "", "delay_ms": 0.0},
        {"name": "   ", "delay_ms": 0.0},
        {"name": "hop", "delay_ms": -1.0},
        {"name": "hop", "jitter_ms": -0.1},
        {"name": "hop", "loss_pct": -0.5},
        {"name": "hop", "loss_pct": 100.1},
        {"name": "hop", "jitter_model": "exponential"},
        {"name": "hop", "delay_ms": float("nan")},
        {"name": "hop", "jitter_ms": float("inf")},
    ],
)
def test_invalid_hop_raises(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        Hop(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"packet_count": 0},
        {"packet_count": -5},
        {"packet_count": 10, "interval_ms": -1.0},
        {"packet_count": 10, "interval_ms": float("nan")},
        {"packet_count": 10, "size_bytes": 0},
        {"packet_count": 10, "size_bytes": -64},
    ],
)
def test_invalid_flow_raises(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        Flow(**kwargs)


def test_empty_path_raises() -> None:
    flow = Flow(packet_count=5)
    with pytest.raises(ValueError):
        simulate(flow, path=[], seed=1)
