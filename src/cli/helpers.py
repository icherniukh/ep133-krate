import re
from typing import Optional
from ko2_client import SampleInfo
from ko2_models import SAMPLE_RATE

def strip_slot_prefix(name: str, slot: int) -> str:
    prefix = f"{slot:03d} "
    if name.startswith(prefix):
        return name[len(prefix) :].strip()
    return name

def looks_generic_name(name: str) -> bool:
    if not name:
        return True
    lowered = name.lower().strip()
    if lowered.startswith("slot "):
        return True
    if re.match(r"^\d{3}(\.pcm)?$", lowered):
        return True
    if lowered.endswith(".pcm"):
        return True
    return False

def choose_display_name(
    fs_name: str,
    meta_name: str | None,
    node_name: str | None,
    slot: int,
    source: str,
) -> str:
    fs_clean = strip_slot_prefix(fs_name, slot).strip()
    meta_clean = (meta_name or "").strip()
    node_clean = (node_name or "").strip()
    if source == "fs":
        return fs_clean or node_clean or meta_clean or f"Slot {slot:03d}"
    if source == "node":
        return node_clean or meta_clean or fs_clean or f"Slot {slot:03d}"
    # auto
    if node_clean and looks_generic_name(fs_clean):
        return node_clean
    if meta_clean and looks_generic_name(fs_clean):
        return meta_clean
    return fs_clean or node_clean or meta_clean or f"Slot {slot:03d}"

def parse_page(arg: str) -> Optional[tuple[int, int]]:
    """Parse page argument: '1' = slots 1-99, '2' = 100-199, etc."""
    try:
        page = int(arg)
        if not 1 <= page <= 10:
            return None
        start = (page - 1) * 100 + 1
        end = page * 100
        return start, end
    except ValueError:
        return None

def confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        resp = input(f"{prompt} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return resp in ("y", "yes")

def short_text(text: str, width: int) -> str:
    if text is None:
        text = ""
    text = str(text)
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."

def sanitize_field(text: str) -> str:
    if text is None:
        return ""
    return str(text).replace("\t", " ").replace("\n", " ").replace("\r", " ")

def format_bar(used: int, total: int, width: int = 28) -> str:
    if total <= 0:
        return ""
    ratio = min(1.0, max(0.0, used / total))
    filled = int(round(ratio * width))
    return "█" * filled + "░" * (width - filled)

def extract_total_memory(info: dict | None) -> Optional[int]:
    if not info:
        return None
    keys = [
        "memory_total_bytes",
        "mem_total_bytes",
        "total_memory_bytes",
        "memory_bytes",
        "mem_bytes",
    ]
    for key in keys:
        val = info.get(key)
        if isinstance(val, (int, float)) and val > 0:
            return int(val)
        if isinstance(val, str) and val.isdigit():
            return int(val)
    return None

def empty_sample(slot: int) -> SampleInfo:
    return SampleInfo(
        slot=slot,
        name="...",
        samplerate=SAMPLE_RATE,
        channels=0,
        size_bytes=0,
    )
