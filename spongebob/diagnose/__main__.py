from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from .models import (
    EARLY_ABORT_CONSECUTIVE_ERRORS,
    ERROR_OUTCOMES,
    Sample,
    validate_port,
    validate_probe_params,
    validate_target,
)
from .probes import probe_tcp


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m spongebob.diagnose",
        description="Run bounded TCP connect probes against a single user-specified target.",
    )
    parser.add_argument("host", help="Single target hostname or IP address")
    parser.add_argument("--port", type=int, default=443, help="Single TCP port (1-65535)")
    parser.add_argument("--count", type=int, default=20, help="Probe count (1-200)")
    parser.add_argument(
        "--interval-ms",
        type=float,
        default=200.0,
        help="Interval between probes in ms (min 100)",
    )
    parser.add_argument(
        "--timeout-ms",
        type=float,
        default=1000.0,
        help="Per-probe connect timeout in ms (100-5000)",
    )
    return parser


def format_summary(samples: list[Sample], requested_count: int) -> str:
    """Format raw probe counts and RTT min/avg/max summary."""
    ok_count = sum(1 for s in samples if s.outcome == "ok")
    timeout_count = sum(1 for s in samples if s.outcome == "timeout")
    error_count = sum(1 for s in samples if s.outcome in ERROR_OUTCOMES)
    rtts = [s.rtt_ms for s in samples if s.rtt_ms is not None]

    lines: list[str] = []
    if (
        len(samples) < requested_count
        and len(samples) >= EARLY_ABORT_CONSECUTIVE_ERRORS
        and all(s.outcome in ERROR_OUTCOMES for s in samples[-EARLY_ABORT_CONSECUTIVE_ERRORS:])
    ):
        lines.append(
            f"Aborted early after {EARLY_ABORT_CONSECUTIVE_ERRORS} consecutive errors "
            f"(last: {samples[-1].outcome})."
        )

    lines.append(f"ok={ok_count} timeout={timeout_count} errors={error_count}")
    if rtts:
        lines.append(
            f"rtt_ms: min={min(rtts):.2f} avg={sum(rtts) / len(rtts):.2f} max={max(rtts):.2f}"
        )
    else:
        lines.append("rtt_ms: none")
    lines.append(
        "Note: RTT is round-trip time; TCP connect timeouts approximate packet loss and are not exact loss."
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        host = validate_target(args.host, "host")
        port = validate_port(args.port)
        count, interval_ms, timeout_ms = validate_probe_params(
            args.count, args.interval_ms, args.timeout_ms
        )
    except (TypeError, ValueError) as exc:
        print(f"Invalid arguments: {exc}", file=sys.stderr)
        return 2

    try:
        answer = input(f"This will contact {host}:{port} {count} times. Continue? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        return 0

    if answer.strip().lower() != "y":
        print("Aborted.")
        return 0

    samples = asyncio.run(
        probe_tcp(
            host=host,
            port=port,
            count=count,
            interval_ms=interval_ms,
            timeout_ms=timeout_ms,
        )
    )
    print(format_summary(samples, count))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
