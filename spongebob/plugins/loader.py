from __future__ import annotations

import re
import string
import tomllib
from pathlib import Path
from typing import Any

from spongebob.narrator.narrator import BANNED_NAMES, DROP_REASON_POOLS, FINDING_POOLS
from spongebob.scenarios import list_builtin_scenarios, load_scenario
from spongebob.scenarios.models import Scenario

from .models import (
    MAX_JOKE_LEN,
    MAX_PLUGIN_FILE_BYTES,
    MAX_PLUGIN_FILES,
    MAX_PLUGIN_TOTAL_BYTES,
    MIN_CONTRAST_RATIO,
    LoadedPlugin,
    PluginManifest,
    PluginRegistry,
)

_PLUGIN_NAME_RE = re.compile(r"^[a-z0-9-]{3,32}$")
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_MANIFEST_KEYS = frozenset({"name", "version", "kind", "description"})
_VALID_KINDS = frozenset({"scenarios", "jokes", "theme"})
_ALLOWED_JOKE_FIELDS = frozenset({"hop", "value"})


def _read_toml_file(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > MAX_PLUGIN_FILE_BYTES:
        raise ValueError(
            f"File {path.name} ({len(raw)} bytes) exceeds limit of {MAX_PLUGIN_FILE_BYTES} bytes"
        )
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"Invalid TOML in {path.name}: {exc}") from exc
    return data


def _validate_folder_limits(folder: Path) -> list[Path]:
    if not folder.is_dir():
        raise FileNotFoundError(f"Plugin folder not found: {folder}")
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    if len(files) > MAX_PLUGIN_FILES:
        raise ValueError(
            f"Plugin {folder.name} has {len(files)} files (max {MAX_PLUGIN_FILES})"
        )
    total_bytes = 0
    for f in files:
        sz = f.stat().st_size
        if sz > MAX_PLUGIN_FILE_BYTES:
            raise ValueError(
                f"File {f.name} ({sz} bytes) exceeds limit of {MAX_PLUGIN_FILE_BYTES} bytes"
            )
        total_bytes += sz
    if total_bytes > MAX_PLUGIN_TOTAL_BYTES:
        raise ValueError(
            f"Plugin {folder.name} total size {total_bytes} bytes exceeds {MAX_PLUGIN_TOTAL_BYTES} bytes"
        )
    return files


def _parse_manifest(folder: Path) -> PluginManifest:
    manifest_path = folder / "plugin.toml"
    if not manifest_path.is_file():
        raise ValueError(f"Missing plugin.toml in {folder}")
    data = _read_toml_file(manifest_path)

    for key in data:
        if key not in _MANIFEST_KEYS:
            raise ValueError(f"Unknown key {key!r} in plugin.toml")
    for req in sorted(_MANIFEST_KEYS):
        if req not in data:
            raise ValueError(f"Missing required key {req!r} in plugin.toml")

    name = data["name"]
    version = data["version"]
    kind = data["kind"]
    description = data["description"]

    if not isinstance(name, str) or not _PLUGIN_NAME_RE.match(name):
        raise ValueError(
            f"Invalid plugin name {name!r}: must be 3-32 lowercase letters, digits, or hyphens"
        )
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Plugin version must be a non-empty string")
    if not isinstance(kind, str) or kind not in _VALID_KINDS:
        raise ValueError(f"Invalid plugin kind {kind!r}: must be scenarios, jokes, or theme")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("Plugin description must be a non-empty string")

    return PluginManifest(name=name, version=version, kind=kind, description=description)  # type: ignore[arg-type]


