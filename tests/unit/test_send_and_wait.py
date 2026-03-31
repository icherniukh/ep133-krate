import time
from typing import Optional

from core.transport import MIDITransport, MIDIDevice


class _FakeTransport(MIDITransport):
    """Minimal transport that queues responses to be returned after a send."""

    def __init__(self, responses: list[bytes]) -> None:
        self._responses = list(responses)
        self._rx_queue: list[bytes] = []
        self.sent: list[bytes] = []

    def discover_devices(self) -> list[MIDIDevice]:
        return []

    def connect(self, device: MIDIDevice) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def send_sysex(self, data: bytes) -> None:
        self.sent.append(data)
        # Simulate device responses arriving after we send.
        self._rx_queue.extend(self._responses)

    def receive_sysex(self, timeout: float = 1.0) -> Optional[bytes]:
        if self._rx_queue:
            return self._rx_queue.pop(0)
        return None


def _te_sysex(cmd: int, seq: int = 1, sub: int = 5, status: int = 0) -> bytes:
    """Build a raw TE SysEx response (with F0/F7 framing)."""
    # EP-133 header: F0 00 20 76 33 40 <cmd> <seq> <sub> <status> ... F7
    # Device family in raw SysEx is 0x33 0x40 at positions [4:6].
    inner = bytes([0x00, 0x20, 0x76, 0x33, 0x40, cmd & 0x7F, seq & 0x7F, sub & 0x7F, status & 0x7F])
    return bytes([0xF0]) + inner + bytes([0xF7])


def _file_response_empty_payload(cmd: int, seq: int = 1, status: int = 0) -> bytes:
    """Build a raw TE file-response SysEx with empty packed payload."""
    inner = bytes([0x00, 0x20, 0x76, 0x33, 0x40, cmd & 0x7F, seq & 0x7F, 0x05, status & 0x7F])
    return bytes([0xF0]) + inner + bytes([0xF7])


def test_send_and_wait_ignores_notifications_and_filters_expected_cmd():
    from core.client import EP133Client
    from core.models import SysExCmd, SysExMessage

    # 0x40 is a device->host notification (not a 0x2x response).
    notification = _te_sysex(0x40)
    wrong_response = _te_sysex(SysExCmd.UPLOAD_DATA - 0x40)  # 0x2C
    wanted_response = _te_sysex(SysExCmd.UPLOAD_END - 0x40, status=0)  # 0x2D

    transport = _FakeTransport([notification, wrong_response, wanted_response])

    client = EP133Client.__new__(EP133Client)
    client._transport = transport
    client._trace_hook = None

    outgoing = SysExMessage().build()  # any sysex payload
    resp = client._send_and_wait(outgoing, timeout=0.2, expect_cmd=(SysExCmd.UPLOAD_END - 0x40))

    assert resp is not None
    assert resp[6] == (SysExCmd.UPLOAD_END - 0x40)


def test_send_and_wait_returns_none_if_only_notifications():
    from core.client import EP133Client
    from core.models import SysExMessage

    transport = _FakeTransport([_te_sysex(0x40), _te_sysex(0x70)])

    client = EP133Client.__new__(EP133Client)
    client._transport = transport
    client._trace_hook = None

    outgoing = SysExMessage().build()
    start = time.time()
    resp = client._send_and_wait(outgoing, timeout=0.05)
    elapsed = time.time() - start

    assert resp is None
    assert elapsed < 1.0


def test_send_file_request_accepts_empty_payload_response():
    from core.client import EP133Client
    from core.models import FileListRequest

    transport = _FakeTransport([_file_response_empty_payload(0x2A, seq=0, status=0)])

    client = EP133Client.__new__(EP133Client)
    client._transport = transport
    client._trace_hook = None
    client._seq = 0

    resp = client._send_file_request(
        FileListRequest(node_id=1000, page=0),
        timeout=0.2,
        expect_resp_cmd=0x2A,
        seq=0,
    )
    assert resp == (0, b"")
