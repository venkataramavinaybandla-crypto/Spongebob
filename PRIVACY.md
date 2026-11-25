# Privacy Policy — Spongebob

Spongebob (Network Impairment Simulator) is built for local, offline impairment simulation and bounded, user-confirmed diagnostics.

## What this software does NOT do
- **No telemetry:** Zero usage metrics, crash reports, or analytics are collected or transmitted.
- **No update checks:** The software never phones home to check for new versions.
- **Zero network calls in Simulate mode:** All packet flows, delays, jitter, packet loss, bandwidth caps, and diagnostic analyses run purely in-memory on a virtual clock.
- **No history or disk writes:** Configurations, probe targets, event logs, metrics, findings, and narrator state live only in memory for the current session and are not saved to disk.

## Diagnose mode network behavior
- **User-confirmed targets only:** Diagnose mode contacts only the single target host and port you explicitly enter, and only after you confirm the consent prompt on every run.
- **No application payload:** TCP connect probes measure handshake round-trip time and close immediately without sending application data.

## Dependencies
- The core simulation engine, meter, event bus, analyzer, narrator, and diagnose probes use only the Python standard library.
- The terminal user interface uses one pinned third-party dependency: `textual==8.2.8`.

This software aims for maximum practical privacy rather than making an "absolute" privacy claim.
