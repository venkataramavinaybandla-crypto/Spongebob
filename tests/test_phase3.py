import math

from spongebob.analyzer import THRESHOLDS, analyze
from spongebob.bus import EventBus, replay
from spongebob.engine import Event, Flow, Hop, default_path, simulate
from spongebob.meter import measure


def test_regression_defaults_unchanged() -> None:
    path = default_path(delay_ms=25.0, jitter_ms=5.0, loss_pct=2.0)
    flow = Flow(packet_count=100, interval_ms=10.0, size_bytes=64)
    events1 = simulate(flow, path=path, seed=42)
    events2 = simulate(flow, path=path, seed=42)
    assert events1 == events2
    for event in events1:
        if event.type == "packet_dropped":
            assert event.reason == "random"
        elif event.type in ("packet_delayed", "packet_delivered"):
            assert event.queue_depth is None


def test_bandwidth_above_and_below_cap() -> None:
    # Offered: 1000 bytes * 8 / 5 ms = 1600 kbps; Cap: 800 kbps
    congested_path = [
        Hop(name="bottleneck", bandwidth_kbps=800.0, queue_limit_packets=5),
    ]
    flow = Flow(packet_count=200, interval_ms=5.0, size_bytes=1000)
    events = simulate(flow, path=congested_path, seed=1)
    metrics = measure(events, packet_size_bytes=flow.size_bytes)

    assert abs(metrics.throughput_kbps - 800.0) <= 800.0 * 0.05
    q_drops = [e for e in events if e.type == "packet_dropped" and e.reason == "queue_full"]
    assert len(q_drops) > 0
    depths = [e.queue_depth for e in events if e.type == "packet_delivered" and e.queue_depth is not None]
    assert max(depths) > 0

    # Offered below cap: 1000 * 8 / 20 ms = 400 kbps < 800 kbps
    under_flow = Flow(packet_count=100, interval_ms=20.0, size_bytes=1000)
    under_events = simulate(under_flow, path=congested_path, seed=1)
    under_drops = [e for e in under_events if e.type == "packet_dropped"]
    assert len(under_drops) == 0


def test_gilbert_elliott_loss_rate_and_burst_length() -> None:
    p_g2b = 0.02
    p_b2g = 0.25
    loss_bad = 100.0
    gilbert_path = [
        Hop(
            name="isp",
            loss_model="gilbert",
            p_good_to_bad=p_g2b,
            p_bad_to_good=p_b2g,
            loss_good=0.0,
            loss_bad=loss_bad,
        )
    ]
    flow = Flow(packet_count=20000, interval_ms=1.0, size_bytes=64)
    events = simulate(flow, path=gilbert_path, seed=77)
    metrics = measure(events, packet_size_bytes=flow.size_bytes)

    theoretical_loss_pct = (p_g2b / (p_g2b + p_b2g)) * loss_bad
    assert abs(metrics.loss_pct - theoretical_loss_pct) <= 1.5

    dropped_seqs = sorted(e.seq for e in events if e.type == "packet_dropped")
    assert all(e.reason == "burst" for e in events if e.type == "packet_dropped")

    bursts: list[int] = []
    run = 1
    for idx in range(1, len(dropped_seqs)):
        if dropped_seqs[idx] == dropped_seqs[idx - 1] + 1:
            run += 1
        else:
            bursts.append(run)
            run = 1
    if dropped_seqs:
        bursts.append(run)

    mean_burst = sum(bursts) / len(bursts)
    expected_burst = 1.0 / p_b2g
    assert abs(mean_burst - expected_burst) <= expected_burst * 0.20

    # Compare against equal average random loss
    random_path = [Hop(name="isp", loss_pct=theoretical_loss_pct)]
    random_events = simulate(flow, path=random_path, seed=77)
    random_seqs = sorted(e.seq for e in random_events if e.type == "packet_dropped")
    r_bursts: list[int] = []
    r_run = 1
    for idx in range(1, len(random_seqs)):
        if random_seqs[idx] == random_seqs[idx - 1] + 1:
            r_run += 1
        else:
            r_bursts.append(r_run)
            r_run = 1
    if random_seqs:
        r_bursts.append(r_run)

    assert max(bursts) > max(r_bursts)


def test_event_bus_wildcard_typed_and_error_isolation() -> None:
    bus = EventBus()
    received_all: list[str] = []
    received_delivered: list[int] = []

    def bad_subscriber(_: Event) -> None:
        raise RuntimeError("boom")

    bus.subscribe("*", lambda e: received_all.append(e.type))
    bus.subscribe("packet_delivered", bad_subscriber)
    bus.subscribe("packet_delivered", lambda e: received_delivered.append(e.seq))

    events = simulate(Flow(packet_count=5, interval_ms=1.0), path=default_path(), seed=1)
    replay(events, bus)

    assert len(received_all) == len(events)
    assert received_delivered == [0, 1, 2, 3, 4]


