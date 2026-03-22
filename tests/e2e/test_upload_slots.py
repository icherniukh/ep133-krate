"""Upload/download roundtrip across slot ranges.

Tests slots <128, 128-255, and >=256 to verify VERIFY and slot encoding
work correctly across all ranges (the sub-byte bug would break >=256).
"""
import tempfile
import wave
from pathlib import Path

import pytest

from core.client import EP133Error, SlotEmptyError
from core.models import MAX_SAMPLE_RATE
from core.ops import copy_slot, move_slot
from tests.helpers import create_test_wav

pytestmark = pytest.mark.e2e

# Slots across encoding boundaries: <128, 128-255, >=256
TEST_ZONE = list(range(980, 1000))


def _find_empty_slots(client, count: int) -> list[int]:
    """Find `count` empty slots in the test zone."""
    sounds = client.list_sounds()
    empty = [s for s in TEST_ZONE if s not in sounds]
    if len(empty) < count:
        pytest.skip(f"Need {count} empty slots in {TEST_ZONE[0]}-{TEST_ZONE[-1]}, found {len(empty)}")
    return empty[:count]


class TestUploadSlotRanges:
    """Upload+download roundtrip verifying PCM integrity across slot ranges."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, ep133_client):
        yield
        sounds = ep133_client.list_sounds()
        for s in TEST_ZONE:
            if s in sounds:
                try:
                    ep133_client.delete(s)
                except EP133Error:
                    pass

    def test_upload_download_pcm_match(self, ep133_client):
        """Upload to 3 slots, download each, verify PCM byte-for-byte."""
        slots = _find_empty_slots(ep133_client, 3)

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            for i, slot in enumerate(slots):
                wav_path = td_path / f"test_{slot}.wav"
                create_test_wav(wav_path, duration_sec=0.05 + i * 0.02)

                ep133_client.put(wav_path, slot, name=f"test-{slot}")

                info = ep133_client.info(slot)
                assert not info.is_empty, f"Slot {slot} empty after upload"
                assert info.samplerate == MAX_SAMPLE_RATE

                dl_path = td_path / f"dl_{slot}.wav"
                ep133_client.get(slot, output_path=dl_path)

                with wave.open(str(wav_path), "rb") as w:
                    original = w.readframes(w.getnframes())
                with wave.open(str(dl_path), "rb") as w:
                    downloaded = w.readframes(w.getnframes())
                assert original == downloaded, f"Slot {slot}: PCM mismatch"


class TestCopy:
    """Copy slot and verify PCM integrity."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, ep133_client):
        yield
        sounds = ep133_client.list_sounds()
        for s in TEST_ZONE:
            if s in sounds:
                try:
                    ep133_client.delete(s)
                except EP133Error:
                    pass

    def test_copy_preserves_pcm(self, ep133_client):
        slots = _find_empty_slots(ep133_client, 2)
        src, dst = slots[0], slots[1]

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            wav_path = td_path / "source.wav"
            create_test_wav(wav_path, duration_sec=0.1)

            ep133_client.put(wav_path, src, name="copy-src")
            copy_slot(ep133_client, src, dst)

            info_dst = ep133_client.info(dst)
            assert not info_dst.is_empty

            dl_src = td_path / "dl_src.wav"
            dl_dst = td_path / "dl_dst.wav"
            ep133_client.get(src, output_path=dl_src)
            ep133_client.get(dst, output_path=dl_dst)

            with wave.open(str(dl_src), "rb") as w:
                pcm_src = w.readframes(w.getnframes())
            with wave.open(str(dl_dst), "rb") as w:
                pcm_dst = w.readframes(w.getnframes())
            assert pcm_src == pcm_dst, "Copy PCM mismatch"


class TestMove:
    """Move slot and verify source empty, destination PCM intact."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, ep133_client):
        yield
        sounds = ep133_client.list_sounds()
        for s in TEST_ZONE:
            if s in sounds:
                try:
                    ep133_client.delete(s)
                except EP133Error:
                    pass

    def test_move_preserves_pcm(self, ep133_client):
        slots = _find_empty_slots(ep133_client, 2)
        src, dst = slots[0], slots[1]

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            wav_path = td_path / "source.wav"
            create_test_wav(wav_path, duration_sec=0.1)

            ep133_client.put(wav_path, src, name="move-src")

            # Save original PCM
            dl_before = td_path / "dl_before.wav"
            ep133_client.get(src, output_path=dl_before)
            with wave.open(str(dl_before), "rb") as w:
                pcm_before = w.readframes(w.getnframes())

            move_slot(ep133_client, src, dst)

            # Source should be empty
            with pytest.raises(SlotEmptyError):
                ep133_client.info(src)

            # Destination PCM should match
            dl_after = td_path / "dl_after.wav"
            ep133_client.get(dst, output_path=dl_after)
            with wave.open(str(dl_after), "rb") as w:
                pcm_after = w.readframes(w.getnframes())
            assert pcm_before == pcm_after, "Move PCM mismatch"


class TestSquash:
    """Squash scattered slots into contiguous range, verify PCM."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, ep133_client):
        yield
        sounds = ep133_client.list_sounds()
        for s in TEST_ZONE:
            if s in sounds:
                try:
                    ep133_client.delete(s)
                except EP133Error:
                    pass

    def test_squash_compacts_and_preserves_pcm(self, ep133_client):
        slots = _find_empty_slots(ep133_client, 5)
        # Upload to scattered slots (0, 2, 4 of the 5 empty)
        slot_a, slot_b, slot_c = slots[0], slots[2], slots[4]
        squash_start = slots[0]

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            wavs = {}
            pcms = {}
            for i, slot in enumerate([slot_a, slot_b, slot_c]):
                wav_path = td_path / f"s{slot}.wav"
                create_test_wav(wav_path, duration_sec=0.05 + i * 0.03)
                ep133_client.put(wav_path, slot, name=f"squash-{slot}")

                dl = td_path / f"dl_orig_{slot}.wav"
                ep133_client.get(slot, output_path=dl)
                with wave.open(str(dl), "rb") as w:
                    pcms[slot] = w.readframes(w.getnframes())

            # Squash: move scattered to contiguous from squash_start
            sounds = ep133_client.list_sounds()
            used = sorted(s for s in [slot_a, slot_b, slot_c])
            mapping = {}
            target = squash_start
            for s in used:
                if s != target:
                    mapping[s] = target
                target += 1

            for old, new in mapping.items():
                name = f"squash-{old}"
                dl_tmp = td_path / f"squash_tmp_{old}.wav"
                ep133_client.get(old, output_path=dl_tmp)
                ep133_client.delete(old)
                ep133_client.put(dl_tmp, new, name=name)

            # Verify: contiguous slots have correct PCM
            expected_slots = [squash_start, squash_start + 1, squash_start + 2]
            original_order = [slot_a, slot_b, slot_c]

            for exp_slot, orig_slot in zip(expected_slots, original_order):
                info = ep133_client.info(exp_slot)
                assert not info.is_empty, f"Slot {exp_slot} empty after squash"

                dl_after = td_path / f"dl_after_{exp_slot}.wav"
                ep133_client.get(exp_slot, output_path=dl_after)
                with wave.open(str(dl_after), "rb") as w:
                    pcm_after = w.readframes(w.getnframes())
                assert pcm_after == pcms[orig_slot], (
                    f"Squash PCM mismatch: slot {orig_slot}->{exp_slot}"
                )
