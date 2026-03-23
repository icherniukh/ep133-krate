"""
MIDI transport abstraction for EP-133 KO-II device communication.

Provides a MidiTransport ABC that decouples the core client from mido so
the same client logic works on desktop (LocalMidiTransport) and on mobile
devices where mido/rtmidi are unavailable (RemoteMidiTransport over HTTP).
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


class RemoteMidiTransport(MidiTransport):
    """HTTP transport — for mobile use via the krate-bridge service."""

    def __init__(self, base_url: str = "http://localhost:8765") -> None:
        try:
            import httpx
        except ImportError as exc:
            raise ImportError(
                "httpx is required for RemoteMidiTransport. "
                "Install it with: pip install httpx"
            ) from exc
        self._client = httpx.Client(base_url=base_url, timeout=30.0)

    def send(self, msg: "mido.Message") -> None:
        self._client.post(
            "/midi/send",
            json={"type": msg.type, "data": list(msg.bytes())},
        )

    def receive(self, timeout: float = 5.0) -> Optional["mido.Message"]:
        if not _mido_available:
            raise RuntimeError("mido is required to decode received MIDI messages")
        resp = self._client.get("/midi/recv", params={"timeout": timeout})
        if resp.status_code == 204:
            return None
        data = resp.json()
        return mido.Message.from_bytes(data["data"])

    def close(self) -> None:
        self._client.close()
