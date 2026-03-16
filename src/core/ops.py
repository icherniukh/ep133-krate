"""Shared device operations for EP-133 KO-II.

High-level operations that combine device client calls with local processing.
Used by both CLI and TUI — keeps command functions thin.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Callable, Optional

from .backup import backup_copy  # noqa: F401 — re-export for convenience
from .models import SAMPLE_RATE


# Type alias for progress callbacks: (current_step, total_steps, message)
ProgressCallback = Optional[Callable[[int, int, str], None]]


def optimize_sample(
    input_path: Path, output_path: Optional[Path] = None,
    downsample_rate: Optional[int] = None, speed: Optional[float] = None,
    mono: bool = True,
) -> tuple[bool, str, int, int]:
    """Optimize a WAV file for EP-133 using sox.

    Downmixes stereo to mono, and downsamples only if rate > SAMPLE_RATE (46875 Hz).
    The device stores samples below 46875 Hz at their original rate (firmware OS 2.0+),
    so there is no reason to upsample.

    Returns:
        (success, message, original_size, optimized_size)
    """
    original_size = input_path.stat().st_size

    if output_path is None:
        output_path = input_path.with_suffix(".opt.wav")

    with wave.open(str(input_path)) as w:
        in_channels = w.getnchannels()
        in_rate = w.getframerate()
        in_depth = w.getsampwidth() * 8

    target_rate = downsample_rate if downsample_rate else SAMPLE_RATE

    needs_downmix = in_channels > 1 and mono
    needs_resample = in_rate > target_rate
    needs_requantize = in_depth > 16
    needs_speed = speed is not None and speed != 1.0

    if not needs_downmix and not needs_resample and not needs_requantize and not needs_speed:
        return True, "already optimal", original_size, original_size

    # Use sox for conversion
    sox_args = ["sox", str(input_path)]
    if needs_downmix:
        sox_args += ["-c", "1"]
    if needs_resample:
        sox_args += ["-r", str(target_rate)]
    if needs_requantize:
        sox_args += ["-b", "16"]

    sox_args.append(str(output_path))

    if needs_speed:
        sox_args += ["speed", str(speed)]

    try:
        subprocess.run(sox_args, capture_output=True, check=True, timeout=30)
        opt_size = output_path.stat().st_size
        return True, "optimized with sox", original_size, opt_size
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ) as e:
        return False, f"error: {e}", original_size, 0


def resolve_transfer_name(
    client: Any, slot: int, entry: dict | None, raw: bool = False,
) -> str:
    """Resolve the display name for a slot, trying node metadata first."""
    fs_name = str(entry.get("name") if entry else f"{slot:03d}.pcm")
    if raw:
        return fs_name

    node_id = int(entry.get("node_id") or 0) if entry else 0
    if node_id:
        try:
            node_meta = client.get_node_metadata(node_id)
        except Exception:
            node_meta = None
        if node_meta:
            node_name = node_meta.get("name") or node_meta.get("sym")
            if node_name:
                return str(node_name)

    try:
        meta = client.info(slot, include_size=False, node_entry=entry)
        if meta.name:
            return meta.name
    except Exception:
        pass

    return fs_name


def move_slot(
    client: Any,
    src: int,
    dst: int,
    *,
    raw: bool = False,
    progress: ProgressCallback = None,
) -> str:
    """Move sample from src to dst. Swaps if dst is occupied.

    Returns a human-readable result message.
    """
    from .client import EP133Error, SlotEmptyError

    sounds = client.list_sounds()
    src_entry = sounds.get(src)
    if not src_entry:
        raise SlotEmptyError(f"Slot {src:03d} is empty")
    dst_entry = sounds.get(dst)

    src_name = resolve_transfer_name(client, src, src_entry, raw)
    dst_name = resolve_transfer_name(client, dst, dst_entry, raw) if dst_entry else ""

    with tempfile.TemporaryDirectory(prefix="krate-move-") as td:
        temp_dir = Path(td)
        src_path = temp_dir / f"slot{src:03d}.wav"
        dst_path = temp_dir / f"slot{dst:03d}.wav"

        if progress:
            progress(1, 3, f"Downloading slot {src:03d}")
        client.get(src, src_path)
        backup_copy(src_path, slot=src, name_hint=src_name)

        if dst_entry:
            client.get(dst, dst_path)
            backup_copy(dst_path, slot=dst, name_hint=dst_name)

        try:
            if dst_entry:
                if progress:
                    progress(2, 3, f"Swapping {src:03d} ↔ {dst:03d}")
                client.put(src_path, dst, name=src_name, progress=False)
                client.put(dst_path, src, name=dst_name, progress=False)
                return f"Swapped {src:03d} ↔ {dst:03d}"
            else:
                if progress:
                    progress(2, 3, f"Moving {src:03d} → {dst:03d}")
                client.put(src_path, dst, name=src_name, progress=False)
                client.delete(src)
                return f"Moved {src:03d} → {dst:03d}"
        except EP133Error:
            # Attempt rollback on failure
            if dst_entry:
                try:
                    client.put(src_path, src, name=src_name, progress=False)
                except Exception:
                    pass
                try:
                    client.put(dst_path, dst, name=dst_name, progress=False)
                except Exception:
                    pass
            raise


def copy_slot(
    client: Any,
    src: int,
    dst: int,
    *,
    raw: bool = False,
    progress: ProgressCallback = None,
) -> str:
    """Copy sample from src to dst. Overwrites dst if occupied.

    Returns a human-readable result message.
    """
    from .client import EP133Error

    sounds = client.list_sounds()
    src_entry = sounds.get(src)
    if not src_entry:
        from .client import SlotEmptyError
        raise SlotEmptyError(f"Slot {src:03d} is empty")
    dst_entry = sounds.get(dst)

    src_name = resolve_transfer_name(client, src, src_entry, raw)
    dst_name = resolve_transfer_name(client, dst, dst_entry, raw) if dst_entry else ""

    with tempfile.TemporaryDirectory(prefix="krate-copy-") as td:
        temp_dir = Path(td)
        src_path = temp_dir / f"slot{src:03d}.wav"
        dst_path = temp_dir / f"slot{dst:03d}.wav"

        if progress:
            progress(1, 3, f"Downloading slot {src:03d}")
        client.get(src, src_path)
        backup_copy(src_path, slot=src, name_hint=src_name)

        if dst_entry:
            client.get(dst, dst_path)
            backup_copy(dst_path, slot=dst, name_hint=dst_name)
            client.delete(dst)

        try:
            if progress:
                progress(2, 3, f"Uploading to slot {dst:03d}")
            client.put(src_path, dst, name=src_name, progress=False)
            return f"Copied {src:03d} → {dst:03d}"
        except EP133Error:
            if dst_entry:
                try:
                    client.put(dst_path, dst, name=dst_name, progress=False)
                except Exception:
                    pass
            raise


def squash_scan(sounds: dict, start: int, end: int) -> dict[int, int]:
    """Return mapping {old_slot: new_slot} for slots that need to move.

    Slots already at the correct sequential position are excluded.
    """
    used_slots = [s for s in sorted(sounds.keys()) if start <= s <= end]
    mapping: dict[int, int] = {}
    target_slot = start
    for slot in used_slots:
        if slot != target_slot:
            mapping[slot] = target_slot
        target_slot += 1
    return mapping


def squash_process(
    mapping: dict[int, int],
    sounds: dict,
    client: Any,
    *,
    raw: bool = False,
    progress: ProgressCallback = None,
) -> None:
    """Execute each move in mapping: get, backup, delete old, put new."""
    from .client import EP133Error

    total = len(mapping)
    for idx, (old_slot, new_slot) in enumerate(mapping.items()):
        entry = sounds.get(old_slot)
        name = resolve_transfer_name(client, old_slot, entry, raw)

        if progress:
            progress(idx + 1, total, f"Squashing {old_slot:03d} → {new_slot:03d}")

        with tempfile.TemporaryDirectory(prefix=f"krate-move{old_slot:03d}-") as td:
            temp_path = Path(td) / f"slot{old_slot:03d}.wav"
            client.get(old_slot, temp_path)
            backup_copy(temp_path, slot=old_slot, name_hint=name)

            deleted = False
            try:
                client.delete(old_slot)
                deleted = True
                client.put(temp_path, new_slot, name=name, progress=False)
            except EP133Error:
                if deleted:
                    try:
                        client.put(temp_path, old_slot, name=name, progress=False)
                    except Exception:
                        pass
                raise
