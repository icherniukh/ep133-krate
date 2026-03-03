from __future__ import annotations
from ko2_models import SAMPLE_RATE

# Table Column Widths (TUI)
COL_WIDTH_MARKER = 2
COL_WIDTH_SLOT = 4
COL_WIDTH_NAME = 45
COL_WIDTH_SIZE = 9
COL_WIDTH_CH = 2
COL_WIDTH_RATE = 6
COL_WIDTH_SEC = 10


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable size with consistent width."""
    if size_bytes <= 0:
        return "-"
    if size_bytes < 1024:
        return f"{size_bytes:5}B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:7.2f}K"
    return f"{size_bytes / (1024 * 1024):7.2f}M"


def format_duration(
    size_bytes: int, samplerate: int = SAMPLE_RATE, channels: int = 1
) -> str:
    """Calculate duration from file size (seconds, 3 decimals)."""
    if size_bytes <= 0 or samplerate <= 0 or channels <= 0:
        return "-"
    # 16-bit = 2 bytes per sample per channel
    bytes_per_frame = 2 * channels
    samples = size_bytes // bytes_per_frame
    seconds = samples / samplerate
    return f"{seconds:.3f}"
