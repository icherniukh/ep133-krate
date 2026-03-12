import array
import math
import tempfile
import wave
from pathlib import Path

import pytest

from core.models import SAMPLE_RATE, BIT_DEPTH, CHANNELS


pytestmark = pytest.mark.e2e

TEST_SLOT = 899


def _make_test_wav(path: Path, freq_hz: float = 440.0, duration_sec: float = 0.2) -> array.array:
    """Create a sine-wave WAV and return the samples for comparison."""
    n = int(SAMPLE_RATE * duration_sec)
    samples = array.array("h", (
        int(16000 * math.sin(2 * math.pi * freq_hz * i / SAMPLE_RATE))
        for i in range(n)
    ))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(BIT_DEPTH // 8)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(samples.tobytes())
    return samples


def _read_wav_samples(path: Path) -> array.array:
    """Read all PCM frames from a WAV file as s16 samples."""
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
    samples = array.array("h")
    samples.frombytes(raw)
    return samples


class TestAudioEncoding:
    def test_upload_download_roundtrip(self, ep133_client):
        """Exact sample-level roundtrip: upload LE s16, download, compare."""
        from core.client import EP133Error, SlotEmptyError

        # Pre-flight: skip if slot is already occupied
        try:
            ep133_client.info(TEST_SLOT)
            pytest.skip(f"Slot {TEST_SLOT} is occupied — refusing to overwrite")
        except SlotEmptyError:
            pass

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            src = tmp / "original.wav"
            dst = tmp / "downloaded.wav"

            original_samples = _make_test_wav(src)

            try:
                ep133_client.put(src, TEST_SLOT, name="enc-test", progress=False)
                ep133_client.get(TEST_SLOT, dst)

                dl = _read_wav_samples(dst)
                orig = original_samples

                assert len(dl) == len(orig), (
                    f"Frame count mismatch: got {len(dl)}, expected {len(orig)}"
                )
                assert dl.tolist() == orig.tolist(), (
                    "Sample mismatch after roundtrip — encoding bug (byte order?)"
                )

            finally:
                try:
                    ep133_client.delete(TEST_SLOT)
                except EP133Error:
                    pass
