"""
EP-133 KO-II Protocol Layer

Defines the "Language" of the device using a Descriptor-based DSL.
Depends only on ko2_types.py for primitive types.
"""

from enum import IntEnum
from typing import Any, Dict, Optional, Type, TypeVar, ClassVar
from abc import ABC, abstractmethod
from ko2_types import WireType, Packed7, U7, BE16, BE32, U14, U14LE, RawBytes, NullBytes

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
SAMPLE_RATE = 46875
BIT_DEPTH = 16
CHANNELS = 1
MAX_SLOTS = 999
UPLOAD_CHUNK_SIZE = 433
UPLOAD_PARENT_NODE = 1000
UPLOAD_DELAY = 0.02
CMD_FILE = 0x05

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
    sub_byte: ClassVar[Optional[int]] = None
    is_packed: ClassVar[bool] = True

    def pack_payload(self) -> bytes:
        raw_payload = super().pack_payload()
        data = Packed7.pack(raw_payload) if self.is_packed else raw_payload
        result = bytes([self.file_cmd])
        if self.sub_byte is not None:
            result += bytes([self.sub_byte])
        return result + data

    @classmethod
    def from_bytes(cls: Type[M], data: bytes) -> M:
        offset = 1
        if cls.sub_byte is not None:
            offset += 1
        payload = data[offset:]
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
    opcode = SysExCmd.UPLOAD_DATA
    file_op = U7Field(default=FileOp.PUT)
    put_type = U7Field(default=0x00)
    file_type = U7Field(default=0x05)
    slot = BE16Field(default=0)
    parent_node = BE16Field(default=UPLOAD_PARENT_NODE)
    file_size = BE32Field(default=0)
    name = NullTerminatedStringField()
    metadata_json = JsonField()

class UploadChunkRequest(FileMessage):
    opcode = SysExCmd.UPLOAD_DATA
    file_op = U7Field(default=FileOp.PUT)
    put_type = U7Field(default=0x01)
    chunk_index = BE16Field(default=0)
    data = RawBytesField(default=b"")

class UploadEndRequest(FileMessage):
    """Empty PUT_DATA chunk that signals end-of-upload to the device.

    The official app sends a zero-byte PUT_DATA (same opcode as data chunks, 0x6C)
    at the next chunk index after the last data chunk. The device ACKs after this,
    then the client sends VERIFY. Using 0x6D (UPLOAD_END) here was wrong.
    Confirmed from captures/sniffer-upload21.jsonl.
    """
    opcode = SysExCmd.UPLOAD_DATA
    file_op = U7Field(default=FileOp.PUT)
    put_type = U7Field(default=0x01)
    chunk_index = BE16Field(default=0)

class DeleteRequest(FileMessage):
    opcode = SysExCmd.UPLOAD
    file_op = U7Field(default=FileOp.DELETE)
    slot = BE16Field(default=0)

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
    sub_byte = 0x08
    is_packed = False
    file_op = U7Field(default=0x07)
    meta_type = U7Field(default=0x02)
    slot = U14Field(default=0)
    padding = NullBytesField(length=2)

class InfoRequest(SysExMessage):
    opcode = SysExCmd.INFO
    fixed_byte = U7Field(default=0x14)
    sub_byte = U7Field(default=0x01)

# --- Responses ---

class SysExResponse(SysExMessage):
    file_cmd = U7Field(expected=0x05)
    sub_byte = U7Field(default=0)
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
    sub_byte = 0x00
    payload = RawBytesField(default=b"")


# --- Logical Helpers (Pure) ---

def decode_14bit(hi: int, lo: int) -> int:
    """Decode a 14-bit (hi/lo 7-bit) value."""
    return (hi << 7) | lo

def decode_node_id(hi: int, lo: int, name: str | None = None) -> int:
    node_id_16 = (hi << 8) | lo
    if hi > 0x7F or lo > 0x7F: return node_id_16
    node_id_14 = (hi << 7) | lo
    if name and name[:3].isdigit():
        prefix = int(name[:3])
        if node_id_14 - 1000 == prefix: return node_id_14
        if node_id_16 - 1000 == prefix: return node_id_16
    return node_id_14 if 1000 <= node_id_14 <= 12000 else node_id_16

def slot_from_sound_entry(entry: dict) -> int | None:
    nid = int(entry.get("node_id") or 0)
    if 1 <= nid <= 999: return nid
    if 1001 <= nid <= 1999: return nid - 1000
    import re
    m = re.match(r"^(\d{1,3})", str(entry.get("name") or ""))
    return int(m.group(1)) if m else None

def parse_file_list_response(payload: bytes) -> list[dict]:
    if len(payload) < 2: return []
    data, entries, offset = payload[2:], [], 0
    while offset + 7 <= len(data):
        hi, lo, flags = data[offset], data[offset+1], data[offset+2]
        size = int.from_bytes(data[offset+3:offset+7], "big")
        offset += 7
        name_bytes = bytearray()
        while offset < len(data) and data[offset] != 0:
            name_bytes.append(data[offset])
            offset += 1
        offset += 1
        name = bytes(name_bytes).decode("utf-8", errors="replace")
        entries.append({"node_id": decode_node_id(hi, lo, name), "flags": flags, "size": size, "name": name, "is_dir": bool(flags & 0x02)})
    return entries
