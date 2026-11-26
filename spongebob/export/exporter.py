from __future__ import annotations

import csv
import ctypes
import io
import json
import os
import re
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from spongebob import __version__
from spongebob.analyzer import Finding
from spongebob.engine.models import Event
from spongebob.meter import Metrics
from spongebob.narrator import MASCOT_NAME, Line
from spongebob.scenarios.models import Scenario

SUPPORTED_EXTENSIONS = (".json", ".csv", ".md")
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_DOWNLOADS_FOLDER_GUID = uuid.UUID("{374DE290-123F-4565-9164-39C4925E467B}")


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _uuid_to_guid(uid: uuid.UUID) -> _GUID:
    data = uid.bytes_le
    guid = _GUID()
    ctypes.memmove(ctypes.byref(guid), data, 16)
    return guid


def get_downloads_dir() -> Path:
    """Resolve the user's Downloads folder without creating directories."""
    if sys.platform == "win32":
        ptr = ctypes.c_wchar_p()
        guid = _uuid_to_guid(_DOWNLOADS_FOLDER_GUID)
        shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
        ole32 = ctypes.windll.ole32  # type: ignore[attr-defined]
        hr = shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(ptr))
        try:
            if hr != 0 or not ptr.value:
                raise FileNotFoundError("Could not resolve Windows Downloads folder.")
            downloads = Path(ptr.value)
        finally:
            if ptr.value is not None:
                ole32.CoTaskMemFree(ptr)
    else:
        downloads = Path.home() / "Downloads"

    if not downloads.is_dir():
        raise FileNotFoundError(f"Downloads folder does not exist: {downloads}")
    return downloads


def _sanitize_target(target: str) -> str:
    cleaned = re.sub(r"[^a-z0-9.-]", "_", target.lower())
    while ".." in cleaned:
        cleaned = cleaned.replace("..", "_")
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = re.sub(r"-+", "-", cleaned)
    cleaned = cleaned.lstrip(".")
    cleaned = cleaned[:60].rstrip(".")
    return cleaned or "target"


def default_export_path(
    kind: str = "diagnose",
    target: str = "target",
    fmt: str = "md",
) -> Path:
    """Build a collision-free default export path inside the user's Downloads folder."""
    ext = fmt.lstrip(".").lower()
    if f".{ext}" not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(SUPPORTED_EXTENSIONS)
        raise ValueError(f"Unsupported export format {fmt!r}. Supported: {supported}")

    downloads = get_downloads_dir()
    safe_kind = _sanitize_target(kind)
    safe_target = _sanitize_target(target)
    stem = f"spongebob-{safe_kind}-{safe_target}"

    candidate = downloads / f"{stem}.{ext}"
    suffix_num = 2
    while candidate.exists():
        candidate = downloads / f"{stem}-{suffix_num}.{ext}"
        suffix_num += 1
    return candidate


@dataclass(frozen=True)
class ExportPayload:
    """Data bundle exported to JSON, CSV, or Markdown."""

    source: Literal["simulation", "diagnose"]
    metrics: Metrics
    findings: list[Finding]
    events: list[Event]
    narrator_lines: tuple[Line, ...] = ()
    scenario: Scenario | None = None
    latency_kind: Literal["one_way", "rtt"] = "one_way"
    target_host: str | None = None
    target_port: int | None = None
    include_events: bool = False
    include_narrator: bool = True


def _escape_csv_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return f"'{text}"
    return text


def _scenario_to_dict(scenario: Scenario) -> dict[str, Any]:
    return {
        "name": scenario.name,
        "description": scenario.description,
        "flow": {
            "packets": scenario.flow.packet_count,
            "interval_ms": scenario.flow.interval_ms,
            "size_bytes": scenario.flow.size_bytes,
            "seed": scenario.seed,
        },
        "hops": [asdict(h) for h in scenario.hops],
    }