def _validate_joke_line(line: Any) -> str:
    if not isinstance(line, str) or not line.strip():
        raise ValueError("Joke line must be a non-empty string")
    if len(line) > MAX_JOKE_LEN:
        raise ValueError(f"Joke line exceeds {MAX_JOKE_LEN} chars")
    for ch in line:
        code = ord(ch)
        if code < 32 or code == 127:
            raise ValueError("Joke line contains disallowed control or escape characters")
    lowered = line.lower()
    for banned in BANNED_NAMES:
        if banned in lowered:
            raise ValueError(f"Joke line contains banned name {banned!r}")

    formatter = string.Formatter()
    try:
        for _literal, field_name, format_spec, conversion in formatter.parse(line):
            if field_name is not None:
                if field_name not in _ALLOWED_JOKE_FIELDS:
                    raise ValueError(
                        f"Disallowed placeholder {{{field_name}}} in joke line; only {{hop}} and {{value}} allowed"
                    )
                if format_spec or conversion:
                    raise ValueError("Format specs/conversions are not allowed in joke placeholders")
        line.format(hop="router", value="42.0")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Invalid joke template: {exc}") from exc
    return line


def _load_scenarios_plugin(manifest: PluginManifest, files: list[Path]) -> dict[str, Scenario]:
    builtins = set(list_builtin_scenarios())
    scenarios: dict[str, Scenario] = {}
    toml_files = [f for f in files if f.suffix == ".toml" and f.name != "plugin.toml"]
    if not toml_files:
        raise ValueError(f"Scenarios plugin {manifest.name!r} contains no scenario .toml files")
    for f in toml_files:
        stem = f.stem
        if stem in builtins:
            raise ValueError(f"Plugin scenario {stem!r} cannot override built-in scenario")
        reg_key = f"{manifest.name}/{stem}"
        if reg_key in builtins:
            raise ValueError(f"Plugin scenario {reg_key!r} cannot override built-in scenario")
        scenarios[reg_key] = load_scenario(f)
    return scenarios


def _load_jokes_plugin(
    manifest: PluginManifest, files: list[Path]
) -> tuple[dict[tuple[str, str], tuple[str, ...]], dict[str, tuple[str, ...]]]:
    toml_files = [f for f in files if f.suffix == ".toml" and f.name != "plugin.toml"]
    if not toml_files:
        raise ValueError(f"Jokes plugin {manifest.name!r} contains no .toml files")

    finding_jokes: dict[tuple[str, str], list[str]] = {}
    drop_jokes: dict[str, list[str]] = {}

    for f in toml_files:
        data = _read_toml_file(f)
        for top_key in data:
            if top_key not in ("findings", "drop_reasons"):
                raise ValueError(f"Unknown key {top_key!r} in {f.name}")

        findings_tbl = data.get("findings", {})
        if not isinstance(findings_tbl, dict):
            raise ValueError(f"[findings] in {f.name} must be a table")
        for key, lines in findings_tbl.items():
            if "." not in key:
                raise ValueError(f"Invalid finding key {key!r}; expected 'CODE.severity'")
            code, sev = key.split(".", 1)
            if (code, sev) not in FINDING_POOLS:
                raise ValueError(f"Unknown finding/severity key {key!r}")
            if not isinstance(lines, list):
                raise ValueError(f"Finding pool {key!r} must be a list of strings")
            validated = [_validate_joke_line(ln) for ln in lines]
            finding_jokes.setdefault((code, sev), []).extend(validated)

        drops_tbl = data.get("drop_reasons", {})
        if not isinstance(drops_tbl, dict):
            raise ValueError(f"[drop_reasons] in {f.name} must be a table")
        for reason, lines in drops_tbl.items():
            if reason not in DROP_REASON_POOLS:
                raise ValueError(f"Unknown drop reason {reason!r}")
            if not isinstance(lines, list):
                raise ValueError(f"Drop reason pool {reason!r} must be a list of strings")
            validated = [_validate_joke_line(ln) for ln in lines]
            drop_jokes.setdefault(reason, []).extend(validated)

    return (
        {k: tuple(v) for k, v in finding_jokes.items()},
        {k: tuple(v) for k, v in drop_jokes.items()},
    )


