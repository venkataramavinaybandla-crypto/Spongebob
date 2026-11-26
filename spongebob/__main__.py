from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from spongebob import __version__


def _add_export_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--export", default=None, help="Export report to .json, .csv, or .md")
    parser.add_argument("--events", action="store_true", help="Include raw events in JSON export")
    parser.add_argument(
        "--no-narrator",
        action="store_true",
        help="Omit mascot lines from output and export",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing export file",
    )


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
    parser.add_argument(
        "--plugins",
        default=None,
        help="Explicitly load data-only plugins from this directory",
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
    diag.add_argument("--plugins", default=None, help="Explicitly load plugins from this directory")
    diag.add_argument(
        "--export-downloads",
        nargs="?",
        const="md",
        default=None,
        choices=("md", "json", "csv"),
        help="Export report to the user's Downloads folder (md, json, or csv; default md)",
    )
    _add_export_flags(diag)

    run_p = subparsers.add_parser(
        "run",
        help="Run a scenario from a TOML file or built-in scenario name.",
    )
    run_p.add_argument("target", help="Path to a .toml scenario file or built-in scenario name")
    run_p.add_argument("--seed", type=int, default=None, help="Override scenario RNG seed")
    run_p.add_argument("--plugins", default=None, help="Explicitly load plugins from this directory")
    _add_export_flags(run_p)

    subparsers.add_parser(
        "scenarios",
        help="List built-in network impairment scenarios.",
    )

    plugins_p = subparsers.add_parser(
        "plugins",
        help="Validate and list data-only plugins inside a directory.",
    )
    plugins_p.add_argument("dir", help="Path to plugin folder or directory of plugin folders")
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
    from spongebob.narrator import MASCOT_NAME, Narrator
    from spongebob.plugins import PluginRegistry, load_plugins_from_dir

    plugins_dir = getattr(args, "plugins", None)
    registry = load_plugins_from_dir(plugins_dir) if plugins_dir else PluginRegistry()
    for pname, err in registry.errors:
        print(f"Skipped plugin {pname}: {err}", file=sys.stderr)

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
    narrator_inst = Narrator(
        extra_finding_pools=registry.finding_jokes or None,
        extra_drop_pools=registry.drop_jokes or None,
    )
    lines = narrator_inst.narrate(findings, metrics, adapted.events, mode="diagnose")

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

    if not getattr(args, "no_narrator", False):
        for line in lines:
            print(f"[{MASCOT_NAME}] {line.text}")

    if adapted.errors:
        for seg, err_samples in adapted.errors.items():
            outcomes = ", ".join(sorted({s.outcome for s in err_samples}))
            print(f"Errors on {seg}: {len(err_samples)} ({outcomes})")

    export_target = getattr(args, "export", None)
    export_dl_fmt = getattr(args, "export_downloads", None)
    if export_target or export_dl_fmt:
        from spongebob.export import ExportPayload, default_export_path, export_report

        payload = ExportPayload(
            source="diagnose",
            metrics=metrics,
            findings=findings,
            events=adapted.events,
            narrator_lines=tuple(lines),
            latency_kind="rtt",
            target_host=host,
            target_port=port,
            include_events=bool(args.events),
            include_narrator=not bool(args.no_narrator),
        )
        try:
            dest = (
                export_target
                if export_target
                else default_export_path(kind="diagnose", target=host, fmt=export_dl_fmt)
            )
            out_path = export_report(payload, dest, force=bool(args.force))
        except (ValueError, FileNotFoundError, FileExistsError, OSError) as exc:
            print(f"Export failed: {exc}", file=sys.stderr)
            return 2
        print(f"Exported report to {out_path}")

    return 0


def _run_scenario_cmd(args: argparse.Namespace) -> int:
    from pathlib import Path

    from spongebob.narrator import MASCOT_NAME, Narrator
    from spongebob.plugins import PluginRegistry, load_plugins_from_dir
    from spongebob.scenarios import load_builtin_scenario, load_scenario, run_scenario

    plugins_dir = getattr(args, "plugins", None)
    registry = load_plugins_from_dir(plugins_dir) if plugins_dir else PluginRegistry()
    for pname, err in registry.errors:
        print(f"Skipped plugin {pname}: {err}", file=sys.stderr)

    target = args.target
    target_path = Path(target)
    try:
        if target_path.is_file():
            scenario = load_scenario(target_path)
        elif target in registry.scenarios:
            scenario = registry.scenarios[target]
        elif target.endswith(".toml") or "\\" in target:
            scenario = load_scenario(target_path)
        else:
            scenario = load_builtin_scenario(target)
    except (FileNotFoundError, ValueError, TypeError) as exc:
        print(f"Error loading scenario: {exc}", file=sys.stderr)
        return 2

    res = run_scenario(scenario, seed=args.seed)
    narrator_inst = Narrator(
        extra_finding_pools=registry.finding_jokes or None,
        extra_drop_pools=registry.drop_jokes or None,
    )
    narrator_lines = narrator_inst.narrate(
        res.findings, res.metrics, res.events, seed=(scenario.seed if args.seed is None else args.seed)
    )
    m = res.metrics

    print(f"Scenario: {scenario.name}")
    print(f"Description: {scenario.description}")
    print(
        f"sent={m.sent} delivered={m.delivered} lost={m.lost} "
        f"loss_pct={m.loss_pct:.1f}%"
    )
    if m.latency_ms is not None:
        print(
            f"latency_ms: min={m.latency_ms.min:.2f} avg={m.latency_ms.avg:.2f} "
            f"max={m.latency_ms.max:.2f} p95={m.latency_ms.p95:.2f}"
        )
    else:
        print("latency_ms: n/a")

    jitter_str = f"{m.jitter_ms:.2f}" if m.jitter_ms is not None else "n/a"
    tp_str = f"{m.throughput_kbps:.2f} kbps" if m.throughput_kbps is not None else "n/a"
    print(f"jitter_ms={jitter_str} reordered={m.reordered} throughput={tp_str}")

    if res.findings:
        for finding in res.findings:
            hop_label = finding.hop if finding.hop is not None else "path"
            print(
                f"[{finding.severity.upper()}] {finding.code} hop={hop_label} "
                f"value={finding.value:.2f} (threshold={finding.threshold:.2f})"
            )
    else:
        print("Findings: none")

    if not getattr(args, "no_narrator", False):
        for line in narrator_lines:
            print(f"[{MASCOT_NAME}] {line.text}")

    if getattr(args, "export", None):
        from spongebob.export import ExportPayload, export_report

        payload = ExportPayload(
            source="simulation",
            metrics=res.metrics,
            findings=res.findings,
            events=res.events,
            narrator_lines=tuple(narrator_lines),
            scenario=scenario,
            latency_kind="one_way",
            include_events=bool(args.events),
            include_narrator=not bool(args.no_narrator),
        )
        try:
            out_path = export_report(payload, args.export, force=bool(args.force))
        except (ValueError, FileNotFoundError, FileExistsError, OSError) as exc:
            print(f"Export failed: {exc}", file=sys.stderr)
            return 2
        print(f"Exported report to {out_path}")

    return 0


def _list_scenarios_cmd() -> int:
    from spongebob.scenarios import list_builtin_scenarios, load_builtin_scenario

    for name in list_builtin_scenarios():
        sc = load_builtin_scenario(name)
        print(f"{name:<20} {sc.name} — {sc.description}")
    return 0


def _plugins_cmd(args: argparse.Namespace) -> int:
    from spongebob.plugins import load_plugins_from_dir

    registry = load_plugins_from_dir(args.dir)
    for plugin in registry.plugins:
        m = plugin.manifest
        if m.kind == "scenarios":
            count = len(plugin.scenarios)
            detail = f"{count} scenarios"
        elif m.kind == "jokes":
            count = sum(len(v) for v in plugin.finding_jokes.values()) + sum(
                len(v) for v in plugin.drop_jokes.values()
            )
            detail = f"{count} joke lines"
        else:
            count = len(plugin.theme_colors)
            detail = f"{count} color roles"
        print(f"{m.name} ({m.version}) [{m.kind}] - {detail}: {m.description}")
    for pname, err in registry.errors:
        print(f"ERROR {pname}: {err}", file=sys.stderr)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for Spongebob (Network Impairment Simulator)."""
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "diagnose":
        return _run_diagnose(args)
    if args.command == "run":
        return _run_scenario_cmd(args)
    if args.command == "scenarios":
        return _list_scenarios_cmd()
    if args.command == "plugins":
        return _plugins_cmd(args)

    from spongebob.ui.app import SimulatorApp

    SimulatorApp(plugins_dir=args.plugins).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
