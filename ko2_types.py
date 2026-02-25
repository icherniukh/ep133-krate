"""
EP-133 Wire-Format Layer

Defines atomic MIDI data types and packing logic for the EP-133 protocol.
Ensures 7-bit MIDI constraints are enforced at the type level.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Sequence, Type, TypeVar, Union


class WireError(Exception):
    """Base class for wire-format errors."""
    pass


class WireDataError(WireError):
    """Data does not conform to MIDI/Wire constraints."""
    pass


class TruncatedMessageError(WireError):
    """Message was shorter than expected."""
    pass


T = TypeVar("T", bound="WireType")


class WireType(ABC):
    """Base class for all EP-133 wire-format types."""

    @abstractmethod
    def encode(self) -> bytes:
        """Encode the value into its wire representation."""
        pass

    @classmethod
    @abstractmethod
    def decode(cls: Type[T], data: bytes) -> tuple[T, int]:
        """Decode from bytes, returning (instance, bytes_consumed)."""
        pass

    @abstractmethod
    def to_python(self) -> Any:
        """Convert to standard Python type (int, bytes, etc.)."""
        pass


class U7(WireType):
    """A single 7-bit MIDI data byte (0-127)."""

    def __init__(self, value: int):
        if not 0 <= value <= 127:
            raise ValueError(f"U7 value must be 0-127, got {value}")
        self.value = value

    def encode(self) -> bytes:
        return bytes([self.value])

    @classmethod
    def decode(cls, data: bytes) -> tuple["U7", int]:
        if not data:
            raise TruncatedMessageError("Empty data for U7 decode")
        val = data[0]
        if val > 127:
            raise WireDataError(f"U7 byte must be <= 127, got 0x{val:02x}")
        return cls(val), 1

    def to_python(self) -> int:
        return self.value

    def __int__(self) -> int:
        return self.value


class U14(WireType):
    """A 14-bit value split into two 7-bit MIDI bytes (hi, lo)."""

    def __init__(self, value: int):
        if not 0 <= value <= 16383:
            raise ValueError(f"U14 value must be 0-16383, got {value}")
        self.value = value

    def encode(self) -> bytes:
        hi = (self.value >> 7) & 0x7F
        lo = self.value & 0x7F
        return bytes([hi, lo])

    @classmethod
    def decode(cls, data: bytes) -> tuple["U14", int]:
        if len(data) < 2:
            raise TruncatedMessageError("Insufficient data for U14 decode")
        hi, lo = data[0], data[1]
        if hi > 127 or lo > 127:
            raise WireDataError(f"U14 bytes must be <= 127, got 0x{hi:02x} 0x{lo:02x}")
        value = (hi << 7) | lo
        return cls(value), 2

    def to_python(self) -> int:
        return self.value

    def __int__(self) -> int:
        return self.value


class U14LE(U14):
    """A 14-bit value split into two 7-bit MIDI bytes (lo, hi)."""

    def encode(self) -> bytes:
        u14 = super().encode()
        return bytes([u14[1], u14[0]])

    @classmethod
    def decode(cls, data: bytes) -> tuple["U14LE", int]:
        if len(data) < 2:
            raise TruncatedMessageError("Insufficient data for U14LE decode")
        lo, hi = data[0], data[1]
        if hi > 127 or lo > 127:
            raise WireDataError(f"U14LE bytes must be <= 127")
        value = (hi << 7) | lo
        return cls(value), 2


class BE16(WireType):
    """A 16-bit Big-Endian value (raw bytes, not 7-bit safe)."""

    def __init__(self, value: int):
        if not 0 <= value <= 65535:
            raise ValueError(f"BE16 value must be 0-65535, got {value}")
        self.value = value

    def encode(self) -> bytes:
        return bytes([(self.value >> 8) & 0xFF, self.value & 0xFF])

    @classmethod
    def decode(cls, data: bytes) -> tuple["BE16", int]:
        if len(data) < 2:
            raise TruncatedMessageError("Insufficient data for BE16 decode")
        value = (data[0] << 8) | data[1]
        return cls(value), 2

    def to_python(self) -> int:
        return self.value

    def __int__(self) -> int:
        return self.value


class BE32(WireType):
    """A 32-bit Big-Endian value (raw bytes, not 7-bit safe)."""

    def __init__(self, value: int):
        if not 0 <= value <= 0xFFFFFFFF:
            raise ValueError(f"BE32 value must be 0-0xFFFFFFFF, got {value}")
        self.value = value

    def encode(self) -> bytes:
        return self.value.to_bytes(4, "big")

    @classmethod
    def decode(cls, data: bytes) -> tuple["BE32", int]:
        if len(data) < 4:
            raise TruncatedMessageError("Insufficient data for BE32 decode")
        value = int.from_bytes(data[:4], "big")
        return cls(value), 4

    def to_python(self) -> int:
        return self.value

    def __int__(self) -> int:
        return self.value


class RawBytes(WireType):
    """Variable-length raw bytes."""

    def __init__(self, value: bytes):
        self.value = value

    def encode(self) -> bytes:
        return self.value

    @classmethod
    def decode(cls, data: bytes) -> tuple["RawBytes", int]:
        # Variable length decode consumes ALL remaining data
        return cls(data), len(data)

    def to_python(self) -> bytes:
        return self.value


class NullBytes(WireType):
    """Fixed-length null padding."""

    def __init__(self, length: int):
        self.length = length

    def encode(self) -> bytes:
        return b"\x00" * self.length

    @classmethod
    def decode(cls, data: bytes, length: int = 0) -> tuple["NullBytes", int]:
        if len(data) < length:
            raise TruncatedMessageError(f"Expected {length} null bytes")
        return cls(length), length

    def to_python(self) -> None:
        return None


class Packed7:
    """TE-specific 8-to-7 bit packing (every 7 bytes becomes 8)."""

    @staticmethod
    def pack(data: bytes) -> bytes:
        result = bytearray()
        for i in range(0, len(data), 7):
            chunk = data[i : i + 7]
            flags = 0
            encoded = []
            for j, b in enumerate(chunk):
                if b & 0x80:
                    flags |= 1 << j
                encoded.append(b & 0x7F)
            result.append(flags)
            result.extend(encoded)
        return bytes(result)

    @staticmethod
    def unpack(data: bytes) -> bytes:
        result = bytearray()
        i = 0
        while i < len(data):
            flags = data[i]
            if flags > 127:
                raise WireDataError(f"Packed7 flags byte must be <= 127, got 0x{flags:02x}")
            i += 1
            for bit in range(7):
                if i >= len(data):
                    # If we have more bits set in flags but no data bytes left, 
                    # the message is truncated.
                    remaining_flags = flags >> bit
                    if remaining_flags != 0:
                        raise TruncatedMessageError("Packed7 data ended before flags were exhausted")
                    break
                msb = ((flags >> bit) & 1) << 7
                result.append((data[i] & 0x7F) | msb)
                i += 1
        return bytes(result)
