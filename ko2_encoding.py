"""Encoding utilities for EP-133 SysEx payloads."""


def encode_7bit(data: bytes) -> bytes:
    """Encode true 8-bit data to TE's 7-bit MIDI format.
    Every 7 bytes becomes 8 bytes, with MSBs in the first flag byte.
    """
    # SysEx data bytes must be 0..127, so we move each input byte's MSB
    # into a shared flags byte (bit j == MSB of byte j), then emit the
    # 7 stripped bytes. unpack_7bit reverses this.
    result = bytearray()
    i = 0
    while i < len(data):
        chunk = data[i : i + 7]
        flags = 0
        encoded_bytes = []
        for j, b in enumerate(chunk):
            if b & 0x80:
                flags |= 1 << j
            encoded_bytes.append(b & 0x7F)
        result.append(flags)
        result.extend(encoded_bytes)
        i += 7
    return bytes(result)


def unpack_7bit(data: bytes) -> bytes:
    """Unpack TE's 7-bit encoded data back to 8-bit."""
    result = bytearray()
    i = 0
    while i < len(data):
        if i >= len(data):
            break
        flags = data[i]
        i += 1
        for bit in range(7):
            if i >= len(data):
                break
            msb = ((flags >> bit) & 1) << 7
            result.append((data[i] & 0x7F) | msb)
            i += 1
    return bytes(result)


def encode_14bit(value: int) -> tuple[int, int]:
    """Encode a value as 14-bit (hi/lo 7-bit) bytes."""
    return (value >> 7) & 0x7F, value & 0x7F


def decode_14bit(hi: int, lo: int) -> int:
    """Decode a 14-bit (hi/lo 7-bit) value."""
    return (hi << 7) | lo


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