def _metrics_to_dict(metrics: Metrics) -> dict[str, Any]:
    return {
        "sent": metrics.sent,
        "delivered": metrics.delivered,
        "lost": metrics.lost,
        "loss_pct": metrics.loss_pct,
        "loss_by_hop": dict(metrics.loss_by_hop),
        "latency_ms": asdict(metrics.latency_ms) if metrics.latency_ms is not None else None,
        "jitter_ms": metrics.jitter_ms,
        "jitter_mean_abs_ms": metrics.jitter_mean_abs_ms,
        "reordered": metrics.reordered,
        "throughput_kbps": metrics.throughput_kbps,
    }


def render_json(payload: ExportPayload) -> str:
    """Render ExportPayload as deterministic JSON."""
    data: dict[str, Any] = {
        "schema": 1,
        "spongebob_version": __version__,
        "source": payload.source,
        "scenario": _scenario_to_dict(payload.scenario) if payload.scenario is not None else None,
        "metrics": _metrics_to_dict(payload.metrics),
        "findings": [asdict(f) for f in payload.findings],
    }
    if payload.source == "diagnose":
        data["latency_kind"] = payload.latency_kind
        data["target"] = {
            "host": payload.target_host,
            "port": payload.target_port,
        }
    if payload.include_narrator:
        data["narrator"] = [asdict(line) for line in payload.narrator_lines]
    if payload.include_events:
        data["events"] = [asdict(ev) for ev in payload.events]
    return json.dumps(data, indent=2) + "\n"


def render_csv(payload: ExportPayload) -> str:
    """Render per-packet CSV with formula-injection escaping."""
    per_seq: dict[int, list[Event]] = {}
    for ev in payload.events:
        per_seq.setdefault(ev.seq, []).append(ev)

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["seq", "send_time_ms", "outcome", "latency_ms", "drop_hop", "drop_reason"])

    for seq in sorted(per_seq):
        seq_events = per_seq[seq]
        send_ev = next((e for e in seq_events if e.type == "packet_sent"), None)
        deliv_ev = next((e for e in seq_events if e.type == "packet_delivered"), None)
        drop_ev = next((e for e in seq_events if e.type == "packet_dropped"), None)

        send_time = send_ev.time_ms if send_ev is not None else ""
        if deliv_ev is not None:
            outcome = "delivered"
            latency = deliv_ev.total_latency_ms if deliv_ev.total_latency_ms is not None else ""
            drop_hop = ""
            drop_reason = ""
        elif drop_ev is not None:
            outcome = "dropped"
            latency = ""
            drop_hop = _escape_csv_cell(drop_ev.hop or "")
            drop_reason = _escape_csv_cell(drop_ev.reason or "")
        else:
            outcome = "sent"
            latency = ""
            drop_hop = ""
            drop_reason = ""

        writer.writerow([seq, send_time, outcome, latency, drop_hop, drop_reason])

    return buf.getvalue()


