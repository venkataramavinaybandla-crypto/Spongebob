# Spongebob

An open-source, terminal-based **Network Impairment Simulator** for **delay**, **jitter**, and **packet loss**.

## Core Focus
Every feature in Spongebob centers on creating, measuring, or explaining the three core network impairments:
- **Delay:** Each packet waits a configured time at a hop before moving on.
- **Jitter:** That wait varies randomly packet to packet (uniform or normal distribution), which can cause packets to arrive out of order.
- **Packet Loss:** Packets are dropped at a hop (random percentage, Gilbert-Elliott bursty loss, or queue-full tail drops).

## Installation

Requires **Python 3.11+**.

From a local clone:

```bash
pipx install .
```

For development (editable install):

```bash
pipx install -e .
```

## Running

Launch the full terminal UI (opens the main menu):

```bash
spongebob
```

You can also run it as a Python module or check CLI flags:

```bash
spongebob --version
spongebob --help
python -m spongebob
python -m spongebob.engine
python -m spongebob.meter
python -m spongebob.analyzer
```

Run the test suite:

```bash
pytest -v
```

## Screens
- **Menu:** Keyboard-first launcher for Simulate, Visualize, Diagnose (`v0.2`, disabled), Narrator toggle (`on/off` for the current session), and Quit.
- **Simulate:** Configure flow parameters (packet count, interval, size, seed) and per-hop settings (`client`, `router`, `isp`, `server`) with live validation. Displays measured metrics, rule-based findings, and mascot narration. Press `V` to open the run in Visualize.
- **Visualize:** Full-terminal Braille living-pipe animation replaying events over the synchronous event bus, with bandwidth bottlenecks, queue pileups, distinct drop shatter effects, live telemetry, and a diagnostic scan pulse. Controls: `Space` pause/resume, `+`/`-` speed (`0.25x`–`8x`), `R` restart, `P` pulse, `Esc` back.

## Reading the Metrics (Plain Guide)
- **Sent / Delivered / Lost / Loss %:** How many packets entered the path, how many reached the end, and how many were dropped along the way.
- **Latency (`min`, `avg`, `max`, `p95`):** One-way travel time from send to delivery in milliseconds (`p95` means 95% of delivered packets arrived in this time or less).
- **Jitter:** How much packet-to-packet arrival timing wobbles (computed using the RFC 3550 smoothed jitter estimator and mean absolute delta).
- **Reordered:** How many packets arrived out of sequence order because later packets overtook earlier ones.
- **Throughput (`kbps`):** Effective delivery rate in kilobits per second across the flow duration.

## Privacy
No telemetry, no analytics, no update checks, zero network calls in simulation mode, and nothing written to disk by default. See [PRIVACY.md](PRIVACY.md) for full details.

## Roadmap
- **v0.1 (current):** Discrete-event engine, meter, synchronous event bus, rule-based analyzer, Textual UI + Braille visualizer, and rule-based mascot narrator.
- **v0.2:** Diagnose mode (probing user-supplied targets).
- **v0.3:** Scenario files, export, and plugins.
