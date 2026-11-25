from __future__ import annotations

from spongebob.engine import Flow, Hop, simulate
from spongebob.meter import measure


def main() -> None:
    path = [
        Hop(name="client", delay_ms=5.0, jitter_ms=1.0, loss_pct=0.0),
        Hop(name="router", delay_ms=15.0, jitter_ms=5.0, loss_pct=2.0),
        Hop(name="isp", delay_ms=25.0, jitter_ms=8.0, loss_pct=3.0),
        Hop(name="server", delay_ms=5.0, jitter_ms=1.0, loss_pct=0.0),
    ]
    flow = Flow(packet_count=500, interval_ms=10.0, size_bytes=64)
    events = simulate(flow=flow, path=path, seed=42)
    metrics = measure(events, packet_size_bytes=flow.size_bytes)

    configured_delay = sum(h.delay_ms for h in path)
    configured_loss = (
        1.0 - (1.0 - 0.0) * (1.0 - 0.02) * (1.0 - 0.03) * (1.0 - 0.0)
    ) * 100.0
    configured_rate_kbps = (flow.size_bytes * 8.0) / flow.interval_ms

    print("Configured:")
    print(f"  packets={flow.packet_count} size_bytes={flow.size_bytes} interval_ms={flow.interval_ms}")
    print(f"  total_delay_ms={configured_delay:.2f} expected_loss_pct={configured_loss:.2f}% rate_kbps={configured_rate_kbps:.2f}")
    print("Measured:")
    print(f"  sent={metrics.sent} delivered={metrics.delivered} lost={metrics.lost} loss_pct={metrics.loss_pct:.2f}%")
    print(f"  loss_by_hop={metrics.loss_by_hop}")
    if metrics.latency_ms is not None:
        print(
            "  latency_ms="
            f"min:{metrics.latency_ms.min:.2f} "
            f"avg:{metrics.latency_ms.avg:.2f} "
            f"max:{metrics.latency_ms.max:.2f} "
            f"p95:{metrics.latency_ms.p95:.2f}"
        )
    else:
        print("  latency_ms=None")
    print(f"  jitter_ms={metrics.jitter_ms:.2f}" if metrics.jitter_ms is not None else "  jitter_ms=None")
    print(
        f"  jitter_mean_abs_ms={metrics.jitter_mean_abs_ms:.2f}"
        if metrics.jitter_mean_abs_ms is not None
        else "  jitter_mean_abs_ms=None"
    )
    print(f"  reordered={metrics.reordered} throughput_kbps={metrics.throughput_kbps:.2f}")


if __name__ == "__main__":
    main()
