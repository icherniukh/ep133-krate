import pytest


def test_7bit_pack_unpacks_to_original():
    from ko2_protocol import encode_7bit, unpack_7bit

    raw = bytes([0x07, 0x02, 0x03, 0xE8, 0x00, 0x00])  # METADATA GET node_id=1000, page=0
    assert unpack_7bit(encode_7bit(raw)) == raw


def test_node_1000_wire_pattern_contains_03_68():
    from ko2_protocol import encode_7bit

    raw = bytes([0x07, 0x02, 0x03, 0xE8, 0x00, 0x00])
    enc = encode_7bit(raw)
    # 0xE8 becomes 0x68 on the wire, with MSB recorded in the pack-flags byte.
    assert enc == bytes([0x08, 0x07, 0x02, 0x03, 0x68, 0x00, 0x00])
