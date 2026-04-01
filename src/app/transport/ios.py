"""iOS MIDI transport — CoreMIDI via ObjC MIDIBridge + rubicon-objc."""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Callable, Optional

from core.transport import MIDITransport, MIDIDevice

_log = logging.getLogger(__name__)

def _objc():
    try:
        from rubicon.objc import ObjCClass, ns_from_py
        from rubicon.objc.api import py_from_ns
    except ImportError as exc:
        raise RuntimeError(
            "rubicon-objc is required for iOS MIDI transport"
        ) from exc
    return ObjCClass, ns_from_py, py_from_ns


class IOSMIDITransport(MIDITransport):

    def __init__(self) -> None:
        ObjCClass, _, __ = _objc()
        self._bridge = ObjCClass("MIDIBridge").alloc().init()
        self._device: Optional[MIDIDevice] = None
        self._callback: Optional[Callable[[bytes], None]] = None
        self._rx_queue: deque[bytes] = deque()

    def discover_devices(self) -> list[MIDIDevice]:
        raw_devices = self._bridge.discoverDevices()
        if not raw_devices:
            return []
        devices = []
        for info in raw_devices:
            name = str(info.objectForKey_("name") or "Unknown")
            has_in_obj = info.objectForKey_("hasInput")
            has_out_obj = info.objectForKey_("hasOutput")
            has_in = bool(has_in_obj.boolValue) if has_in_obj is not None else False
            has_out = bool(has_out_obj.boolValue) if has_out_obj is not None else False
            devices.append(MIDIDevice(
                name=name,
                source_id=name,
                destination_id=name,
                has_input=has_in,
                has_output=has_out,
            ))
        return devices

    def connect(self, device: MIDIDevice) -> None:
        _, ns_from_py, __ = _objc()
        ok = self._bridge.connectToDevice_(ns_from_py(device.name))
        if not ok:
            raise RuntimeError(f"Failed to connect to {device.name}")
        self._device = device
        _log.info("iOS: connected to %s", device.name)

    def disconnect(self) -> None:
        self._bridge.disconnect()
        self._device = None
        self._rx_queue.clear()

    def send_sysex(self, data: bytes) -> None:
        _, ns_from_py, __ = _objc()
        ns_data = ns_from_py(data)
        ok = self._bridge.sendSysEx_(ns_data)
        if not ok:
            raise RuntimeError("iOS: MIDIBridge sendSysEx failed")

    def receive_sysex(self, timeout: float = 1.0) -> Optional[bytes]:
        _, __, py_from_ns = _objc()
        
        if self._rx_queue:
            msg = self._rx_queue.pop(0)
            if self._callback:
                self._callback(msg)
            return msg

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            messages = self._bridge.drainReceivedMessages()
            # NSArray (ObjCListInstance): None if nil, len() gives count.
            if messages is not None and len(messages) > 0:
                for i in range(len(messages)):
                    ns_data = messages[i]        # ObjCListInstance supports [i]
                    raw: bytes = py_from_ns(ns_data)
                    self._rx_queue.append(raw)
                
                if self._rx_queue:
                    msg = self._rx_queue.pop(0)
                    if self._callback:
                        self._callback(msg)
                    return msg
            time.sleep(0.005)
        return None

    def set_receive_callback(self, cb: Optional[Callable[[bytes], None]]) -> None:
        self._callback = cb

    @property
    def is_connected(self) -> bool:
        return bool(self._bridge.isConnected)
