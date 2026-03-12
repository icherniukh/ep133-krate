"""
Tests for cmd_audition and AuditionRequest.

Wire format verified against two captures (PROT-001):
  sniffer-2026-03-10-165130.jsonl — slots 1–4, TE Tool devid=0x60
  sniffer-2026-03-10-173014.jsonl — slots 501–808, TE Tool devid=0x61

The TE Sample Tool uses rotating devids 0x60–0x6A; ko2 uses fixed 0x6A.
Raw payload structure (12 bytes): 05 01 [slot_hi] [slot_lo] 00×6 03 E8
Slot is BE16 at bytes [2:4]. Confirmed range: 1–808.
"""
import pytest
from unittest.mock import Mock, patch
from ko2_models import AuditionRequest, UPLOAD_PARENT_NODE
from ko2_types import Packed7
from ko2_display import View


# ---------------------------------------------------------------------------
# Wire format tests — verified against capture data
# ---------------------------------------------------------------------------

def _build_expected(slot: int, seq: int = 0) -> bytes:
    """Build expected SysEx bytes for AuditionRequest(slot) using fixed devid 0x6A."""
    slot_hi = (slot >> 8) & 0xFF
    slot_lo = slot & 0xFF
    raw_payload = bytes([
        0x05,               # FileOp.PLAYBACK
        0x01,               # action=play
        slot_hi,            # slot BE16 high byte
        slot_lo,            # slot BE16 low byte
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # padding (6 bytes)
        (UPLOAD_PARENT_NODE >> 8) & 0xFF,     # parent_node hi = 0x03
        UPLOAD_PARENT_NODE & 0xFF,            # parent_node lo = 0xE8
    ])
    assert len(raw_payload) == 12
    packed = Packed7.pack(raw_payload)
    return (
        bytes([0xF0, 0x00, 0x20, 0x76, 0x33, 0x40, 0x6A, seq, 0x05])
        + packed
        + bytes([0xF7])
    )


@pytest.mark.parametrize("slot,seq", [
    (1, 0x00),  # capture 165130 seq=0x61: raw=0501000100000000000003e8
    (2, 0x01),  # capture 165130 seq=0x62: raw=0501000200000000000003e8
    (3, 0x02),  # capture 165130 seq=0x63: raw=0501000300000000000003e8
    (4, 0x03),  # capture 165130 seq=0x64: raw=0501000400000000000003e8
    (501, 0x00),  # capture 173014 seq=0x78: raw=050101f500000000000003e8
    (502, 0x01),  # capture 173014 seq=0x7A: raw=050101f600000000000003e8
    (503, 0x02),  # capture 173014 seq=0x79: raw=050101f700000000000003e8
    (808, 0x03),  # capture 173014 seq=0x7D: raw=0501032800000000000003e8
])
def test_audition_request_payload_matches_capture(slot, seq):
    """AuditionRequest payload matches decoded capture bytes for all confirmed slots."""
    msg = AuditionRequest(slot=slot)
    built = msg.build(seq=seq)
    expected = _build_expected(slot=slot, seq=seq)
    assert built == expected, (
        f"slot={slot}: got {built.hex()}, expected {expected.hex()}"
    )


def test_audition_request_payload_structure_low_slot():
    """Verify raw payload field layout for a low slot (fits in slot_lo only)."""
    msg = AuditionRequest(slot=7)
    built = msg.build(seq=0)
    packed = built[9:-1]
    raw = Packed7.unpack(packed)
    assert raw[0] == 0x05         # FileOp.PLAYBACK
    assert raw[1] == 0x01         # action=play
    assert raw[2] == 0x00         # slot_hi (0 for slot < 256)
    assert raw[3] == 7            # slot_lo
    assert raw[4:10] == b'\x00' * 6  # padding
    assert raw[10] == 0x03        # parent_node hi (1000 >> 8)
    assert raw[11] == 0xE8        # parent_node lo (1000 & 0xFF)


