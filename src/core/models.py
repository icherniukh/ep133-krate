"""
EP-133 KO-II Protocol Layer

Defines the "Language" of the device using a Descriptor-based DSL.
Depends only on core.types.py for primitive types.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Dict, Optional, Type, TypeVar, ClassVar
from abc import ABC, abstractmethod
from .types import WireType, Packed7, U7, BE16, BE32, U14, U14LE, RawBytes, NullBytes

# --- Protocol Opcodes & Constants ---

SYSEX_START = 0xF0
SYSEX_END = 0xF7
TE_MFG_ID = bytes([0x00, 0x20, 0x76])
DEVICE_FAMILY = bytes([0x33, 0x40])
HDR_PREFIX = TE_MFG_ID + DEVICE_FAMILY

class SysExCmd(IntEnum):
    INIT = 0x61
    LIST_FILES = 0x6A
    PLAYBACK = 0x76
    INFO = 0x77
    GET_META = 0x75
    PROJECT = 0x7C
    UPLOAD_DATA = 0x6C
    UPLOAD_END = 0x6D
    UPLOAD = 0x7E
    DOWNLOAD = 0x7D
    RESPONSE = 0x37
    RESPONSE_ALT = 0x3D

class FileOp(IntEnum):
    INIT = 0x01
    PUT = 0x02
    GET = 0x03
    LIST = 0x04
    PLAYBACK = 0x05
    DELETE = 0x06
    METADATA = 0x07
    VERIFY = 0x0B

class GetType(IntEnum):
    INIT = 0x00
    DATA = 0x01

class MetaType(IntEnum):
    SET = 0x01
    GET = 0x02

# Device Constraints
MAX_SAMPLE_RATE = 46875
SAMPLE_RATE = MAX_SAMPLE_RATE  # backward-compat alias
BIT_DEPTH = 16
CHANNELS = 1
MAX_SLOTS = 999
UPLOAD_CHUNK_SIZE = 433
UPLOAD_PARENT_NODE = 1000
UPLOAD_DELAY = 0.02
CMD_FILE = 0x05

# Size-band thresholds (bytes). All frontends share these so colour
# gradients stay consistent across rendering targets.
_SIZE_BANDS: list[tuple[int, int]] = [
    (0,                  50 * 1024),
    (50 * 1024,         200 * 1024),
    (200 * 1024,        500 * 1024),
    (500 * 1024,      1024 * 1024),
    (1024 * 1024,   2 * 1024 * 1024),
    (2 * 1024 * 1024, 10 * 1024 * 1024),
]


@dataclass
class Sample:
    """A sample in a slot on the EP-133."""
    slot: int
    name: str
    sym: str = ""
    samplerate: int = MAX_SAMPLE_RATE
    format: str = "s16"
    channels: int = 1
    channels_known: bool = False
    size_bytes: int = 0
    duration: float = 0.0
    is_empty: bool = False

    @classmethod
    def empty(cls, slot: int) -> "Sample":
        return cls(slot=slot, name="(empty)", is_empty=True)

    @property
    def formatted_size(self) -> str:
        return Sample.format_size(self.size_bytes)

    @property
    def duration_str(self) -> str:
        return Sample.format_duration(self.size_bytes, self.samplerate, self.channels)

    @property
    def channels_abbr(self) -> str:
        return Sample.channels_label(self.channels)

    @property
    def slot_id(self) -> str:
        return f"{self.slot:03d}"

    @property
    def size_band(self) -> tuple[int, float] | None:
        return Sample.size_band_for(self.size_bytes)

    @staticmethod
    def format_size(size_bytes: int) -> str:
        if size_bytes <= 0:
            return "-"
        if size_bytes < 1024:
            return f"{size_bytes:5}B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:7.2f}K"
        return f"{size_bytes / (1024 * 1024):7.2f}M"

    @staticmethod
    def format_duration(size_bytes: int, samplerate: int = MAX_SAMPLE_RATE, channels: int = 1) -> str:
        if size_bytes <= 0 or samplerate <= 0 or channels <= 0:
            return "-"
        bytes_per_frame = 2 * channels
        samples = size_bytes // bytes_per_frame
        return f"{samples / samplerate:.3f}"

    @staticmethod
    def channels_label(n: int) -> str:
        if n == 2:
            return "S"
        if n == 1:
            return "M"
        return "-"

    @staticmethod
    def size_band_for(size_bytes: int) -> tuple[int, float] | None:
        if size_bytes <= 0:
            return None
        for i, (lo, hi) in enumerate(_SIZE_BANDS):
            if size_bytes < hi:
                return (i, (size_bytes - lo) / (hi - lo))
        return (len(_SIZE_BANDS) - 1, 1.0)


# Backward-compat alias
SampleInfo = Sample


# --- Descriptor DSL ---

class Field(ABC):
    def __init__(self, wire_type=None, default=None, expected=None, length=None):
        self.wire_type = wire_type
        self.default = default
        self.expected = expected
        self.length = length
        self.name = None

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner):
        if instance is None: return self
        return instance._values.get(self.name, self.default)

    def __set__(self, instance, value):
        if self.expected is not None and value != self.expected:
            raise ValueError(f"Expected {self.expected} for {self.name}, got {value}")
        instance._values[self.name] = value

    def pack(self, instance) -> bytes:
        val = self.__get__(instance, type(instance))
        if self.wire_type:
            if self.wire_type == NullBytes:
                return NullBytes(self.length).encode()
            if val is None:
                raise ValueError(f"Missing required value for field '{self.name}'")
            return self.wire_type(val).encode()
        return b""

    def unpack(self, data: bytes, offset: int) -> tuple[Any, int]:
        if self.wire_type:
            if self.wire_type == NullBytes:
                obj, consumed = NullBytes.decode(data[offset:], self.length)
                return None, consumed
            obj, consumed = self.wire_type.decode(data[offset:])
            return obj.to_python(), consumed
        return None, 0

class U7Field(Field):
    def __init__(self, **kwargs): super().__init__(wire_type=U7, **kwargs)
class BE16Field(Field):
    def __init__(self, **kwargs): super().__init__(wire_type=BE16, **kwargs)
class BE32Field(Field):
    def __init__(self, **kwargs): super().__init__(wire_type=BE32, **kwargs)
class U14Field(Field):
    def __init__(self, **kwargs): super().__init__(wire_type=U14, **kwargs)
class U14LEField(Field):
    def __init__(self, **kwargs): super().__init__(wire_type=U14LE, **kwargs)
class RawBytesField(Field):
    def __init__(self, **kwargs): super().__init__(wire_type=RawBytes, **kwargs)
class NullBytesField(Field):
    def __init__(self, length, **kwargs): super().__init__(wire_type=NullBytes, length=length, **kwargs)

class NullTerminatedStringField(Field):
    def pack(self, instance) -> bytes:
        val = self.__get__(instance, type(instance)) or ""
        return val.encode("utf-8") + b"\x00"

    def unpack(self, data: bytes, offset: int) -> tuple[str, int]:
        end = data.find(b"\x00", offset)
        if end == -1: end = len(data)
        val = data[offset:end].decode("utf-8", errors="replace")
        return val, (end - offset + 1)

class JsonField(Field):
    def pack(self, instance) -> bytes:
        import json
        val = self.__get__(instance, type(instance)) or {}
        if isinstance(val, str): return val.encode("utf-8")
        return json.dumps(val, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    def unpack(self, data: bytes, offset: int) -> tuple[dict, int]:
        import json
        raw = data[offset:].rstrip(b"\x00")
        try:
            return json.loads(raw.decode("utf-8")), len(data) - offset
        except json.JSONDecodeError:
            return {}, len(data) - offset


# --- Base Message Structures ---

class MessageMeta(type):
    def __new__(mcs, name, bases, namespace):
        fields = []
        for key, value in list(namespace.items()):
            if isinstance(value, Field):
                fields.append((key, value))
        
        base_fields = []
        for base in bases:
            if hasattr(base, "_fields"):
                base_fields.extend(base._fields)
        
        namespace["_fields"] = base_fields + fields
        return super().__new__(mcs, name, bases, namespace)

M = TypeVar("M", bound="SysExMessage")

class SysExMessage(metaclass=MessageMeta):
    """Base class for all EP-133 SysEx messages."""
    opcode: ClassVar[SysExCmd] = SysExCmd.INIT
    _registry: ClassVar[Dict[int, Type["SysExMessage"]]] = {}

    def __init__(self, **kwargs):
        self._values = {}
        for name, field in self._fields:
            if field.expected is not None:
                self._values[name] = field.expected
            elif name in kwargs:
                self._values[name] = kwargs[name]
            elif field.default is not None:
                self._values[name] = field.default

    @classmethod
    def register(cls, opcode: int):
        def wrapper(subclass):
            cls._registry[opcode] = subclass
            return subclass
        return wrapper

    def build(self, seq: int = 0) -> bytes:
        """Serialize message to full SysEx bytes."""
        payload = self.pack_payload()
        header = bytes([SYSEX_START]) + HDR_PREFIX + bytes([self.opcode, seq])
        return header + payload + bytes([SYSEX_END])

    def pack_payload(self) -> bytes:
        """Serialize all descriptor fields."""
        data = b""
        for name, field in self._fields:
            data += field.pack(self)
        return data

    @classmethod
    def from_bytes(cls: Type[M], data: bytes) -> M:
        """Deserialize from raw bytes (payload after seq byte)."""
        instance = cls()
        offset = 0
        for name, field in cls._fields:
            if offset >= len(data) and not isinstance(field, NullBytesField):
                break
            val, consumed = field.unpack(data, offset)
            if val is not None:
                instance._values[name] = val
            offset += consumed
        return instance

class FileMessage(SysExMessage):
    """Base class for 0x05 group messages."""
    file_cmd: ClassVar[int] = 0x05
    is_packed: ClassVar[bool] = True

    def pack_payload(self) -> bytes:
        raw_payload = super().pack_payload()
        data = Packed7.pack(raw_payload) if self.is_packed else raw_payload
        return bytes([self.file_cmd]) + data

    @classmethod
    def from_bytes(cls: Type[M], data: bytes) -> M:
        payload = data[1:]
        if cls.is_packed:
            payload = Packed7.unpack(payload)
        
        instance = cls()
        field_offset = 0
        for name, field in cls._fields:
            if field_offset >= len(payload): break
            val, consumed = field.unpack(payload, field_offset)
            if val is not None:
                instance._values[name] = val
            field_offset += consumed
        return instance

# --- Concrete Messages ---

class DownloadInitRequest(FileMessage):
    opcode = SysExCmd.DOWNLOAD
    file_op = U7Field(default=FileOp.GET)
    get_type = U7Field(default=GetType.INIT)
    slot = BE16Field(default=0)
    padding = NullBytesField(length=5)

class DownloadChunkRequest(FileMessage):
    opcode = SysExCmd.DOWNLOAD
    file_op = U7Field(default=FileOp.GET)
    get_type = U7Field(default=GetType.DATA)
    page = U14LEField(default=0)

class UploadInitRequest(FileMessage):
    opcode = SysExCmd.UPLOAD
    file_op = U7Field(default=FileOp.PUT)
    put_type = U7Field(default=0x00)
    file_type = U7Field(default=0x05)
    slot = BE16Field(default=0)
    parent_node = BE16Field(default=UPLOAD_PARENT_NODE)
    file_size = BE32Field(default=0)
    name = NullTerminatedStringField()
    metadata_json = JsonField()

class UploadChunkRequest(FileMessage):
    opcode = SysExCmd.UPLOAD
    file_op = U7Field(default=FileOp.PUT)
    put_type = U7Field(default=0x01)
    chunk_index = BE16Field(default=0)
    data = RawBytesField(default=b"")

class UploadEndRequest(FileMessage):
    """Empty PUT chunk that signals end-of-upload to the device.

    The official app sends a zero-byte PUT chunk at the next chunk index
    after the last data chunk. The device ACKs after this, then the client
    sends VERIFY. Confirmed from tests/fixtures/sniffer-upload21.jsonl — all
    upload messages use opcode 0x7E (UPLOAD).
    """
    opcode = SysExCmd.UPLOAD
    file_op = U7Field(default=FileOp.PUT)
    put_type = U7Field(default=0x01)
    chunk_index = BE16Field(default=0)

class UploadVerifyRequest(FileMessage):
    """VERIFY command sent after the empty sentinel chunk and after METADATA SET.

    Wire payload: 0B <slot_hi> <slot_lo> (3 bytes, no sub byte).
    Confirmed from tests/fixtures/sniffer-upload-kick-official.jsonl:
    both VERIFYs around META_SET use payload 0B 00 61 for slot 97.
    Official sequence: empty sentinel → ACK → VERIFY → METADATA SET → ACK → VERIFY
    """
    opcode = SysExCmd.UPLOAD
    file_op = U7Field(default=FileOp.VERIFY)
    slot = BE16Field(default=0)

class DeleteRequest(FileMessage):
    opcode = SysExCmd.UPLOAD
    file_op = U7Field(default=FileOp.DELETE)
    slot = BE16Field(default=0)

class AuditionRequest(FileMessage):
    """Trigger on-device sample preview (PROT-001).

    Decoded payload (12 bytes):
      [0x05][action][slot_hi][slot_lo][0x00×6][parent_node_hi][parent_node_lo]

    Confirmed from captures:
      sniffer-2026-03-10-165130.jsonl: slots 1–4, raw=050100NN00000000000003e8
      sniffer-2026-03-10-173014.jsonl: slots 501–808, raw=050101NN/050103NN confirmed
    Slot is BE16 at bytes [2:4]. The TE Sample Tool uses rotating devids 0x60–0x6A;
    we use the fixed FILE devid (0x6A) for predictable response matching.
    action: 0x01=play. parent_node=UPLOAD_PARENT_NODE targets sounds root.
    """
    opcode = SysExCmd.LIST_FILES
    file_op = U7Field(default=FileOp.PLAYBACK)
    action = U7Field(default=0x01)
    slot = BE16Field(default=1)
    padding = NullBytesField(length=6)
    parent_node = BE16Field(default=UPLOAD_PARENT_NODE)

class FileListRequest(FileMessage):
    opcode = SysExCmd.LIST_FILES
    file_op = U7Field(default=FileOp.LIST)
    page = BE16Field(default=0)
    node_id = BE16Field(default=UPLOAD_PARENT_NODE)

class MetadataGetRequest(FileMessage):
    opcode = SysExCmd.LIST_FILES
    file_op = U7Field(default=FileOp.METADATA)
    meta_type = U7Field(default=MetaType.GET)
    node_id = BE16Field(default=0)
    page = BE16Field(default=0)

class MetadataSetRequest(FileMessage):
    opcode = SysExCmd.LIST_FILES
    file_op = U7Field(default=FileOp.METADATA)
    meta_type = U7Field(default=MetaType.SET)
    node_id = BE16Field(default=0)
    metadata_json = JsonField()

class MetadataGetLegacyRequest(FileMessage):
    opcode = SysExCmd.GET_META
    file_op = U7Field(default=0x07)
    meta_type = U7Field(default=0x02)
    slot = BE16Field(default=0)
    padding = NullBytesField(length=2)

class InfoRequest(SysExMessage):
    opcode = SysExCmd.INFO
    fixed_byte = U7Field(default=0x14)
    sub_cmd = U7Field(default=0x01)

# --- Responses ---

class SysExResponse(SysExMessage):
    file_cmd = U7Field(expected=0x05)
    status = U7Field(default=0)
    payload = RawBytesField(default=b"")

    @classmethod
    def from_sysex(cls, data: bytes) -> Optional["SysExResponse"]:
        if len(data) < 10: return None
        target_cls = cls._registry.get(data[6], GenericResponse)
        return target_cls.from_bytes(data[8:-1])

@SysExMessage.register(SysExCmd.RESPONSE)
class GenericResponse(SysExResponse):
    pass

@SysExMessage.register(SysExCmd.LIST_FILES - 0x40)  # 0x2A File List Response
class FileListResponse(FileMessage):
    payload = RawBytesField(default=b"")

@SysExMessage.register(SysExCmd.DOWNLOAD - 0x40)  # 0x3D
class DownloadInitResponse(FileMessage):
    file_op = U7Field(expected=0x03)
    get_type = U7Field(expected=0x00)
    file_type = U7Field(expected=0x05)
    file_size = BE32Field(default=0)
    filename = NullTerminatedStringField()


# --- Protocol Payload Decoders ---

def decode_14bit(hi: int, lo: int) -> int:
    """Decode a 14-bit (hi/lo 7-bit) value."""
    return (hi << 7) | lo

def decode_node_id(hi: int, lo: int, name: str | None = None) -> int:
    """Decode node_id from LIST response as BE16 (confirmed from device capture)."""
    return (hi << 8) | lo

def slot_from_sound_entry(entry: dict) -> int | None:
    import re
    name = str(entry.get("name") or "")
    m = re.match(r"^(\d{1,3})", name)
    prefix = int(m.group(1)) if m else None

    nid = int(entry.get("node_id") or 0)
    if 1 <= nid <= 999:
        if prefix is not None and prefix != nid:
            return prefix
        return nid
    if 1001 <= nid <= 1999:
        mapped = nid - 1000
        if prefix is not None and prefix != mapped:
            return prefix
        return mapped
    return prefix

def parse_file_list_response(payload: bytes) -> list[dict]:
    if len(payload) < 2:
        return []
    data, entries, offset = payload[2:], [], 0
    while offset + 7 <= len(data):
        hi, lo, flags = data[offset], data[offset + 1], data[offset + 2]
        size = int.from_bytes(data[offset + 3 : offset + 7], "big")
        offset += 7
        name_bytes = bytearray()
        while offset < len(data) and data[offset] != 0:
            name_bytes.append(data[offset])
            offset += 1
        if offset >= len(data):
            break
        offset += 1
        name = bytes(name_bytes).decode("utf-8", errors="replace")
        entries.append(
            {
                "node_id": decode_node_id(hi, lo, name),
                "flags": flags,
                "size": size,
                "name": name,
                "is_dir": bool(flags & 0x02),
            }
        )
    return entries
