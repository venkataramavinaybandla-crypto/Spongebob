# Privacy Policy — Spongebob

Spongebob (Network Impairment Simulator) is built for local, offline experimentation with simulated network impairments.

## What this software does NOT do
- **No telemetry:** Zero usage metrics, crash reports, or analytics are collected or transmitted.
- **No update checks:** The software never phones home to check for new versions.
- **No network calls in simulation mode:** All packet flows, delays, jitter, packet loss, bandwidth caps, and diagnostic analyses run purely in-memory on a virtual clock.
- **No disk writes by default:** Simulation configurations, event logs, metrics, findings, and narrator state live only in memory for the current session and are not saved to disk.

## Dependencies
- The core simulation engine, meter, event bus, analyzer, and narrator use only the Python standard library.
- The terminal user interface uses one pinned third-party dependency: `textual==8.2.8`.

## Future versions (v0.2+)
- Planned `Diagnose` mode (v0.2, currently disabled) will only contact network targets explicitly entered by the user.

This software aims for maximum practical privacy rather than making an "absolute" privacy claim.
