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
    # Flag says data follows, but buffer ends
    bad_data = bytes([0x01])  # Flag for 1 byte, but no bytes follow
    with pytest.raises(TruncatedMessageError):
        Packed7.unpack(bad_data)

    # Valid flags, but data ends in middle of 7-byte chunk
    with pytest.raises(TruncatedMessageError):
        Packed7.unpack(bytes([0x03, 0x01]))  # Flag for 2 bytes, but only 1 follows


def test_packed7_invalid_flags():
    with pytest.raises(WireDataError):
        Packed7.unpack(bytes([0x80, 0x01]))  # Flags byte has bit 7 set
