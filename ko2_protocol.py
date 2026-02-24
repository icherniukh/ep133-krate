#!/usr/bin/env python3
"""
EP-133 KO-II Protocol Constants

MIDI SysEx protocol for Teenage Engineering EP-133.
Based on PROTOCOL.md and live analysis.
"""

from enum import IntEnum
import re

from ko2_wire import BE16, BE32, Packed7, U14


# --- Node ID Decoding Logic ---


def _parse_slot_prefix(name: str) -> int | None:
    if len(name) < 3:
        return None
    if name[:3].isdigit():
        try:
            return int(name[:3])
        except ValueError:
            return None
    return None


def decode_node_id(hi: int, lo: int, name: str | None = None) -> int:
    """Decode node ID from hi/lo bytes.

    Some firmwares emit 14-bit (7-bit split) node IDs in FILE LIST responses.
    If bytes are already 8-bit (hi/lo > 0x7F), use 16-bit decode.
    Otherwise, use filename prefix to disambiguate when possible.
    """
    node_id_16 = (hi << 8) | lo
    if hi > 0x7F or lo > 0x7F:
        return node_id_16

    # 14-bit split (7-bit MIDI encoding)
    node_id_14 = decode_14bit(hi, lo)
    slot_prefix = _parse_slot_prefix(name or "")
    if slot_prefix is not None:
        if node_id_14 - 1000 == slot_prefix:
            return node_id_14
        if node_id_16 - 1000 == slot_prefix:
            return node_id_16

    # Prefer 14-bit if it lands in expected EP-133 node ranges.
    if 1000 <= node_id_14 <= 12000:
        return node_id_14
    return node_id_16


def decode_14bit(hi: int, lo: int) -> int:
    """Decode a 14-bit (hi/lo 7-bit) value."""
    return (hi << 7) | lo


# --- Protocol Constants ---


class FileOp(IntEnum):
    """FILE operations (second byte after TE_SYSEX_FILE=0x05)"""

    INIT = 0x01  # Initialize communication
    PUT = 0x02  # Upload file
    GET = 0x03  # Download file
    LIST = 0x04  # List files
    PLAYBACK = 0x05  # Playback control
    DELETE = 0x06  # Delete sample
    METADATA = 0x07  # Metadata operations
    VERIFY = 0x0B  # Verify commit (used in upload sequence)


class GetType(IntEnum):
    """GET sub-operation types"""

    INIT = 0x00  # Initialize download
    DATA = 0x01  # Request data chunk


class MetaType(IntEnum):
    """METADATA sub-operation types"""

    SET = 0x01  # Set metadata
    GET = 0x02  # Get metadata


# --- MIDI Protocol Structure ---

# SysEx markers
SYSEX_START = 0xF0
SYSEX_END = 0xF7

# Teenage Engineering Manufacturer ID
TE_MFG_ID = bytes([0x00, 0x20, 0x76])

# Device family (always 33 40)
DEVICE_FAMILY = bytes([0x33, 0x40])


class SysExCmd(IntEnum):
    """EP-133 SysEx Opcodes (Command Bytes)"""

    # Core Commands
    INIT = 0x61  # Initialization
    PLAYBACK = 0x76  # Playback/audition
    INFO = 0x77  # Device info, metadata
    GET_META = 0x75  # Get sample metadata
    PROJECT = 0x7C  # Project switching
    UPLOAD_DATA = 0x6C  # Upload data transfer (init + chunks)
    UPLOAD_END = 0x6D  # Upload end marker (end-of-upload)
    UPLOAD = 0x7E  # Upload operations (commit, delete, move)
    DOWNLOAD = 0x7D  # File download (GET)
    RESPONSE = 0x37  # Standard device response
    RESPONSE_ALT = 0x3D  # Alternative device response (observed in downloads)

    # Legacy/Alias Commands
    DEV_ID = 0x06  # Device identity query


class RspCmd(IntEnum):
    """EP-133 Response Commands"""

    INFO = 0x37  # Info/data response (device byte)
    META = 0x35  # Metadata response


# EP-133 Manufacturer ID + Device Family (prefix before device ID)
HDR_PREFIX = TE_MFG_ID + DEVICE_FAMILY


# Full header with device ID for different operations
def build_header(cmd: SysExCmd) -> bytes:
    """Build SysEx header F0 + TE_MFG_ID + DEVICE_FAMILY + cmd"""
    return bytes([SYSEX_START]) + TE_MFG_ID + DEVICE_FAMILY + bytes([cmd])


# SysEx End
END = bytes([SYSEX_END])

# Command groups
CMD_FILE = 0x05  # FILE operations command group
FIXED_BYTE = 0x00  # Fixed byte in most messages

# Command sub-operations
GET_INIT = 0x00
GET_DATA = 0x01
PUT_INIT = 0x00
PUT_DATA = 0x01

# Metadata sub-operations
META_GET = 0x02
META_SET = 0x01

# --- Sample/Device Constants ---

