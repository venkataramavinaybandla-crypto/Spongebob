import ast
import subprocess
from pathlib import Path

import pytest

from spongebob.analyzer import Finding
from spongebob.engine import Event
from spongebob.meter import LatencyStats, Metrics
from spongebob.narrator import (
    DROP_REASON_POOLS,
    FINDING_POOLS,
    HEALTHY_POOL,
    MASCOT_NAME,
    SUMMARY_POOL,
    Narrator,
    narrate,
)
from spongebob.ui.app import SimulatorApp

BANNED_NAMES = (
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

FINDING_CODES = (
    "HIGH_DELAY",
    "HIGH_JITTER",
    "PACKET_LOSS",
    "BURST_LOSS",
    "BANDWIDTH_CHOKE",
    "REORDERING",
)

NETWORK_MODULES = {
    "socket",
    "urllib",
    "http",
    "requests",
    "ftplib",
    "smtplib",
    "poplib",
    "imaplib",
    "aiohttp",
    "httpx",
    "websocket",
    "websockets",
}


def test_narrator_pool_sizes_fields_and_banned_names() -> None:
    assert len(HEALTHY_POOL) >= 10
    for code in FINDING_CODES:
        for severity in ("warn", "critical"):
            pool = FINDING_POOLS[(code, severity)]
            assert len(pool) >= 8, f"{code}/{severity} has fewer than 8 lines"
            assert len(set(pool)) == len(pool), f"Duplicate lines in {code}/{severity}"

    all_templates = (
        list(HEALTHY_POOL)
        + list(SUMMARY_POOL)
        + [t for p in DROP_REASON_POOLS.values() for t in p]
        + [t for p in FINDING_POOLS.values() for t in p]
    )

    assert all(banned not in MASCOT_NAME.lower() for banned in BANNED_NAMES)
    for tmpl in all_templates:
        rendered = tmpl.format(hop="router", value="42.0")
        assert "{hop}" not in rendered and "{value}" not in rendered
        lowered = tmpl.lower()
        for banned in BANNED_NAMES:
            assert banned not in lowered, f"Banned name {banned!r} found in {tmpl!r}"


def test_narrator_no_repeats_before_exhaustion_and_seed_determinism() -> None:
    metrics = Metrics(
        sent=100,
        delivered=100,
        lost=0,
        loss_pct=0.0,
        loss_by_hop={},
        latency_ms=LatencyStats(10.0, 10.0, 10.0, 10.0),
        jitter_ms=0.0,
        jitter_mean_abs_ms=0.0,
        reordered=0,
        throughput_kbps=50.0,
    )

    # Seed determinism
    l1 = narrate([], metrics, [], seed=42)
    l2 = narrate([], metrics, [], seed=42)
    l3 = narrate([], metrics, [], seed=99)
    assert l1 == l2
    assert l1 != l3

    # No repeats before exhaustion for HEALTHY_POOL (size 10)
    session = Narrator()
    seen_healthy: list[str] = []
    for i in range(len(HEALTHY_POOL)):
        lines = session.narrate([], metrics, [], seed=i)
        seen_healthy.append(lines[0].text)
    assert len(set(seen_healthy)) == len(HEALTHY_POOL)


def test_narrator_covers_every_finding_healthy_and_drop_reasons() -> None:
    metrics = Metrics(
        sent=100,
        delivered=90,
        lost=10,
        loss_pct=10.0,
        loss_by_hop={"isp": 10},
        latency_ms=LatencyStats(10.0, 200.0, 450.0, 400.0),
        jitter_ms=40.0,
        jitter_mean_abs_ms=35.0,
        reordered=5,
        throughput_kbps=40.0,
    )

    healthy_lines = narrate([], metrics, [], seed=1)
    assert len(healthy_lines) >= 1
    assert healthy_lines[0].tone == "calm"

    for code in FINDING_CODES:
        for severity in ("warn", "critical"):
            f = Finding(code=code, severity=severity, hop="isp", value=55.0, threshold=10.0)
            lines = narrate([f], metrics, [], seed=1)
            assert len(lines) >= 2
            expected_tone = "frantic" if severity == "critical" else "worried"
            assert lines[0].tone == expected_tone

    for reason in ("random", "burst", "queue_full"):
        ev = Event("packet_dropped", 1, 10.0, "router", reason=reason)  # type: ignore[arg-type]
        lines = narrate([], metrics, [ev], seed=1)
        assert any(line.tone == "chaotic" and line.hop == "router" for line in lines)


@pytest.mark.asyncio
async def test_narrator_toggle_in_menu_session_only() -> None:
    app = SimulatorApp()
    async with app.run_test(size=(100, 40)) as pilot:
        assert app.narrator_enabled is True
        await pilot.click("#btn-narrator-toggle")
        await pilot.pause()
        assert app.narrator_enabled is False
        await pilot.press("n")
        await pilot.pause()
        assert app.narrator_enabled is True


def test_privacy_guard_no_network_imports_or_file_writes_in_src() -> None:
    src_root = Path("spongebob")
    allowed_network_file = Path("spongebob", "diagnose", "probes.py")
    allowed_in_probes = {"socket"}
    export_dir = Path("spongebob", "export")

    for py_file in src_root.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        is_probes = py_file == allowed_network_file
        is_export = export_dir in py_file.parents
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if is_probes and top in allowed_in_probes:
                        continue
                    assert top not in NETWORK_MODULES, f"Network import {top} in {py_file}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                if is_probes and top in allowed_in_probes:
                    continue
                assert top not in NETWORK_MODULES, f"Network import {top} in {py_file}"
            elif isinstance(node, ast.Call) and not is_export:
                if isinstance(node.func, ast.Name) and node.func.id == "open":
                    # Disallow write/append/exclusive modes
                    for arg in node.args[1:2]:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            assert not any(m in arg.value for m in ("w", "a", "x", "+")), (
                                f"File write mode in {py_file}"
                            )
                elif isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in ("write_text", "write_bytes"), (
                        f"Path write call in {py_file}"
                    )


def test_release_guard_no_private_files_tracked_in_git() -> None:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        pytest.skip("git not available")
        return

    if res.returncode != 0 or res.stdout.strip() != "true":
        pytest.skip("not inside a git repository")
        return

    ls = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = set(ls.stdout.splitlines())
    forbidden = {
        "agents.md",
        "architecture.json",
        "memory.md",
        "context.md",
        "workflows.md",
        "persona_maaaaa.txt",
    }
    for path in tracked:
        assert path not in forbidden, f"Forbidden private file tracked: {path}"
        assert not path.lower().startswith("pre-requirements/"), (
            f"Forbidden directory tracked: {path}"
        )
