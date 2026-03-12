from __future__ import annotations

import re
import time
from pathlib import Path


DEFAULT_BACKUP_DIR = Path(".ko2-backups")


def sanitize_filename_part(name: str, max_len: int = 80) -> str:
    name = re.sub(r"\s+", " ", name.strip())
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name)
    name = name.strip(" ._-")
    if not name:
        return "sample"
    return name[:max_len]


def backup_copy(
    src: Path,
    *,
    slot: int,
    name_hint: str = "",
    backup_dir: Path = DEFAULT_BACKUP_DIR,
) -> Path:
    """Copy a downloaded sample to a durable backup location.

    The destination path always ends with `.bak`.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%S")
    safe = sanitize_filename_part(name_hint) if name_hint else f"slot{slot:03d}"
    suffix = src.suffix or ".wav"
    dst = backup_dir / f"{slot:03d}_{safe}_{ts}{suffix}.bak"
    dst.write_bytes(src.read_bytes())
    return dst