SAMPLE_RATE = 46875  # EP-133 native sample rate (Hz)
BIT_DEPTH = 16  # 16-bit audio
CHANNELS = 1  # Mono
MAX_SLOTS = 999  # Maximum sample slots

# --- Upload Constants ---

UPLOAD_CHUNK_SIZE = 433  # Max bytes per chunk (after 7-bit unpacking)
UPLOAD_PARENT_NODE = 1000  # Parent node ID for /sounds/ directory (0x03E8)
UPLOAD_DELAY = 0.02  # Delay between chunks (20ms) - device needs this


# --- Helper Functions ---


def slot_from_sound_entry(entry: dict) -> int | None:
    """Resolve a sample slot number (1-999) from a /sounds FILE LIST entry.

    /sounds is a filesystem directory (node_id=1000). Child nodes commonly use:
      node_id 1001..1999  => slot = node_id - 1000
      node_id 1..999      => slot = node_id (newer firmwares)

    As a fallback, some firmwares include the slot as a filename prefix like
    "850 ..." or "850.wav". We parse a leading 1-3 digit prefix.
    """
    try:
        node_id = int(entry.get("node_id") or 0)
    except Exception:
        node_id = 0

    if 1 <= node_id <= MAX_SLOTS:
        return node_id

    if 1001 <= node_id <= 1999:
        slot = node_id - 1000
        if 1 <= slot <= MAX_SLOTS:
            return slot

    name = str(entry.get("name") or "")
    m = re.match(r"^(\d{1,3})", name)
    if not m:
        return None
    try:
        slot = int(m.group(1))
    except Exception:
        return None
    return slot if 1 <= slot <= MAX_SLOTS else None


def build_sysex(data: bytes) -> bytes:
    """Build complete SysEx message with header and end.

    Args:
        data: Command and payload bytes

    Returns:
        Complete SysEx message (F0 ... data ... F7)
    """
    return bytes([SYSEX_START]) + TE_MFG_ID + DEVICE_FAMILY + data + bytes([SYSEX_END])


def build_info_request(slot: int) -> bytes:
    """Build METADATA GET request. Returns raw bytes (no 7-bit encoding needed).
    Format: 05 08 07 02 [slot_hi_7bit] [slot_lo_7bit] 00 00
    Confirmed working against device. Uses 0x08 as fixed byte (not 0x00).
    """
    return bytes([0x05, 0x08, 0x07, 0x02]) + U14(slot).encode() + b"\x00\x00"


def build_download_init_request(slot: int) -> bytes:
    # Slot uses raw 16-bit big-endian (hi byte first).
    payload_raw = bytes([FileOp.GET, GET_INIT]) + BE16(slot).encode() + b"\x00" * 5
    return bytes([CMD_FILE]) + Packed7.pack(payload_raw)


def build_download_chunk_request(page: int) -> bytes:
    # Page uses 14-bit little-endian split (lo then hi) per observed traffic.
    # Note: U14(page).encode() returns [hi, lo], so we swap for this specific op.
    u14 = U14(page).encode()
    payload_raw = bytes([FileOp.GET, GET_DATA, u14[1], u14[0]])
    return bytes([CMD_FILE]) + Packed7.pack(payload_raw)


def build_delete_request(slot: int) -> bytes:
    """Build DELETE request. Slot uses big-endian encoding (hi, lo)."""
    payload_raw = bytes([FileOp.DELETE]) + BE16(slot).encode()
    return bytes([CMD_FILE]) + Packed7.pack(payload_raw)


def build_upload_init_request(
    slot: int, file_size: int, channels: int, samplerate: int, name: str
) -> bytes:
    name_bytes = name.encode("utf-8")
    metadata = f'{{"channels":{channels},"samplerate":{samplerate}}}'.encode("utf-8")

    # Slot encoding in upload init is big-endian
    payload_raw = bytearray(
        [
            FileOp.PUT,
            PUT_INIT,
            0x05,  # Audio file type
        ]
    )
    payload_raw.extend(BE16(slot).encode())
    payload_raw.extend(BE16(UPLOAD_PARENT_NODE).encode())
    payload_raw.extend(BE32(file_size).encode())
    payload_raw.extend(name_bytes)
    payload_raw.append(0x00)
    payload_raw.extend(metadata)

    return Packed7.pack(bytes(payload_raw))


def build_upload_chunk_request(chunk_index: int, audio_data: bytes) -> bytes:
    payload_raw = (
        bytes([FileOp.PUT, PUT_DATA]) + BE16(chunk_index).encode() + audio_data
    )
    return bytes([CMD_FILE]) + Packed7.pack(payload_raw)


def build_upload_end_request(final_chunk_index: int) -> bytes:
    payload_raw = bytes([FileOp.PUT, PUT_DATA]) + BE16(final_chunk_index).encode()
    return bytes([CMD_FILE]) + Packed7.pack(payload_raw)


