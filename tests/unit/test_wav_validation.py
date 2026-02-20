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


def test_put_rejects_invalid_samplerate_without_device():
    # EP133Client.put() validates WAV format before any MIDI I/O; so we can
    # unit-test the guardrails without CoreMIDI.
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(CHANNELS)
            wav.setsampwidth(BIT_DEPTH // 8)
            wav.setframerate(8000)
            wav.writeframes(b"\x00\x00" * 1000)

        client = EP133Client.__new__(EP133Client)
        with pytest.raises(EP133Error, match="Sample rate"):
            client.put(path, 999, progress=False)
    finally:
        path.unlink(missing_ok=True)

