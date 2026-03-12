import re

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
