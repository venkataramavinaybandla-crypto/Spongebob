from __future__ import annotations

from spongebob.analyzer import analyze
from spongebob.engine import Flow, Hop, simulate


def main() -> None:
    path = [
        Hop(name="client", delay_ms=10.0, jitter_ms=2.0),
        Hop(name="router", delay_ms=20.0, jitter_ms=45.0, bandwidth_kbps=40.0, queue_limit_packets=5),
        Hop(
            name="isp",
            delay_ms=160.0,
            loss_model="gilbert",
            p_good_to_bad=0.05,
            p_bad_to_good=0.2,
            loss_good=0.0,
            loss_bad=100.0,
        ),
        Hop(name="server", delay_ms=10.0),
    ]
    flow = Flow(packet_count=200, interval_ms=5.0, size_bytes=128)
    events = simulate(flow=flow, path=path, seed=42)
    findings = analyze(events, path)

    if not findings:
        print("No findings: path is healthy.")
        return

    for finding in findings:
        location = finding.hop if finding.hop is not None else "path"
        print(
            f"[{finding.severity.upper()}] {finding.code} hop={location} "
            f"value={finding.value:.2f} threshold={finding.threshold:.2f}"
        )


if __name__ == "__main__":
    main()
