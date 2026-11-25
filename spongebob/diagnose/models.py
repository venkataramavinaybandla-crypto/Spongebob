from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Outcome = Literal["ok", "timeout", "refused", "unreachable", "dns_error"]

ERROR_OUTCOMES: frozenset[Outcome] = frozenset({"refused", "unreachable", "dns_error"})

MAX_COUNT = 200
MIN_INTERVAL_MS = 100.0
MIN_TIMEOUT_MS = 100.0
MAX_TIMEOUT_MS = 5000.0
EARLY_ABORT_CONSECUTIVE_ERRORS = 3


@dataclass(frozen=True)
class Sample:
    """Single probe result with monotonic send timestamp, round-trip time, and outcome."""

    seq: int
    sent_at_ms: float
    rtt_ms: float | None
    outcome: Outcome


def validate_target(target: str, field_name: str = "host") -> str:
    """Validate that a target is a single non-empty host or hostname string."""
    if not isinstance(target, str):
        raise TypeError(f"{field_name} must be a string, got {type(target).__name__}")
    cleaned = target.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must be a non-empty string")
    if any(ch.isspace() or ch == "," for ch in cleaned):
        raise ValueError(f"{field_name} must be a single target without spaces or commas")
    return cleaned


def validate_port(port: int) -> int:
    """Validate that port is a single integer in 1..65535."""
    if isinstance(port, bool) or not isinstance(port, int):
        raise TypeError(f"port must be a single integer, got {type(port).__name__}")
    if port < 1 or port > 65535:
        raise ValueError(f"port must be between 1 and 65535, got {port}")
    return port


def _validate_finite_number(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a number, got {type(value).__name__}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be finite, got {value}")
    return result


def validate_probe_params(
    count: int,
    interval_ms: float,
    timeout_ms: float,
) -> tuple[int, float, float]:
    """Enforce safety limits for probe count, interval, and timeout."""
    if isinstance(count, bool) or not isinstance(count, int):
        raise TypeError(f"count must be an integer, got {type(count).__name__}")
    if count < 1 or count > MAX_COUNT:
        raise ValueError(f"count must be between 1 and {MAX_COUNT}, got {count}")

    interval = _validate_finite_number(interval_ms, "interval_ms")
    if interval < MIN_INTERVAL_MS:
        raise ValueError(f"interval_ms must be >= {MIN_INTERVAL_MS}, got {interval_ms}")

    timeout = _validate_finite_number(timeout_ms, "timeout_ms")
    if timeout < MIN_TIMEOUT_MS or timeout > MAX_TIMEOUT_MS:
        raise ValueError(
            f"timeout_ms must be between {MIN_TIMEOUT_MS} and {MAX_TIMEOUT_MS}, got {timeout_ms}"
        )

    return count, interval, timeout
