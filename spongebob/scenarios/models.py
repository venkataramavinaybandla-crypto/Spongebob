from __future__ import annotations

from dataclasses import dataclass

from spongebob.analyzer import Finding
from spongebob.engine.models import Event, Flow, Hop
from spongebob.meter import Metrics
from spongebob.narrator import Line

MAX_SCENARIO_BYTES = 65_536
MAX_HOPS = 12
MAX_PACKETS = 100_000


@dataclass(frozen=True)
class Scenario:
    """Validated network impairment scenario definition."""

    name: str
    description: str
    flow: Flow
    hops: tuple[Hop, ...]
    seed: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("scenario name must be a non-empty string")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("scenario description must be a non-empty string")
        if not isinstance(self.flow, Flow):
            raise TypeError(f"flow must be a Flow, got {type(self.flow).__name__}")
        if self.flow.packet_count > MAX_PACKETS:
            raise ValueError(
                f"packets must be <= {MAX_PACKETS}, got {self.flow.packet_count}"
            )
        if not self.hops:
            raise ValueError("scenario must define at least one hop")
        if len(self.hops) > MAX_HOPS:
            raise ValueError(f"scenario hops must be <= {MAX_HOPS}, got {len(self.hops)}")
        for hop in self.hops:
            if not isinstance(hop, Hop):
                raise TypeError(f"hops must be Hop instances, got {type(hop).__name__}")
        if self.seed is not None and (isinstance(self.seed, bool) or not isinstance(self.seed, int)):
            raise TypeError(f"seed must be an integer or None, got {type(self.seed).__name__}")


@dataclass(frozen=True)
class ScenarioRunResult:
    """Full pipeline output from executing a Scenario."""

    scenario: Scenario
    events: list[Event]
    metrics: Metrics
    findings: list[Finding]
    narrator_lines: list[Line]
