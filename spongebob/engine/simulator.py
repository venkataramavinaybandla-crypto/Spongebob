from __future__ import annotations

import heapq
import random
from collections import deque
from typing import Iterable, Literal

from .models import DropReason, Event, Flow, Hop, Packet, default_path

_ActionKind = Literal["send", "arrive_hop", "finish_hop"]


class Simulator:
    """Deterministic discrete-event network impairment simulator on a virtual clock."""

    def __init__(self, path: Iterable[Hop] | None = None, seed: int | None = None) -> None:
        hops = list(default_path() if path is None else path)
        if not hops:
            raise ValueError("path must contain at least one hop")
        for hop in hops:
            if not isinstance(hop, Hop):
                raise TypeError(f"path elements must be Hop instances, got {type(hop).__name__}")
        self.path: tuple[Hop, ...] = tuple(hops)
        self.seed = seed

    def _sample_hop_delay(self, hop: Hop, rng: random.Random) -> float:
        if hop.jitter_ms == 0.0:
            return hop.delay_ms
        if hop.jitter_model == "uniform":
            offset = rng.uniform(-hop.jitter_ms, hop.jitter_ms)
        else:
            offset = rng.gauss(0.0, hop.jitter_ms)
        return max(0.0, hop.delay_ms + offset)

    def _should_drop_random(self, hop: Hop, rng: random.Random) -> bool:
        if hop.loss_pct <= 0.0:
            return False
        if hop.loss_pct >= 100.0:
            return True
        return rng.random() < (hop.loss_pct / 100.0)

    def _should_drop_gilbert(
        self, hop: Hop, hop_index: int, in_good_state: list[bool], rng: random.Random
    ) -> bool:
        if in_good_state[hop_index]:
            if hop.p_good_to_bad > 0.0 and rng.random() < hop.p_good_to_bad:
                in_good_state[hop_index] = False
        else:
            if hop.p_bad_to_good > 0.0 and rng.random() < hop.p_bad_to_good:
                in_good_state[hop_index] = True

        loss_pct = hop.loss_good if in_good_state[hop_index] else hop.loss_bad
        if loss_pct <= 0.0:
            return False
        if loss_pct >= 100.0:
            return True
        return rng.random() < (loss_pct / 100.0)

    def _check_loss(
        self, hop: Hop, hop_index: int, in_good_state: list[bool], rng: random.Random
    ) -> DropReason | None:
        if hop.loss_model == "random":
            return "random" if self._should_drop_random(hop, rng) else None
        return "burst" if self._should_drop_gilbert(hop, hop_index, in_good_state, rng) else None

    def run(self, flow: Flow) -> list[Event]:
        """Run a flow through the configured path and return chronological events."""
        if not isinstance(flow, Flow):
            raise TypeError(f"flow must be a Flow instance, got {type(flow).__name__}")

        rng = random.Random(self.seed)
        events: list[Event] = []
        queue: list[tuple[float, int, _ActionKind, Packet, int, float, int | None]] = []
        order = 0

        num_hops = len(self.path)
        in_good_state = [True] * num_hops
        link_free_time = [0.0] * num_hops
        queued_finish_times: list[deque[float]] = [deque() for _ in range(num_hops)]

        for seq in range(flow.packet_count):
            send_time_ms = seq * flow.interval_ms
            packet = Packet(seq=seq, size_bytes=flow.size_bytes, send_time_ms=send_time_ms)
            heapq.heappush(queue, (send_time_ms, order, "send", packet, 0, 0.0, None))
            order += 1

        last_hop_index = num_hops - 1

        while queue:
            time_ms, _, action, packet, hop_index, hop_delay, queue_depth = heapq.heappop(queue)

            if action == "send":
                events.append(
                    Event(
                        type="packet_sent",
                        seq=packet.seq,
                        time_ms=time_ms,
                        hop=None,
                    )
                )
                heapq.heappush(queue, (time_ms, order, "arrive_hop", packet, 0, 0.0, None))
                order += 1

            elif action == "arrive_hop":
                hop = self.path[hop_index]
                drop_reason = self._check_loss(hop, hop_index, in_good_state, rng)
                if drop_reason is not None:
                    events.append(
                        Event(
                            type="packet_dropped",
                            seq=packet.seq,
                            time_ms=time_ms,
                            hop=hop.name,
                            reason=drop_reason,
                        )
                    )
                    continue

                if hop.bandwidth_kbps is not None:
                    hop_queue = queued_finish_times[hop_index]
                    while hop_queue and hop_queue[0] <= time_ms:
                        hop_queue.popleft()
                    depth = len(hop_queue)
                    if hop.queue_limit_packets is not None and depth >= hop.queue_limit_packets:
                        events.append(
                            Event(
                                type="packet_dropped",
                                seq=packet.seq,
                                time_ms=time_ms,
                                hop=hop.name,
                                reason="queue_full",
                            )
                        )
                        continue
                    tx_time_ms = (packet.size_bytes * 8.0) / hop.bandwidth_kbps
                    start_tx = max(time_ms, link_free_time[hop_index])
                    finish_tx = start_tx + tx_time_ms
                    link_free_time[hop_index] = finish_tx
                    hop_queue.append(finish_tx)
                    serialization_delay = finish_tx - time_ms
                    applied_delay = serialization_delay + self._sample_hop_delay(hop, rng)
                    recorded_depth: int | None = depth
                else:
                    applied_delay = self._sample_hop_delay(hop, rng)
                    recorded_depth = None

                finish_time = time_ms + applied_delay
                heapq.heappush(
                    queue,
                    (finish_time, order, "finish_hop", packet, hop_index, applied_delay, recorded_depth),
                )
                order += 1

            elif action == "finish_hop":
                hop = self.path[hop_index]
                total_latency = time_ms - packet.send_time_ms
                if hop_index == last_hop_index:
                    events.append(
                        Event(
                            type="packet_delivered",
                            seq=packet.seq,
                            time_ms=time_ms,
                            hop=hop.name,
                            delay_ms=hop_delay,
                            total_latency_ms=total_latency,
                            queue_depth=queue_depth,
                        )
                    )
                else:
                    events.append(
                        Event(
                            type="packet_delayed",
                            seq=packet.seq,
                            time_ms=time_ms,
                            hop=hop.name,
                            delay_ms=hop_delay,
                            total_latency_ms=total_latency,
                            queue_depth=queue_depth,
                        )
                    )
                    heapq.heappush(
                        queue,
                        (time_ms, order, "arrive_hop", packet, hop_index + 1, 0.0, None),
                    )
                    order += 1

        return events


def simulate(
    flow: Flow,
    path: Iterable[Hop] | None = None,
    seed: int | None = None,
) -> list[Event]:
    """Convenience function to run a discrete-event simulation for a flow and path."""
    return Simulator(path=path, seed=seed).run(flow)