def test_analyzer_healthy_flow_returns_empty() -> None:
    path = default_path(delay_ms=10.0)
    events = simulate(Flow(packet_count=50, interval_ms=10.0), path=path, seed=1)
    assert analyze(events, path) == []


def test_analyzer_all_findings_and_severities() -> None:
    # HIGH_DELAY warn (>150) & critical (>400)
    warn_delay_path = [Hop(name="wan", delay_ms=200.0)]
    f_warn = analyze(simulate(Flow(packet_count=20), path=warn_delay_path, seed=1), warn_delay_path)
    assert any(f.code == "HIGH_DELAY" and f.severity == "warn" and f.hop is None for f in f_warn)

    crit_delay_path = [Hop(name="wan", delay_ms=450.0)]
    f_crit = analyze(simulate(Flow(packet_count=20), path=crit_delay_path, seed=1), crit_delay_path)
    assert any(f.code == "HIGH_DELAY" and f.severity == "critical" and f.hop is None for f in f_crit)

    # HIGH_JITTER pins highest std-dev hop
    jitter_path = [
        Hop(name="ok", delay_ms=10.0, jitter_ms=5.0),
        Hop(name="shaky", delay_ms=100.0, jitter_ms=70.0),  # uniform std-dev ~ 70/sqrt(3) ≈ 40.4 > 30
    ]
    f_jit = analyze(simulate(Flow(packet_count=500, interval_ms=100.0), path=jitter_path, seed=5), jitter_path)
    assert any(f.code == "HIGH_JITTER" and f.severity == "warn" and f.hop == "shaky" for f in f_jit)

    crit_jitter_path = [Hop(name="terrible", delay_ms=200.0, jitter_ms=150.0)]  # std-dev ~ 86.6 > 75
    f_jit_c = analyze(simulate(Flow(packet_count=500, interval_ms=200.0), path=crit_jitter_path, seed=5), crit_jitter_path)
    assert any(f.code == "HIGH_JITTER" and f.severity == "critical" and f.hop == "terrible" for f in f_jit_c)

    # PACKET_LOSS pins hop
    loss_path = [Hop(name="clean"), Hop(name="dropper", loss_pct=8.0)]
    f_loss = analyze(simulate(Flow(packet_count=500), path=loss_path, seed=10), loss_path)
    assert any(f.code == "PACKET_LOSS" and f.severity == "critical" and f.hop == "dropper" for f in f_loss)

    # BURST_LOSS >= 3 warn, >= 8 critical
    burst_events = [
        Event("packet_sent", i, float(i), None) for i in range(20)
    ] + [
        Event("packet_dropped", i, float(i), "isp", reason="burst") for i in range(5, 8)
    ] + [
        Event("packet_delivered", i, float(i), "isp", delay_ms=0.0, total_latency_ms=0.0)
        for i in range(20)
        if i not in range(5, 8)
    ]
    f_burst_w = analyze(burst_events, [Hop(name="isp")])
    assert any(f.code == "BURST_LOSS" and f.severity == "warn" and f.hop == "isp" for f in f_burst_w)

    burst_events_crit = [
        Event("packet_sent", i, float(i), None) for i in range(20)
    ] + [
        Event("packet_dropped", i, float(i), "isp", reason="burst") for i in range(2, 11)
    ] + [
        Event("packet_delivered", i, float(i), "isp", delay_ms=0.0, total_latency_ms=0.0)
        for i in range(20)
        if i not in range(2, 11)
    ]
    f_burst_c = analyze(burst_events_crit, [Hop(name="isp")])
    assert any(f.code == "BURST_LOSS" and f.severity == "critical" and f.hop == "isp" for f in f_burst_c)

    # BANDWIDTH_CHOKE
    bw_path = [Hop(name="tight", bandwidth_kbps=200.0, queue_limit_packets=2)]
    f_bw = analyze(simulate(Flow(packet_count=100, interval_ms=5.0, size_bytes=1000), path=bw_path, seed=1), bw_path)
    assert any(f.code == "BANDWIDTH_CHOKE" and f.severity == "critical" and f.hop == "tight" for f in f_bw)

    # REORDERING
    reord_path = [Hop(name="j", delay_ms=50.0, jitter_ms=45.0)]
    f_reord = analyze(simulate(Flow(packet_count=100, interval_ms=1.0), path=reord_path, seed=17), reord_path)
    assert any(f.code == "REORDERING" and f.hop is None for f in f_reord)

    # Sorting: critical before warn
    severities = [f.severity for f in f_bw]
    rank = {"critical": 0, "warn": 1, "info": 2}
    assert [rank[s] for s in severities] == sorted(rank[s] for s in severities)
    assert "HIGH_DELAY" in THRESHOLDS
