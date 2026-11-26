from __future__ import annotations

import random

from rich.style import Style
from rich.text import Text
from textual.widgets import Static

from spongebob import __version__
from spongebob.ui.canvas import detect_truecolor, rgb_to_ansi256

# Exact palette sampled from reference image 1
BG = "#000501"
BG_RGB = (0, 5, 1)

BANNER_BLUE = "#004fc5"
BANNER_BLUE_RGB = (0, 79, 197)

CREAM = "#cbf7bc"
CREAM_RGB = (203, 247, 188)

SIGNAL_GREEN = "#14e96d"
SIGNAL_GREEN_RGB = (20, 233, 109)

TEAL_LIGHT = "#d7fcff"
TEAL_LIGHT_RGB = (215, 252, 255)

TEAL_MID = "#208e9d"
TEAL_MID_RGB = (32, 142, 157)

TEAL_DARK = "#104c42"
TEAL_DARK_RGB = (16, 76, 66)

RED_RULE = "#d5574b"
RED_RULE_RGB = (213, 87, 75)

WARN_AMBER = "#facc15"
WARN_AMBER_RGB = (250, 204, 21)

CRIT_RED = "#f87171"
CRIT_RED_RGB = (248, 113, 113)

DIM_TEXT = "#649e8a"
DIM_TEXT_RGB = (100, 158, 138)

DEFAULT_PALETTE: dict[str, str] = {
    "bg": BG,
    "banner_blue": BANNER_BLUE,
    "cream": CREAM,
    "signal_green": SIGNAL_GREEN,
    "teal_light": TEAL_LIGHT,
    "teal_mid": TEAL_MID,
    "teal_dark": TEAL_DARK,
    "red_rule": RED_RULE,
    "warn_amber": WARN_AMBER,
    "crit_red": CRIT_RED,
    "dim_text": DIM_TEXT,
}

THEME_ROLES: frozenset[str] = frozenset(DEFAULT_PALETTE.keys())


def build_base_css(palette: dict[str, str] | None = None) -> str:
    """Build base Textual CSS from a palette dictionary."""
    p = {**DEFAULT_PALETTE, **(palette or {})}
    return f"""
Screen {{
    background: {p['bg']};
    color: {p['cream']};
}}
.top-title {{
    height: 1;
    padding: 0 1;
    background: {p['bg']};
    color: {p['cream']};
    text-style: bold;
}}
.red-rule {{
    height: 1;
    background: {p['bg']};
    color: {p['red_rule']};
}}
.screen-banner {{
    height: auto;
    padding: 0 1;
    background: {p['banner_blue']};
    color: {p['cream']};
    text-style: bold;
    border: solid {p['signal_green']};
}}
.outlined-box {{
    border: solid {p['signal_green']};
    background: {p['bg']};
    color: {p['cream']};
    padding: 0 1;
}}
.box-title {{
    text-style: bold;
    color: {p['signal_green']};
}}
.status-bar {{
    height: 1;
    padding: 0 1;
    background: {p['bg']};
    color: {p['signal_green']};
    border-top: solid {p['signal_green']};
}}
Button {{
    background: {p['bg']};
    color: {p['cream']};
    border: solid {p['signal_green']};
    min-height: 1;
    height: auto;
}}
Button:focus {{
    background: {p['banner_blue']};
    color: {p['cream']};
    text-style: bold;
}}
Button.-primary {{
    background: {p['bg']};
    color: {p['signal_green']};
    border: solid {p['signal_green']};
}}
Button.-primary:focus {{
    background: {p['banner_blue']};
    color: {p['cream']};
    text-style: bold;
}}
Button.-error {{
    background: {p['bg']};
    color: {p['crit_red']};
    border: solid {p['red_rule']};
}}
Button.-error:focus {{
    background: {p['banner_blue']};
    color: {p['cream']};
    text-style: bold;
}}
Input {{
    background: {p['bg']};
    color: {p['cream']};
    border: solid {p['signal_green']};
}}
Input:focus {{
    border: solid {p['teal_light']};
}}
Checkbox {{
    background: {p['bg']};
    color: {p['cream']};
    border: none;
}}
Select {{
    background: {p['bg']};
    color: {p['cream']};
}}
Footer {{
    background: {p['bg']};
    color: {p['dim_text']};
}}
"""


SUBTITLE = "NETWORK IMPAIRMENT SIMULATOR AND VISUALIZER"

WORDMARK_LINES: tuple[str, ...] = (
    "▄▀▀▀ █▀▀▄ ▄▀▀▄ █▄ █ ▄▀▀▀ █▀▀▀ █▀▀▄ ▄▀▀▄ █▀▀▄",
    " ▀▀▄ █▄▄▀ █  █ █ ▀█ █ ▀█ █▀▀  █▀▀▄ █  █ █▀▀▄",
    "▀▀▀  █    ▀▄▄▀ █  █ ▀▄▄▀ █▄▄▄ █▄▄▀ ▀▄▄▀ █▄▄▀",
)

