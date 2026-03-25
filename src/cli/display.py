"""
EP-133 terminal display layer.

Defines how sample data is rendered to the terminal.  Swap the view
instance in main() to change all display behaviour without touching any
command logic (e.g. replace with JsonView for machine-readable output).
"""
from __future__ import annotations

import json
import sys
from typing import Protocol, runtime_checkable

from core.models import Sample


class Colors:
    """ANSI escape code constants for terminal colouring."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    BRIGHT_GREEN = "\033[48;5;22m"
    GREEN = "\033[48;5;28m"
    YELLOW = "\033[48;5;226m"
    ORANGE = "\033[48;5;208m"
    RED = "\033[48;5;196m"
    BRIGHT_RED = "\033[48;5;88m"
    CYAN = "\033[38;5;39m"
    FG_GRAY = "\033[38;5;245m"
    FG_DIM = "\033[90m"
    FG_GREEN = "\033[38;5;82m"
    FG_YELLOW = "\033[38;5;226m"
    FG_RED = "\033[38;5;196m"


@runtime_checkable
class View(Protocol):
    """Presentation interface for ko2 CLI commands.

    All methods are fire-and-forget I/O operations.  Implementations can
    write to a terminal, emit JSON, or silently discard output.  Command
    functions depend only on this interface — never on a concrete class.
    """

    # --- generic output primitives ---
    def warn(self, message: str) -> None: ...
    def info(self, message: str) -> None: ...
    def section(self, title: str) -> None: ...
    def step(self, message: str) -> None: ...
    def success(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...
    def kv(self, label: str, value: str) -> None: ...
    def progress(self, current: int, total: int, message: str = "") -> None: ...

    # --- domain-data methods (View owns the presentation decision) ---
    def render_samples(self, samples: list[Sample], start: int, end: int) -> None: ...
    def sample_detail(self, info: Sample) -> None: ...



class TerminalView:
    """Renders EP-133 sample listings as colored, aligned terminal output."""

    # ANSI 256-color palette per size band
    _ANSI_PALETTE: list[list[int]] = [
        [22, 28],
        [28, 34],
        [58, 94],
        [94, 130],
        [130, 88],
        [88, 52],
    ]

    # --- Terminal Formatting Strategies ---

    def _size_color(self, size_bytes: int) -> str:
        result = Sample.size_band_for(size_bytes)
        if result is None:
            return ""
        band_idx, ratio = result
        palette = self._ANSI_PALETTE[band_idx]
        idx = min(len(palette) - 1, int(ratio * len(palette)))
        return f"\033[48;5;{palette[idx]}m"

    def _format_row(self, info: Sample) -> str:
        size_str = info.formatted_size if info.size_bytes else "-"
        color = self._size_color(info.size_bytes) if info.size_bytes else ""
        reset = Colors.RESET if info.size_bytes else ""

        channels_str = info.channels_abbr
        channels_color = (
            f"{Colors.BOLD}{Colors.FG_RED}" if info.channels == 2 else Colors.FG_DIM
        )

        name = info.name
        if len(name) > 32:
            name = name[:29] + "..."

        size_width = 8
        size_display = (
            f"{color}{size_str:>{size_width}}{reset}"
            if info.size_bytes
            else f"{size_str:>{size_width}}"
        )
        return (
            f"  {Colors.FG_DIM}{info.slot_id}{Colors.RESET}  "
            f"{name:<32}  "
            f"{channels_color}{channels_str}{Colors.RESET}  "
            f"{size_display}  "
            f"{info.duration_str:>9}"
        )

    def _row(self, info: Sample) -> None:
        print(self._format_row(info))

    def _table_header(self) -> None:
        print(f"  {'Slot':>4}  {'Name':<32}  {'CH':>2}  {'Size':>8}  {'s':>9}")
        print(f"  {'-'*4}  {'-'*32}  {'--':>2}  {'-'*8}  {'-'*9}")

    def _oversized_warning(self, samples: list[Sample]) -> None:
        oversized = [s for s in samples if s.size_bytes > 100 * 1024]
        if oversized:
            print(
                f"\n  {Colors.FG_YELLOW}⚠ {len(oversized)} samples over 100KB{Colors.RESET}"
            )
            print(f"  Run {Colors.FG_GREEN}ko2 optimize-all{Colors.RESET} to optimize")

    # --- public protocol methods ---

    def warn(self, message: str) -> None:
        print(f"  {Colors.FG_YELLOW}⚠ {message}{Colors.RESET}")

    def info(self, message: str) -> None:
        print(f"  {message}")

    def section(self, title: str) -> None:
        print(f"{Colors.CYAN}{title}{Colors.RESET}")

    def step(self, message: str) -> None:
        print(f"  {Colors.FG_DIM}{message}{Colors.RESET}")

    def success(self, message: str) -> None:
        print(f"  {Colors.FG_GREEN}✓{Colors.RESET} {message}")

    def error(self, message: str) -> None:
        print(f"  ❌ {message}")

    def kv(self, label: str, value: str) -> None:
        print(f"  {label:<14} {value}")

    def progress(self, current: int, total: int, message: str = "") -> None:
        if total <= 0:
            return
        pct = current / total
        filled = int(30 * pct)
        progress_bar = "█" * filled + "░" * (30 - filled)
        sys.stdout.write(f"\r  {progress_bar} {pct*100:.0f}% {message}")
        sys.stdout.flush()

    def render_samples(self, samples: list[Sample], start: int, end: int) -> None:
        used = [s for s in samples if s.size_bytes]
        total_size = sum(s.size_bytes for s in used)
        print(f"\n  Slots {start:03d}-{end:03d}")
        print(f"  Found {len(used)} samples, {Sample.format_size(total_size)} total\n")
        self._table_header()
        for info in samples:
            self._row(info)
        self._oversized_warning(samples)

    def sample_detail(self, info: Sample) -> None:
        print(f"📵 Slot {info.slot:03d}")
        print(f"   Name: {info.name}")
        if info.sym:
            print(f"   Symbol: {info.sym}")
        print(f"   Rate: {info.samplerate} Hz")
        print(f"   Format: {info.format}")
        print(f"   Channels: {info.channels}")
        if info.size_bytes:
            print(f"   Size: {info.formatted_size}")
            print(f"   Duration: {info.duration_str}s")



class SilentView:
    """No-op view — used as test double and --quiet backend."""

    def warn(self, message: str) -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def section(self, title: str) -> None:
        pass

    def step(self, message: str) -> None:
        pass

    def success(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass

    def kv(self, label: str, value: str) -> None:
        pass

    def progress(self, current: int, total: int, message: str = "") -> None:
        pass

    def render_samples(self, samples: list[Sample], start: int, end: int) -> None:
        pass

    def sample_detail(self, info: Sample) -> None:
        pass


class JsonView:
    """Structured JSON output view — machine-readable backend for --json."""

    def warn(self, message: str) -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def section(self, title: str) -> None:
        pass

    def step(self, message: str) -> None:
        pass

    def success(self, message: str) -> None:
        print(json.dumps({"status": "ok", "message": message}))

    def error(self, message: str) -> None:
        print(json.dumps({"status": "error", "message": message}))

    def kv(self, label: str, value: str) -> None:
        print(json.dumps({label: value}))

    def progress(self, current: int, total: int, message: str = "") -> None:
        pass

    def render_samples(self, samples: list[Sample], start: int, end: int) -> None:
        used = [s for s in samples if s.size_bytes]
        total_bytes = sum(s.size_bytes for s in used)
        print(
            json.dumps(
                {
                    "samples": [
                        {
                            "slot": s.slot,
                            "name": s.name,
                            "size_bytes": s.size_bytes,
                            "samplerate": s.samplerate,
                            "channels": s.channels,
                        }
                        for s in used
                    ],
                    "count": len(used),
                    "total_bytes": total_bytes,
                    "range": [start, end],
                }
            )
        )

    def sample_detail(self, info: Sample) -> None:
        d: dict = {
            "slot": info.slot,
            "name": info.name,
            "samplerate": info.samplerate,
            "format": info.format,
            "channels": info.channels,
        }
        if info.size_bytes:
            d["size_bytes"] = info.size_bytes
        if getattr(info, "sym", None):
            d["sym"] = info.sym
        print(json.dumps(d))
