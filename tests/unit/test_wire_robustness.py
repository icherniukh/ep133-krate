import pytest
from ko2_types import U7, U14, BE16, BE32, Packed7, WireDataError, TruncatedMessageError


def test_u7_validation():
    with pytest.raises(ValueError):
        U7(128)
    with pytest.raises(WireDataError):
        U7.decode(bytes([0x80]))


def test_u14_validation():
    with pytest.raises(ValueError):
        U14(16384)
    with pytest.raises(WireDataError):
        U14.decode(bytes([0x80, 0x00]))
    with pytest.raises(TruncatedMessageError):
        U14.decode(bytes([0x01]))


def test_packed7_edge_cases():
    # Length not multiple of 7
    data = b"hello"
    packed = Packed7.pack(data)
    assert len(packed) == 6  # 1 flags byte + 5 data
    assert Packed7.unpack(packed) == data

    # MSB handling
    data = bytes([0x80, 0x01])
    packed = Packed7.pack(data)
    assert packed[0] == 0x01  # First bit set
    assert Packed7.unpack(packed) == data


def test_packed7_truncation():
    # TE hardware occasionally sends dirty pack-flags (bits set for omitted bytes).
    # Unpack should gracefully process the available bytes.
    dirty_data = bytes([0x01])  # Flag bit set for 1 byte, but no bytes follow
    assert Packed7.unpack(dirty_data) == b""

    dirty_data_2 = bytes([0x03, 0x01])  # Flag bits set for 2 bytes, but only 1 follows
    assert Packed7.unpack(dirty_data_2) == bytes([0x81])


def test_packed7_invalid_flags():
    with pytest.raises(WireDataError):
        Packed7.unpack(bytes([0x80, 0x01]))  # Flags byte has bit 7 set
