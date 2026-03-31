"""Cross-platform MIDI transport factory."""

from __future__ import annotations

import sys
from core.transport import MIDITransport, MIDIDevice


def create_transport(**kwargs) -> MIDITransport:
    if sys.platform == "ios":
        from .ios import IOSMIDITransport
        return IOSMIDITransport(**kwargs)

    from core.desktop_transport import DesktopMIDITransport
    return DesktopMIDITransport(**kwargs)


__all__ = ["MIDITransport", "MIDIDevice", "create_transport"]