def render_markdown(payload: ExportPayload) -> str:
    """Render ExportPayload as a readable Markdown report."""
    lines: list[str] = []
    if payload.scenario is not None:
        lines.append(f"# Spongebob Report — {payload.scenario.name}")
        lines.append("")
        lines.append(payload.scenario.description)
    elif payload.target_host is not None:
        port_part = f":{payload.target_port}" if payload.target_port is not None else ""
        lines.append(f"# Spongebob Diagnose Report — {payload.target_host}{port_part}")
    else:
        lines.append("# Spongebob Report")

    m = payload.metrics
    if payload.source == "simulation" and payload.scenario is not None:
        cfg_delay = sum(h.delay_ms for h in payload.scenario.hops)
        cfg_jitter = max(h.jitter_ms for h in payload.scenario.hops)
        survive = 1.0
        for h in payload.scenario.hops:
            survive *= 1.0 - (h.loss_pct / 100.0)
        cfg_loss = (1.0 - survive) * 100.0

        meas_delay = f"{m.latency_ms.avg:.2f} ms" if m.latency_ms is not None else "n/a"
        meas_jitter = f"{m.jitter_ms:.2f} ms" if m.jitter_ms is not None else "n/a"
        meas_loss = f"{m.loss_pct:.2f}%"

        lines.extend(
            [
                "",
                "## Configured vs Measured",
                "",
                "| Metric | Configured | Measured |",
                "| --- | --- | --- |",
                f"| DELAY (avg) | {cfg_delay:.2f} ms | {meas_delay} |",
                f"| JITTER (max hop / RFC3550) | {cfg_jitter:.2f} ms | {meas_jitter} |",
                f"| LOSS | {cfg_loss:.2f}% | {meas_loss} |",
            ]
        )

    lines.extend(["", "## Metrics", ""])
    lines.append(f"- **Sent:** {m.sent}")
    lines.append(f"- **Delivered:** {m.delivered}")
    lines.append(f"- **Lost:** {m.lost} ({m.loss_pct:.2f}%)")
    if m.latency_ms is not None:
        lat_label = "Round-trip time" if payload.latency_kind == "rtt" else "Latency"
        lines.append(
            f"- **{lat_label} (ms):** min={m.latency_ms.min:.2f}, "
            f"avg={m.latency_ms.avg:.2f}, max={m.latency_ms.max:.2f}, p95={m.latency_ms.p95:.2f}"
        )
    else:
        lines.append("- **Latency (ms):** n/a")
    jit_str = f"{m.jitter_ms:.2f} ms" if m.jitter_ms is not None else "n/a"
    lines.append(f"- **Jitter (RFC3550):** {jit_str}")
    lines.append(f"- **Reordered:** {m.reordered}")
    tp_str = f"{m.throughput_kbps:.2f} kbps" if m.throughput_kbps is not None else "n/a"
    lines.append(f"- **Throughput:** {tp_str}")

    lines.extend(["", "## Findings", ""])
    if payload.findings:
        for f in payload.findings:
            hop_label = f.hop if f.hop is not None else "path"
            lines.append(
                f"- **[{f.severity.upper()}] {f.code}** ({hop_label}): "
                f"{f.value:.2f} > {f.threshold:.2f}"
            )
    else:
        lines.append("- None.")

    if payload.include_narrator:
        lines.extend(["", f"## {MASCOT_NAME}", ""])
        if payload.narrator_lines:
            for nl in payload.narrator_lines:
                lines.append(f"- {nl.text}")
        else:
            lines.append("- None.")

    if payload.source == "diagnose":
        lines.extend(
            [
                "",
                "## Honest Limits",
                "",
                "- Measurements reflect **round-trip time** (not one-way delay).",
                "- TCP connect **timeouts approximate packet loss** and are not exact loss.",
                "- Throughput is **n/a** because no application data is sent.",
            ]
        )

    lines.append("")
    return "\n".join(lines)


def render_export(payload: ExportPayload, extension: str) -> str:
    """Render payload according to file extension (.json, .csv, .md)."""
    ext = extension.lower()
    if ext == ".json":
        return render_json(payload)
    if ext == ".csv":
        return render_csv(payload)
    if ext == ".md":
        return render_markdown(payload)
    supported = ", ".join(SUPPORTED_EXTENSIONS)
    raise ValueError(f"Unsupported export format {extension!r}. Supported: {supported}")


def export_report(
    payload: ExportPayload,
    path: str | Path,
    force: bool = False,
) -> Path:
    """Atomically write an export report to the exact user-specified path."""
    out_path = Path(path)
    ext = out_path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(SUPPORTED_EXTENSIONS)
        raise ValueError(f"Unsupported export format {out_path.suffix!r}. Supported: {supported}")

    if not out_path.parent.is_dir():
        raise FileNotFoundError(f"Parent directory does not exist: {out_path.parent}")

    if out_path.exists() and not force:
        raise FileExistsError(f"File already exists (use --force to overwrite): {out_path}")

    content = render_export(payload, ext)

    tmp_fd, tmp_name = tempfile.mkstemp(dir=out_path.parent, prefix=".spongebob_", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, out_path)
    except BaseException:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    return out_path
