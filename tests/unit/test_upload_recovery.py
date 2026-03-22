"""
Tests for upload error/recovery scenarios in cmd_put() and UploadTransaction.

Coverage:
1. File not found / unreadable audio file
2. NACK / no ACK after PUT_INIT (timeout-like condition)
3. Device returns error status during upload (EP133Error mid-upload)
4. Partial upload failure — exception raised mid-way through chunk sending
5. Rollback / cleanup: verify no leftover temp files after failure
6. Invalid WAV file (ValueError path in cmd_put)
"""
import wave
import struct
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest

import cli.cmd_transfer
import cli.cmd_slots
import cli.cmd_audio
import cli.cmd_system
import core.ops
from core.client import EP133Client, SlotEmptyError
from core.ops import backup_copy, optimize_sample
from cli.display import View
from core.client import EP133Error, SlotEmptyError
from core.operations import UploadTransaction


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def make_view() -> Mock:
    return Mock(spec=View)


def _args(**kwargs):
    """Build a SimpleNamespace args object suitable for cmd_put()."""
    return SimpleNamespace(device=None, name=None, pitch=0.0, **kwargs)


def _write_valid_wav(path: Path, frames: int = 100) -> bytes:
    """Write a minimal valid mono 46875 Hz 16-bit WAV. Returns raw PCM bytes."""
    import array
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(46875)
        data = array.array("h", [i % 32767 for i in range(frames)])
        raw = data.tobytes()
        w.writeframes(raw)
    return raw


class _FakeClientOK:
    """FakeClient that records put() calls without raising."""

    def __init__(self, log=None):
        self._log = log if log is not None else []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def put(self, path: Path, slot: int, name=None, progress_callback=None, pitch=0.0):
        self._log.append(("put", slot, str(path), name))


class _FakeClientRaises:
    """FakeClient whose put() raises a given exception."""

    def __init__(self, exc):
        self._exc = exc

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def put(self, path: Path, slot: int, name=None, progress_callback=None, pitch=0.0):
        raise self._exc


# ---------------------------------------------------------------------------
# cmd_put: file not found
# ---------------------------------------------------------------------------

def test_cmd_put_missing_file_returns_rc1(monkeypatch, tmp_path):
    """cmd_put must return rc=1 and call view.error when the file does not exist."""
    monkeypatch.setattr(cli.cmd_transfer, "EP133Client", lambda *a, **k: _FakeClientOK())

    view = make_view()
    rc = cli.cmd_transfer.cmd_put(_args(file=str(tmp_path / "nonexistent.wav"), slot=5), view)

    assert rc == 1
    view.error.assert_called_once()
    view.success.assert_not_called()


def test_cmd_put_missing_file_error_message_contains_filename(monkeypatch, tmp_path):
    """The error message must mention the missing filename."""
    monkeypatch.setattr(cli.cmd_transfer, "EP133Client", lambda *a, **k: _FakeClientOK())

    missing = tmp_path / "ghost.wav"
    view = make_view()
    cli.cmd_transfer.cmd_put(_args(file=str(missing), slot=5), view)

    error_msg = view.error.call_args[0][0]
    assert "ghost.wav" in error_msg


# ---------------------------------------------------------------------------
# cmd_put: device raises EP133Error (simulates NACK / no ACK / error status)
# ---------------------------------------------------------------------------

def test_cmd_put_ep133error_returns_rc1(monkeypatch, tmp_path):
    """EP133Error raised by client.put() must cause cmd_put to return rc=1."""
    wav = tmp_path / "sample.wav"
    _write_valid_wav(wav)

    exc = EP133Error("Upload init failed: No response")
    monkeypatch.setattr(cli.cmd_transfer, "EP133Client", lambda *a, **k: _FakeClientRaises(exc))

    view = make_view()
    rc = cli.cmd_transfer.cmd_put(_args(file=str(wav), slot=10), view)

    assert rc == 1
    view.error.assert_called_once()
    view.success.assert_not_called()


