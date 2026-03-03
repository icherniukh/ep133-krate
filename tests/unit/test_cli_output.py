"""
Tests for cmd_* output via Mock(spec=View).

Each test verifies that commands call the correct view methods on success/error
paths without touching stdout directly.
"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import ko2
from ko2_display import View
from ko2_client import SlotEmptyError, EP133Error


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def make_view() -> Mock:
    return Mock(spec=View)


def _args(**kwargs):
    return SimpleNamespace(device=None, yes=True, **kwargs)


class FakeClient:
    """Minimal in-memory device client for CLI tests."""

    def __init__(self, sounds=None, log=None):
        self._sounds = sounds or {}
        self._log = log if log is not None else []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def list_sounds(self):
        return self._sounds

    def get(self, slot, path=None):
        if slot not in self._sounds:
            raise SlotEmptyError(f"slot {slot} empty")
        if path is not None:
            Path(path).write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
        self._log.append(("get", slot))
        return path

    def put(self, path, slot, name=None, progress=False, pitch=0.0):
        self._log.append(("put", slot, name))

    def delete(self, slot):
        self._log.append(("delete", slot))

    def info(self, slot, include_size=False, node_entry=None):
        if slot not in self._sounds:
            raise SlotEmptyError(f"slot {slot} empty")
        entry = self._sounds[slot]
        return SimpleNamespace(
            slot=slot,
            name=entry.get("name", f"slot{slot:03d}.pcm"),
            size_bytes=int(entry.get("size", 0)),
            samplerate=46875,
            channels=1,
            sym="",
            format="s16",
            channels_known=True,
        )

    def rename(self, slot, new_name):
        self._log.append(("rename", slot, new_name))


# ---------------------------------------------------------------------------
# cmd_get
# ---------------------------------------------------------------------------

def test_cmd_get_success(monkeypatch, tmp_path):
    sounds = {5: {"name": "kick.wav", "size": 1000}}
    log = []
    client = FakeClient(sounds, log)
    monkeypatch.setattr(ko2, "EP133Client", lambda *a, **k: client)

    output = tmp_path / "kick.wav"
    view = make_view()
    rc = ko2.cmd_get(_args(slot=5, output=str(output)), view)

    assert rc == 0
    view.success.assert_called_once()
    assert str(output) in view.success.call_args[0][0]
    view.error.assert_not_called()


def test_cmd_get_empty_slot(monkeypatch):
    client = FakeClient(sounds={})
    monkeypatch.setattr(ko2, "EP133Client", lambda *a, **k: client)

    view = make_view()
    rc = ko2.cmd_get(_args(slot=99, output=None), view)

    assert rc == 1
    view.error.assert_called_once()
    assert "99" in view.error.call_args[0][0]
    view.success.assert_not_called()


# ---------------------------------------------------------------------------
# cmd_put
# ---------------------------------------------------------------------------

def test_cmd_put_success(monkeypatch, tmp_path):
    wav = tmp_path / "sample.wav"
    wav.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
    log = []
    client = FakeClient(sounds={}, log=log)
    monkeypatch.setattr(ko2, "EP133Client", lambda *a, **k: client)

    view = make_view()
    rc = ko2.cmd_put(_args(file=str(wav), slot=10, name=None, pitch=0.0), view)

    assert rc == 0
    view.success.assert_called_once()
    assert "10" in view.success.call_args[0][0]
    view.error.assert_not_called()


def test_cmd_put_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(ko2, "EP133Client", lambda *a, **k: FakeClient())

    view = make_view()
    rc = ko2.cmd_put(_args(file=str(tmp_path / "missing.wav"), slot=10, name=None, pitch=0.0), view)

    assert rc == 1
    view.error.assert_called_once()
    view.success.assert_not_called()


# ---------------------------------------------------------------------------
# cmd_move
# ---------------------------------------------------------------------------

def test_cmd_move_to_empty(monkeypatch):
    sounds = {1: {"name": "001.pcm", "node_id": 1, "size": 100}}
    log = []
    client = FakeClient(sounds, log)
    monkeypatch.setattr(ko2, "EP133Client", lambda *a, **k: client)
    monkeypatch.setattr(ko2, "backup_copy", lambda *a, **k: None)

    view = make_view()
    rc = ko2.cmd_move(_args(src=1, dst=2, raw=True), view)

    assert rc == 0
    view.success.assert_called_once()
    assert "001" in view.success.call_args[0][0]
    assert "002" in view.success.call_args[0][0]
    view.error.assert_not_called()


def test_cmd_move_empty_source(monkeypatch):
    client = FakeClient(sounds={})
    monkeypatch.setattr(ko2, "EP133Client", lambda *a, **k: client)

    view = make_view()
    rc = ko2.cmd_move(_args(src=5, dst=10, raw=True), view)

    assert rc == 1
    view.error.assert_called_once()
    view.success.assert_not_called()


# ---------------------------------------------------------------------------
# cmd_copy
# ---------------------------------------------------------------------------

def test_cmd_copy_to_empty(monkeypatch):
    sounds = {1: {"name": "001.pcm", "node_id": 1, "size": 100}}
    log = []
    client = FakeClient(sounds, log)
    monkeypatch.setattr(ko2, "EP133Client", lambda *a, **k: client)
    monkeypatch.setattr(ko2, "backup_copy", lambda *a, **k: None)

    view = make_view()
    rc = ko2.cmd_copy(_args(src=1, dst=3, raw=True), view)

    assert rc == 0
    view.success.assert_called_once()
    view.error.assert_not_called()


def test_cmd_copy_empty_source(monkeypatch):
    client = FakeClient(sounds={})
    monkeypatch.setattr(ko2, "EP133Client", lambda *a, **k: client)

    view = make_view()
    rc = ko2.cmd_copy(_args(src=5, dst=10, raw=True), view)

    assert rc == 1
    view.error.assert_called_once()


# ---------------------------------------------------------------------------
# cmd_delete
# ---------------------------------------------------------------------------

def test_cmd_delete_success(monkeypatch):
    sounds = {7: {"name": "snare.pcm", "size": 500}}
    log = []
    client = FakeClient(sounds, log)
    monkeypatch.setattr(ko2, "EP133Client", lambda *a, **k: client)

    view = make_view()
    rc = ko2.cmd_delete(_args(slot=7), view)

    assert rc == 0
    view.success.assert_called_once()
    assert "7" in view.success.call_args[0][0]
    view.error.assert_not_called()


def test_cmd_delete_empty_slot(monkeypatch):
    client = FakeClient(sounds={})
    monkeypatch.setattr(ko2, "EP133Client", lambda *a, **k: client)

    view = make_view()
    rc = ko2.cmd_delete(_args(slot=7), view)

    assert rc == 1
    view.success.assert_not_called()


# ---------------------------------------------------------------------------
# cmd_rename
# ---------------------------------------------------------------------------

def test_cmd_rename_success(monkeypatch, tmp_path):
    sounds = {10: {"name": "old.pcm", "size": 100}}
    log = []
    client = FakeClient(sounds, log)
    monkeypatch.setattr(ko2, "EP133Client", lambda *a, **k: client)
    monkeypatch.setattr(ko2, "backup_copy", lambda *a, **k: tmp_path / "backup.wav")

    view = make_view()
    rc = ko2.cmd_rename(_args(slot=10, name="new name"), view)

    assert rc == 0
    view.success.assert_called_once()
    assert "new name" in view.success.call_args[0][0]
    view.error.assert_not_called()


def test_cmd_rename_empty_slot(monkeypatch):
    client = FakeClient(sounds={})
    monkeypatch.setattr(ko2, "EP133Client", lambda *a, **k: client)

    view = make_view()
    rc = ko2.cmd_rename(_args(slot=99, name="x"), view)

    assert rc == 1
    view.error.assert_called_once()


# ---------------------------------------------------------------------------
# cmd_optimize paths
# ---------------------------------------------------------------------------

def test_cmd_optimize_success(monkeypatch, tmp_path):
    import wave, array

    def make_wav(path, channels=2, rate=48000):
        with wave.open(str(path), "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(2)
            w.setframerate(rate)
            frames = array.array("h", [0] * rate)
            w.writeframes(frames.tobytes())

    sounds = {3: {"name": "drums.pcm", "size": 20 * 1024}}
    log = []
    client = FakeClient(sounds, log)
    client.get = lambda slot, path=None: (make_wav(path, 2, 48000), log.append(("get", slot)))[1]

    monkeypatch.setattr(ko2, "EP133Client", lambda *a, **k: client)
    monkeypatch.setattr(ko2, "backup_copy", lambda *a, **k: tmp_path / "bak.wav")
    monkeypatch.setattr(
        ko2, "optimize_sample",
        lambda p, **kw: (True, "optimized with sox", 20 * 1024, 10 * 1024),
    )

    view = make_view()
    rc = ko2.cmd_optimize(_args(slot=3, rate=None, speed=None, pitch=0.0, keep_stereo=False), view)

    assert rc == 0
    view.success.assert_called()
    view.error.assert_not_called()


def test_cmd_optimize_already_optimal(monkeypatch, tmp_path):
    import wave, array

    def make_wav(path):
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(46875)
            w.writeframes(array.array("h", [0] * 100).tobytes())

    sounds = {5: {"name": "kick.pcm", "size": 1000}}
    log = []
    client = FakeClient(sounds, log)
    client.get = lambda slot, path=None: (make_wav(path), log.append(("get", slot)))[1]

    monkeypatch.setattr(ko2, "EP133Client", lambda *a, **k: client)
    monkeypatch.setattr(ko2, "backup_copy", lambda *a, **k: None)
    monkeypatch.setattr(
        ko2, "optimize_sample",
        lambda p, **kw: (True, "already optimal", 1000, 1000),
    )

    view = make_view()
    rc = ko2.cmd_optimize(_args(slot=5, rate=None, speed=None, pitch=0.0, keep_stereo=False), view)

    assert rc == 0
    view.success.assert_called_once()
    assert "optimal" in view.success.call_args[0][0].lower()


def test_cmd_optimize_empty_slot(monkeypatch):
    client = FakeClient(sounds={})
    monkeypatch.setattr(ko2, "EP133Client", lambda *a, **k: client)

    view = make_view()
    rc = ko2.cmd_optimize(_args(slot=99, rate=None, speed=None, pitch=0.0, keep_stereo=False), view)

    assert rc == 1
    view.error.assert_called_once()
    view.success.assert_not_called()
