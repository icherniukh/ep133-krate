from typing import Optional

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
