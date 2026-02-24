"""
EP-133 Protocol Messages

Defines high-level command and response structures using declarative wire types.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from ko2_protocol import (
    SysExCmd, FileOp, GetType, MetaType,
    SYSEX_START, SYSEX_END, TE_MFG_ID, DEVICE_FAMILY, UPLOAD_PARENT_NODE
)
from ko2_wire import WireType, Packed7, BE16, BE32, U14, U14LE


@dataclass
class SysExMessage:
    """Base class for all EP-133 SysEx messages."""

    opcode: SysExCmd = SysExCmd.INIT

    def build(self, seq: int = 0) -> bytes:
        """Serialize the message to full SysEx bytes."""
        payload = self.pack_payload()
        # [F0] [00 20 76] [33 40] [CMD] [SEQ] ... [F7]
        header = bytes([SYSEX_START]) + TE_MFG_ID + DEVICE_FAMILY
        return header + bytes([self.opcode, seq]) + payload + bytes([SYSEX_END])

    def pack_payload(self) -> bytes:
        """Override in subclasses to define payload bit-packing."""
        return b""


@dataclass
class FileMessage(SysExMessage):
    """Base class for messages involving the CMD_FILE (0x05) group."""

    file_cmd: int = 0x05
    sub_byte: Optional[int] = None  # Optional byte before payload
    is_packed: bool = True          # Whether to use 7-bit packing

    def pack_payload(self) -> bytes:
        raw_payload = self.build_raw_payload()
        
        if self.is_packed:
            data = Packed7.pack(raw_payload)
        else:
            data = raw_payload

        result = bytes([self.file_cmd])
        if self.sub_byte is not None:
            result += bytes([self.sub_byte])
        result += data
        return result

    def build_raw_payload(self) -> bytes:
        """Override to define the 8-bit payload."""
        return b""


# --- Download Messages ---

@dataclass
class DownloadInitRequest(FileMessage):
    opcode: SysExCmd = SysExCmd.DOWNLOAD
    file_op: FileOp = FileOp.GET
    get_type: GetType = GetType.INIT
    slot: int = 0

    def build_raw_payload(self) -> bytes:
        return bytes([self.file_op, self.get_type]) + BE16(self.slot).encode() + b"\x00" * 5


@dataclass
class DownloadChunkRequest(FileMessage):
    opcode: SysExCmd = SysExCmd.DOWNLOAD
    file_op: FileOp = FileOp.GET
    get_type: GetType = GetType.DATA
    page: int = 0

    def build_raw_payload(self) -> bytes:
        return bytes([self.file_op, self.get_type]) + U14LE(self.page).encode()


# --- Upload Messages ---

@dataclass
class UploadInitRequest(FileMessage):
    opcode: SysExCmd = SysExCmd.UPLOAD_DATA
    file_op: FileOp = FileOp.PUT
    put_type: int = 0x00  # PUT_INIT
    file_type: int = 0x05  # Audio
    slot: int = 0
    parent_node: int = UPLOAD_PARENT_NODE
    file_size: int = 0
    name: str = ""
    metadata_json: str = ""

    def build_raw_payload(self) -> bytes:
        payload = bytearray([self.file_op, self.put_type, self.file_type])
        payload.extend(BE16(self.slot).encode())
        payload.extend(BE16(self.parent_node).encode())
        payload.extend(BE32(self.file_size).encode())
        payload.extend(self.name.encode("utf-8"))
        payload.append(0x00)
        payload.extend(self.metadata_json.encode("utf-8"))
        return bytes(payload)


@dataclass
class UploadChunkRequest(FileMessage):
    opcode: SysExCmd = SysExCmd.UPLOAD_DATA
    file_op: FileOp = FileOp.PUT
    put_type: int = 0x01  # PUT_DATA
    chunk_index: int = 0
    data: bytes = b""

    def build_raw_payload(self) -> bytes:
        return bytes([self.file_op, self.put_type]) + BE16(self.chunk_index).encode() + self.data


@dataclass
class UploadEndRequest(FileMessage):
    opcode: SysExCmd = SysExCmd.UPLOAD_END
    file_op: FileOp = FileOp.PUT
    put_type: int = 0x01  # PUT_DATA
    chunk_index: int = 0

    def build_raw_payload(self) -> bytes:
        return bytes([self.file_op, self.put_type]) + BE16(self.chunk_index).encode()


# --- File Operations ---

@dataclass
class DeleteRequest(FileMessage):
    opcode: SysExCmd = SysExCmd.UPLOAD
    file_op: FileOp = FileOp.DELETE
    slot: int = 0

    def build_raw_payload(self) -> bytes:
        return bytes([self.file_op]) + BE16(self.slot).encode()


@dataclass
class FileListRequest(FileMessage):
    opcode: SysExCmd = SysExCmd.LIST_FILES
    file_op: FileOp = FileOp.LIST
    node_id: int = UPLOAD_PARENT_NODE
    page: int = 0

    def build_raw_payload(self) -> bytes:
        return bytes([self.file_op]) + BE16(self.page).encode() + BE16(self.node_id).encode()


# --- Metadata Messages ---

@dataclass
class MetadataGetRequest(FileMessage):
    opcode: SysExCmd = SysExCmd.LIST_FILES
    file_op: FileOp = FileOp.METADATA
    meta_type: MetaType = MetaType.GET
    node_id: int = 0
    page: int = 0

    def build_raw_payload(self) -> bytes:
        return bytes([self.file_op, self.meta_type]) + BE16(self.node_id).encode() + BE16(self.page).encode()


@dataclass
class MetadataSetRequest(FileMessage):
    opcode: SysExCmd = SysExCmd.LIST_FILES
    file_op: FileOp = FileOp.METADATA
    meta_type: MetaType = MetaType.SET
    node_id: int = 0
    metadata_json: str = ""

    def build_raw_payload(self) -> bytes:
        return bytes([self.file_op, self.meta_type]) + BE16(self.node_id).encode() + \
               self.metadata_json.encode("utf-8") + b"\x00"


@dataclass
class MetadataGetLegacyRequest(FileMessage):
    """Legacy METADATA GET request (Cmd 0x75). 
    Uses a sub_byte 0x08 and is NOT 7-bit packed.
    """
    opcode: SysExCmd = SysExCmd.GET_META
    sub_byte: int = 0x08
    is_packed: bool = False
    slot: int = 0

    def build_raw_payload(self) -> bytes:
        return bytes([0x07, 0x02]) + U14(self.slot).encode() + b"\x00\x00"


@dataclass
class InfoRequest(SysExMessage):
    """Device info query (Cmd 0x77)."""
    opcode: SysExCmd = SysExCmd.INFO
    fixed_byte: int = 0x14
    sub_byte: int = 0x01

    def pack_payload(self) -> bytes:
        return bytes([self.fixed_byte, self.sub_byte])