def build_file_list_request(node_id: int, page: int = 0) -> bytes:
    """Build FILE LIST request payload for a directory node."""
    payload_raw = bytes([FileOp.LIST]) + BE16(page).encode() + BE16(node_id).encode()
    return bytes([CMD_FILE]) + Packed7.pack(payload_raw)


def parse_file_list_response(payload: bytes) -> list[dict]:
    """Parse decoded payload from a FILE LIST response.

    Payload format (decoded/unpacked) matches references/rcy:
    - First 2 bytes: header/unknown
    - Then repeated entries:
      [node_hi node_lo flags size_b3 size_b2 size_b1 size_b0] [name 0-terminated]
    """
    if len(payload) < 2:
        return []

    data = payload[2:]
    entries: list[dict] = []
    offset = 0

    while offset + 7 <= len(data):
        hi = data[offset]
        lo = data[offset + 1]
        flags = data[offset + 2]
        size = (
            (data[offset + 3] << 24)
            | (data[offset + 4] << 16)
            | (data[offset + 5] << 8)
            | data[offset + 6]
        )
        offset += 7

        name_bytes = bytearray()
        while offset < len(data) and data[offset] != 0:
            name_bytes.append(data[offset])
            offset += 1
        offset += 1  # skip null terminator (or end)

        name = bytes(name_bytes).decode("utf-8", errors="replace")
        node_id = decode_node_id(hi, lo, name)
        if name:
            entries.append(
                {
                    "node_id": node_id,
                    "flags": flags,
                    "size": size,
                    "name": name,
                    "is_dir": bool(flags & 0x02),
                }
            )

    return entries


def parse_file_list_response_raw(payload: bytes) -> list[dict]:
    """Parse decoded payload from a FILE LIST response without decoding node IDs."""
    if len(payload) < 2:
        return []

    data = payload[2:]
    entries: list[dict] = []
    offset = 0

    while offset + 7 <= len(data):
        hi = data[offset]
        lo = data[offset + 1]
        flags = data[offset + 2]
        size = (
            (data[offset + 3] << 24)
            | (data[offset + 4] << 16)
            | (data[offset + 5] << 8)
            | data[offset + 6]
        )
        offset += 7

        name_bytes = bytearray()
        while offset < len(data) and data[offset] != 0:
            name_bytes.append(data[offset])
            offset += 1
        offset += 1  # skip null terminator (or end)

        name = bytes(name_bytes).decode("utf-8", errors="replace")
        if name:
            entries.append(
                {
                    "hi": hi,
                    "lo": lo,
                    "flags": flags,
                    "size": size,
                    "name": name,
                    "is_dir": bool(flags & 0x02),
                }
            )

    return entries


def build_metadata_get_request(node_id: int, page: int = 0) -> bytes:
    """Build FILE METADATA GET request payload for a node ID (filesystem node)."""
    payload_raw = (
        bytes([FileOp.METADATA, MetaType.GET])
        + BE16(node_id).encode()
        + BE16(page).encode()
    )
    return bytes([CMD_FILE]) + Packed7.pack(payload_raw)


def build_metadata_set_request(node_id: int, metadata_json: str) -> bytes:
    """Build FILE METADATA SET request payload for a node ID (filesystem node)."""
    payload_raw = (
        bytes([FileOp.METADATA, MetaType.SET])
        + BE16(node_id).encode()
        + metadata_json.encode("utf-8")
        + b"\x00"
    )
    return bytes([CMD_FILE]) + Packed7.pack(payload_raw)


def parse_json_from_sysex(data: bytes, offset: int = 10) -> dict | None:
    """Extract and parse JSON from SysEx response.

    Args:
        data: Raw SysEx response bytes
        offset: Bytes to skip before JSON (default: 10)

    Returns:
        Parsed JSON dict, or None if parsing fails

    Note:
        The EP-133 inserts null bytes throughout JSON and may truncate responses.
        This function filters null bytes and extracts key-value pairs manually
        to handle truncation gracefully.
    """
    import re

    if len(data) < offset:
        return None

    # Convert to string, dropping only null bytes (EP-133 inserts 0x00 between chars)
    raw = bytes(b for b in data[offset:] if b != 0)
    json_str = raw.decode("utf-8", errors="ignore")
    if "{" in json_str:
        json_str = json_str[json_str.find("{") :]

    # Extract JSON object
    if "{" not in json_str:
        return None

    # Use regex to extract key-value pairs
    # Pattern: "key":value where value is string, number, or boolean
    result = {}

    # Find string key-value pairs like "name":"value"
    for match in re.finditer(r'"([^"]+)":"([^"]*)"', json_str):
        key, value = match.groups()
        result[key] = value

    # Find numeric key-value pairs like "samplerate":46875
    for match in re.finditer(r'"([^"]+)":(-?\d+)', json_str):
        key, value = match.groups()
        try:
            result[key] = int(value)
        except ValueError:
            pass

    # Find boolean key-value pairs
    for match in re.finditer(r'"([^"]+)":(true|false)', json_str):
        key, value = match.groups()
        result[key] = value == "true"

    # Return result if we found at least one field
    return result if result else None
