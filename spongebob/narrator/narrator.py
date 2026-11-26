from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

MASCOT_NAME = "Wobbles the Sea Cucumber"

BANNED_NAMES: tuple[str, ...] = (
    "spongebob",
    "bikini bottom",
    "krusty krab",
    "patrick",
    "squidward",
    "sandy cheeks",
    "plankton",
    "mr. krabs",
    "gary",
    "finding nemo",
    "dory",
    "ariel",
    "sebastian",
    "flounder",
)

HEALTHY_POOL: tuple[str, ...] = (
    "Wiggle-tastic! Every packet glided through like a happy sea cucumber at {value}!",
    "Zero drama on the reef today—{hop} is smoother than polished kelp!",
    "All clear! Not a single dropped shell or wobbly current in sight!",
    "Totally fine, probably—actually, no, it's genuinely pristine! Smooth sailing!",
    "My antennae say: zero congestion, zero panic, 100% ocean breeze!",
    "Packets arrived in neat little rows like synchronized krill!",
    "No bumps, no tangles, no crabby queues—just pure aquatic zen!",
    "If networks were tide pools, this one would win Best Behavior!",
    "Everything arrived right on cue! Even the pickiest starfish would approve!",
    "Smooth currents from end to end—my sea-cucumber heart is beaming!",
)

SUMMARY_POOL: tuple[str, ...] = (
    "Run complete! {value} packets made it across the reef—every packet is an adventure!",
    "Splashdown! {value} deliveries logged and counted by my squishy flippers!",
    "That's a wrap on the tide! {value} packets reached the far shore!",
    "Wiggle-tastic finish! {value} packets completed their underwater voyage!",
    "End of the current! {value} packets checked in at the destination!",
    "Bubbles up! The flow wrapped with {value} deliveries!",
)

DIAGNOSE_SUMMARY_POOL: tuple[str, ...] = (
    "Live reef check done! {value} probes made the round trip without getting lost at sea!",
    "Diagnose swim complete—{value} round-trip replies surfaced from the far shore!",
    "Probe patrol reporting back: {value} handshakes came home safely!",
    "My antennae tallied the live tide: {value} probes completed the round trip!",
    "End of the live check! {value} probes bounced back across the reef!",
    "Flipper-count complete! {value} probes answered the knock on the ocean floor!",
)

DROP_REASON_POOLS: dict[str, tuple[str, ...]] = {
    "random": (
        "Oops! A stray current at {hop} gently misplaced {value} packets—totally normal reef weather!",
        "Random sea-foam ate {value} packets near {hop}, but the rest are swimming strong!",
        "A passing jellyfish bumped {hop} and {value} packets drifted off course!",
        "Mystery bubbles at {hop} vanished {value} packets into the deep blue!",
        "Coin-flip currents at {hop} claimed {value} packets—keep paddling!",
        "Just a tiny bit of ocean static at {hop}: {value} packets wandered off!",
    ),
    "burst": (
        "Whoa! A whole school of {value} packets vanished together in a burst at {hop}!",
        "A sudden riptide at {hop} swept away {value} packets in one big gulp!",
        "Burst alert! {hop} blinked and {value} consecutive packets went sightseeing!",
        "Hold onto your tentacles—{hop} hit a kelp-tangle burst and lost {value} packets!",
        "A grumpy tide-wave at {hop} swallowed {value} packets back-to-back!",
        "Clump-o-rama! {value} packets took an unscheduled detour together at {hop}!",
    ),
    "queue_full": (
        "The waiting room at {hop} overflowed—{value} packets got bounced at the door!",
        "Too many swimmers in the narrow tube at {hop}! {value} packets spilled out!",
        "Queue jam at {hop}! {value} packets couldn't squeeze into the buffer!",
        "Full house at {hop}! {value} latecomers had to turn around!",
        "The bottle-neck at {hop} backed up and tail-dropped {value} packets!",
        "No more standing room at {hop}—{value} packets were politely turned away!",
    ),
    "timeout": (
        "Crickets on the reef! {hop} left {value} probes knocking with no reply before the bell!",
        "Knock-knock at {hop}—{value} probes waited until the tide clock ran out!",
        "No wave back from {hop}: {value} probes timed out in the deep blue!",
        "The seashell phone at {hop} rang and rang—{value} probes timed out!",
        "Radio silence near {hop}! {value} probes never heard a bubble back in time!",
        "Sleepy currents at {hop} let {value} probes time out without a handshake!",
        "Still waiting on {hop}—{value} probes swam past the timeout buoy!",
        "Ghost town at {hop}! {value} probes got zero answer before the whistle blew!",
    ),
}

