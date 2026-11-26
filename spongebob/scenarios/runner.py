from __future__ import annotations

from spongebob.analyzer import analyze
from spongebob.engine import simulate
from spongebob.meter import measure
from spongebob.narrator import narrate

from .models import Scenario, ScenarioRunResult


def run_scenario(scenario: Scenario, seed: int | None = None) -> ScenarioRunResult:
    """Execute a Scenario through engine, meter, analyzer, and narrator."""
    effective_seed = scenario.seed if seed is None else seed
    events = simulate(flow=scenario.flow, path=scenario.hops, seed=effective_seed)
    metrics = measure(events, packet_size_bytes=scenario.flow.size_bytes)
    findings = analyze(events, scenario.hops)
    narrator_lines = narrate(findings, metrics, events, seed=effective_seed)
    return ScenarioRunResult(
        scenario=scenario,
        events=events,
        metrics=metrics,
        findings=findings,
        narrator_lines=narrator_lines,
    )
