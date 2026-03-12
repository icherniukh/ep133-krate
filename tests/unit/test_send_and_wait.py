import time

import mido


class _FakeInPort:
    def __init__(self) -> None:
        self._queue: list[mido.Message] = []

    def iter_pending(self):
        queued = self._queue
        self._queue = []
        return queued


class _FakeOutPort:
    def __init__(self, inport: _FakeInPort, after_send: list[mido.Message]) -> None:
        self._inport = inport
        self._after_send = after_send
        self.sent: list[mido.Message] = []

    def send(self, msg: mido.Message) -> None:
        self.sent.append(msg)
        # Simulate device responses arriving after we send.
        self._inport._queue.extend(self._after_send)


def _incoming_te_sysex(cmd: int, seq: int = 1, sub: int = 5, status: int = 0) -> mido.Message:
    # mido sysex data excludes F0/F7. EP-133 header is:
    # 00 20 76 33 40 <cmd> <seq> <sub> <status> ...
    data = bytes([0x00, 0x20, 0x76, 0x33, 0x40, cmd & 0x7F, seq & 0x7F, sub & 0x7F, status & 0x7F])
    return mido.Message("sysex", data=data)


def _incoming_file_response_empty_payload(cmd: int, seq: int = 1, status: int = 0) -> mido.Message:
    # Response body without packed payload bytes:
    # 00 20 76 33 40 <cmd> <seq> 05 <status>
    data = bytes([0x00, 0x20, 0x76, 0x33, 0x40, cmd & 0x7F, seq & 0x7F, 0x05, status & 0x7F])
    return mido.Message("sysex", data=data)


def test_send_and_wait_ignores_notifications_and_filters_expected_cmd():
    from core.client import EP133Client
    from core.models import SysExCmd, SysExMessage

    inport = _FakeInPort()
    # 0x40 is a device->host notification in rcy docs (not a 0x2x response).
    notification = _incoming_te_sysex(0x40)
    wrong_response = _incoming_te_sysex(SysExCmd.UPLOAD_DATA - 0x40)  # 0x2C
    wanted_response = _incoming_te_sysex(SysExCmd.UPLOAD_END - 0x40, status=0)  # 0x2D
    outport = _FakeOutPort(inport, [notification, wrong_response, wanted_response])

    client = EP133Client.__new__(EP133Client)
    client._inport = inport
    client._outport = outport

    outgoing = SysExMessage().build()  # any sysex payload
    resp = client._send_and_wait(outgoing, timeout=0.2, expect_cmd=(SysExCmd.UPLOAD_END - 0x40))

    assert resp is not None
    assert resp[6] == (SysExCmd.UPLOAD_END - 0x40)


def test_send_and_wait_returns_none_if_only_notifications():
    from core.client import EP133Client
    from core.models import SysExMessage

    inport = _FakeInPort()
    outport = _FakeOutPort(inport, [_incoming_te_sysex(0x40), _incoming_te_sysex(0x70)])

    client = EP133Client.__new__(EP133Client)
    client._inport = inport
    client._outport = outport

    outgoing = SysExMessage().build()
    start = time.time()
    resp = client._send_and_wait(outgoing, timeout=0.05)
    elapsed = time.time() - start

    assert resp is None
    assert elapsed < 1.0


def test_send_file_request_accepts_empty_payload_response():
    from core.client import EP133Client
    from core.models import FileListRequest

    inport = _FakeInPort()
    # 0x2A = LIST_FILES response class for 0x6A requests.
    outport = _FakeOutPort(inport, [_incoming_file_response_empty_payload(0x2A, seq=0, status=0)])

    client = EP133Client.__new__(EP133Client)
    client._inport = inport
    client._outport = outport
    client._seq = 0

    resp = client._send_file_request(
        FileListRequest(node_id=1000, page=0),
        timeout=0.2,
        expect_resp_cmd=0x2A,
        seq=0,
    )
    assert resp == (0, b"")
