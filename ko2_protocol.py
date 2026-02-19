#!/usr/bin/env python3
"""
EP-133 KO-II Protocol Constants

MIDI SysEx protocol for Teenage Engineering EP-133.
Based on PROTOCOL.md and live analysis.
"""

from enum import IntEnum


# --- Protocol Constants ---


class SysExCmd(IntEnum):
    """EP-133 SysEx Commands (DEPRECATED - use DeviceId enum instead)"""

    # Query/Read Commands
    GET_INFO = 0x77  # Get device info
    GET_META = 0x75  # Get sample metadata

    # Device Commands
    DEV_ID = 0x06  # Device identity query
    SWITCH_PROJ = 0x7C  # Switch project


class RspCmd(IntEnum):
    """EP-133 Response Commands"""

    INFO = 0x37  # Info/data response (device byte)
    META = 0x35  # Metadata response


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


# Device IDs (third byte of device identification)
class DeviceId(IntEnum):
    """Device ID byte for different operations"""

    INIT = 0x61  # Initialization
    PLAYBACK = 0x76  # Playback/audition
    INFO = 0x77  # Device info, metadata
    GET_META = 0x75  # Get sample metadata
    PROJECT = 0x7C  # Project switching (NEW - from external repos)
    UPLOAD_DATA = 0x6C  # Upload data transfer (init + chunks)
    UPLOAD = 0x7E  # Upload operations (commit, delete, move)
    DOWNLOAD = 0x7D  # File download (GET)
    RESPONSE = 0x37  # Standard device response
    RESPONSE_ALT = 0x3D  # Alternative device response (observed in downloads)


# EP-133 Manufacturer ID + Device Family (prefix before device ID)
HDR_PREFIX = TE_MFG_ID + DEVICE_FAMILY


# Full header with device ID for different operations
def build_header(device_id: int) -> bytes:
    """Build SysEx header F0 + TE_MFG_ID + DEVICE_FAMILY + device_id"""
    return bytes([SYSEX_START]) + TE_MFG_ID + DEVICE_FAMILY + bytes([device_id])


# SysEx End
END = bytes([SYSEX_END])

# Command groups
CMD_FILE = 0x05  # FILE operations command group

# Common patterns in requests
PAT_META_REQ = bytes([0x05, 0x08, 0x07, 0x02])  # Metadata request pattern
PAT_DATA_REQ = bytes([0x05, 0x08, 0x03, 0x01, 0x00])  # Data request pattern
PAT_DATA_PREP = bytes([0x05, 0x00, 0x03, 0x01, 0x00])  # Data preparation pattern
PAT_DATA_RSP = bytes([0x05, 0x00, 0x02, 0x00])  # Data response header

# Fixed bytes
FIXED_BYTE = 0x00  # Fixed byte in most messages
E_EMPTY = bytes([0x00, 0x00])  # Empty slot marker in requests


# --- Sample/Device Constants ---

SAMPLE_RATE = 44100  # EP-133 sample rate (Hz) - must be 44100 for uploads
BIT_DEPTH = 16  # 16-bit audio
CHANNELS = 1  # Mono
MAX_SLOTS = 999  # Maximum sample slots

# --- Upload Constants ---

UPLOAD_CHUNK_SIZE = 433  # Max bytes per chunk (after 7-bit unpacking)
UPLOAD_PARENT_NODE = 1000  # Parent node ID for /sounds/ directory
UPLOAD_DELAY = 0.02  # Delay between chunks (20ms) - device needs this


# --- Helper Functions ---


def encode_slot(slot: int) -> tuple[int, int]:
    """Encode slot number (1-999) to 7-bit MIDI bytes (little-endian).

    Used for metadata queries and other operations.

    Returns:
        (high_byte, low_byte) - little-endian order
    """
    if not (1 <= slot <= MAX_SLOTS):
        raise ValueError(f"Slot must be 1-{MAX_SLOTS}, got {slot}")

    low = slot & 0x7F
    high = (slot >> 7) & 0x7F
    return high, low


def encode_slot_be(slot: int) -> tuple[int, int]:
    """Encode slot number (1-999) to 7-bit MIDI bytes (big-endian).

    Used for download operations (GET).

    Returns:
        (high_byte, low_byte) - big-endian order
    """
    if not (1 <= slot <= MAX_SLOTS):
        raise ValueError(f"Slot must be 1-{MAX_SLOTS}, got {slot}")

    high = (slot >> 7) & 0x7F
    low = slot & 0x7F
    return high, low


def decode_slot(high: int, low: int) -> int:
    """Decode 7-bit MIDI bytes to slot number (little-endian).

    Returns:
        Slot number (1-999)
    """
    return ((high & 0x7F) << 7) | (low & 0x7F)


def decode_slot_be(high: int, low: int) -> int:
    """Decode 7-bit MIDI bytes to slot number (big-endian).

    Returns:
        Slot number (1-999)
    """
    return ((high & 0x7F) << 7) | (low & 0x7F)


def build_sysex(data: bytes) -> bytes:
    """Build complete SysEx message with header and end.

    Args:
        data: Command and payload bytes

    Returns:
        Complete SysEx message (F0 ... data ... F7)
    """
    return bytes([SYSEX_START]) + TE_MFG_ID + DEVICE_FAMILY + data + END


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

    # Convert to string, keeping valid ASCII and JSON structural chars
    # EP-133 inserts null bytes between characters, so we filter them out
    json_str = "".join(
        chr(b) if (32 <= b < 127 or b in [123, 125, 58, 44]) else ""
        for b in data[offset:]
    )

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
