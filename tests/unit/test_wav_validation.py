import tempfile
import wave
from pathlib import Path

import pytest

from ko2_client import EP133Client, EP133Error
from ko2_protocol import SAMPLE_RATE, BIT_DEPTH, CHANNELS
from tests.helpers import create_test_wav


def test_create_test_wav_is_valid_ep133_format():
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        create_test_wav(path, 0.1)
        with wave.open(str(path), "rb") as wav:
            assert wav.getframerate() == SAMPLE_RATE
            assert wav.getnchannels() == CHANNELS
            assert wav.getsampwidth() == BIT_DEPTH // 8
    finally:
        path.unlink(missing_ok=True)


def test_put_accepts_non_native_samplerate_without_device():
    # put() no longer enforces 46875 Hz; any positive rate is accepted.
    # Validation only rejects wrong channel count or bit depth.
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(CHANNELS)
            wav.setsampwidth(BIT_DEPTH // 8)
            wav.setframerate(8000)
            wav.writeframes(b"\x00\x00" * 1000)

        client = EP133Client.__new__(EP133Client)
        # Should NOT raise for sample rate — fails later at MIDI I/O
        with pytest.raises(Exception) as exc_info:
            client.put(path, 999, progress=False)
        assert "Sample rate" not in str(exc_info.value)
    finally:
        path.unlink(missing_ok=True)

