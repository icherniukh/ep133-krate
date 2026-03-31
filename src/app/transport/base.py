"""Backward-compat re-export — canonical location is core.transport."""

from core.transport import MIDITransport, MIDIDevice, _SysExMsg  # noqa: F401

__all__ = ["MIDITransport", "MIDIDevice", "_SysExMsg"]
