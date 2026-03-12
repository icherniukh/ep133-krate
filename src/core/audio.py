"""Digital signal processing (DSP) algorithms and analysis routines for EP-133 audio payloads.

Pure functions for WAV data analysis — no device communication.
Shared between CLI, TUI, and future web/mobile frontends.
"""

from __future__ import annotations

import array
import hashlib
import io
import struct
import wave
from typing import Any


def detect_channels(data: bytes, sample_check: int = 4000) -> int:
    """Detect mono vs stereo from raw s16 LE PCM data.

    For stereo interleaved PCM, even-indexed (L) and odd-indexed (R) samples
    are from independent channels and differ substantially. For mono PCM,
    adjacent samples are highly correlated (smooth waveform), so |L-R| is
    small relative to the signal amplitude.

    Returns 2 if mean(|L-R|) / mean(|sample|) > 1.0, else 1.
    """
    if len(data) < 8:
        return 1
    n = min(len(data) // 2, sample_check)
    values = struct.unpack(f"<{n}h", data[: n * 2])
    mean_abs = sum(abs(v) for v in values) / n
    if mean_abs == 0:
        return 1
    mean_lr_diff = sum(abs(values[i] - values[i + 1]) for i in range(0, n - 1, 2)) / (n // 2)
    return 2 if (mean_lr_diff / mean_abs) > 1.0 else 1


def extract_waveform_bins(wav_bytes: bytes, width: int) -> dict[str, Any] | None:
    """Compute min/max amplitude bins for waveform visualization.

    Returns dict with 'mins', 'maxs' (lists of quantized int8 values), and 'width'.
    """
    width = max(64, min(1024, int(width)))
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        channels = max(1, int(wf.getnchannels() or 1))
        sample_width = int(wf.getsampwidth() or 2)
        n_frames = int(wf.getnframes() or 0)
        if n_frames <= 0:
            return None
        raw = wf.readframes(n_frames)

    samples = decode_samples(raw, sample_width)
    if not samples:
        return None

    mins = [1.0] * width
    maxs = [-1.0] * width

    frame_count = min(n_frames, len(samples) // channels)
    if frame_count <= 0:
        return None
    for frame in range(frame_count):
        idx = frame * channels
        total = 0.0
        for c in range(channels):
            total += samples[idx + c]
        value = total / channels
        bucket = min(width - 1, (frame * width) // max(1, frame_count))
        if value < mins[bucket]:
            mins[bucket] = value
        if value > maxs[bucket]:
            maxs[bucket] = value

    for i in range(width):
        if mins[i] > maxs[i]:
            mins[i] = 0.0
            maxs[i] = 0.0

    mins_q = [int(max(-127, min(127, round(v * 127.0)))) for v in mins]
    maxs_q = [int(max(-127, min(127, round(v * 127.0)))) for v in maxs]
    return {"mins": mins_q, "maxs": maxs_q, "width": width}


def extract_fingerprint(wav_bytes: bytes) -> dict[str, Any] | None:
    """SHA256 fingerprint + WAV metadata from raw WAV bytes."""
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            channels = max(1, int(wf.getnchannels() or 1))
            sample_width = int(wf.getsampwidth() or 2)
            samplerate = int(wf.getframerate() or 0)
            n_frames = int(wf.getnframes() or 0)
            pcm = wf.readframes(n_frames)
    except Exception:
        return None

    if not pcm:
        return None

    sha256 = hashlib.sha256(pcm).hexdigest()
    duration_s = (n_frames / samplerate) if samplerate > 0 else 0.0
    return {
        "sha256": sha256,
        "frames": n_frames,
        "channels": channels,
        "samplerate": samplerate,
        "sample_width": sample_width,
        "duration_s": duration_s,
    }


def decode_samples(raw: bytes, sample_width: int) -> list[float]:
    """Decode raw PCM bytes to normalized float samples in [-1.0, 1.0]."""
    if sample_width == 2:
        pcm = array.array("h")
        pcm.frombytes(raw)
        # WAV data is little-endian PCM.
        if pcm.itemsize == 2 and array.array("H", [1]).tobytes() != b"\x01\x00":
            pcm.byteswap()
        scale = 32768.0
        return [max(-1.0, min(1.0, sample / scale)) for sample in pcm]

    if sample_width == 1:
        return [((b - 128) / 128.0) for b in raw]

    # Unsupported/rare sample widths in this app path.
    return []


# Backward-compatible aliases used by existing code
_detect_channels = detect_channels
_extract_waveform_bins_from_wav_bytes = extract_waveform_bins
_extract_fingerprint_from_wav_bytes = extract_fingerprint
_decode_samples = decode_samples
