from __future__ import annotations

import os
from typing import Iterable

RGB = tuple[int, int, int]

# Braille dot bitmasks for (dx in {0, 1}, dy in {0, 1, 2, 3})
_BRAILLE_MAP: tuple[tuple[int, int, int, int], tuple[int, int, int, int]] = (
    (0x01, 0x02, 0x04, 0x40),
    (0x08, 0x10, 0x20, 0x80),
)


def detect_truecolor() -> bool:
    """Return True if the environment advertises 24-bit truecolor support."""
    colorterm = os.environ.get("COLORTERM", "").lower()
    return colorterm in ("truecolor", "24bit")


def rgb_to_ansi256(r: int, g: int, b: int) -> int:
    """Convert an 8-bit RGB triple to the nearest xterm 256-color index."""
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))
    if r == g == b:
        if r < 8:
            return 16
        if r > 248:
            return 231
        return round(((r - 8) / 247) * 24) + 232
    ri = round(r / 255 * 5)
    gi = round(g / 255 * 5)
    bi = round(b / 255 * 5)
    return 16 + 36 * ri + 6 * gi + bi


class BrailleCanvas:
    """Pure 2x4-subpixel Braille canvas with per-cell 24-bit RGB color and fade."""

    def __init__(self, cols: int, rows: int) -> None:
        if cols < 1 or rows < 1:
            raise ValueError(f"cols and rows must be >= 1, got ({cols}, {rows})")
        self.cols = cols
        self.rows = rows
        self.pixel_width = cols * 2
        self.pixel_height = rows * 4
        self._masks: list[list[int]] = [[0] * cols for _ in range(rows)]
        self._colors: list[list[RGB | None]] = [[None] * cols for _ in range(rows)]

    def clear(self) -> None:
        """Clear all sub-pixels and colors."""
        for r in range(self.rows):
            for c in range(self.cols):
                self._masks[r][c] = 0
                self._colors[r][c] = None

    def set_pixel(self, x: int, y: int, color: RGB = (255, 255, 255)) -> None:
        """Set a sub-pixel at (x, y) with the given RGB color (bounds-safe)."""
        if x < 0 or y < 0 or x >= self.pixel_width or y >= self.pixel_height:
            return
        col = x >> 1
        row = y >> 2
        dx = x & 1
        dy = y & 3
        self._masks[row][col] |= _BRAILLE_MAP[dx][dy]
        self._colors[row][col] = color

    def clear_pixel(self, x: int, y: int) -> None:
        """Clear a sub-pixel at (x, y) (bounds-safe)."""
        if x < 0 or y < 0 or x >= self.pixel_width or y >= self.pixel_height:
            return
        col = x >> 1
        row = y >> 2
        dx = x & 1
        dy = y & 3
        self._masks[row][col] &= ~_BRAILLE_MAP[dx][dy]
        if self._masks[row][col] == 0:
            self._colors[row][col] = None

    def get_char(self, col: int, row: int) -> str:
        """Return the Unicode Braille character at cell (col, row)."""
        if col < 0 or row < 0 or col >= self.cols or row >= self.rows:
            return chr(0x2800)
        return chr(0x2800 + self._masks[row][col])

    def get_color(self, col: int, row: int) -> RGB | None:
        """Return the RGB color at cell (col, row), or None if empty."""
        if col < 0 or row < 0 or col >= self.cols or row >= self.rows:
            return None
        return self._colors[row][col]

    def fade(self, factor: float = 0.72, cutoff: int = 10) -> None:
        """Monotonically dim all cell colors by factor; clear cells below cutoff."""
        if factor <= 0.0:
            self.clear()
            return
        clamped_factor = min(1.0, factor)
        for r in range(self.rows):
            for c in range(self.cols):
                color = self._colors[r][c]
                if color is None:
                    continue
                nr = int(color[0] * clamped_factor)
                ng = int(color[1] * clamped_factor)
                nb = int(color[2] * clamped_factor)
                if max(nr, ng, nb) < cutoff:
                    self._masks[r][c] = 0
                    self._colors[r][c] = None
                else:
                    self._colors[r][c] = (nr, ng, nb)

    def draw_line(self, x0: int, y0: int, x1: int, y1: int, color: RGB) -> None:
        """Draw a sub-pixel line using Bresenham's algorithm."""
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        x, y = x0, y0
        while True:
            self.set_pixel(x, y, color)
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

    def draw_circle(self, cx: int, cy: int, radius: int, color: RGB) -> None:
        """Draw a filled sub-pixel disc."""
        r2 = radius * radius
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy <= r2:
                    self.set_pixel(cx + dx, cy + dy, color)

    def iter_rows(self) -> Iterable[list[tuple[str, RGB | None]]]:
        """Yield each row as a list of (braille_char, rgb_or_none) tuples."""
        for r in range(self.rows):
            yield [
                (chr(0x2800 + self._masks[r][c]), self._colors[r][c])
                for c in range(self.cols)
            ]
