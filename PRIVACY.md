# Privacy Policy — Spongebob

Spongebob (Network Impairment Simulator) is built for local, offline impairment simulation and bounded, user-confirmed diagnostics.

## What this software does NOT do
- **No telemetry:** Zero usage metrics, crash reports, or analytics are collected or transmitted.
- **No update checks:** The software never phones home to check for new versions.
- **Zero network calls in Simulate mode:** All packet flows, delays, jitter, packet loss, bandwidth caps, and diagnostic analyses run purely in-memory on a virtual clock.
- **No history or automatic disk writes:** Configurations, probe targets, event logs, metrics, findings, and narrator state live only in memory for the current session.

## Explicit file and network access
- **Diagnose mode:** Contacts only the single target host and port you explicitly type, and only after you confirm the consent prompt on every run. No application data is sent.
- **Scenarios and plugins:** Files are read only from paths you explicitly type or pass via CLI flags; no home or default directories are scanned.
- **Plugins are data-only:** Plugins are parsed as TOML data only and are never imported or executed as code.
- **Exports:** Files are written only when you explicitly request an export (`--export <path>`, `--export-downloads`, or UI **Export**), to that exact path only. Diagnose export suggests a file in your Downloads folder, shows the exact path first, and writes only after you confirm. Diagnose reports include the target host you typed, so share them with care.

## Dependencies
- The core simulation engine, meter, event bus, analyzer, narrator, diagnose probes, scenarios, export, and plugin loader use only the Python standard library.
- The terminal user interface uses one pinned third-party dependency: `textual==8.2.8`.

This software aims for maximum practical privacy rather than making an "absolute" privacy claim.
