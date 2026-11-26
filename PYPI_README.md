# Spongebob

Spongebob is an open-source, terminal-based **Network Impairment Simulator** focused on **Delay**, **Jitter**, and **Packet Loss**. Configure a multi-hop network path, inject controlled impairments into a simulated packet flow on a deterministic virtual clock, measure the resulting network metrics, and inspect rule-based findings and live terminal animations.

- **Delay:** Each packet waits a set time at a hop before moving on.
- **Jitter:** Wait times vary randomly per packet (uniform or normal), which can cause packets to arrive out of order.
- **Packet Loss:** Packets are dropped at a hop via random percentage, Gilbert-Elliott bursty loss, or queue-full tail drops under a bandwidth cap.

## Install

Requires **Python 3.11+**.

```bash
pipx install spongebob-cli
```

Or with pip:

```bash
pip install spongebob-cli
```

## Run

Launch the terminal UI:

```bash
spongebob
```

Headless CLI commands:

```bash
spongebob --version
spongebob scenarios
spongebob run <scenario-or-file.toml>
spongebob diagnose <host>
```

## Diagnose Mode Limits

Diagnose mode probes a single user-supplied target using bounded TCP connect timing (and optional system DNS resolution) and feeds samples into the meter, analyzer, narrator, and visualizer:

- Measures **round-trip time (RTT)**, not one-way delay.
- TCP connect timeouts **approximate packet loss**; they are not exact packet loss.
- Throughput is reported as `n/a`, and bandwidth choke or reordering findings are skipped.
- Enforces single target, single port (`1-65535`), max `200` probes, minimum `100 ms` interval, and `100-5000 ms` timeout.

## Privacy

- **Zero network calls in Simulate mode:** All simulation, measurement, and analysis run purely in-memory.
- **User-confirmed Diagnose targets only:** Contacts only the single host and port you enter, after explicit confirmation.
- **No telemetry or history:** Nothing is collected or saved automatically; exports write only to the exact path you confirm.
- **Data-only plugins:** Plugins are parsed as TOML data only and are never imported or executed as code.

Source code and full documentation: https://github.com/venkataramavinaybandla-crypto/Spongebob
