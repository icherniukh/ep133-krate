from ko2_tui.waveform_store import WaveformStore
import json


def test_waveform_store_roundtrip(tmp_path):
    path = tmp_path / "waveform-kv.json"
    store = WaveformStore(path=path)
    sig = {"name": "kick", "size_bytes": 1234, "channels": 1, "samplerate": 46875}
    bins = {"mins": [-10, -5, -2], "maxs": [10, 7, 3], "width": 3}

    assert store.get_for_slot(1, sig) is None
    store.set_for_slot(1, sig, bins, fingerprint={"sha256": "a" * 64})
    assert store.get_for_slot(1, sig) == bins
    entry = store.get_entry_for_slot(1, sig)
    assert isinstance(entry, dict)
    assert isinstance(entry.get("fp"), dict)

    store2 = WaveformStore(path=path)
    assert store2.get_for_slot(1, sig) == bins


def test_waveform_store_signature_mismatch(tmp_path):
    store = WaveformStore(path=tmp_path / "waveform-kv.json")
    store.set_for_slot(
        7,
        {"name": "snare", "size_bytes": 2222, "channels": 1, "samplerate": 46875},
        {"mins": [0], "maxs": [0], "width": 1},
    )
    miss = store.get_for_slot(
        7,
        {"name": "snare-v2", "size_bytes": 2222, "channels": 1, "samplerate": 46875},
    )
    assert miss is None


def test_waveform_store_fingerprint_index_roundtrip(tmp_path):
    store = WaveformStore(path=tmp_path / "waveform-kv.json")
    hash_hex = "b" * 64
    payload = {"sha256": hash_hex, "slot": 9, "bins": {"mins": [0], "maxs": [1], "width": 1}}
    store.set_fingerprint(hash_hex, payload)
    got = store.get_fingerprint(hash_hex)
    assert got == payload


def test_waveform_store_uses_hash_first_layout(tmp_path):
    path = tmp_path / "waveform-kv.json"
    store = WaveformStore(path=path)
    sig = {"name": "hat", "size_bytes": 3333, "channels": 1, "samplerate": 46875}
    bins = {"mins": [0, -1], "maxs": [1, 2], "width": 2}
    fp = {"sha256": "d" * 64, "frames": 200, "channels": 1, "samplerate": 46875, "duration_s": 0.01}
    store.set_for_slot(12, sig, bins, fingerprint=fp)

    raw = json.loads(path.read_text(encoding="utf-8"))
    slot = raw["slots"]["12"]
    assert slot["hash"] == "d" * 64
    assert "bins" not in slot
    assert isinstance(raw["fingerprints"]["d" * 64]["bins"], dict)
