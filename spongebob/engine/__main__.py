from __future__ import annotations

from .models import Flow, Hop
from .simulator import simulate


def main() -> None:
    path = [
        Hop(name="client", delay_ms=5.0, jitter_ms=1.0, loss_pct=0.0),
        Hop(name="router", delay_ms=15.0, jitter_ms=5.0, loss_pct=2.0),
        Hop(name="isp", delay_ms=25.0, jitter_ms=8.0, loss_pct=3.0),
        Hop(name="server", delay_ms=5.0, jitter_ms=1.0, loss_pct=0.0),
    ]
    flow = Flow(packet_count=100, interval_ms=10.0, size_bytes=64)
    events = simulate(flow=flow, path=path, seed=42)

    sent = sum(1 for event in events if event.type == "packet_sent")
    delivered = sum(1 for event in events if event.type == "packet_delivered")
    dropped = sum(1 for event in events if event.type == "packet_dropped")

    print(f"sent={sent} delivered={delivered} dropped={dropped}")


if __name__ == "__main__":
    main()
