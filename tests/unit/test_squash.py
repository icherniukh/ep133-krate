from pathlib import Path
from types import SimpleNamespace

import cli.cmd_transfer
import cli.cmd_slots
import cli.cmd_audio
import cli.cmd_system
import core.ops
from core.client import EP133Client, SlotEmptyError
from core.ops import backup_copy, optimize_sample
from cli.display import SilentView


class FakeClient:
    def __init__(self, sounds, log):
        self._sounds = sounds
        self._log = log

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def list_sounds(self):
        return self._sounds

    def get(self, slot, path: Path):
        path.write_bytes(b"dummy")
        self._log.append(("get", slot))

    def put(self, path: Path, slot: int, name=None, progress_callback=None):
        self._log.append(("put", slot, name))

    def delete(self, slot: int):
        self._log.append(("delete", slot))


def _args(**kwargs):
    defaults = dict(device=None, raw=True, yes=True, page=None, range=None, execute=False)
    return SimpleNamespace(**{**defaults, **kwargs})


# --- mapping algorithm (no I/O) ---

def test_squash_mapping_no_gaps():
    """Compact slots produce an empty mapping — nothing to move."""
    used_slots = [1, 2, 3]
    start = 1
    mapping = {}
    target = start
    for slot in used_slots:
        if slot != target:
            mapping[slot] = target
        target += 1
    assert mapping == {}


def test_squash_mapping_fills_gaps():
    """Slots with gaps are renumbered to fill from the range start."""
    # Samples at 1, 3, 7, 9 should map to 1, 2, 3, 4
    used_slots = [1, 3, 7, 9]
    start = 1
    mapping = {}
    target = start
    for slot in used_slots:
        if slot != target:
            mapping[slot] = target
        target += 1
    assert mapping == {3: 2, 7: 3, 9: 4}


def test_squash_mapping_no_leading_slot():
    """Gap at the start: first sample is not at range start."""
    # Range starts at 1, samples at 3 and 5
    used_slots = [3, 5]
    start = 1
    mapping = {}
    target = start
    for slot in used_slots:
        if slot != target:
            mapping[slot] = target
        target += 1
    assert mapping == {3: 1, 5: 2}


# --- cmd_squash integration (mocked client) ---

def test_squash_execute_moves_gapped_slots(monkeypatch):
    """--execute performs get/delete/put for each slot that needs to move."""
    log = []
    sounds = {
        1: {"name": "kick.pcm", "node_id": 1, "size": 100},
        3: {"name": "snare.pcm", "node_id": 3, "size": 100},
        7: {"name": "hat.pcm", "node_id": 7, "size": 100},
    }
    monkeypatch.setattr(cli.cmd_slots, "EP133Client", lambda *_a, **_kw: FakeClient(sounds, log))
    monkeypatch.setattr("core.ops.backup_copy", lambda *a, **k: None)

    rc = cli.cmd_slots.cmd_squash(_args(execute=True), SilentView())

    assert rc == 0
    # slot 1 stays — must not be touched
    assert ("get", 1) not in log
    assert ("delete", 1) not in log
    # slot 3 → 2
    assert ("get", 3) in log
    assert ("delete", 3) in log
    assert ("put", 2, "snare.pcm") in log
    # slot 7 → 3
    assert ("get", 7) in log
    assert ("delete", 7) in log
    assert ("put", 3, "hat.pcm") in log


def test_squash_execute_order_within_each_move(monkeypatch):
    """For each slot, get and delete happen before put to the new slot."""
    log = []
    sounds = {
        2: {"name": "bass.pcm", "node_id": 2, "size": 100},
    }
    monkeypatch.setattr(cli.cmd_slots, "EP133Client", lambda *_a, **_kw: FakeClient(sounds, log))
    monkeypatch.setattr("core.ops.backup_copy", lambda *a, **k: None)

    cli.cmd_slots.cmd_squash(_args(execute=True), SilentView())

    # slot 2 → 1: get then delete then put
    assert log.index(("get", 2)) < log.index(("delete", 2))
    assert log.index(("delete", 2)) < log.index(("put", 1, "bass.pcm"))


def test_squash_dry_run_fires_no_operations(monkeypatch):
    """Default dry-run mode prints the plan but issues no get/delete/put calls."""
    log = []
    sounds = {
        2: {"name": "bass.pcm", "node_id": 2, "size": 100},
        5: {"name": "pad.pcm", "node_id": 5, "size": 100},
    }
    monkeypatch.setattr(cli.cmd_slots, "EP133Client", lambda *_a, **_kw: FakeClient(sounds, log))
    monkeypatch.setattr("core.ops.backup_copy", lambda *a, **k: None)

    rc = cli.cmd_slots.cmd_squash(_args(execute=False), SilentView())

    assert rc == 0
    assert log == []


def test_squash_already_compact_exits_early(monkeypatch):
    """When there are no gaps, squash exits with rc=0 and no MIDI operations."""
    log = []
    sounds = {
        1: {"name": "a.pcm", "node_id": 1, "size": 100},
        2: {"name": "b.pcm", "node_id": 2, "size": 100},
        3: {"name": "c.pcm", "node_id": 3, "size": 100},
    }
    monkeypatch.setattr(cli.cmd_slots, "EP133Client", lambda *_a, **_kw: FakeClient(sounds, log))

    rc = cli.cmd_slots.cmd_squash(_args(execute=True), SilentView())

    assert rc == 0
    assert log == []
