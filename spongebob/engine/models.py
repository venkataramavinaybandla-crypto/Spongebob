from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

JitterModel = Literal["uniform", "normal"]
LossModel = Literal["random", "gilbert"]
DropReason = Literal["random", "burst", "queue_full"]
EventType = Literal[
    "packet_sent",
    "packet_delayed",
    "packet_dropped",
    "packet_delivered",
]

DEFAULT_HOP_NAMES: tuple[str, ...] = ("client", "router", "isp", "server")


def _validate_non_negative_finite(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a number, got {type(value).__name__}")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{field_name} must be a finite non-negative number, got {value}")
    return result


def _validate_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer, got {type(value).__name__}")
    if value <= 0:
        raise ValueError(f"{field_name} must be a positive integer, got {value}")
    return value


@dataclass(frozen=True)
class Hop:
    """A single network hop with independent delay, jitter, loss, and bandwidth settings."""

    name: str
    delay_ms: float = 0.0
    jitter_ms: float = 0.0
    loss_pct: float = 0.0
    jitter_model: JitterModel = "uniform"
    bandwidth_kbps: float | None = None
    queue_limit_packets: int | None = None
    loss_model: LossModel = "random"
    p_good_to_bad: float = 0.0
    p_bad_to_good: float = 0.0
    loss_good: float = 0.0
    loss_bad: float = 100.0

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("hop name must be a non-empty string")
        object.__setattr__(
            self, "delay_ms", _validate_non_negative_finite(self.delay_ms, "delay_ms")
        )
        object.__setattr__(
            self, "jitter_ms", _validate_non_negative_finite(self.jitter_ms, "jitter_ms")
        )
        loss = _validate_non_negative_finite(self.loss_pct, "loss_pct")
        if loss > 100.0:
            raise ValueError(f"loss_pct must be between 0 and 100, got {self.loss_pct}")
        object.__setattr__(self, "loss_pct", loss)
        if self.jitter_model not in ("uniform", "normal"):
            raise ValueError(
                f"jitter_model must be 'uniform' or 'normal', got {self.jitter_model!r}"
            )
        if self.bandwidth_kbps is not None:
            bw = _validate_non_negative_finite(self.bandwidth_kbps, "bandwidth_kbps")
            if bw <= 0.0:
                raise ValueError(f"bandwidth_kbps must be > 0, got {self.bandwidth_kbps}")
            object.__setattr__(self, "bandwidth_kbps", bw)
        if self.queue_limit_packets is not None:
            _validate_positive_int(self.queue_limit_packets, "queue_limit_packets")
        if self.loss_model not in ("random", "gilbert"):
            raise ValueError(
                f"loss_model must be 'random' or 'gilbert', got {self.loss_model!r}"
            )
        for prob_field in ("p_good_to_bad", "p_bad_to_good"):
            prob = _validate_non_negative_finite(getattr(self, prob_field), prob_field)
            if prob > 1.0:
                raise ValueError(f"{prob_field} must be between 0 and 1, got {prob}")
            object.__setattr__(self, prob_field, prob)
        for pct_field in ("loss_good", "loss_bad"):
            pct = _validate_non_negative_finite(getattr(self, pct_field), pct_field)
            if pct > 100.0:
                raise ValueError(f"{pct_field} must be between 0 and 100, got {pct}")
            object.__setattr__(self, pct_field, pct)


@dataclass(frozen=True)
class Flow:
    """Definition of a packet stream to inject into a simulated path."""

    packet_count: int
    interval_ms: float = 10.0
    size_bytes: int = 64

    def __post_init__(self) -> None:
        _validate_positive_int(self.packet_count, "packet_count")
        object.__setattr__(
            self,
            "interval_ms",
            _validate_non_negative_finite(self.interval_ms, "interval_ms"),
        )
        _validate_positive_int(self.size_bytes, "size_bytes")


@dataclass(frozen=True)
class Packet:
    """A simulated packet carrying sequence number, size, and send timestamp."""

    seq: int
    size_bytes: int
    send_time_ms: float

    def __post_init__(self) -> None:
        if isinstance(self.seq, bool) or not isinstance(self.seq, int) or self.seq < 0:
            raise ValueError(f"seq must be a non-negative integer, got {self.seq}")
        _validate_positive_int(self.size_bytes, "size_bytes")
        object.__setattr__(
            self,
            "send_time_ms",
            _validate_non_negative_finite(self.send_time_ms, "send_time_ms"),
        )


@dataclass(frozen=True)
class Event:
    """Chronological simulation event record emitted by the engine."""

    type: EventType
    seq: int
    time_ms: float
    hop: str | None
    delay_ms: float | None = None
    total_latency_ms: float | None = None
    reason: DropReason | None = None
    queue_depth: int | None = None


def default_path(
    delay_ms: float = 0.0,
    jitter_ms: float = 0.0,
    loss_pct: float = 0.0,
    jitter_model: JitterModel = "uniform",
) -> list[Hop]:
    """Return the default 4-hop path (client, router, isp, server)."""
    return [
        Hop(
            name=name,
            delay_ms=delay_ms,
            jitter_ms=jitter_ms,
            loss_pct=loss_pct,
            jitter_model=jitter_model,
        )
        for name in DEFAULT_HOP_NAMES
    ]