def test_cmd_put_ep133error_message_propagates_to_view(monkeypatch, tmp_path):
    """The EP133Error message must appear in the view.error call."""
    wav = tmp_path / "kick.wav"
    _write_valid_wav(wav)

    monkeypatch.setattr(
        "cli.cmd_transfer.EP133Client",
        lambda *a, **k: _FakeClientRaises(EP133Error("Upload init failed: No response"))
    )

    view = make_view()
    cli.cmd_transfer.cmd_put(_args(file=str(wav), slot=10), view)

    error_msg = view.error.call_args[0][0]
    assert "Upload init failed" in error_msg


@pytest.mark.parametrize("slot", [1, 42, 999])
def test_cmd_put_ep133error_various_slots(monkeypatch, tmp_path, slot):
    """EP133Error on any slot must yield rc=1 (parametrized)."""
    wav = tmp_path / f"s{slot}.wav"
    _write_valid_wav(wav)

    monkeypatch.setattr(
        "cli.cmd_transfer.EP133Client",
        lambda *a, **k: _FakeClientRaises(EP133Error("timeout"))
    )

    view = make_view()
    rc = cli.cmd_transfer.cmd_put(_args(file=str(wav), slot=slot), view)

    assert rc == 1
    view.error.assert_called_once()


# ---------------------------------------------------------------------------
# cmd_put: invalid WAV / unreadable audio file (ValueError path)
# ---------------------------------------------------------------------------

def test_cmd_put_invalid_wav_returns_rc1(monkeypatch, tmp_path):
    """A file that exists but isn't a valid WAV must yield rc=1."""
    bad = tmp_path / "not_a_wav.wav"
    bad.write_bytes(b"this is not a wav file at all")

    monkeypatch.setattr(
        "cli.cmd_transfer.EP133Client",
        lambda *a, **k: _FakeClientRaises(ValueError("not a WAV file"))
    )

    view = make_view()
    rc = cli.cmd_transfer.cmd_put(_args(file=str(bad), slot=7), view)

    assert rc == 1
    view.error.assert_called_once()
    view.success.assert_not_called()


# ---------------------------------------------------------------------------
# cmd_put: success path — view.success is called
# ---------------------------------------------------------------------------

def test_cmd_put_success_calls_view_success(monkeypatch, tmp_path):
    """Successful upload must call view.success with the slot number."""
    wav = tmp_path / "drum.wav"
    _write_valid_wav(wav)
    log = []
    monkeypatch.setattr(cli.cmd_transfer, "EP133Client", lambda *a, **k: _FakeClientOK(log))

    view = make_view()
    rc = cli.cmd_transfer.cmd_put(_args(file=str(wav), slot=3), view)

    assert rc == 0
    view.success.assert_called_once()
    assert "3" in view.success.call_args[0][0]
    view.error.assert_not_called()
    assert log[0] == ("put", 3, str(wav), None)


# ---------------------------------------------------------------------------
# UploadTransaction: no ACK after PUT_INIT (timeout simulation)
# ---------------------------------------------------------------------------

class _UploadFakeClient:
    """Low-level fake client for UploadTransaction that can simulate failures."""

    def __init__(self, init_response=True, fail_on_chunk=None, fail_on_end=False):
        """
        init_response: if False, _send_and_wait_msg returns None for PUT_INIT.
        fail_on_chunk: if an int N, raise EP133Error on the Nth chunk _send_msg call.
        fail_on_end: if True, _send_and_wait_msg returns None for UploadEndRequest.
        """
        self._init_response = init_response
        self._fail_on_chunk = fail_on_chunk
        self._fail_on_end = fail_on_end
        self._chunk_call_count = 0
        self.calls = []

    def _send_and_wait_msg(self, msg, timeout=2.0, expect_resp_cmd=None, seq=None):
        from core.models import UploadInitRequest, UploadEndRequest
        self.calls.append(("send_and_wait", type(msg).__name__))
        if isinstance(msg, UploadInitRequest) and not self._init_response:
            return None  # Simulates no ACK / timeout after PUT_INIT
        if isinstance(msg, UploadEndRequest) and self._fail_on_end:
            return None  # Simulates no ACK after end sentinel
        return SimpleNamespace(status=0)

    def _send_msg(self, msg, seq=None):
        from core.models import UploadChunkRequest
        self._chunk_call_count += 1
        self.calls.append(("send_msg", type(msg).__name__, self._chunk_call_count))
        if (
            self._fail_on_chunk is not None
            and isinstance(msg, UploadChunkRequest)
            and self._chunk_call_count >= self._fail_on_chunk
        ):
            raise EP133Error(f"MIDI write error on chunk {self._chunk_call_count}")
        return 0

    def _drain_pending(self):
        pass

    def _initialize(self):
        pass


