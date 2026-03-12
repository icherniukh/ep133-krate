from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cli.cmd_transfer
import cli.cmd_slots
import cli.cmd_audio
import cli.cmd_system
import core.ops
import cli.helpers
from ko2_client import EP133Client, SlotEmptyError
from core.ops import backup_copy, optimize_sample
from ko2_display import View
from ko2_tui.waveform_store import WaveformStore
from tests.helpers import create_test_wav


class FingerprintClient:
    def __init__(self, wav_path: Path, slot: int = 7):
        self.wav_path = wav_path
        self.slot = int(slot)
        self.meta_patches: list[tuple[int, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def info(self, slot: int, include_size: bool = True):
        if int(slot) != self.slot:
            raise SlotEmptyError(f"slot {slot} empty")
        return SimpleNamespace(
            slot=self.slot,
            name="afterparty kick",
            size_bytes=1234,
            samplerate=46875,
            channels=1,
            sym="",
            format="s16",
        )

    def get(self, slot: int, output_path: Path):
        if int(slot) != self.slot:
            raise SlotEmptyError(f"slot {slot} empty")
        Path(output_path).write_bytes(self.wav_path.read_bytes())
        return Path(output_path)

    def update_slot_metadata(self, slot: int, patch: dict):
        self.meta_patches.append((int(slot), dict(patch)))
        return dict(patch)


def _view() -> Mock:
    return Mock(spec=View)


def test_fingerprint_write_populates_kv_and_metadata(monkeypatch, tmp_path):
    source_wav = tmp_path / "src.wav"
    create_test_wav(source_wav, duration_sec=0.15)
    fake = FingerprintClient(source_wav, slot=7)
    monkeypatch.setattr(cli.cmd_audio, "EP133Client", lambda *a, **k: fake)

    store_path = tmp_path / "waveform-kv.json"
    args = SimpleNamespace(
        device="EP-133",
        fp_action="write",
        slot=7,
        width=96,
        store=str(store_path),
        no_meta=False,
        file=None,
    )
    view = _view()
    rc = cli.cmd_audio.cmd_fingerprint(args, view)

    assert rc == 0
    assert fake.meta_patches
    patch = fake.meta_patches[-1][1]
    assert "ko2.fp.sha256" in patch

    store = WaveformStore(path=store_path)
    entry = store.get_entry_for_slot(7)
    assert entry is not None
    bins = entry.get("bins")
    assert isinstance(bins, dict)
    assert len(bins.get("mins") or []) == 96
    fp = entry.get("fp")
    assert isinstance(fp, dict)
    hash_hex = str(fp.get("sha256") or "")
    assert len(hash_hex) == 64
    assert store.get_fingerprint(hash_hex) is not None


def test_fingerprint_read_uses_cached_entry(monkeypatch, tmp_path):
    source_wav = tmp_path / "src.wav"
    create_test_wav(source_wav, duration_sec=0.1)
    fake = FingerprintClient(source_wav, slot=7)
    monkeypatch.setattr(cli.cmd_audio, "EP133Client", lambda *a, **k: fake)

    store_path = tmp_path / "waveform-kv.json"
    store = WaveformStore(path=store_path)
    sig = {
        "name": "afterparty kick",
        "size_bytes": 1234,
        "channels": 1,
        "samplerate": 46875,
    }
    fp = {
        "sha256": "a" * 64,
        "frames": 4687,
        "channels": 1,
        "samplerate": 46875,
        "duration_s": 0.1,
    }
    store.set_for_slot(7, sig, {"mins": [0] * 64, "maxs": [1] * 64, "width": 64}, fingerprint=fp)
    store.set_fingerprint(fp["sha256"], {"slot": 7, "bins": {"mins": [0], "maxs": [1], "width": 1}})

    args = SimpleNamespace(
        device="EP-133",
        fp_action="read",
        slot=7,
        width=64,
        store=str(store_path),
    )
    view = _view()
    rc = cli.cmd_audio.cmd_fingerprint(args, view)

    assert rc == 0
    view.section.assert_called_once()
    kv_pairs = [c.args for c in view.kv.call_args_list]
    assert ("Hash", "a" * 64) in kv_pairs


def test_fingerprint_verify_success(monkeypatch, tmp_path):
    source_wav = tmp_path / "src.wav"
    create_test_wav(source_wav, duration_sec=0.1)
    fake = FingerprintClient(source_wav, slot=7)
    monkeypatch.setattr(cli.cmd_audio, "EP133Client", lambda *a, **k: fake)

    store_path = tmp_path / "waveform-kv.json"
    write_args = SimpleNamespace(
        device="EP-133",
        fp_action="write",
        slot=7,
        width=96,
        store=str(store_path),
        no_meta=True,
        file=None,
    )
    assert cli.cmd_audio.cmd_fingerprint(write_args, _view()) == 0

    verify_args = SimpleNamespace(
        device="EP-133",
        fp_action="verify",
        slot=7,
        width=96,
        store=str(store_path),
        file=str(source_wav),
    )
    view = _view()
    rc = cli.cmd_audio.cmd_fingerprint(verify_args, view)
    assert rc == 0
    view.success.assert_called_once()