BASE_THEME_CSS = f"""
Screen {{
    background: {BG};
    color: {CREAM};
}}
.top-title {{
    height: 1;
    padding: 0 1;
    background: {BG};
    color: {CREAM};
    text-style: bold;
}}
.red-rule {{
    height: 1;
    background: {BG};
    color: {RED_RULE};
}}
.screen-banner {{
    height: auto;
    padding: 0 1;
    background: {BANNER_BLUE};
    color: {CREAM};
    text-style: bold;
    border: solid {SIGNAL_GREEN};
}}
.outlined-box {{
    border: solid {SIGNAL_GREEN};
    background: {BG};
    color: {CREAM};
    padding: 0 1;
}}
.box-title {{
    text-style: bold;
    color: {SIGNAL_GREEN};
}}
.status-bar {{
    height: 1;
    padding: 0 1;
    background: {BG};
    color: {SIGNAL_GREEN};
    border-top: solid {SIGNAL_GREEN};
}}
Button {{
    background: {BG};
    color: {CREAM};
    border: solid {SIGNAL_GREEN};
    min-height: 1;
    height: auto;
}}
Button:focus {{
    background: {BANNER_BLUE};
    color: {CREAM};
    text-style: bold;
}}
Button.-primary {{
    background: {BG};
    color: {SIGNAL_GREEN};
    border: solid {SIGNAL_GREEN};
}}
Button.-primary:focus {{
    background: {BANNER_BLUE};
    color: {CREAM};
    text-style: bold;
}}
Button.-error {{
    background: {BG};
    color: {CRIT_RED};
    border: solid {RED_RULE};
}}
Button.-error:focus {{
    background: {BANNER_BLUE};
    color: {CREAM};
    text-style: bold;
}}
Input {{
    background: {BG};
    color: {CREAM};
    border: solid {SIGNAL_GREEN};
}}
Input:focus {{
    border: solid {TEAL_LIGHT};
}}
Checkbox {{
    background: {BG};
    color: {CREAM};
    border: none;
}}
Select {{
    background: {BG};
    color: {CREAM};
}}
Footer {{
    background: {BG};
    color: {DIM_TEXT};
}}
"""


def color_style(
    rgb: tuple[int, int, int],
    truecolor: bool | None = None,
    bg_rgb: tuple[int, int, int] | None = None,
) -> Style:
    """Build a Rich Style with 256-color fallback when truecolor is unavailable."""
    use_tc = detect_truecolor() if truecolor is None else truecolor
    if use_tc:
        fg = f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"
        bg = f"rgb({bg_rgb[0]},{bg_rgb[1]},{bg_rgb[2]})" if bg_rgb is not None else None
        return Style(color=fg, bgcolor=bg)
    fg_idx = rgb_to_ansi256(*rgb)
    bg_idx = rgb_to_ansi256(*bg_rgb) if bg_rgb is not None else None
    return Style(color=f"color({fg_idx})", bgcolor=f"color({bg_idx})" if bg_idx is not None else None)


def generate_signal_bands(width: int, rows: int, seed: int = 42) -> list[list[tuple[str, tuple[int, int, int]]]]:
    """Generate deterministic jittering/lossy horizontal signal-band rows."""
    rng = random.Random(seed)
    tones = (TEAL_LIGHT_RGB, TEAL_MID_RGB, TEAL_DARK_RGB)
    glyphs = ("▀", "▄", "─")
    band_rows: list[list[tuple[str, tuple[int, int, int]]]] = []

    for r in range(rows):
        row_cells: list[tuple[str, tuple[int, int, int]]] = []
        # Occasional missing band (loss motif)
        if rng.random() < 0.18 and r > 0:
            band_rows.append([(" ", BANNER_BLUE_RGB)] * width)
            continue

        x = 0
        while x < width:
            seg_len = rng.randint(3, 12)
            # Jittered thickness/glyph and occasional gap
            if rng.random() < 0.22:
                ch = " "
                rgb = BANNER_BLUE_RGB
            else:
                ch = glyphs[(r + rng.randint(0, 1)) % len(glyphs)]
                rgb = tones[min(len(tones) - 1, (r + rng.randint(0, 1)) % len(tones))]
            for _ in range(min(seg_len, width - x)):
                row_cells.append((ch, rgb))
                x += 1
        band_rows.append(row_cells)
    return band_rows


def render_signal_band_text(
    width: int,
    rows: int,
    seed: int = 42,
    truecolor: bool | None = None,
) -> Text:
    """Render deterministic signal-band stripes as Rich Text on royal-blue background."""
    use_tc = detect_truecolor() if truecolor is None else truecolor
    bands = generate_signal_bands(width, rows, seed=seed)
    text = Text()
    for r_idx, row in enumerate(bands):
        for ch, rgb in row:
            text.append(ch, style=color_style(rgb, truecolor=use_tc, bg_rgb=BANNER_BLUE_RGB))
        if r_idx < len(bands) - 1:
            text.append("\n")
    return text


def segmented_bar(fraction: float, width: int = 12) -> str:
    """Return a segmented ASCII/block progress bar."""
    clamped = max(0.0, min(1.0, fraction))
    filled = int(round(clamped * width))
    return f"[{'█' * filled}{'░' * (width - filled)}]"


def format_status_line(label: str, fraction: float = 1.0, bar_width: int = 12) -> str:
    """Format the bottom status line with a segmented progress bar."""
    pct = int(round(max(0.0, min(1.0, fraction)) * 100))
    return f"{label}  {segmented_bar(fraction, width=bar_width)} {pct:>3}%"


class RedTopRule(Static):
    """Full-width red rule rendered across the top under the screen title."""

    def on_mount(self) -> None:
        self._refresh_rule()

    def on_resize(self) -> None:
        self._refresh_rule()

    def _refresh_rule(self) -> None:
        w = max(20, self.size.width or 80)
        self.update("━" * w)


def make_top_title(screen_name: str) -> Static:
    """Create the consistent top title bar."""
    return Static(f"SPONGEBOB v{__version__}  //  {screen_name.upper()}", classes="top-title")
