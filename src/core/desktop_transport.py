"""Desktop MIDI transport — mido + rtmidi for CLI/TUI on macOS/Linux."""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from .transport import MIDITransport, MIDIDevice

_log = logging.getLogger(__name__)

try:
    import mido
    _mido_available = True
except ImportError:
    mido = None  # type: ignore[assignment]
    _mido_available = False


class DesktopMIDITransport(MIDITransport):

    def __init__(self) -> None:
        self._outport = None
        self._inport = None
        self._device: Optional[MIDIDevice] = None
        self._callback: Optional[Callable[[bytes], None]] = None

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_devices(self) -> list[MIDIDevice]:
        if not _mido_available:
            return []

        sources = set(mido.get_input_names())
        dests = set(mido.get_output_names())
        all_names = sources | dests

        devices = []
        for name in sorted(all_names):
            if "Session 1" in name or "Network Session" in name:
                continue
            devices.append(MIDIDevice(
                name=name,
                source_id=name if name in sources else "",
                destination_id=name if name in dests else "",
                has_input=name in sources,
                has_output=name in dests,
            ))
        return devices

    @classmethod
    def find_ep133(cls) -> Optional[MIDIDevice]:
        """Locate an EP-133 in available MIDI ports."""
        if not _mido_available:
            return None
        sources = set(mido.get_input_names())
        for port in mido.get_output_names():
            if "EP-133" in port or "EP-1320" in port:
                return MIDIDevice(
                    name=port,
                    source_id=port if port in sources else "",
                    destination_id=port,
                    has_input=port in sources,
                    has_output=True,
                )
        return None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self, device: MIDIDevice) -> None:
        if not _mido_available:
            raise RuntimeError("mido is not installed")

        self.disconnect()

        if device.has_output:
            self._outport = mido.open_output(device.destination_id)
        if device.has_input:
            self._inport = mido.open_input(device.source_id)

        self._device = device
        _log.info("Connected to %s", device.name)

    def disconnect(self) -> None:
        if self._outport:
            self._outport.close()
            self._outport = None
        if self._inport:
            self._inport.close()
            self._inport = None
        self._device = None

    # ------------------------------------------------------------------
    # Send / Receive
    # ------------------------------------------------------------------

    def send_sysex(self, data: bytes) -> None:
        if not self._outport:
            raise RuntimeError("Not connected — no output port")
        inner = data[1:-1] if len(data) >= 2 else data
        self._outport.send(mido.Message("sysex", data=list(inner)))

    def receive_sysex(self, timeout: float = 1.0) -> Optional[bytes]:
        if not self._inport:
            return None

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for msg in self._inport.iter_pending():
                if msg.type == "sysex":
                    raw = bytes([0xF0]) + bytes(msg.data) + bytes([0xF7])
                    if self._callback:
                        self._callback(raw)
                    return raw

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            parser_queue = getattr(self._inport, "_queue", None)
            raw_queue = getattr(parser_queue, "_queue", None)
            if raw_queue is not None and hasattr(raw_queue, "get"):
                from queue import Empty
                try:
                    msg = raw_queue.get(timeout=min(remaining, 0.1))
                    if msg.type == "sysex":
                        raw = bytes([0xF0]) + bytes(msg.data) + bytes([0xF7])
                        if self._callback:
                            self._callback(raw)
                        return raw
                except Empty:
                    continue
            else:
                time.sleep(0.001)

        return None

    def set_receive_callback(self, cb: Optional[Callable[[bytes], None]]) -> None:
        self._callback = cb

    @property
    def is_connected(self) -> bool:
        return self._device is not None
