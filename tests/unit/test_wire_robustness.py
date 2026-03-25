import pytest
from core.types import U7, U14, Packed7, WireDataError, TruncatedMessageError


# ---------------------------------------------------------------------------
# U7 validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [128, 255, 16383])
def test_u7_value_too_large(value):
    with pytest.raises(ValueError):
        U7(value)


@pytest.mark.parametrize("raw", [bytes([0x80]), bytes([0xFF])])
def test_u7_decode_invalid_byte(raw):
    with pytest.raises(WireDataError):
        U7.decode(raw)


# ---------------------------------------------------------------------------
# U14 validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [16384, 32767, 65535])
def test_u14_value_too_large(value):
    with pytest.raises(ValueError):
        U14(value)


@pytest.mark.parametrize("raw,exc", [
    (bytes([0x80, 0x00]), WireDataError),
    (bytes([0x01]),       TruncatedMessageError),
])
def test_u14_decode_invalid(raw, exc):
    with pytest.raises(exc):
        U14.decode(raw)


# ---------------------------------------------------------------------------
# Packed7 edge cases
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Packed7 truncation (TE hardware dirty pack-flags)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dirty_data,expected", [
    (bytes([0x01]),       b""),             # Flag bit set for 1 byte, no bytes follow
    (bytes([0x03, 0x01]), bytes([0x81])),   # Flag bits set for 2 bytes, only 1 follows
])
def test_packed7_truncation(dirty_data, expected):
    # TE hardware occasionally sends dirty pack-flags (bits set for omitted bytes).
    # Unpack should gracefully process the available bytes.
    assert Packed7.unpack(dirty_data) == expected


def test_packed7_invalid_flags():
    with pytest.raises(WireDataError):
        Packed7.unpack(bytes([0x80, 0x01]))  # Flags byte has bit 7 set