FINDING_POOLS: dict[tuple[str, str], tuple[str, ...]] = {
    ("HIGH_DELAY", "warn"): (
        "Packets are taking a scenic {value} ms cruise across {hop}—maybe they stopped for kelp snacks!",
        "A little sluggish at {value} ms on {hop}, like a sleepy sea turtle!",
        "Delay is {value} ms across {hop}—not late, just fashionably unhurried!",
        "The current is thick today: {value} ms average trip over {hop}!",
        "Packets are paddling through molasses at {value} ms on {hop}!",
        "Slow-motion swim! {hop} clocked {value} ms—plenty of time to admire the coral!",
        "Warming up the flippers: {value} ms one-way delay across {hop}!",
        "A leisurely {value} ms drift on {hop}—hope nobody is waiting for a snappy ping!",
    ),
    ("HIGH_DELAY", "critical"): (
        "WHOA! {value} ms on {hop}?! Those packets are practically hibernating in a trench!",
        "MAJOR LAG! {value} ms across {hop}—a glacier swims faster than this!",
        "DEEP-SEA FREEZE! {hop} is dragging packets through {value} ms of mud!",
        "ALERT! {value} ms delay on {hop}—even a barnacle could outrun that!",
        "CRITICAL CRAWL! {value} ms on {hop}—packets are aging like driftwood!",
        "SOS FROM THE TRENCH! {value} ms one-way latency on {hop}!",
        "MEGA-STRETCH! {hop} is holding packets hostage for {value} ms!",
        "TURTLE OVERDRIVE! {value} ms across {hop} is way past nap time!",
    ),
    ("HIGH_JITTER", "warn"): (
        "Wobbly currents at {hop}! Delay std-dev is {value} ms—every packet has its own rhythm!",
        "Chaotic wiggly waves at {hop} ({value} ms spread)—who needs steady timing anyway?",
        "Jitterbugs spotted at {hop}! {value} ms wobble in the travel times!",
        "Some packets sprint, some stroll at {hop}—{value} ms of pure unpredictability!",
        "The metronome at {hop} is tipsy: {value} ms jitter!",
        "Up, down, sideways—{hop} is bouncing packet delays by {value} ms!",
        "Choppy surface at {hop} with {value} ms jitter—hold onto your shell!",
        "A little sea-sick at {hop}: {value} ms delay variance!",
    ),
    ("HIGH_JITTER", "critical"): (
        "WHIRLPOOL! {hop} is thrashing delays by {value} ms—total timing chaos!",
        "CRITICAL WOBBLE! {value} ms jitter at {hop}—packets don't know which tide it is!",
        "MAELSTROM AT {hop}! {value} ms std-dev is scrambling the whole stream!",
        "EXTREME TURBULENCE! {hop} is tossing packets around with {value} ms jitter!",
        "ABYSSALQUAKE! {value} ms jitter at {hop}—steady clocks need not apply!",
        "WILD RIDE AT {hop}! {value} ms of pure, unfiltered delay whiplash!",
        "PANIC IN THE KELP! {hop} jitter spiked to {value} ms!",
        "SPIN CYCLE! {hop} is churning delays by {value} ms!",
    ),
    ("PACKET_LOSS", "warn"): (
        "A few nibbles at {hop}: {value}% of packets went missing—probably fine!",
        "Tiny leak in the hull at {hop}: {value}% packet loss!",
        "{hop} misplaced {value}% of the swimmers—check under the rocks!",
        "Gentle scatter at {hop}: {value}% loss, plenty still made it!",
        "Sea-gulls got {value}% of the packets passing {hop}!",
        "Mild packet evaporation at {hop}: {value}%!",
        "{hop} has a {value}% drip—time to patch that coral pipe!",
        "A cheeky {value}% loss rate at {hop}—keep swimming!",
    ),
    ("PACKET_LOSS", "critical"): (
        "BLACK HOLE AT {hop}! {value}% of packets vanished into the abyss!",
        "MAYDAY! {hop} is devouring {value}% of the flow!",
        "CRITICAL LEAK! {value}% packet loss at {hop}—the pipe has a giant hole!",
        "SINKING SHIP! {hop} dropped {value}% of everything that touched it!",
        "ALARM! {hop} is eating {value}% of packets for breakfast!",
        "TIDAL DISASTER! {value}% loss at {hop}—barely anything gets through!",
        "RED ALERT AT {hop}! {value}% of the fleet is gone!",
        "GIANT CRAB ON THE LINE! {hop} snipped {value}% of all packets!",
    ),
    ("BURST_LOSS", "warn"): (
        "Consecutive {value}-packet hiccup at {hop}—a little clump went missing!",
        "{hop} sneezed and dropped {value} packets in a row!",
        "Mini-riptide at {hop}: {value} back-to-back packets vanished!",
        "A {value}-packet gap appeared at {hop}—must've been a passing whale!",
        "Clumpy loss at {hop}: {value} sequential packets took a break!",
        "Burst-o-meter tingled at {hop} with {value} consecutive drops!",
        "{hop} blinked for {value} packets straight!",
        "A neat little {value}-packet hole punched out at {hop}!",
    ),
    ("BURST_LOSS", "critical"): (
        "MASSIVE BLACKOUT AT {hop}! {value} packets in a row just disappeared!",
        "CRITICAL BURST! {hop} went dark for {value} consecutive packets!",
        "GIANT SQUID ATTACK! {value} back-to-back packets vanished at {hop}!",
        "CHASM AT {hop}! {value} sequential packets fell into the trench!",
        "SEVERE RIPTIDE! {hop} wiped out {value} packets in a single streak!",
        "TOTAL BLINKOUT! {value} consecutive drops at {hop}!",
        "MEGA-CLUMP LOSS! {hop} swallowed {value} packets without pausing!",
        "EMERGENCY! {hop} lost {value} packets straight—check the reef!",
    ),
    ("BANDWIDTH_CHOKE", "warn"): (
        "Squeeze play at {hop}! Queue is backing up ({value}) in the narrow pipe!",
        "Traffic jam forming at {hop} ({value})—too many packets, tiny straw!",
        "{hop} is puffing its cheeks—queue/drops hit {value}!",
        "Bottleneck alert at {hop}: {value} piling up behind the cap!",
        "Single-file swimming at {hop}—{value} waiting in line!",
        "Narrow coral tunnel at {hop} caused {value} congestion!",
        "A bit cramped at {hop}: {value} queued or bumped!",
        "Slow-funnel at {hop} ({value})—packets are bumper-to-bumper!",
    ),
    ("BANDWIDTH_CHOKE", "critical"): (
        "GRIDLOCK AT {hop}! {value}% queue-full drops—the pipe is bursting!",
        "CRITICAL CHOKE! {hop} is overflowing with {value}% tail-drops!",
        "TINY STRAW EXPLOSION! {hop} rejected {value}% of packets at the queue!",
        "CLOGGED REEF! {hop} hit {value}% queue-full loss—nothing fits!",
        "MEGA-BOTTLENECK! {value}% of packets bounced off {hop}'s full buffer!",
        "OVERFLOW PANIC AT {hop}! {value}% dropped because the queue is packed!",
        "TRAFFIC APOCALYPSE! {hop} spilled {value}% from an overstuffed queue!",
        "NO ROOM IN THE OCEAN! {hop} tail-dropped {value}%!",
    ),
    ("REORDERING", "warn"): (
        "Leapfrog! {value}% of packets arrived out of order across {hop}!",
        "Musical chairs on {hop}: {value}% of packets overtook their friends!",
        "A little queue-jumping ({value}%) along {hop}!",
        "Fast swimmers passed slow swimmers: {value}% reordered on {hop}!",
        "Sequence shuffle! {value}% of deliveries on {hop} swapped places!",
        "Playful dolphins nudged {value}% of packets out of order on {hop}!",
        "Mild scramble: {value}% reordering detected on {hop}!",
        "Packets playing tag on {hop}—{value}% arrived ahead of earlier seqs!",
    ),
    ("REORDERING", "critical"): (
        "TOTAL SCRAMBLE! {value}% of packets arrived out of order on {hop}!",
        "CHAOS CONGA LINE! {value}% reordering across {hop}!",
        "BLENDER MODE! {hop} tossed {value}% of packets into a salad!",
        "CRITICAL SHUFFLE! {value}% of deliveries on {hop} overtook each other!",
        "BACKWARDS SWIM! {value}% reordering on {hop}—sequence numbers are dizzy!",
        "STAMPEDE! {value}% of packets scrambled past each other on {hop}!",
        "ANARCHY IN THE PIPE! {value}% out-of-order arrivals on {hop}!",
        "WHIRLPOOL SHUFFLE! {hop} scrambled {value}% of the stream!",
    ),
}


