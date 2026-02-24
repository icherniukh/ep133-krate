"""
EP-133 Wire-Format Layer

Defines atomic MIDI data types and packing logic for the EP-133 protocol.
Ensures 7-bit MIDI constraints are enforced at the type level.
"""

from abc import ABC, abstractmethod
from typing import Any, Sequence


class WireType(ABC):
    """Base class for all EP-133 wire-format types."""

    @abstractmethod
    def encode(self) -> bytes:
        """Encode the value into its wire representation."""
        pass

    @classmethod
    @abstractmethod
    def decode(cls, data: bytes) -> tuple["WireType", int]:
        """Decode from bytes, returning (instance, bytes_consumed)."""
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
            raise ValueError("Empty data for U7 decode")
        return cls(data[0]), 1

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
            raise ValueError("Insufficient data for U14 decode")
        value = (data[0] << 7) | (data[1] & 0x7F)
        return cls(value), 2

    def __int__(self) -> int:
        return self.value


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
            raise ValueError("Insufficient data for BE16 decode")
        value = (data[0] << 8) | data[1]
        return cls(value), 2

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
            raise ValueError("Insufficient data for BE32 decode")
        value = int.from_bytes(data[:4], "big")
        return cls(value), 4

    def __int__(self) -> int:
        return self.value


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
            i += 1
            for bit in range(7):
                if i >= len(data):
                    break
                msb = ((flags >> bit) & 1) << 7
                result.append((data[i] & 0x7F) | msb)
                i += 1
        return bytes(result)
