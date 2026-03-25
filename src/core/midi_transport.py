"""
MIDI transport abstraction for EP-133 KO-II device communication.

Provides a MidiTransport ABC that decouples EP133Client from mido.
Desktop use: LocalMidiTransport wraps a mido port pair.
Mobile use: the Toga companion app talks directly to the krate-bridge
HTTP API (/slots, /upload, /slots/{slot}) — it does not use EP133Client
or MidiTransport at all. The bridge runs on a Mac/PC with mido available.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

try:
    import mido
    _mido_available = True
except ImportError:
    mido = None  # type: ignore[assignment]
    _mido_available = False


class MidiTransport(ABC):
    """Abstract MIDI transport interface."""

    @abstractmethod
    def send(self, msg: "mido.Message") -> None:
        """Send a MIDI message to the device."""
        ...

    @abstractmethod
    def receive(self, timeout: float = 5.0) -> Optional["mido.Message"]:
        """Receive the next MIDI message, or None if timeout expires."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release transport resources."""
        ...


class LocalMidiTransport(MidiTransport):
    """Wraps an existing mido port pair — for desktop use."""

    def __init__(self, in_port: "mido.ports.Input", out_port: "mido.ports.Output") -> None:
        self._in = in_port
        self._out = out_port

    def send(self, msg: "mido.Message") -> None:
        self._out.send(msg)

    def receive(self, timeout: float = 5.0) -> Optional["mido.Message"]:
        return self._in.receive(timeout=timeout, block=True)

    def close(self) -> None:
        self._in.close()
        self._out.close()