@dataclass(frozen=True)
class Line:
    """A single mascot narration line."""

    text: str
    tone: str
    hop: str | None


class Narrator:
    """Rule-based mascot narrator with weighted selection and no-repeat session memory."""

    def __init__(
        self,
        extra_finding_pools: Mapping[tuple[str, str], Sequence[str]] | None = None,
        extra_drop_pools: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        self._used: dict[str, set[int]] = {}
        self._extra_finding_pools: dict[tuple[str, str], tuple[str, ...]] = (
            {k: tuple(v) for k, v in extra_finding_pools.items()}
            if extra_finding_pools
            else {}
        )
        self._extra_drop_pools: dict[str, tuple[str, ...]] = (
            {k: tuple(v) for k, v in extra_drop_pools.items()}
            if extra_drop_pools
            else {}
        )

    def reset(self) -> None:
        """Clear no-repeat memory for a fresh session."""
        self._used.clear()

    def _pick(self, pool_key: str, pool: Sequence[str], rng: random.Random) -> str:
        used = self._used.setdefault(pool_key, set())
        available = [i for i in range(len(pool)) if i not in used]
        if not available:
            used.clear()
            available = list(range(len(pool)))
        # Weighted toward earlier (punchier) lines while still covering the whole pool
        weights = [max(1, len(pool) - idx) for idx in available]
        chosen_idx = rng.choices(available, weights=weights, k=1)[0]
        used.add(chosen_idx)
        return pool[chosen_idx]

    def narrate(
        self,
        findings: Sequence[Any],
        metrics: Any | None,
        events: Sequence[Any] | None = None,
        seed: int | None = None,
        mode: str = "simulate",
    ) -> list[Line]:
        """Produce mascot narration lines for findings, drop reasons, and summary."""
        rng = random.Random(seed)
        lines: list[Line] = []

        if not findings:
            template = self._pick("healthy", HEALTHY_POOL, rng)
            delivered = getattr(metrics, "delivered", 0) if metrics is not None else 0
            lines.append(
                Line(
                    text=template.format(hop="the path", value=f"{delivered} packets"),
                    tone="calm",
                    hop=None,
                )
            )
        else:
            for finding in findings:
                code = getattr(finding, "code", "")
                severity = getattr(finding, "severity", "warn")
                hop = getattr(finding, "hop", None)
                value = getattr(finding, "value", 0.0)
                base_pool = FINDING_POOLS.get((code, severity))
                extra_pool = self._extra_finding_pools.get((code, severity), ())
                if base_pool is None and not extra_pool:
                    continue
                pool = tuple(base_pool or ()) + extra_pool
                template = self._pick(f"{code}:{severity}", pool, rng)
                hop_label = hop if hop is not None else "the path"
                tone = "frantic" if severity == "critical" else "worried"
                lines.append(
                    Line(
                        text=template.format(hop=hop_label, value=f"{value:.1f}"),
                        tone=tone,
                        hop=hop,
                    )
                )

        if events:
            drop_counts: dict[tuple[str, str | None], int] = {}
            for ev in events:
                if getattr(ev, "type", None) == "packet_dropped":
                    reason = getattr(ev, "reason", None)
                    if reason in DROP_REASON_POOLS:
                        key = (reason, getattr(ev, "hop", None))
                        drop_counts[key] = drop_counts.get(key, 0) + 1
            for (reason, hop), count in drop_counts.items():
                pool = DROP_REASON_POOLS[reason] + self._extra_drop_pools.get(reason, ())
                template = self._pick(f"drop:{reason}", pool, rng)
                lines.append(
                    Line(
                        text=template.format(hop=hop or "the path", value=str(count)),
                        tone="chaotic",
                        hop=hop,
                    )
                )

        if metrics is not None:
            delivered = getattr(metrics, "delivered", 0)
            sent = getattr(metrics, "sent", 0)
            if mode == "diagnose":
                summary_tmpl = self._pick("diagnose_summary", DIAGNOSE_SUMMARY_POOL, rng)
            else:
                summary_tmpl = self._pick("summary", SUMMARY_POOL, rng)
            lines.append(
                Line(
                    text=summary_tmpl.format(hop="the path", value=f"{delivered}/{sent}"),
                    tone="upbeat",
                    hop=None,
                )
            )

        return lines


def narrate(
    findings: Sequence[Any],
    metrics: Any | None,
    events: Sequence[Any] | None = None,
    seed: int | None = None,
    mode: str = "simulate",
) -> list[Line]:
    """Stateless convenience wrapper around Narrator.narrate()."""
    return Narrator().narrate(findings, metrics, events, seed=seed, mode=mode)
