from __future__ import annotations

from .adapter import AdapterResult, samples_to_events
from .models import (
    EARLY_ABORT_CONSECUTIVE_ERRORS,
    ERROR_OUTCOMES,
    MAX_COUNT,
    MAX_TIMEOUT_MS,
    MIN_INTERVAL_MS,
    MIN_TIMEOUT_MS,
    Outcome,
    Sample,
)
from .probes import probe_dns, probe_tcp

__all__ = [
    "AdapterResult",
    "EARLY_ABORT_CONSECUTIVE_ERRORS",
    "ERROR_OUTCOMES",
    "MAX_COUNT",
    "MAX_TIMEOUT_MS",
    "MIN_INTERVAL_MS",
    "MIN_TIMEOUT_MS",
    "Outcome",
    "Sample",
    "probe_dns",
    "probe_tcp",
    "samples_to_events",
]