def test_audition_request_payload_structure_high_slot():
    """Verify raw payload field layout for a high slot (slot_hi non-zero)."""
    msg = AuditionRequest(slot=808)
    built = msg.build(seq=0)
    packed = built[9:-1]
    raw = Packed7.unpack(packed)
    assert raw[0] == 0x05
    assert raw[1] == 0x01
    assert raw[2] == 0x03         # 808 >> 8 = 3
    assert raw[3] == 0x28         # 808 & 0xFF = 40 = 0x28
    assert raw[4:10] == b'\x00' * 6
    assert raw[10] == 0x03
    assert raw[11] == 0xE8


def test_audition_request_opcode():
    """AuditionRequest uses SysExCmd.LIST_FILES (0x6A) — fixed FILE devid."""
    from ko2_models import SysExCmd
    assert AuditionRequest.opcode == SysExCmd.LIST_FILES


# ---------------------------------------------------------------------------
# cmd_audition integration tests (FakeClient pattern)
# ---------------------------------------------------------------------------

class FakeClient:
    def __init__(self):
        self.audition_calls = []
        self._error = None

    def __enter__(self): return self
    def __exit__(self, *a): pass

    def audition(self, slot: int):
        if self._error:
            raise self._error
        self.audition_calls.append(slot)


def _make_view():
    return Mock(spec=View)


def _run_cmd_audition(slot, fake_client, error=None):
    from cli.cmd_audio import cmd_audition
    if error:
        fake_client._error = error
    args = Mock()
    args.slot = slot
    args.device = "fake"
    view = _make_view()
    with patch("cli.cmd_audio.EP133Client", return_value=fake_client):
        rc = cmd_audition(args, view)
    return rc, view


def test_cmd_audition_success_calls_view_success():
    client = FakeClient()
    rc, view = _run_cmd_audition(slot=3, fake_client=client)
    assert rc == 0
    view.success.assert_called_once()
    assert "003" in view.success.call_args[0][0]


def test_cmd_audition_sends_correct_slot():
    client = FakeClient()
    _run_cmd_audition(slot=5, fake_client=client)
    assert client.audition_calls == [5]


def test_cmd_audition_high_slot():
    """Audition works for slots > 127 (BE16 encoding required)."""
    client = FakeClient()
    _run_cmd_audition(slot=501, fake_client=client)
    assert client.audition_calls == [501]


def test_cmd_audition_ep133error_returns_rc1():
    from ko2_client import EP133Error
    client = FakeClient()
    rc, view = _run_cmd_audition(slot=1, fake_client=client, error=EP133Error("no response"))
    assert rc == 1
    view.error.assert_called_once()


def test_cmd_audition_ep133error_message_forwarded():
    from ko2_client import EP133Error
    client = FakeClient()
    rc, view = _run_cmd_audition(slot=2, fake_client=client, error=EP133Error("Audition failed: status=0x01"))
    view.error.assert_called_once()
    assert "Audition failed" in view.error.call_args[0][0]


def test_cmd_audition_step_called_before_success():
    """view.step is called with the slot before audition fires."""
    client = FakeClient()
    _rc, view = _run_cmd_audition(slot=8, fake_client=client)
    view.step.assert_called_once()
    assert "008" in view.step.call_args[0][0]


# ---------------------------------------------------------------------------
# Worker audition_started event tests
# ---------------------------------------------------------------------------

def test_worker_emits_audition_started():
    """Worker should emit audition_started with slot and duration_s after ACK."""
    import pytest
    from ko2_tui.worker import DeviceWorker, WorkerEvent
    from ko2_tui.actions import WorkerRequest
    from queue import Queue

    events: list[WorkerEvent] = []

    class FakeAuditionClient:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def audition(self, slot): pass

    req_q: Queue = Queue()
    evt_q: Queue = Queue()
    req_q.put(WorkerRequest(op="audition", payload={"slot": 5, "duration_s": 2.0}))
    req_q.put(WorkerRequest(op="stop"))

    worker = DeviceWorker(
        device_name="test",
        request_queue=req_q,
        event_queue=evt_q,
        client_factory=lambda name, **kw: FakeAuditionClient(),
    )
    worker.run()

    while not evt_q.empty():
        events.append(evt_q.get_nowait())

    kinds = [e.kind for e in events]
    assert "audition_started" in kinds

    ev = next(e for e in events if e.kind == "audition_started")
    assert ev.payload["slot"] == 5
    assert ev.payload["duration_s"] == pytest.approx(2.0)
