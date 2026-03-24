"""
Unit tests for the MIDI transport abstraction (src/core/midi_transport.py)
and the EP133Client transport= injection path.

All tests run without real MIDI hardware by mocking mido and httpx.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# LocalMidiTransport
# ---------------------------------------------------------------------------


class TestLocalMidiTransport:
    def test_send_delegates_to_out_port(self):
        from core.midi_transport import LocalMidiTransport

        in_port = MagicMock()
        out_port = MagicMock()
        transport = LocalMidiTransport(in_port, out_port)

        msg = MagicMock()
        transport.send(msg)
        out_port.send.assert_called_once_with(msg)

    def test_receive_delegates_to_in_port(self):
        from core.midi_transport import LocalMidiTransport

        in_port = MagicMock()
        out_port = MagicMock()
        expected_msg = MagicMock()
        in_port.receive.return_value = expected_msg

        transport = LocalMidiTransport(in_port, out_port)
        result = transport.receive(timeout=3.0)

        in_port.receive.assert_called_once_with(timeout=3.0, block=True)
        assert result is expected_msg

    def test_receive_default_timeout(self):
        from core.midi_transport import LocalMidiTransport

        in_port = MagicMock()
        in_port.receive.return_value = None
        transport = LocalMidiTransport(in_port, MagicMock())
        transport.receive()
        in_port.receive.assert_called_once_with(timeout=5.0, block=True)

    def test_close_closes_both_ports(self):
        from core.midi_transport import LocalMidiTransport

        in_port = MagicMock()
        out_port = MagicMock()
        transport = LocalMidiTransport(in_port, out_port)
        transport.close()
        in_port.close.assert_called_once()
        out_port.close.assert_called_once()

    def test_is_subclass_of_midi_transport(self):
        from core.midi_transport import LocalMidiTransport, MidiTransport

        assert issubclass(LocalMidiTransport, MidiTransport)


# ---------------------------------------------------------------------------
# RemoteMidiTransport
# ---------------------------------------------------------------------------


class TestRemoteMidiTransport:
    def test_send_posts_to_midi_send_endpoint(self):
        from core.midi_transport import RemoteMidiTransport

        mock_client_instance = MagicMock()
        mock_httpx = _make_httpx_module(mock_client_instance)

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            import importlib
            import core.midi_transport as mod
            importlib.reload(mod)
            transport = mod.RemoteMidiTransport(base_url="http://localhost:8765")

        import mido
        msg = mido.Message("sysex", data=[0x00, 0x20, 0x6B])
        transport.send(msg)

        mock_client_instance.post.assert_called_once()
        call_kwargs = mock_client_instance.post.call_args
        assert call_kwargs[0][0] == "/midi/send"
        json_body = call_kwargs[1]["json"]
        assert json_body["type"] == "sysex"
        assert isinstance(json_body["data"], list)

    def test_receive_returns_none_on_204(self):
        from core.midi_transport import RemoteMidiTransport

        mock_client_instance = MagicMock()
        resp_204 = MagicMock()
        resp_204.status_code = 204
        mock_client_instance.get.return_value = resp_204
        mock_httpx = _make_httpx_module(mock_client_instance)

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            import importlib
            import core.midi_transport as mod
            importlib.reload(mod)
            transport = mod.RemoteMidiTransport(base_url="http://localhost:8765")

        result = transport.receive(timeout=2.0)
        assert result is None
        mock_client_instance.get.assert_called_once_with("/midi/recv", params={"timeout": 2.0})

    def test_receive_decodes_message_from_json(self):
        import mido
        from core.midi_transport import RemoteMidiTransport

        # Build a real sysex message to use as the expected return value
        real_msg = mido.Message("sysex", data=[0x00, 0x20, 0x6B, 0x00, 0x04, 0x20])
        raw_bytes = list(real_msg.bytes())

        mock_client_instance = MagicMock()
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {"data": raw_bytes}
        mock_client_instance.get.return_value = resp_200
        mock_httpx = _make_httpx_module(mock_client_instance)

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            import importlib
            import core.midi_transport as mod
            importlib.reload(mod)
            transport = mod.RemoteMidiTransport(base_url="http://localhost:8765")

        result = transport.receive(timeout=5.0)
        assert result is not None
        assert result.type == "sysex"
        assert list(result.bytes()) == raw_bytes

    def test_close_closes_httpx_client(self):
        from core.midi_transport import RemoteMidiTransport

        mock_client_instance = MagicMock()
        mock_httpx = _make_httpx_module(mock_client_instance)

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            import importlib
            import core.midi_transport as mod
            importlib.reload(mod)
            transport = mod.RemoteMidiTransport(base_url="http://localhost:8765")

        transport.close()
        mock_client_instance.close.assert_called_once()

    def test_is_subclass_of_midi_transport(self):
        from core.midi_transport import RemoteMidiTransport, MidiTransport

        assert issubclass(RemoteMidiTransport, MidiTransport)


# ---------------------------------------------------------------------------
# EP133Client backward compatibility (transport=None)
# ---------------------------------------------------------------------------


class TestEP133ClientBackwardCompat:
    """EP133Client with no transport= kwarg must behave exactly as before."""

    def test_init_raises_without_device(self, monkeypatch):
        from core.client import EP133Client, DeviceNotFoundError
        monkeypatch.setattr("core.client.find_device", lambda: None)
        with pytest.raises(DeviceNotFoundError):
            EP133Client(device_name=None)

    def test_init_accepts_explicit_device_name(self, monkeypatch):
        """Constructor succeeds when a device name is given directly."""
        from core.client import EP133Client
        # find_device should not be called when device_name is explicit
        client = EP133Client(device_name="EP-133 MIDI")
        assert client.device_name == "EP-133 MIDI"
        assert client._transport is None

    def test_transport_is_none_by_default(self, monkeypatch):
        from core.client import EP133Client
        monkeypatch.setattr("core.client.find_device", lambda: "EP-133 MIDI")
        client = EP133Client()
        assert client._transport is None

    def test_connect_opens_mido_ports_when_no_transport(self, monkeypatch):
        import mido
        from core.client import EP133Client

        mock_out = MagicMock()
        mock_in = MagicMock()
        mock_in.iter_pending.return_value = iter([])
        mock_in.receive.return_value = None

        monkeypatch.setattr("core.client.find_device", lambda: "EP-133 MIDI")
        monkeypatch.setattr(mido, "open_output", lambda name: mock_out)
        monkeypatch.setattr(mido, "open_input", lambda name: mock_in)
        # Stub _initialize to avoid real MIDI handshake
        with patch.object(EP133Client, "_initialize"):
            client = EP133Client()
            client.connect()

        assert client._outport is mock_out
        assert client._inport is mock_in


# ---------------------------------------------------------------------------
# EP133Client with injected transport
# ---------------------------------------------------------------------------


class TestEP133ClientWithTransport:
    def _make_client_with_mock_transport(self):
        """Return (client, mock_transport) pair without opening mido ports."""
        from core.client import EP133Client

        mock_transport = MagicMock()
        mock_transport.receive.return_value = None

        with patch.object(EP133Client, "_initialize"):
            client = EP133Client(transport=mock_transport)
            client.connect()

        return client, mock_transport

    def test_device_not_required_when_transport_given(self):
        from core.client import EP133Client

        mock_transport = MagicMock()
        mock_transport.receive.return_value = None

        with patch.object(EP133Client, "_initialize"):
            # Should NOT raise DeviceNotFoundError
            client = EP133Client(transport=mock_transport)

        assert client._transport is mock_transport
        assert client._outport is None
        assert client._inport is None

    def test_connect_does_not_open_mido_ports(self, monkeypatch):
        import mido
        from core.client import EP133Client

        open_output_calls = []
        open_input_calls = []
        monkeypatch.setattr(mido, "open_output", lambda n: open_output_calls.append(n))
        monkeypatch.setattr(mido, "open_input", lambda n: open_input_calls.append(n))

        mock_transport = MagicMock()
        mock_transport.receive.return_value = None

        with patch.object(EP133Client, "_initialize"):
            client = EP133Client(transport=mock_transport)
            client.connect()

        assert open_output_calls == []
        assert open_input_calls == []

    def test_close_delegates_to_transport(self):
        client, mock_transport = self._make_client_with_mock_transport()
        client.close()
        mock_transport.close.assert_called_once()

    def test_port_send_delegates_to_transport(self):
        import mido
        client, mock_transport = self._make_client_with_mock_transport()
        msg = mido.Message("sysex", data=[0x00, 0x20, 0x6B])
        client._port_send(msg)
        mock_transport.send.assert_called_once_with(msg)

    def test_recv_message_blocking_delegates_to_transport(self):
        import mido
        client, mock_transport = self._make_client_with_mock_transport()
        expected = mido.Message("sysex", data=[0x01, 0x02])
        mock_transport.receive.return_value = expected

        result = client._recv_message_blocking(timeout=3.0)
        mock_transport.receive.assert_called_with(timeout=3.0)
        assert result is expected

    def test_drain_pending_skips_inport_when_transport_set(self):
        client, mock_transport = self._make_client_with_mock_transport()
        # _inport is None — would raise AttributeError if _drain_pending tried to use it
        assert client._inport is None
        client._drain_pending()  # must not raise

    def test_context_manager_calls_connect_and_close(self):
        from core.client import EP133Client

        mock_transport = MagicMock()
        mock_transport.receive.return_value = None

        with patch.object(EP133Client, "_initialize"):
            with EP133Client(transport=mock_transport) as client:
                assert client._transport is mock_transport
        mock_transport.close.assert_called_once()


# ---------------------------------------------------------------------------
# MidiTransport ABC cannot be instantiated
# ---------------------------------------------------------------------------


class TestMidiTransportABC:
    def test_cannot_instantiate_abstract_class(self):
        from core.midi_transport import MidiTransport

        with pytest.raises(TypeError):
            MidiTransport()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_all_methods(self):
        from core.midi_transport import MidiTransport

        class Incomplete(MidiTransport):
            def send(self, msg): pass
            # missing receive and close

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _make_httpx_module(client_instance: MagicMock) -> MagicMock:
    """Return a mock httpx module whose Client() returns client_instance."""
    mock_httpx = MagicMock()
    mock_httpx.Client.return_value = client_instance
    # Expose ConnectError so imports in screens don't fail
    mock_httpx.ConnectError = ConnectionError
    return mock_httpx
