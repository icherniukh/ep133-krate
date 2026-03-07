from __future__ import annotations

from typing import Any, cast

from rich.console import RenderableType
from rich.panel import Panel
from rich.text import Text
from textual.widgets import Static


class WaveformWidget(Static):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__("", **kwargs)
        self._slot: int | None = None
        self._pending: bool = False
        self._bins: dict[str, Any] | None = None

    def set_empty(self) -> None:
        self._slot = None
        self._pending = False
        self._bins = None
        self.refresh()

    def set_pending(self, slot: int) -> None:
        self._slot = slot
        self._pending = True
        self._bins = None
        self.refresh()

    def set_not_loaded(self, slot: int) -> None:
        self._slot = slot
        self._pending = False
        self._bins = None
        self.refresh()

    def set_bins(self, slot: int, bins: dict[str, Any]) -> None:
        self._slot = slot
        self._pending = False
        self._bins = bins
        self.refresh()

    def render(self) -> RenderableType:
        slot = self._slot
        if slot is None:
            return Panel(
                Text("No sample in this slot", style="dim"),
                title="Waveform",
                border_style="grey37",
            )

        if self._pending:
            return Panel(
                Text("Computing waveform...", style="italic #f59e0b"),
                title=f"Waveform {slot:03d}",
                subtitle="background job",
                border_style="#f59e0b",
            )

        if not self._bins:
            return Panel(
                Text("Press Enter to load waveform", style="dim"),
                title=f"Waveform {slot:03d}",
                border_style="grey50",
            )

        bins = self._bins
        w = int(self.size.width or 0)
        h = int(self.size.height or 0)
        # widget.size is padding-box (inside CSS border, including padding).
        # Width: -2 for CSS padding(0 1), -2 for Panel border = -4.
        # Height: no vertical CSS padding, -2 for Panel border = -2.
        cols = max(24, w - 4) if w > 0 else 72
        rows = max(4, h - 2) if h > 0 else 10
        art = _render_waveform_braille(
            cast(list[int], bins.get("mins", [])),
            cast(list[int], bins.get("maxs", [])),
            width_chars=cols,
            height_chars=rows,
        )
        text = Text()
        center = (len(art) - 1) / 2.0
        for idx, line in enumerate(art):
            dist = abs(idx - center) / center if center > 0 else 0.0
            color = "#f59e0b" if dist > 0.75 else "#2dd4bf" if dist > 0.4 else "#22d3ee"
            text.append(line, style=f"bold {color}")
            if idx < len(art) - 1:
                text.append("\n")
        return Panel(
            text,
            title=f"Waveform {slot:03d}",
            subtitle="cached",
            border_style="#0ea5e9",
        )


def _render_waveform_braille(
    mins_q: list[int], maxs_q: list[int], *, width_chars: int, height_chars: int
) -> list[str]:
    if not mins_q or not maxs_q or len(mins_q) != len(maxs_q):
        return [" " * max(1, width_chars) for _ in range(max(1, height_chars))]

    width_chars = max(8, int(width_chars))
    height_chars = max(3, int(height_chars))
    px_h = height_chars * 4
    n = len(mins_q)

    mins_f = [max(-127, min(127, int(v))) / 127.0 for v in mins_q]
    maxs_f = [max(-127, min(127, int(v))) / 127.0 for v in maxs_q]

    cells = [[0 for _ in range(width_chars)] for _ in range(height_chars)]
    for cx in range(width_chars):
        # Chunk min/max: take the true peak over the input bins mapped to this column.
        lo_idx = int(cx * n / width_chars)
        hi_idx = min(max(lo_idx + 1, int((cx + 1) * n / width_chars)), n)
        lo = min(mins_f[lo_idx:hi_idx])
        hi = max(maxs_f[lo_idx:hi_idx])

        # Envelope: symmetric bar around center so zero-crossings don't create gaps.
        amp = max(abs(lo), abs(hi))
        y_top = int(round((1.0 - amp) * 0.5 * (px_h - 1)))
        y_bottom = int(round((1.0 + amp) * 0.5 * (px_h - 1)))
        y_top = max(0, min(px_h - 1, y_top))
        y_bottom = max(0, min(px_h - 1, y_bottom))

        for y in range(y_top, y_bottom + 1):
            cy = y // 4
            ly = y % 4
            cells[cy][cx] |= _braille_bit(0, ly)
            cells[cy][cx] |= _braille_bit(1, ly)

    lines: list[str] = []
    for row in cells:
        line = "".join(chr(0x2800 + bits) if bits else " " for bits in row).rstrip()
        lines.append(line if line else " ")
    return lines


def _resample_series(values: list[float], target: int) -> list[float]:
    if not values:
        return [0.0] * max(1, target)
    if target <= 1:
        return [float(values[0])]
    if len(values) == target:
        return [float(v) for v in values]
    out: list[float] = []
    last = len(values) - 1
    for i in range(target):
        pos = (i * last) / (target - 1)
        lo = int(pos)
        hi = min(lo + 1, last)
        frac = pos - lo
        out.append((values[lo] * (1.0 - frac)) + (values[hi] * frac))
    return out


def _braille_bit(x: int, y: int) -> int:
    if x == 0:
        if y == 0:
            return 1 << 0
        if y == 1:
            return 1 << 1
        if y == 2:
            return 1 << 2
        return 1 << 6
    if y == 0:
        return 1 << 3
    if y == 1:
        return 1 << 4
    if y == 2:
        return 1 << 5
    return 1 << 7
