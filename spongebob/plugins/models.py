from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from spongebob.scenarios.models import Scenario

PluginKind = Literal["scenarios", "jokes", "theme"]

MAX_PLUGIN_FILES = 20
MAX_PLUGIN_FILE_BYTES = 65_536
MAX_PLUGIN_TOTAL_BYTES = 524_288
MAX_JOKE_LEN = 200
MIN_CONTRAST_RATIO = 4.5


@dataclass(frozen=True)
class PluginManifest:
    """Validated plugin.toml metadata."""

    name: str
    version: str
    kind: PluginKind
    description: str


@dataclass(frozen=True)
class LoadedPlugin:
    """Validated data-only plugin payload."""

    manifest: PluginManifest
    scenarios: dict[str, Scenario] = field(default_factory=dict)
    finding_jokes: dict[tuple[str, str], tuple[str, ...]] = field(default_factory=dict)
    drop_jokes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    theme_colors: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginRegistry:
    """Aggregated data from explicitly loaded plugins."""

    plugins: tuple[LoadedPlugin, ...] = ()
    scenarios: dict[str, Scenario] = field(default_factory=dict)
    finding_jokes: dict[tuple[str, str], tuple[str, ...]] = field(default_factory=dict)
    drop_jokes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    theme_colors: dict[str, str] = field(default_factory=dict)
    errors: tuple[tuple[str, str], ...] = ()
