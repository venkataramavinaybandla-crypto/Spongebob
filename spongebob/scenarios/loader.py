from __future__ import annotations

import importlib.resources
import tomllib
from pathlib import Path
from typing import Any

from spongebob.engine.models import Flow, Hop

from .models import MAX_HOPS, MAX_PACKETS, MAX_SCENARIO_BYTES, Scenario

_TOP_LEVEL_KEYS = frozenset({"scenario", "flow", "hop"})
_SCENARIO_REQUIRED = frozenset({"name", "description"})
_FLOW_REQUIRED = frozenset({"packets", "interval_ms", "size_bytes"})
_FLOW_ALLOWED = _FLOW_REQUIRED | frozenset({"seed"})
_HOP_REQUIRED = frozenset({"name", "delay_ms", "jitter_ms", "loss_pct"})
_HOP_OPTIONAL = frozenset(
    {
        "jitter_model",
        "bandwidth_kbps",
        "queue_limit_packets",
        "loss_model",
        "p_good_to_bad",
        "p_bad_to_good",
        "loss_good",
        "loss_bad",
    }
)
_HOP_ALLOWED = _HOP_REQUIRED | _HOP_OPTIONAL


def _check_keys(
    table: dict[str, Any],
    section: str,
    required: frozenset[str],
    allowed: frozenset[str],
) -> None:
    for key in table:
        if key not in allowed:
            raise ValueError(f"Unknown key {key!r} in [{section}]")
    for req in sorted(required):
        if req not in table:
            raise ValueError(f"Missing required key {req!r} in [{section}]")


def _parse_scenario_dict(data: dict[str, Any]) -> Scenario:
    for key in data:
        if key not in _TOP_LEVEL_KEYS:
            raise ValueError(f"Unknown top-level key {key!r}")

    for req_section in ("scenario", "flow", "hop"):
        if req_section not in data:
            raise ValueError(f"Missing required section {req_section!r}")

    scen_tbl = data["scenario"]
    if not isinstance(scen_tbl, dict):
        raise ValueError("[scenario] must be a table")
    _check_keys(scen_tbl, "scenario", _SCENARIO_REQUIRED, _SCENARIO_REQUIRED)

    flow_tbl = data["flow"]
    if not isinstance(flow_tbl, dict):
        raise ValueError("[flow] must be a table")
    _check_keys(flow_tbl, "flow", _FLOW_REQUIRED, _FLOW_ALLOWED)

    packets = flow_tbl["packets"]
    if not isinstance(packets, bool) and isinstance(packets, int) and packets > MAX_PACKETS:
        raise ValueError(f"packets must be <= {MAX_PACKETS}, got {packets}")
    flow = Flow(
        packet_count=packets,
        interval_ms=flow_tbl["interval_ms"],
        size_bytes=flow_tbl["size_bytes"],
    )
    seed = flow_tbl.get("seed")

    hop_list = data["hop"]
    if not isinstance(hop_list, list) or not hop_list:
        raise ValueError("[[hop]] must be a non-empty array of tables")
    if len(hop_list) > MAX_HOPS:
        raise ValueError(f"scenario hops must be <= {MAX_HOPS}, got {len(hop_list)}")

    hops: list[Hop] = []
    for idx, hop_tbl in enumerate(hop_list):
        if not isinstance(hop_tbl, dict):
            raise ValueError(f"[[hop]] entry {idx} must be a table")
        _check_keys(hop_tbl, f"hop[{idx}]", _HOP_REQUIRED, _HOP_ALLOWED)
        hops.append(Hop(**hop_tbl))

    return Scenario(
        name=scen_tbl["name"],
        description=scen_tbl["description"],
        flow=flow,
        hops=tuple(hops),
        seed=seed,
    )


def loads_scenario(text: str) -> Scenario:
    """Parse and validate a scenario from a TOML string."""
    raw_bytes = text.encode("utf-8")
    if len(raw_bytes) > MAX_SCENARIO_BYTES:
        raise ValueError(
            f"Scenario size {len(raw_bytes)} bytes exceeds limit of {MAX_SCENARIO_BYTES} bytes"
        )
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid TOML: {exc}") from exc
    return _parse_scenario_dict(data)


def load_scenario(path: str | Path) -> Scenario:
    """Load and validate a scenario from a user-specified TOML file."""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Scenario file not found: {file_path}")
    size = file_path.stat().st_size
    if size > MAX_SCENARIO_BYTES:
        raise ValueError(
            f"Scenario file {file_path} ({size} bytes) exceeds limit of {MAX_SCENARIO_BYTES} bytes"
        )
    raw = file_path.read_bytes()
    if len(raw) > MAX_SCENARIO_BYTES:
        raise ValueError(
            f"Scenario file {file_path} ({len(raw)} bytes) exceeds limit of {MAX_SCENARIO_BYTES} bytes"
        )
    return loads_scenario(raw.decode("utf-8"))


def _toml_str(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def dump_scenario(scenario: Scenario) -> str:
    """Serialize a Scenario to deterministic TOML."""
    lines: list[str] = [
        "[scenario]",
        f"name = {_toml_str(scenario.name)}",
        f"description = {_toml_str(scenario.description)}",
        "",
        "[flow]",
        f"packets = {scenario.flow.packet_count}",
        f"interval_ms = {scenario.flow.interval_ms}",
        f"size_bytes = {scenario.flow.size_bytes}",
    ]
    if scenario.seed is not None:
        lines.append(f"seed = {scenario.seed}")

    for hop in scenario.hops:
        lines.extend(
            [
                "",
                "[[hop]]",
                f"name = {_toml_str(hop.name)}",
                f"delay_ms = {hop.delay_ms}",
                f"jitter_ms = {hop.jitter_ms}",
                f"loss_pct = {hop.loss_pct}",
                f"jitter_model = {_toml_str(hop.jitter_model)}",
            ]
        )
        if hop.bandwidth_kbps is not None:
            lines.append(f"bandwidth_kbps = {hop.bandwidth_kbps}")
        if hop.queue_limit_packets is not None:
            lines.append(f"queue_limit_packets = {hop.queue_limit_packets}")
        lines.extend(
            [
                f"loss_model = {_toml_str(hop.loss_model)}",
                f"p_good_to_bad = {hop.p_good_to_bad}",
                f"p_bad_to_good = {hop.p_bad_to_good}",
                f"loss_good = {hop.loss_good}",
                f"loss_bad = {hop.loss_bad}",
            ]
        )

    lines.append("")
    return "\n".join(lines)


def list_builtin_scenarios() -> list[str]:
    """Return sorted names of built-in scenarios (without .toml extension)."""
    root = importlib.resources.files("spongebob.scenarios.builtin")
    names = [
        entry.name[:-5]
        for entry in root.iterdir()
        if entry.name.endswith(".toml")
    ]
    return sorted(names)


def load_builtin_scenario(name: str) -> Scenario:
    """Load a built-in scenario by name using importlib.resources."""
    root = importlib.resources.files("spongebob.scenarios.builtin")
    target = root.joinpath(f"{name}.toml")
    if not target.is_file():
        available = ", ".join(list_builtin_scenarios())
        raise FileNotFoundError(
            f"Unknown built-in scenario {name!r}. Available: {available}"
        )
    return loads_scenario(target.read_text(encoding="utf-8"))