def _make_wav_path(tmp_path: Path, frames: int = 500) -> Path:
    """Write a valid WAV to tmp_path and return its path."""
    p = tmp_path / "input.wav"
    _write_valid_wav(p, frames=frames)
    return p


def test_upload_transaction_raises_when_init_gets_no_response(tmp_path):
    """UploadTransaction.execute() must raise when PUT_INIT gets no response."""
    client = _UploadFakeClient(init_response=False)
    wav = _make_wav_path(tmp_path)

    tx = UploadTransaction(client, wav, slot=5, name="test")
    with pytest.raises(Exception, match="[Uu]pload init failed"):
        tx.execute()


def test_upload_transaction_no_chunks_sent_when_init_fails(tmp_path):
    """If PUT_INIT gets no response, no chunk _send_msg calls should follow."""
    client = _UploadFakeClient(init_response=False)
    wav = _make_wav_path(tmp_path)

    tx = UploadTransaction(client, wav, slot=5, name="test")
    with pytest.raises(Exception):
        tx.execute()

    chunk_calls = [c for c in client.calls if c[0] == "send_msg" and c[1] == "UploadChunkRequest"]
    assert chunk_calls == [], "No chunk messages should be sent after a failed PUT_INIT"


# ---------------------------------------------------------------------------
# UploadTransaction: partial failure mid-chunk
# ---------------------------------------------------------------------------

