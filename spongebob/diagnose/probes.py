from __future__ import annotations

import asyncio
import socket
import time
from collections.abc import Awaitable, Callable

from .models import (
    EARLY_ABORT_CONSECUTIVE_ERRORS,
    ERROR_OUTCOMES,
    Outcome,
    Sample,
    validate_port,
    validate_probe_params,
    validate_target,
)


async def _run_probe_loop(
    count: int,
    interval_ms: float,
    probe_once: Callable[[], Awaitable[tuple[Outcome, float | None]]],
) -> list[Sample]:
    """Execute a bounded probe sequence with monotonic timestamps and early error abort."""
    samples: list[Sample] = []
    consecutive_errors = 0

    for seq in range(count):
        start_s = time.monotonic()
        sent_at_ms = start_s * 1000.0
        outcome, rtt_ms = await probe_once()
        samples.append(
            Sample(
                seq=seq,
                sent_at_ms=sent_at_ms,
                rtt_ms=rtt_ms,
                outcome=outcome,
            )
        )

        if outcome in ERROR_OUTCOMES:
            consecutive_errors += 1
            if consecutive_errors >= EARLY_ABORT_CONSECUTIVE_ERRORS:
                break
        else:
            # Timeouts approximate packet loss, not errors, so they reset the error streak.
            consecutive_errors = 0

        if seq + 1 < count:
            elapsed_ms = (time.monotonic() - start_s) * 1000.0
            remaining_s = (interval_ms - elapsed_ms) / 1000.0
            if remaining_s > 0.0:
                await asyncio.sleep(remaining_s)

    return samples


async def probe_tcp(
    host: str,
    port: int = 443,
    count: int = 20,
    interval_ms: float = 200,
    timeout_ms: float = 1000,
) -> list[Sample]:
    """Time TCP connect round-trips to a single host:port without sending application data."""
    target = validate_target(host, "host")
    valid_port = validate_port(port)
    valid_count, valid_interval, valid_timeout = validate_probe_params(
        count, interval_ms, timeout_ms
    )
    timeout_s = valid_timeout / 1000.0

    async def _once() -> tuple[Outcome, float | None]:
        t0 = time.monotonic()
        try:
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, valid_port),
                timeout=timeout_s,
            )
            rtt_ms = (time.monotonic() - t0) * 1000.0
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return "ok", rtt_ms
        except (TimeoutError, asyncio.TimeoutError):
            return "timeout", None
        except ConnectionRefusedError:
            return "refused", None
        except socket.gaierror:
            return "dns_error", None
        except OSError:
            return "unreachable", None

    return await _run_probe_loop(valid_count, valid_interval, _once)


async def probe_dns(
    name: str,
    count: int = 20,
    interval_ms: float = 200,
    timeout_ms: float = 1000,
) -> list[Sample]:
    """Time system-resolver DNS lookups for a single target name."""
    target = validate_target(name, "name")
    valid_count, valid_interval, valid_timeout = validate_probe_params(
        count, interval_ms, timeout_ms
    )
    timeout_s = valid_timeout / 1000.0
    loop = asyncio.get_running_loop()

    async def _once() -> tuple[Outcome, float | None]:
        t0 = time.monotonic()
        try:
            await asyncio.wait_for(
                loop.getaddrinfo(target, None),
                timeout=timeout_s,
            )
            rtt_ms = (time.monotonic() - t0) * 1000.0
            return "ok", rtt_ms
        except (TimeoutError, asyncio.TimeoutError):
            return "timeout", None
        except socket.gaierror:
            return "dns_error", None
        except OSError:
            return "unreachable", None

    return await _run_probe_loop(valid_count, valid_interval, _once)
