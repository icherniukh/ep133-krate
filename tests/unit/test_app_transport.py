"""
Unit tests for the MIDI transport abstraction (core/transport.py)
and the EP133Client transport injection path.

All tests run without real MIDI hardware by mocking transports.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# MIDITransport ABC
# ---------------------------------------------------------------------------


class TestMIDITransportABC:
    def test_cannot_instantiate_abstract_class(self):
        from core.transport import MIDITransport

        with pytest.raises(TypeError):
            MIDITransport()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_all_methods(self):
        from core.transport import MIDITransport

        class Incomplete(MIDITransport):
            def discover_devices(self): return []
            def connect(self, device): pass
            # missing disconnect, send_sysex, receive_sysex

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# iOS receive queue (pure-Python bridge; no ObjC or MIDI access)
# ---------------------------------------------------------------------------


@pytest.fixture
def ios_receiver(monkeypatch):
    from app.transport import ios

    bridge = MagicMock()
    bridge.alloc.return_value.init.return_value = bridge
    py_from_ns = MagicMock(side_effect=bytes)
    monkeypatch.setattr(
        ios, "_objc",
        lambda: (MagicMock(return_value=bridge), MagicMock(), py_from_ns),
    )
    return ios.IOSMIDITransport(), bridge, py_from_ns


class TestIOSMIDITransportReceive:
    @pytest.mark.parametrize("with_callback", [False, True])
    def test_cached_messages_are_consumed_fifo(self, ios_receiver, with_callback):
        transport, bridge, py_from_ns = ios_receiver
        messages = [b"\xf0\x01\xf7", b"\xf0\x02\xf7"]
        transport._rx_queue.extend(messages)
        delivered = []
        if with_callback:
            transport.set_receive_callback(delivered.append)

        for index, message in enumerate(messages):
            assert transport.receive_sysex(timeout=0) == message
            assert list(transport._rx_queue) == messages[index + 1:]
            assert delivered == (messages[:index + 1] if with_callback else [])

        bridge.drainReceivedMessages.assert_not_called()
        py_from_ns.assert_not_called()

    @pytest.mark.parametrize("with_callback", [False, True])
    def test_drained_batch_is_consumed_fifo(self, ios_receiver, with_callback):
        transport, bridge, py_from_ns = ios_receiver
        messages = [b"\xf0\x01\xf7", b"\xf0\x02\xf7", b"\xf0\x03\xf7"]
        native_messages = [bytearray(message) for message in messages]
        bridge.drainReceivedMessages.return_value = native_messages
        delivered = []
        if with_callback:
            transport.set_receive_callback(delivered.append)

        for index, message in enumerate(messages):
            received = transport.receive_sysex(timeout=1 if index == 0 else 0)
            assert isinstance(received, bytes)
            assert received == message
            assert list(transport._rx_queue) == messages[index + 1:]
            assert delivered == (messages[:index + 1] if with_callback else [])

        bridge.drainReceivedMessages.assert_called_once_with()
        assert py_from_ns.call_args_list == [call(message) for message in native_messages]

    @pytest.mark.parametrize("empty_batch", [None, []])
    def test_empty_receive_times_out(self, ios_receiver, monkeypatch, empty_batch):
        from app.transport import ios

        transport, bridge, py_from_ns = ios_receiver
        bridge.drainReceivedMessages.return_value = empty_batch
        callback = MagicMock()
        transport.set_receive_callback(callback)
        clock = MagicMock()
        clock.monotonic.side_effect = [10.0, 10.0, 11.0]
        monkeypatch.setattr(ios, "time", clock)

        assert transport.receive_sysex(timeout=0.5) is None
        assert not transport._rx_queue
        bridge.drainReceivedMessages.assert_called_once_with()
        clock.sleep.assert_called_once_with(0.005)
        callback.assert_not_called()
        py_from_ns.assert_not_called()


# ---------------------------------------------------------------------------
# EP133Client backward compatibility (transport=None, auto-creates desktop)
# ---------------------------------------------------------------------------


class TestEP133ClientBackwardCompat:
    """EP133Client with no transport= kwarg auto-creates a DesktopMIDITransport."""

    def test_init_raises_without_device(self, monkeypatch):
        from core.client import EP133Client, DeviceNotFoundError
        monkeypatch.setattr("core.client.find_device", lambda: None)
        with pytest.raises(DeviceNotFoundError):
            EP133Client(device_name=None)

    def test_init_accepts_explicit_device_name(self, monkeypatch):
        """Constructor succeeds when a device name is given directly."""
        from core.client import EP133Client
        from core.desktop_transport import DesktopMIDITransport
        client = EP133Client(device_name="EP-133 MIDI")
        assert client.device_name == "EP-133 MIDI"
        assert isinstance(client._transport, DesktopMIDITransport)

    def test_auto_creates_transport(self, monkeypatch):
        from core.client import EP133Client
        from core.desktop_transport import DesktopMIDITransport
        monkeypatch.setattr("core.client.find_device", lambda: "EP-133 MIDI")
        client = EP133Client()
        assert isinstance(client._transport, DesktopMIDITransport)

    def test_connect_delegates_to_transport(self, monkeypatch):
        from core.client import EP133Client

        monkeypatch.setattr("core.client.find_device", lambda: "EP-133 MIDI")
        with patch.object(EP133Client, "_initialize"):
            client = EP133Client()
            # Mock the transport's connect to avoid real MIDI
            client._transport = MagicMock()
            client._transport.receive_sysex.return_value = None
            client.connect()

        client._transport.connect.assert_called_once()


# ---------------------------------------------------------------------------
# EP133Client with injected transport
# ---------------------------------------------------------------------------


class TestEP133ClientWithTransport:
    def _make_client_with_mock_transport(self):
        """Return (client, mock_transport) pair without opening mido ports."""
        from core.client import EP133Client

        mock_transport = MagicMock()
        mock_transport.receive_sysex.return_value = None

        with patch.object(EP133Client, "_initialize"):
            client = EP133Client(transport=mock_transport)
            client.connect()

        return client, mock_transport

    def test_device_not_required_when_transport_given(self):
        from core.client import EP133Client

        mock_transport = MagicMock()
        mock_transport.receive_sysex.return_value = None

        with patch.object(EP133Client, "_initialize"):
            # Should NOT raise DeviceNotFoundError
            client = EP133Client(transport=mock_transport)

        assert client._transport is mock_transport

    def test_connect_does_not_auto_connect_transport(self):
        """When transport is injected, connect() should not call transport.connect()
        (the caller already connected the transport before injecting it)."""
        from core.client import EP133Client

        mock_transport = MagicMock()
        mock_transport.receive_sysex.return_value = None

        with patch.object(EP133Client, "_initialize"):
            client = EP133Client(transport=mock_transport)
            client.connect()

        mock_transport.connect.assert_not_called()

    def test_close_delegates_to_transport(self):
        client, mock_transport = self._make_client_with_mock_transport()
        client.close()
        mock_transport.close.assert_called_once()

    def test_send_sysex_delegates_to_transport(self):
        client, mock_transport = self._make_client_with_mock_transport()
        data = bytes([0xF0, 0x00, 0x20, 0x6B, 0xF7])
        client._send_sysex(data)
        mock_transport.send_sysex.assert_called_once_with(data)

    def test_recv_delegates_to_transport(self):
        client, mock_transport = self._make_client_with_mock_transport()
        mock_transport.receive_sysex.return_value = bytes([0xF0, 0x01, 0x02, 0xF7])

        result = client._recv_next_sysex(timeout=3.0)
        mock_transport.receive_sysex.assert_called_with(timeout=3.0)
        assert result == bytes([0xF0, 0x01, 0x02, 0xF7])

    def test_drain_pending_calls_transport(self):
        client, mock_transport = self._make_client_with_mock_transport()
        # First call returns data, second returns None to end drain loop
        mock_transport.receive_sysex.side_effect = [b"\xf0\x01\xf7", None]
        client._drain_pending()  # must not raise
        assert mock_transport.receive_sysex.call_count == 2

    def test_context_manager_calls_connect_and_close(self):
        from core.client import EP133Client

        mock_transport = MagicMock()
        mock_transport.receive_sysex.return_value = None

        with patch.object(EP133Client, "_initialize"):
            with EP133Client(transport=mock_transport) as client:
                assert client._transport is mock_transport
        mock_transport.close.assert_called_once()