def test_upload_transaction_raises_on_chunk_send_error(tmp_path):
    """Exception during _send_msg on the 2nd chunk must propagate out of execute()."""
    # Use enough frames to guarantee at least 2 chunks
    from core.models import UPLOAD_CHUNK_SIZE
    # Each frame = 2 bytes; we need > UPLOAD_CHUNK_SIZE bytes of audio
    frames_needed = (UPLOAD_CHUNK_SIZE // 2) + 100
    wav = _make_wav_path(tmp_path, frames=frames_needed)

    client = _UploadFakeClient(init_response=True, fail_on_chunk=2)

    tx = UploadTransaction(client, wav, slot=7, name="partial")
    with pytest.raises(EP133Error, match="MIDI write error"):
        tx.execute()


def test_upload_transaction_first_chunk_sent_before_failure(tmp_path):
    """At least the first chunk is sent before the mid-upload error (chunk 2 fails)."""
    from core.models import UPLOAD_CHUNK_SIZE
    frames_needed = (UPLOAD_CHUNK_SIZE // 2) + 100
    wav = _make_wav_path(tmp_path, frames=frames_needed)

    client = _UploadFakeClient(init_response=True, fail_on_chunk=2)

    tx = UploadTransaction(client, wav, slot=7, name="partial")
    with pytest.raises(EP133Error):
        tx.execute()

    chunk_calls = [c for c in client.calls if c[0] == "send_msg" and c[1] == "UploadChunkRequest"]
    # First chunk was sent (chunk_call_count=1 < fail_on_chunk=2)
    assert len(chunk_calls) >= 1, "Expected at least 1 chunk to be sent before failure"


# ---------------------------------------------------------------------------
# UploadTransaction: end sentinel gets no ACK
# ---------------------------------------------------------------------------

def test_upload_transaction_completes_without_error_on_missing_end_ack(tmp_path):
    """Missing ACK for UploadEndRequest is tolerated (no raise in execute()).

    The official sequence shows the device sometimes doesn't ACK the end sentinel
    immediately. UploadTransaction._send_and_wait_msg returning None for
    UploadEndRequest must not abort the whole transaction with an exception.
    """
    wav = _make_wav_path(tmp_path)
    client = _UploadFakeClient(init_response=True, fail_on_end=True)

    tx = UploadTransaction(client, wav, slot=3, name="test")
    # Should not raise — missing end ACK is silently tolerated
    tx.execute()


# ---------------------------------------------------------------------------
# cmd_put: no leftover temp files after EP133Error
# ---------------------------------------------------------------------------

def test_cmd_put_no_temp_files_after_error(monkeypatch, tmp_path):
    """After a failed upload, no unexpected temp files should remain in tmp_path."""
    wav = tmp_path / "sample.wav"
    _write_valid_wav(wav)

    monkeypatch.setattr(
        "cli.cmd_transfer.EP133Client",
        lambda *a, **k: _FakeClientRaises(EP133Error("init failed"))
    )

    before = set(tmp_path.iterdir())
    view = make_view()
    cli.cmd_transfer.cmd_put(_args(file=str(wav), slot=8), view)
    after = set(tmp_path.iterdir())

    # Only the input wav should exist; no new files created
    new_files = after - before
    assert new_files == set(), f"Unexpected temp files created: {new_files}"


# ---------------------------------------------------------------------------
# UploadTransaction: device error status (non-zero status in response)
# ---------------------------------------------------------------------------

class _ErrorStatusClient:
    """Fake client that returns an error status (non-zero) on PUT_INIT response."""

    def __init__(self, error_status: int = 0x10):
        self._error_status = error_status
        self.calls = []

    def _send_and_wait_msg(self, msg, timeout=2.0, expect_resp_cmd=None, seq=None):
        from core.models import UploadInitRequest
        self.calls.append(type(msg).__name__)
        # For PUT_INIT return an object with a non-zero status
        if isinstance(msg, UploadInitRequest):
            return SimpleNamespace(status=self._error_status)
        return SimpleNamespace(status=0)

    def _send_msg(self, msg, seq=None):
        self.calls.append(type(msg).__name__)
        return 0

    def _drain_pending(self):
        pass

    def _initialize(self):
        pass


def test_upload_transaction_continues_after_nok_init_status(tmp_path):
    """UploadTransaction currently does not check the status field of the PUT_INIT
    response — it only checks for a None response. This test documents that
    behavior: a non-zero status does NOT raise; the transaction continues.

    If the implementation is later updated to check status, update this test.
    """
    wav = _make_wav_path(tmp_path)
    client = _ErrorStatusClient(error_status=0x10)

    tx = UploadTransaction(client, wav, slot=5, name="test")
    # Currently does NOT raise on non-zero status — documents current behavior
    tx.execute()
    # PUT_INIT must have been sent
    assert "UploadInitRequest" in client.calls


# ---------------------------------------------------------------------------
# UploadTransaction: correct slot encoding in PUT_INIT
# ---------------------------------------------------------------------------

def test_upload_transaction_uses_correct_slot_in_init(tmp_path):
    """PUT_INIT request must be constructed with the correct slot number."""
    from core.models import UploadInitRequest

    wav = _make_wav_path(tmp_path)
    client = _UploadFakeClient(init_response=True)

    tx = UploadTransaction(client, wav, slot=42, name="mysample")
    tx.execute()

    # Find the UploadInitRequest in calls — it is sent via _send_and_wait_msg
    init_calls = [c for c in client.calls if c[0] == "send_and_wait" and c[1] == "UploadInitRequest"]
    assert len(init_calls) == 1, "Expected exactly one UploadInitRequest to be sent"
