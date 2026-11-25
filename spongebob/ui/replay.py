from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from spongebob.analyzer import Finding
from spongebob.engine.models import DropReason, Event
from spongebob.meter import measure

_SEVERITY_RANK: dict[str, int] = {"critical": 0, "warn": 1, "info": 2}


@dataclass(frozen=True)
class ParticleState:
    """Visual state of an in-flight packet at virtual time t_ms."""

    seq: int
    x_norm: float
    hop_index: int
    jitter_offset: float


@dataclass(frozen=True)
class DropEffect:
    """Visual state of a recently dropped packet at virtual time t_ms."""

    seq: int
    hop_index: int
    reason: DropReason | None
    age_ms: float


@dataclass(frozen=True)
class PulseTarget:
    """Target hop and finding for the diagnostic scan pulse."""

    hop_name: str | None
    hop_index: int | None
    finding: Finding | None
    all_clear: bool


@dataclass(frozen=True)
class ReplayState:
    """Pure snapshot of the visualizer state at virtual time t_ms."""

    time_ms: float
    max_time_ms: float
    particles: tuple[ParticleState, ...]
    drops: tuple[DropEffect, ...]
    queue_depths: dict[str, int]
    sent: int
    delivered: int
    lost: int
    loss_pct: float
    latency_avg_ms: float | None
    jitter_ms: float | None
    reordered: int


def select_pulse_target(
    findings: Sequence[Finding], hop_names: Sequence[str]
) -> PulseTarget:
    """Pick the highest-severity finding's hop, or return all-clear when none."""
    if not findings:
        return PulseTarget(hop_name=None, hop_index=None, finding=None, all_clear=True)

    ordered = sorted(findings, key=lambda f: _SEVERITY_RANK.get(f.severity, 99))
    top = ordered[0]
    if top.hop is not None and top.hop in hop_names:
        return PulseTarget(
            hop_name=top.hop,
            hop_index=list(hop_names).index(top.hop),
            finding=top,
            all_clear=False,
        )

    # Path-level finding: stall at the end of the pipe if hops exist
    fallback_idx = len(hop_names) - 1 if hop_names else None
    return PulseTarget(
        hop_name=top.hop,
        hop_index=fallback_idx,
        finding=top,
        all_clear=False,
    )


def compute_replay_state(
    events: Sequence[Event],
    hop_names: Sequence[str],
    t_ms: float,
    drop_ttl_ms: float = 220.0,
) -> ReplayState:
    """Compute pure replay state at virtual time t_ms from a list of engine events."""
    if not events:
        return ReplayState(
            time_ms=t_ms,
            max_time_ms=0.0,
            particles=(),
            drops=(),
            queue_depths={name: 0 for name in hop_names},
            sent=0,
            delivered=0,
            lost=0,
            loss_pct=0.0,
            latency_avg_ms=None,
            jitter_ms=None,
            reordered=0,
        )

    max_time_ms = max(e.time_ms for e in events)
    num_hops = max(1, len(hop_names))
    hop_to_idx = {name: i for i, name in enumerate(hop_names)}

    # Group events per packet sequence number
    per_seq: dict[int, list[Event]] = {}
    for event in events:
        per_seq.setdefault(event.seq, []).append(event)

    particles: list[ParticleState] = []
    drops: list[DropEffect] = []
    queue_depths: dict[str, int] = {name: 0 for name in hop_names}

    for seq, seq_events in per_seq.items():
        seq_events.sort(key=lambda e: e.time_ms)
        send_ev = next((e for e in seq_events if e.type == "packet_sent"), None)
        if send_ev is None or t_ms < send_ev.time_ms:
            continue

        # Build hop traversal intervals: (hop_idx, start_t, end_t, event)
        last_t = send_ev.time_ms
        dropped_ev: Event | None = None
        delivered_ev: Event | None = None
        active_particle: ParticleState | None = None

        for ev in seq_events:
            if ev.type == "packet_sent":
                continue
            if ev.type == "packet_dropped":
                if ev.time_ms <= t_ms:
                    dropped_ev = ev
                break
            if ev.type in ("packet_delayed", "packet_delivered"):
                h_idx = hop_to_idx.get(ev.hop or "", 0)
                seg_start_t = last_t
                seg_end_t = ev.time_ms
                if seg_start_t <= t_ms < seg_end_t and seg_end_t > seg_start_t:
                    frac = (t_ms - seg_start_t) / (seg_end_t - seg_start_t)
                    x_norm = (h_idx + frac) / num_hops
                    wobble = ((seq % 5) - 2) * 0.15
                    active_particle = ParticleState(
                        seq=seq,
                        x_norm=max(0.0, min(1.0, x_norm)),
                        hop_index=h_idx,
                        jitter_offset=wobble,
                    )
                    if ev.hop in queue_depths and ev.queue_depth is not None:
                        queue_depths[ev.hop] = max(queue_depths[ev.hop], ev.queue_depth)
                    break
                last_t = seg_end_t
                if ev.type == "packet_delivered" and ev.time_ms <= t_ms:
                    delivered_ev = ev
                    if ev.hop in queue_depths and ev.queue_depth is not None:
                        queue_depths[ev.hop] = ev.queue_depth

        if dropped_ev is not None:
            age = t_ms - dropped_ev.time_ms
            if 0.0 <= age <= drop_ttl_ms:
                h_idx = hop_to_idx.get(dropped_ev.hop or "", 0)
                drops.append(
                    DropEffect(
                        seq=seq,
                        hop_index=h_idx,
                        reason=dropped_ev.reason,
                        age_ms=age,
                    )
                )
        elif active_particle is not None:
            particles.append(active_particle)
        elif delivered_ev is not None and t_ms - delivered_ev.time_ms <= 40.0:
            # Brief arrival flash at the end of the pipe
            particles.append(
                ParticleState(
                    seq=seq,
                    x_norm=1.0,
                    hop_index=num_hops - 1,
                    jitter_offset=0.0,
                )
            )

    events_up_to_t = [e for e in events if e.time_ms <= t_ms]
    live_metrics = measure(events_up_to_t)

    return ReplayState(
        time_ms=t_ms,
        max_time_ms=max_time_ms,
        particles=tuple(particles),
        drops=tuple(drops),
        queue_depths=queue_depths,
        sent=live_metrics.sent,
        delivered=live_metrics.delivered,
        lost=live_metrics.lost,
        loss_pct=live_metrics.loss_pct,
        latency_avg_ms=(
            live_metrics.latency_ms.avg if live_metrics.latency_ms is not None else None
        ),
        jitter_ms=live_metrics.jitter_ms,
        reordered=live_metrics.reordered,
    )
