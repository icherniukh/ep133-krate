import tempfile
from pathlib import Path

import pytest

from cli.sysinfo import extract_total_memory as _extract_total_memory
from ko2_client import EP133Error

from tests.helpers import create_test_wav

pytestmark = pytest.mark.e2e

TEST_SLOTS = list(range(890, 900))  # reserved test zone
UPLOAD_SLOT_A = 893
UPLOAD_SLOT_B = 895
SQUASH_START = 891  # 893 → 891, 895 → 892
SQUASH_END = 899
EXPECTED_SLOTS = [891, 892]
MIN_FREE_BYTES = 100_000  # 100 KB


def _squash_range(client, start: int, end: int) -> None:
    """Move all occupied slots in [start..end] to fill sequentially from start."""
    sounds = client.list_sounds()
    used_slots = sorted(s for s in sounds if start <= s <= end)

    mapping: dict[int, int] = {}
    target = start
    for slot in used_slots:
        if slot != target:
            mapping[slot] = target
        target += 1

    for old_slot, new_slot in mapping.items():
        name = sounds[old_slot].get("name") or f"slot{old_slot:03d}"
        with tempfile.TemporaryDirectory(prefix=f"ko2-squash{old_slot}-") as td:
            tmp = Path(td) / f"slot{old_slot:03d}.wav"
            client.get(old_slot, tmp)
            client.delete(old_slot)
            client.put(tmp, new_slot, name=name, progress=False)


class TestSquashHardware:
    """Hardware test: upload to scattered slots, squash to compact them."""

    def test_squash_roundtrip(self, ep133_client):
        # Pre-flight: verify test zone is clear
        sounds = ep133_client.list_sounds()
        occupied = [s for s in TEST_SLOTS if s in sounds]
        if occupied:
            pytest.skip(f"Test slots not clean: {occupied}")

        # Memory check
        info = ep133_client.device_info()
        total_mem = _extract_total_memory(info) or (64 * 1024 * 1024)
        used_size = sum(int(e.get("size") or 0) for e in sounds.values())
        free = total_mem - used_size
        assert free >= MIN_FREE_BYTES, f"Insufficient free memory: {free:,} bytes"

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            wav_a = td_path / "sample_a.wav"
            wav_b = td_path / "sample_b.wav"
            create_test_wav(wav_a, duration_sec=0.2)
            create_test_wav(wav_b, duration_sec=0.3)

            try:
                # Upload to scattered slots
                ep133_client.put(wav_a, UPLOAD_SLOT_A, name="squash-test-a", progress=False)
                ep133_client.put(wav_b, UPLOAD_SLOT_B, name="squash-test-b", progress=False)

                sounds = ep133_client.list_sounds()
                assert UPLOAD_SLOT_A in sounds, f"Upload to slot {UPLOAD_SLOT_A} failed"
                assert UPLOAD_SLOT_B in sounds, f"Upload to slot {UPLOAD_SLOT_B} failed"

                # Squash range 891-899: 893→891, 895→892
                _squash_range(ep133_client, SQUASH_START, SQUASH_END)

                # Verify compacted positions
                sounds = ep133_client.list_sounds()
                for s in EXPECTED_SLOTS:
                    assert s in sounds, f"Expected sample at slot {s} after squash"
                assert UPLOAD_SLOT_A not in sounds, f"Slot {UPLOAD_SLOT_A} should be empty after squash"
                assert UPLOAD_SLOT_B not in sounds, f"Slot {UPLOAD_SLOT_B} should be empty after squash"

            finally:
                sounds = ep133_client.list_sounds()
                for slot in TEST_SLOTS:
                    if slot in sounds:
                        try:
                            ep133_client.delete(slot)
                        except EP133Error:
                            pass
