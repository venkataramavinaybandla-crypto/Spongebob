# Spongebob Diagnose Report — 127.0.0.1:443

## Metrics

- **Sent:** 20
- **Delivered:** 0
- **Lost:** 20 (100.00%)
- **Latency (ms):** n/a
- **Jitter (RFC3550):** n/a
- **Reordered:** 0
- **Throughput:** n/a

## Findings

- **[CRITICAL] PACKET_LOSS** (tcp:127.0.0.1:443): 100.00 > 5.00
- **[CRITICAL] BURST_LOSS** (tcp:127.0.0.1:443): 20.00 > 8.00

## Wobbles the Sea Cucumber

- ALARM! tcp:127.0.0.1:443 is eating 100.0% of packets for breakfast!
- SEVERE RIPTIDE! tcp:127.0.0.1:443 wiped out 20.0 packets in a single streak!
- Crickets on the reef! tcp:127.0.0.1:443 left 20 probes knocking with no reply before the bell!
- End of the live check! 0/20 probes bounced back across the reef!

## Honest Limits

- Measurements reflect **round-trip time** (not one-way delay).
- TCP connect **timeouts approximate packet loss** and are not exact loss.
- Throughput is **n/a** because no application data is sent.
