from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from spongebob import __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spongebob",
        description="Spongebob — Network Impairment Simulator for delay, jitter, and packet loss.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"spongebob {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command")
    diag = subparsers.add_parser(
        "diagnose",
        help="Probe a single user-specified target and analyze RTT, jitter, and timeouts.",
    )
    diag.add_argument("host", help="Single target hostname or IP address")
    diag.add_argument("--port", type=int, default=443, help="Single TCP port (1-65535)")
    diag.add_argument("--count", type=int, default=20, help="Probe count (1-200)")
    diag.add_argument(
        "--interval-ms",
        type=float,
        default=200.0,
        help="Interval between probes in ms (min 100)",
    )
    diag.add_argument(
        "--timeout-ms",
        type=float,
        default=1000.0,
        help="Per-probe timeout in ms (100-5000)",
    )
    diag.add_argument(
        "--dns",
        action="store_true",
        help="Also probe system DNS resolution before TCP connect",
    )
    return parser


def _run_diagnose(args: argparse.Namespace) -> int:
    from spongebob.analyzer import analyze
    from spongebob.diagnose import Sample, probe_dns, probe_tcp, samples_to_events
    from spongebob.diagnose.models import (
        validate_port,
        validate_probe_params,
        validate_target,
    )
    from spongebob.meter import measure
    from spongebob.narrator import MASCOT_NAME, narrate

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

    async def _run_all() -> dict[str, list[Sample]]:
        results: dict[str, list[Sample]] = {}
        if args.dns:
            results["dns"] = await probe_dns(
                host, count=count, interval_ms=interval_ms, timeout_ms=timeout_ms
            )
        results[f"tcp:{host}:{port}"] = await probe_tcp(
            host, port=port, count=count, interval_ms=interval_ms, timeout_ms=timeout_ms
        )
        return results

    results = asyncio.run(_run_all())
    adapted = samples_to_events(results)
    metrics = measure(adapted.events, packet_size_bytes=adapted.size_bytes)
    findings = analyze(adapted.events, adapted.path, latency_kind=adapted.latency_kind)
    lines = narrate(findings, metrics, adapted.events, mode="diagnose")

    print(
        f"sent={metrics.sent} delivered={metrics.delivered} lost={metrics.lost} "
        f"loss_pct={metrics.loss_pct:.1f}% (timeouts approximate packet loss)"
    )
    if metrics.latency_ms is not None:
        print(
            f"round-trip time (ms): min={metrics.latency_ms.min:.2f} "
            f"avg={metrics.latency_ms.avg:.2f} max={metrics.latency_ms.max:.2f} "
            f"p95={metrics.latency_ms.p95:.2f}"
        )
    else:
        print("round-trip time (ms): n/a")

    jitter_str = f"{metrics.jitter_ms:.2f}" if metrics.jitter_ms is not None else "n/a"
    throughput_str = (
        f"{metrics.throughput_kbps:.2f} kbps"
        if metrics.throughput_kbps is not None
        else "n/a"
    )
    print(f"jitter_ms={jitter_str} throughput={throughput_str}")

    if findings:
        for finding in findings:
            hop_label = finding.hop if finding.hop is not None else "path"
            print(
                f"[{finding.severity.upper()}] {finding.code} hop={hop_label} "
                f"value={finding.value:.2f} (threshold={finding.threshold:.2f})"
            )
    else:
        print("Findings: none")

    for line in lines:
        print(f"[{MASCOT_NAME}] {line.text}")

    if adapted.errors:
        for seg, err_samples in adapted.errors.items():
            outcomes = ", ".join(sorted({s.outcome for s in err_samples}))
            print(f"Errors on {seg}: {len(err_samples)} ({outcomes})")

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for Spongebob (Network Impairment Simulator)."""
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "diagnose":
        return _run_diagnose(args)

    from spongebob.ui.app import SimulatorApp

    SimulatorApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
