from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from spongebob.engine.models import Event, Hop

from .models import ERROR_OUTCOMES, Sample


@dataclass(frozen=True)
class AdapterResult:
    """Adapted probe results ready for the meter, analyzer, and narrator pipeline."""

    events: list[Event]
    path: list[Hop]
    latency_kind: Literal["rtt"] = "rtt"
    errors: dict[str, list[Sample]] | None = None
    size_bytes: int = 0


def samples_to_events(results: Mapping[str, Sequence[Sample]]) -> AdapterResult:
    """Convert per-segment probe Samples into engine Events, a Hop path, and non-loss errors."""
    path: list[Hop] = [Hop(name="you")]
    errors: dict[str, list[Sample]] = {}
    probe_items: list[tuple[float, int, int, str, Sample]] = []

    for seg_idx, (segment_name, samples) in enumerate(results.items()):
        path.append(Hop(name=segment_name))
        for sample in samples:
            if sample.outcome in ERROR_OUTCOMES:
                errors.setdefault(segment_name, []).append(sample)
            else:
                probe_items.append(
                    (sample.sent_at_ms, seg_idx, sample.seq, segment_name, sample)
                )

    probe_items.sort(key=lambda item: (item[0], item[1], item[2]))

    events: list[Event] = []
    for seq, (_sent_at, _seg_idx, _orig_seq, segment_name, sample) in enumerate(probe_items):
        events.append(
            Event(
                type="packet_sent",
                seq=seq,
                time_ms=sample.sent_at_ms,
                hop="you",
            )
        )
        if sample.outcome == "ok":
            rtt = sample.rtt_ms if sample.rtt_ms is not None else 0.0
            events.append(
                Event(
                    type="packet_delivered",
                    seq=seq,
                    time_ms=sample.sent_at_ms + rtt,
                    hop=segment_name,
                    delay_ms=rtt,
                    total_latency_ms=rtt,
                )
            )
        elif sample.outcome == "timeout":
            events.append(
                Event(
                    type="packet_dropped",
                    seq=seq,
                    time_ms=sample.sent_at_ms,
                    hop=segment_name,
                    reason="timeout",
                )
            )

    events.sort(key=lambda e: (e.time_ms, 0 if e.type == "packet_sent" else 1, e.seq))

    return AdapterResult(
        events=events,
        path=path,
        latency_kind="rtt",
        errors=errors,
        size_bytes=0,
    )
