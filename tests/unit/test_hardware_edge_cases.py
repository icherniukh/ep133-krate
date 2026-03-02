import pytest
from ko2_models import FileListResponse
from ko2_types import Packed7, WireDataError, TruncatedMessageError


def test_file_list_response_handles_invalid_file_payload():
    """
    The device returns 'invalid file' with a leading 0x80 byte when querying
    a missing or invalid node. This broke strict parsing. FileListResponse
    should treat the entire unpacked body as RawBytesField to avoid crashing.
    """
    # Simulate an invalid file payload with a high byte (0x80)
    # The actual payload we saw was: b'\x80invali\x00 \xe6il\xe5\xa0\x80d'
    # We will just ensure FileListResponse doesn't crash on high bytes in payload.
    payload = b'\x80invalid file'
    
    # Create the raw SysEx bytes for a FileListResponse (opcode = 0x2A)
    # The payload starts after CMD_FILE (0x05) and native pack_flags
    packed_payload = bytes([0x05]) + Packed7.pack(payload)

    resp = FileListResponse.from_bytes(packed_payload)
    # Now it should be a RawBytesField which accepts anything
    assert resp.payload == payload

def test_packed7_truncation_dirty_flags():
    """
    TE hardware occasionally sends dirty pack-flags (bits set for omitted bytes).
    Unpack should gracefully process the available bytes.
    """
    dirty_data = bytes([0x01])  # Flag bit set for 1 byte, but no bytes follow
    assert Packed7.unpack(dirty_data) == b""

    dirty_data_2 = bytes([0x03, 0x01])  # Flag bits set for 2 bytes, but only 1 follows
    assert Packed7.unpack(dirty_data_2) == bytes([0x81])
