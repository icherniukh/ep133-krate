#!/usr/bin/env python3
"""
EP-133 KO-II Protocol Constants

MIDI SysEx protocol for Teenage Engineering EP-133.
Based on PROTOCOL.md and live analysis.
"""

from enum import IntEnum
import re

from ko2_encoding import decode_node_id, encode_14bit, encode_7bit, unpack_7bit


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
    slot_hi, slot_lo = encode_14bit(slot)
    return bytes([0x05, 0x08, 0x07, 0x02, slot_hi, slot_lo, 0x00, 0x00])


def build_download_init_request(slot: int) -> bytes:
    # Slot uses raw 16-bit big-endian (hi byte first). Same convention as
    # upload and delete. encode_7bit handles the 7-bit safety for slot_lo > 127.
    slot_hi = (slot >> 8) & 0xFF
    slot_lo = slot & 0xFF
    payload_raw = bytes(
        [
            0x03,  # FileOp.GET
            GET_INIT,
            slot_hi,
            slot_lo,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,  # 5-byte offset/padding
        ]
    )
    payload = encode_7bit(payload_raw)
    return bytes([CMD_FILE]) + payload


def build_download_chunk_request(page: int) -> bytes:
    # Little-endian 7-bit split per CLIENT.py
    page_hi, page_lo = encode_14bit(page)
    payload_raw = bytes([0x03, GET_DATA, page_lo, page_hi])  # FileOp.GET
    payload = encode_7bit(payload_raw)
    return bytes([CMD_FILE]) + payload


def build_delete_request(slot: int) -> bytes:
    """Build DELETE request. Slot uses big-endian encoding (hi, lo)."""
    slot_hi = (slot >> 8) & 0xFF
    slot_lo = slot & 0xFF
    payload_raw = bytes(
        [
            0x06,  # FileOp.DELETE
            slot_hi,
            slot_lo,
        ]
    )
    payload = encode_7bit(payload_raw)
    return bytes([CMD_FILE]) + payload


def build_upload_init_request(
    slot: int, file_size: int, channels: int, samplerate: int, name: str
) -> bytes:
    name_bytes = name.encode("utf-8")
    metadata = f'{{"channels":{channels},"samplerate":{samplerate}}}'.encode("utf-8")
    size_bytes = file_size.to_bytes(4, "big")

    # Slot encoding in upload init is big-endian (per UPLOAD_PROTOCOL_DETAILS.md)
    payload_raw = bytearray(
        [
            0x02,  # FileOp.PUT
            PUT_INIT,
            0x05,  # Audio file type
            (slot >> 8) & 0xFF,
            slot & 0xFF,
            (UPLOAD_PARENT_NODE >> 8) & 0xFF,
            UPLOAD_PARENT_NODE & 0xFF,
        ]
    )
    payload_raw.extend(size_bytes)
    payload_raw.extend(name_bytes)
    payload_raw.append(0x00)
    payload_raw.extend(metadata)

    # 7-bit pack the raw bytes. Note: the first byte after CMD_FILE is a 7-bit
    # packing MSB bitmap (not a semantic "operation flags" byte).
    return encode_7bit(bytes(payload_raw))


def build_upload_chunk_request(chunk_index: int, audio_data: bytes) -> bytes:
    payload_raw = bytearray(
        [
            0x02,  # FileOp.PUT
            PUT_DATA,
            (chunk_index >> 8) & 0xFF,
            chunk_index & 0xFF,
        ]
    )
    payload_raw.extend(audio_data)
    payload = encode_7bit(bytes(payload_raw))
    return bytes([CMD_FILE]) + payload


def build_upload_end_request(final_chunk_index: int) -> bytes:
    payload_raw = bytes(
        [
            0x02,  # FileOp.PUT
            PUT_DATA,
            (final_chunk_index >> 8) & 0xFF,
            final_chunk_index & 0xFF,
        ]
    )
    payload = encode_7bit(payload_raw)
    return bytes([CMD_FILE]) + payload


def build_file_list_request(node_id: int, page: int = 0) -> bytes:
    """Build FILE LIST request payload for a directory node.

    This is the mechanism used by the official tool / rcy to enumerate the
    EP-133 filesystem (e.g. node 1000 = /sounds/).

    Args:
        node_id: Directory node ID (e.g. 1000 for /sounds/)
        page: Page number (pagination)
    """
    payload_raw = bytes(
        [
            FileOp.LIST,
            (page >> 8) & 0xFF,
            page & 0xFF,
            (node_id >> 8) & 0xFF,
            node_id & 0xFF,
        ]
    )
    payload = encode_7bit(payload_raw)
    return bytes([CMD_FILE]) + payload


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
    payload_raw = bytes(
        [
            FileOp.METADATA,
            MetaType.GET,
            (node_id >> 8) & 0xFF,
            node_id & 0xFF,
            (page >> 8) & 0xFF,
            page & 0xFF,
        ]
    )
    payload = encode_7bit(payload_raw)
    return bytes([CMD_FILE]) + payload


def build_metadata_set_request(node_id: int, metadata_json: str) -> bytes:
    """Build FILE METADATA SET request payload for a node ID (filesystem node)."""
    metadata_bytes = metadata_json.encode("utf-8") + b"\x00"
    payload_raw = (
        bytes(
            [
                FileOp.METADATA,
                MetaType.SET,
                (node_id >> 8) & 0xFF,
                node_id & 0xFF,
            ]
        )
        + metadata_bytes
    )
    payload = encode_7bit(payload_raw)
    return bytes([CMD_FILE]) + payload


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
