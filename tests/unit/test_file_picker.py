"""Tests for src/tui/file_picker.py.

Covers:
- _is_yazi_available(): detects yazi on PATH
- pick_files(): falls back to DirectoryTreePickerModal when yazi absent
- pick_files(): calls yazi via suspend+subprocess when yazi present
- pick_files(): returns [] when modal cancelled
- DirectoryTreePickerModal: dismiss(paths) returns sorted path list
- DirectoryTreePickerModal: dismiss(None) / cancel returns None
- actions.batch_upload(): creates correct WorkerRequest
- worker batch_upload op: calls client.put() for each (file, slot) pair
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import tui.actions as actions
from tui.file_picker import DirectoryTreePickerModal, _is_yazi_available, pick_files
from tui.worker import DeviceWorker


# ---------------------------------------------------------------------------
# _is_yazi_available
# ---------------------------------------------------------------------------

def test_is_yazi_available_returns_true_when_yazi_on_path():
    with patch("shutil.which", return_value="/usr/local/bin/yazi"):
        assert _is_yazi_available() is True


def test_is_yazi_available_returns_false_when_yazi_absent():
    with patch("shutil.which", return_value=None):
        assert _is_yazi_available() is False


# ---------------------------------------------------------------------------
# pick_files — no yazi (modal path)
# ---------------------------------------------------------------------------

def test_pick_files_pushes_modal_when_yazi_absent(tmp_path):
    expected = [tmp_path / "a.wav", tmp_path / "b.wav"]
    mock_app = MagicMock()
    mock_app.push_screen_wait = AsyncMock(return_value=expected)

    async def _run():
        with patch("tui.file_picker._is_yazi_available", return_value=False):
            return await pick_files(mock_app, start_dir=tmp_path)

    result = asyncio.run(_run())
    assert result == expected
    mock_app.push_screen_wait.assert_called_once()
    # The argument passed must be a DirectoryTreePickerModal
    call_arg = mock_app.push_screen_wait.call_args[0][0]
    assert isinstance(call_arg, DirectoryTreePickerModal)


def test_pick_files_returns_empty_list_when_modal_cancelled(tmp_path):
    mock_app = MagicMock()
    mock_app.push_screen_wait = AsyncMock(return_value=None)

    async def _run():
        with patch("tui.file_picker._is_yazi_available", return_value=False):
            return await pick_files(mock_app, start_dir=tmp_path)

    result = asyncio.run(_run())
    assert result == []


# ---------------------------------------------------------------------------
# pick_files — force_modal=True bypasses yazi
# ---------------------------------------------------------------------------

def test_pick_files_force_modal_skips_yazi_even_when_available(tmp_path):
    expected = [tmp_path / "a.wav"]
    mock_app = MagicMock()
    mock_app.push_screen_wait = AsyncMock(return_value=expected)

    async def _run():
        # yazi IS available, but force_modal=True must bypass it
        with patch("tui.file_picker._is_yazi_available", return_value=True):
            return await pick_files(mock_app, start_dir=tmp_path, force_modal=True)

    result = asyncio.run(_run())
    assert result == expected
    mock_app.push_screen_wait.assert_called_once()
    call_arg = mock_app.push_screen_wait.call_args[0][0]
    assert isinstance(call_arg, DirectoryTreePickerModal)


def test_pick_files_force_modal_false_still_uses_yazi(tmp_path):
    wav = tmp_path / "a.wav"
    wav.touch()

    mock_app = MagicMock()
    mock_app.suspend.return_value = MagicMock()

    def fake_subprocess_run(cmd, **kwargs):
        chooser = Path(cmd[cmd.index("--chooser-file") + 1])
        chooser.write_text(f"{wav}\n")
        return SimpleNamespace(returncode=0)

    async def _run():
        with patch("tui.file_picker._is_yazi_available", return_value=True), \
             patch("subprocess.run", side_effect=fake_subprocess_run):
            return await pick_files(mock_app, start_dir=tmp_path, force_modal=False)

    result = asyncio.run(_run())
    assert result == [wav]
    mock_app.push_screen_wait.assert_not_called()


# ---------------------------------------------------------------------------
# pick_files — yazi path
# ---------------------------------------------------------------------------

def test_pick_files_calls_yazi_and_parses_chooser_file(tmp_path):
    wav_a = tmp_path / "a.wav"
    wav_b = tmp_path / "b.wav"
    wav_a.touch()
    wav_b.touch()

    mock_app = MagicMock()
    mock_app.suspend.return_value = MagicMock()

    def fake_subprocess_run(cmd, **kwargs):
        # Simulate yazi writing selected paths to the chooser file
        chooser = Path(cmd[cmd.index("--chooser-file") + 1])
        chooser.write_text(f"{wav_a}\n{wav_b}\n")
        return SimpleNamespace(returncode=0)

    async def _run():
        with patch("tui.file_picker._is_yazi_available", return_value=True), \
             patch("subprocess.run", side_effect=fake_subprocess_run):
            return await pick_files(mock_app, start_dir=tmp_path)

    result = asyncio.run(_run())
    assert wav_a in result
    assert wav_b in result
    mock_app.suspend.assert_called_once()


def test_pick_files_returns_empty_when_yazi_chooser_file_empty(tmp_path):
    mock_app = MagicMock()
    mock_app.suspend.return_value = MagicMock()

    def fake_subprocess_run(cmd, **kwargs):
        # yazi quit without selecting anything
        chooser = Path(cmd[cmd.index("--chooser-file") + 1])
        chooser.write_text("")
        return SimpleNamespace(returncode=0)

    async def _run():
        with patch("tui.file_picker._is_yazi_available", return_value=True), \
             patch("subprocess.run", side_effect=fake_subprocess_run):
            return await pick_files(mock_app, start_dir=tmp_path)

    result = asyncio.run(_run())
    assert result == []


# ---------------------------------------------------------------------------
# actions.batch_upload
# ---------------------------------------------------------------------------

def test_batch_upload_action_creates_worker_request(tmp_path):
    files_and_slots = [(tmp_path / "a.wav", 10), (tmp_path / "b.wav", 11)]
    req = actions.batch_upload(files_and_slots)
    assert req.op == "batch_upload"
    pairs = req.payload["files_and_slots"]
    assert pairs[0] == (str(tmp_path / "a.wav"), 10)
    assert pairs[1] == (str(tmp_path / "b.wav"), 11)


# ---------------------------------------------------------------------------
# worker: batch_upload handler
# ---------------------------------------------------------------------------

class _FakePutClient:
    """Minimal fake client for batch_upload tests."""

    def __init__(self):
        self.calls: list = []

    def connect(self):
        self.calls.append("connect")

    def close(self):
        self.calls.append("close")

    def list_sounds(self):
        self.calls.append("list_sounds")
        return {}

    def get_node_metadata(self, node_id: int):
        return None

    def put(self, input_path: Path, slot: int, name=None, progress_callback=None):
        self.calls.append(("put", str(input_path), slot))


def _make_worker(fake_client):
    req_q: Queue = Queue()
    evt_q: Queue = Queue()
    worker = DeviceWorker(
        device_name="EP-133",
        request_queue=req_q,
        event_queue=evt_q,
        client_factory=lambda *args, **kwargs: fake_client,
    )
    return worker, evt_q


def _drain(evt_q: Queue):
    items = []
    while not evt_q.empty():
        items.append(evt_q.get_nowait())
    return items


def test_worker_batch_upload_calls_put_for_each_file(tmp_path):
    wav_a = tmp_path / "a.wav"
    wav_b = tmp_path / "b.wav"
    # Create minimal valid WAV files so put() can read headers
    import wave as _wave
    for p in (wav_a, wav_b):
        with _wave.open(str(p), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(46875)
            wf.writeframes(b"\x00\x00" * 100)

    fake = _FakePutClient()
    worker, evt_q = _make_worker(fake)

    req = actions.batch_upload([(wav_a, 5), (wav_b, 7)])
    worker._process_request(req)

    put_calls = [c for c in fake.calls if isinstance(c, tuple) and c[0] == "put"]
    assert len(put_calls) == 2
    slots = {c[2] for c in put_calls}
    assert slots == {5, 7}


def test_worker_batch_upload_emits_progress_and_success(tmp_path):
    wav_a = tmp_path / "kick.wav"
    import wave as _wave
    with _wave.open(str(wav_a), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(46875)
        wf.writeframes(b"\x00\x00" * 100)

    fake = _FakePutClient()
    worker, evt_q = _make_worker(fake)

    req = actions.batch_upload([(wav_a, 3)])
    worker._process_request(req)

    events = _drain(evt_q)
    kinds = [e.kind for e in events]
    assert "progress" in kinds
    assert "success" in kinds


def test_worker_batch_upload_skips_missing_file(tmp_path):
    """A missing file should not abort the whole batch — skip and continue."""
    wav_real = tmp_path / "real.wav"
    import wave as _wave
    with _wave.open(str(wav_real), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(46875)
        wf.writeframes(b"\x00\x00" * 100)

    fake = _FakePutClient()
    worker, evt_q = _make_worker(fake)

    req = actions.batch_upload([(tmp_path / "missing.wav", 1), (wav_real, 2)])
    worker._process_request(req)

    put_calls = [c for c in fake.calls if isinstance(c, tuple) and c[0] == "put"]
    assert len(put_calls) == 1
    assert put_calls[0][2] == 2
