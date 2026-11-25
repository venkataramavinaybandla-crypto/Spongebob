from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from spongebob.engine.models import Event, Hop
from spongebob.meter import measure

Severity = Literal["critical", "warn", "info"]

THRESHOLDS: dict[str, dict[str, float]] = {
    "HIGH_DELAY": {"warn": 150.0, "critical": 400.0},
    "HIGH_JITTER": {"warn": 30.0, "critical": 75.0},
    "PACKET_LOSS": {"warn": 1.0, "critical": 5.0},
    "BURST_LOSS": {"warn": 3.0, "critical": 8.0},
    "BANDWIDTH_CHOKE": {"queue_depth_warn": 5.0, "drop_pct_critical": 5.0},
    "REORDERING": {"warn": 1.0, "critical": 5.0},
}

_SEVERITY_ORDER: dict[Severity, int] = {
    "critical": 0,
    "warn": 1,
    "info": 2,
}


@dataclass(frozen=True)
class Finding:
    """Rule-based diagnostic finding produced by the analyzer."""

    code: str
    severity: Severity
    hop: str | None
    value: float
    threshold: float


def _longest_consecutive_run(seqs: list[int]) -> int:
    if not seqs:
        return 0
    ordered = sorted(set(seqs))
    longest = 1
    current = 1
    for idx in range(1, len(ordered)):
        if ordered[idx] == ordered[idx - 1] + 1:
            current += 1
            if current > longest:
                longest = current
        else:
            current = 1
    return longest


def analyze(events: Iterable[Event], path: Iterable[Hop]) -> list[Finding]:
    """Analyze simulation events against a path and return findings sorted by severity."""
    event_list = list(events)
    path_list = list(path)
    if not event_list or not path_list:
        return []

    metrics = measure(event_list)
    findings: list[Finding] = []

    delays_by_hop: dict[str, list[float]] = defaultdict(list)
    depths_by_hop: dict[str, list[int]] = defaultdict(list)
    drops_by_hop: dict[str, list[Event]] = defaultdict(list)

    for event in event_list:
        if event.hop is None:
            continue
        if event.type in ("packet_delayed", "packet_delivered"):
            if event.delay_ms is not None:
                delays_by_hop[event.hop].append(event.delay_ms)
            if event.queue_depth is not None:
                depths_by_hop[event.hop].append(event.queue_depth)
        elif event.type == "packet_dropped":
            drops_by_hop[event.hop].append(event)

    # 1. HIGH_DELAY (path-level)
    if metrics.latency_ms is not None:
        avg_delay = metrics.latency_ms.avg
        t_delay = THRESHOLDS["HIGH_DELAY"]
        if avg_delay > t_delay["critical"]:
            findings.append(
                Finding("HIGH_DELAY", "critical", None, avg_delay, t_delay["critical"])
            )
        elif avg_delay > t_delay["warn"]:
            findings.append(
                Finding("HIGH_DELAY", "warn", None, avg_delay, t_delay["warn"])
            )

    # 2. HIGH_JITTER (pin hop with highest delay std-dev)
    worst_jitter_hop: str | None = None
    worst_jitter_val = -1.0
    for hop in path_list:
        hop_delays = delays_by_hop.get(hop.name, [])
        if len(hop_delays) >= 2:
            std_dev = statistics.pstdev(hop_delays)
            if std_dev > worst_jitter_val:
                worst_jitter_val = std_dev
                worst_jitter_hop = hop.name
    if worst_jitter_hop is not None:
        t_jitter = THRESHOLDS["HIGH_JITTER"]
        if worst_jitter_val > t_jitter["critical"]:
            findings.append(
                Finding(
                    "HIGH_JITTER",
                    "critical",
                    worst_jitter_hop,
                    worst_jitter_val,
                    t_jitter["critical"],
                )
            )
        elif worst_jitter_val > t_jitter["warn"]:
            findings.append(
                Finding(
                    "HIGH_JITTER",
                    "warn",
                    worst_jitter_hop,
                    worst_jitter_val,
                    t_jitter["warn"],
                )
            )

    # Per-hop findings: PACKET_LOSS, BURST_LOSS, BANDWIDTH_CHOKE
    arrivals = metrics.sent
    t_loss = THRESHOLDS["PACKET_LOSS"]
    t_burst = THRESHOLDS["BURST_LOSS"]
    t_bw = THRESHOLDS["BANDWIDTH_CHOKE"]

    for hop in path_list:
        hop_drops = drops_by_hop.get(hop.name, [])
        drop_count = len(hop_drops)

        if arrivals > 0:
            loss_pct = (drop_count / arrivals) * 100.0
            if loss_pct > t_loss["critical"]:
                findings.append(
                    Finding("PACKET_LOSS", "critical", hop.name, loss_pct, t_loss["critical"])
                )
            elif loss_pct > t_loss["warn"]:
                findings.append(
                    Finding("PACKET_LOSS", "warn", hop.name, loss_pct, t_loss["warn"])
                )

        longest_burst = _longest_consecutive_run([e.seq for e in hop_drops])
        if longest_burst >= t_burst["critical"]:
            findings.append(
                Finding(
                    "BURST_LOSS",
                    "critical",
                    hop.name,
                    float(longest_burst),
                    t_burst["critical"],
                )
            )
        elif longest_burst >= t_burst["warn"]:
            findings.append(
                Finding(
                    "BURST_LOSS",
                    "warn",
                    hop.name,
                    float(longest_burst),
                    t_burst["warn"],
                )
            )

        queue_full_drops = sum(1 for e in hop_drops if e.reason == "queue_full")
        queue_full_pct = (queue_full_drops / arrivals * 100.0) if arrivals > 0 else 0.0
        hop_depths = depths_by_hop.get(hop.name, [])
        avg_depth = (sum(hop_depths) / len(hop_depths)) if hop_depths else 0.0

        if queue_full_pct > t_bw["drop_pct_critical"]:
            findings.append(
                Finding(
                    "BANDWIDTH_CHOKE",
                    "critical",
                    hop.name,
                    queue_full_pct,
                    t_bw["drop_pct_critical"],
                )
            )
        elif queue_full_drops > 0:
            findings.append(
                Finding(
                    "BANDWIDTH_CHOKE",
                    "warn",
                    hop.name,
                    float(queue_full_drops),
                    1.0,
                )
            )
        elif avg_depth > t_bw["queue_depth_warn"]:
            findings.append(
                Finding(
                    "BANDWIDTH_CHOKE",
                    "warn",
                    hop.name,
                    avg_depth,
                    t_bw["queue_depth_warn"],
                )
            )

        arrivals = max(0, arrivals - drop_count)

    # 6. REORDERING (path-level)
    if metrics.delivered > 0:
        reorder_pct = (metrics.reordered / metrics.delivered) * 100.0
        t_reorder = THRESHOLDS["REORDERING"]
        if reorder_pct > t_reorder["critical"]:
            findings.append(
                Finding("REORDERING", "critical", None, reorder_pct, t_reorder["critical"])
            )
        elif reorder_pct > t_reorder["warn"]:
            findings.append(
                Finding("REORDERING", "warn", None, reorder_pct, t_reorder["warn"])
            )

    findings.sort(key=lambda f: _SEVERITY_ORDER[f.severity])
    return findings
