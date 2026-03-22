"""Sample name sanitization for EP-133 upload.

The device stores names as ASCII in metadata JSON. Non-ASCII characters
(Cyrillic, CJK, accented Latin, etc.) become '?' on the device. This
module transliterates unicode to ASCII-safe equivalents before upload.
"""
from __future__ import annotations

import re

from unidecode import unidecode


def sanitize_sample_name(name: str) -> str:
    """Transliterate and clean a sample name for the EP-133.

    - Cyrillic, accented Latin, CJK → ASCII via unidecode
    - Strip non-printable characters
    - Collapse whitespace
    """
    if not name:
        return name
    ascii_name = unidecode(name)
    ascii_name = re.sub(r"[^\x20-\x7E]", "", ascii_name)
    ascii_name = re.sub(r"\s+", " ", ascii_name).strip()
    return ascii_name or name
