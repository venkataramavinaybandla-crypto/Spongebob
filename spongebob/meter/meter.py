from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from spongebob.engine.models import Event


@dataclass(frozen=True)
class LatencyStats:
    """Summary statistics for one-way packet latency in milliseconds."""

    min: float
    avg: float
    max: float
    p95: float


@dataclass(frozen=True)
class Metrics:
    """Measured network impairment metrics computed from engine events."""

    sent: int
    delivered: int
    lost: int
    loss_pct: float
    loss_by_hop: dict[str, int]
    latency_ms: LatencyStats | None
    jitter_ms: float | None
    jitter_mean_abs_ms: float | None
    reordered: int
    throughput_kbps: float | None


def _percentile_95(sorted_values: list[float]) -> float:
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    pos = 0.95 * (n - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def measure(events: Iterable[Event], packet_size_bytes: int = 64) -> Metrics:
    """Compute delivery, loss, latency, jitter, reordering, and throughput metrics."""
    if isinstance(packet_size_bytes, bool) or not isinstance(packet_size_bytes, int) or packet_size_bytes < 0:
        raise ValueError(f"packet_size_bytes must be a non-negative integer, got {packet_size_bytes}")

    sent = 0
    delivered_events: list[Event] = []
    loss_by_hop: dict[str, int] = {}
    first_send_time_ms: float | None = None

    for event in events:
        if event.type == "packet_sent":
            sent += 1
            if first_send_time_ms is None or event.time_ms < first_send_time_ms:
                first_send_time_ms = event.time_ms
        elif event.type == "packet_dropped":
            if event.hop is not None:
                loss_by_hop[event.hop] = loss_by_hop.get(event.hop, 0) + 1
        elif event.type == "packet_delivered":
            delivered_events.append(event)

    delivered = len(delivered_events)
    lost = sum(loss_by_hop.values()) if sent == 0 else max(0, sent - delivered)
    loss_pct = (lost / sent * 100.0) if sent > 0 else 0.0

    if delivered == 0:
        return Metrics(
            sent=sent,
            delivered=0,
            lost=lost,
            loss_pct=loss_pct,
            loss_by_hop=loss_by_hop,
            latency_ms=None,
            jitter_ms=None,
            jitter_mean_abs_ms=None,
            reordered=0,
            throughput_kbps=None if packet_size_bytes == 0 else 0.0,
        )

    delivered_events.sort(key=lambda e: e.time_ms)

    latencies = [
        e.total_latency_ms if e.total_latency_ms is not None else 0.0
        for e in delivered_events
    ]
    sorted_latencies = sorted(latencies)
    latency_stats = LatencyStats(
        min=sorted_latencies[0],
        avg=sum(latencies) / delivered,
        max=sorted_latencies[-1],
        p95=_percentile_95(sorted_latencies),
    )

    jitter_ms = 0.0
    if delivered >= 2:
        abs_deltas: list[float] = []
        for idx in range(1, delivered):
            delta = abs(latencies[idx] - latencies[idx - 1])
            jitter_ms += (delta - jitter_ms) / 16.0
            abs_deltas.append(delta)
        jitter_mean_abs_ms = sum(abs_deltas) / len(abs_deltas)
    else:
        jitter_mean_abs_ms = 0.0

    reordered = 0
    max_seq_seen = -1
    for event in delivered_events:
        if event.seq < max_seq_seen:
            reordered += 1
        else:
            max_seq_seen = event.seq

    last_delivery_time_ms = delivered_events[-1].time_ms
    if packet_size_bytes == 0:
        throughput_kbps: float | None = None
    elif first_send_time_ms is not None and last_delivery_time_ms > first_send_time_ms:
        duration_ms = last_delivery_time_ms - first_send_time_ms
        throughput_kbps = (delivered * packet_size_bytes * 8.0) / duration_ms
    else:
        throughput_kbps = 0.0

    return Metrics(
        sent=sent,
        delivered=delivered,
        lost=lost,
        loss_pct=loss_pct,
        loss_by_hop=loss_by_hop,
        latency_ms=latency_stats,
        jitter_ms=jitter_ms,
        jitter_mean_abs_ms=jitter_mean_abs_ms,
        reordered=reordered,
        throughput_kbps=throughput_kbps,
    )
