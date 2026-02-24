"""
EP-133 Protocol Messages

Defines high-level command and response structures.
"""

from dataclasses import dataclass, field
from ko2_protocol import SysExCmd, FileOp, GetType
from ko2_wire import BE16, U7


@dataclass
class DownloadInitRequest:
    """Request to initialize a file download."""

    opcode: SysExCmd = SysExCmd.DOWNLOAD
    seq: int = 0
    file_cmd: int = 0x05
    # The payload is usually 7-bit packed, but let's define the logical fields first.
    file_op: FileOp = FileOp.GET
    get_type: GetType = GetType.INIT
    slot: BE16 = field(default_factory=lambda: BE16(0))
    padding: bytes = b"\x00" * 5

    def build_payload(self) -> bytes:
        """Build the raw payload before 7-bit packing."""
        return bytes([self.file_op, self.get_type]) + self.slot.encode() + self.padding
