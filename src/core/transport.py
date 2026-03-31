"""Abstract MIDI transport — platform-agnostic interface for send/receive.

Canonical location for the transport ABC, device model, and SysEx message
wrapper.  Platform-specific implementations (DesktopMIDITransport,
IOSMIDITransport) live in their respective modules and import from here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class MIDIDevice:
    name: str
    source_id: str = ""
    destination_id: str = ""
    has_input: bool = False
    has_output: bool = False
    platform_data: dict = field(default_factory=dict)

    @property
    def is_bidirectional(self) -> bool:
        return self.has_input and self.has_output


class MIDITransport(ABC):
    """Platform-agnostic MIDI transport.

    EP133Client calls send_sysex(), receive_sysex(), and close() on this.
    The UI layer calls discover_devices(), connect(), disconnect().
    """

    @abstractmethod
    def discover_devices(self) -> list[MIDIDevice]: ...

    @abstractmethod
    def connect(self, device: MIDIDevice) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def send_sysex(self, data: bytes) -> None: ...

    @abstractmethod
    def receive_sysex(self, timeout: float = 1.0) -> Optional[bytes]: ...

    def set_receive_callback(self, cb: Optional[Callable[[bytes], None]]) -> None:
        pass

    def send(self, msg) -> None:
        if hasattr(msg, "type") and msg.type == "sysex":
            raw = bytes([0xF0]) + bytes(msg.data) + bytes([0xF7])
            self.send_sysex(raw)

    def receive(self, timeout: float = 1.0):
        raw = self.receive_sysex(timeout=timeout)
        if raw is None:
            return None
        data = raw[1:-1] if len(raw) >= 2 else raw
        return _SysExMsg(data)

    def close(self) -> None:
        self.disconnect()

    @property
    def is_connected(self) -> bool:
        return False


class _SysExMsg:
    __slots__ = ("type", "data")

    def __init__(self, data: bytes):
        self.type = "sysex"
        self.data = data
