from types import SimpleNamespace
from pathlib import Path

import cli.cmd_transfer
import cli.cmd_slots
import cli.cmd_audio
import cli.cmd_system
import core.ops
from core.client import EP133Client, SlotEmptyError
from core.ops import backup_copy, optimize_sample
from cli.display import TerminalView
from core.client import SlotEmptyError


class FakeClient:
    def __init__(self, sounds, log):
        self._sounds = sounds
        self._log = log

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def list_sounds(self):
        return self._sounds

    
    def info(self, slot, include_size=False):
        if slot not in self._sounds:
            raise SlotEmptyError(f"slot {slot} empty")
        e = self._sounds[slot]
        return SimpleNamespace(name=e.get("name"), size_bytes=e.get("size"))

    def get(self, slot, path: Path):
        path.write_bytes(b"dummy")
        self._log.append(("get", slot))

    def put(self, path: Path, slot: int, name=None, progress_callback=None):
        self._log.append(("put", slot, name))

    def delete(self, slot: int):
        self._log.append(("delete", slot))


def _args(**kwargs):
    return SimpleNamespace(
        device=None,
        raw=True,
        yes=True,
        **kwargs,
    )


def test_move_to_empty(monkeypatch):
    log = []
    sounds = {1: {"name": "001.pcm", "node_id": 1, "size": 100}}
    monkeypatch.setattr(cli.cmd_slots, "EP133Client", lambda *_args, **_kw: FakeClient(sounds, log))
    monkeypatch.setattr("core.ops.backup_copy", lambda *a, **k: None)

    rc = cli.cmd_slots.cmd_move(_args(src=1, dst=2), TerminalView())
    assert rc == 0
    assert log == [("get", 1), ("put", 2, "001.pcm"), ("delete", 1)]


def test_move_swap(monkeypatch):
    log = []
    sounds = {
        1: {"name": "001.pcm", "node_id": 1, "size": 100},
        2: {"name": "002.pcm", "node_id": 2, "size": 120},
    }
    monkeypatch.setattr(cli.cmd_slots, "EP133Client", lambda *_args, **_kw: FakeClient(sounds, log))
    monkeypatch.setattr("core.ops.backup_copy", lambda *a, **k: None)

    rc = cli.cmd_slots.cmd_move(_args(src=1, dst=2), TerminalView())
    assert rc == 0
    assert log == [
        ("get", 1),
        ("get", 2),
        ("put", 2, "001.pcm"),
        ("put", 1, "002.pcm"),
    ]


def test_copy_to_empty(monkeypatch):
    log = []
    sounds = {1: {"name": "001.pcm", "node_id": 1, "size": 100}}
    monkeypatch.setattr(cli.cmd_slots, "EP133Client", lambda *_args, **_kw: FakeClient(sounds, log))
    monkeypatch.setattr("core.ops.backup_copy", lambda *a, **k: None)

    rc = cli.cmd_slots.cmd_copy(_args(src=1, dst=3), TerminalView())
    assert rc == 0
    assert log == [("get", 1), ("put", 3, "001.pcm")]


def test_copy_overwrite(monkeypatch):
    log = []
    sounds = {
        1: {"name": "001.pcm", "node_id": 1, "size": 100},
        3: {"name": "003.pcm", "node_id": 3, "size": 90},
    }
    monkeypatch.setattr(cli.cmd_slots, "EP133Client", lambda *_args, **_kw: FakeClient(sounds, log))
    monkeypatch.setattr("core.ops.backup_copy", lambda *a, **k: None)

    rc = cli.cmd_slots.cmd_copy(_args(src=1, dst=3), TerminalView())
    assert rc == 0
    assert log == [
        ("get", 1),
        ("get", 3),
        ("delete", 3),
        ("put", 3, "001.pcm"),
    ]