def _relative_luminance(hex_color: str) -> float:
    r = int(hex_color[1:3], 16) / 255.0
    g = int(hex_color[3:5], 16) / 255.0
    b = int(hex_color[5:7], 16) / 255.0

    def _lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _contrast_ratio(c1: str, c2: str) -> float:
    l1 = _relative_luminance(c1)
    l2 = _relative_luminance(c2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _load_theme_plugin(manifest: PluginManifest, files: list[Path]) -> dict[str, str]:
    from spongebob.ui.theme import DEFAULT_PALETTE, THEME_ROLES

    toml_files = [f for f in files if f.suffix == ".toml" and f.name != "plugin.toml"]
    if not toml_files:
        raise ValueError(f"Theme plugin {manifest.name!r} contains no .toml files")

    colors: dict[str, str] = {}
    for f in toml_files:
        data = _read_toml_file(f)
        for top_key in data:
            if top_key != "colors":
                raise ValueError(f"Unknown key {top_key!r} in {f.name}; expected [colors]")
        colors_tbl = data.get("colors", {})
        if not isinstance(colors_tbl, dict):
            raise ValueError(f"[colors] in {f.name} must be a table")
        for role, val in colors_tbl.items():
            if role not in THEME_ROLES:
                raise ValueError(f"Unknown theme role {role!r}")
            if not isinstance(val, str) or not _HEX_COLOR_RE.match(val):
                raise ValueError(f"Invalid hex color {val!r} for role {role!r}; expected #RRGGBB")
            colors[role] = val.lower()

    merged = {**DEFAULT_PALETTE, **colors}
    for fg_role, bg_role in (("cream", "bg"), ("signal_green", "bg"), ("cream", "banner_blue")):
        ratio = _contrast_ratio(merged[fg_role], merged[bg_role])
        if ratio < MIN_CONTRAST_RATIO:
            raise ValueError(
                f"Low contrast ratio ({ratio:.2f} < {MIN_CONTRAST_RATIO}) between {fg_role} and {bg_role}"
            )
    return colors


def load_plugin(folder: str | Path) -> LoadedPlugin:
    """Load and validate a single data-only plugin folder."""
    plugin_dir = Path(folder)
    files = _validate_folder_limits(plugin_dir)
    manifest = _parse_manifest(plugin_dir)

    if manifest.kind == "scenarios":
        return LoadedPlugin(
            manifest=manifest,
            scenarios=_load_scenarios_plugin(manifest, files),
        )
    if manifest.kind == "jokes":
        f_jokes, d_jokes = _load_jokes_plugin(manifest, files)
        return LoadedPlugin(
            manifest=manifest,
            finding_jokes=f_jokes,
            drop_jokes=d_jokes,
        )
    return LoadedPlugin(
        manifest=manifest,
        theme_colors=_load_theme_plugin(manifest, files),
    )


def load_plugins_from_dir(plugins_dir: str | Path) -> PluginRegistry:
    """Explicitly load all valid plugins from a user-provided folder, skipping failures."""
    root = Path(plugins_dir)
    if not root.is_dir():
        return PluginRegistry(errors=((str(root), f"Plugin directory not found: {root}"),))

    candidates = [root] if (root / "plugin.toml").is_file() else sorted(
        p for p in root.iterdir() if p.is_dir()
    )

    loaded: list[LoadedPlugin] = []
    scenarios: dict[str, Scenario] = {}
    finding_jokes: dict[tuple[str, str], list[str]] = {}
    drop_jokes: dict[str, list[str]] = {}
    theme_colors: dict[str, str] = {}
    errors: list[tuple[str, str]] = []

    for candidate in candidates:
        try:
            plugin = load_plugin(candidate)
        except Exception as exc:
            errors.append((candidate.name, str(exc)))
            continue
        loaded.append(plugin)
        scenarios.update(plugin.scenarios)
        for k, lines in plugin.finding_jokes.items():
            finding_jokes.setdefault(k, []).extend(lines)
        for k, lines in plugin.drop_jokes.items():
            drop_jokes.setdefault(k, []).extend(lines)
        theme_colors.update(plugin.theme_colors)

    return PluginRegistry(
        plugins=tuple(loaded),
        scenarios=scenarios,
        finding_jokes={k: tuple(v) for k, v in finding_jokes.items()},
        drop_jokes={k: tuple(v) for k, v in drop_jokes.items()},
        theme_colors=theme_colors,
        errors=tuple(errors),
    )
