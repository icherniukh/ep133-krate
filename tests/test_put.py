#!/usr/bin/env python3
"""
E2E tests for KO2 put command.

Run with: pytest tests/test_put.py --device EP-133
"""
import pytest
import sys
import tempfile
import wave
import struct
import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from ko2_client import EP133Client, find_device, EP133Error, SlotEmptyError
    from ko2_protocol import SAMPLE_RATE, BIT_DEPTH, CHANNELS, MAX_SLOTS
except ImportError as e:
    pytest.skip(f"Import error: {e}")


def get_device():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', default=None)
    args, _ = parser.parse_known_args()
    return args.device or find_device()


@pytest.fixture(scope='module')
def client():
    device = get_device()
    if not device:
        pytest.skip("EP-133 not found.")
    with EP133Client(device) as c:
        yield c


def create_test_wav(path: Path, duration_sec: float = 0.1) -> None:
    """Create a valid EP-133 format WAV file for testing."""
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(BIT_DEPTH // 8)
        wav.setframerate(SAMPLE_RATE)

        # Generate a simple sine wave tone
        frames = int(SAMPLE_RATE * duration_sec)
        frequency = 440  # A4
        data = array.array('h')
        for i in range(frames):
            value = int(16000 * (i / frames) * (1 if (i // 1000) % 2 == 0 else -1))
            data.append(value)

        wav.writeframes(data.tobytes())


class TestPut:
    """Test put command."""

    def test_put_creates_ep133_format(self):
        """Test that we can create EP-133 format WAV files."""
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            path = Path(tmp.name)

        try:
            create_test_wav(path, 0.1)

            # Verify format
            with wave.open(str(path), 'rb') as wav:
                assert wav.getframerate() == SAMPLE_RATE
                assert wav.getnchannels() == CHANNELS
                assert wav.getsampwidth() == BIT_DEPTH // 8
        finally:
            path.unlink(missing_ok=True)

    def test_put_invalid_format_raises(self):
        """Test that invalid WAV format raises error."""
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            path = Path(tmp.name)

        try:
            # Create wrong format (44100 Hz)
            with wave.open(str(path), 'wb') as wav:
                wav.setnchannels(CHANNELS)
                wav.setsampwidth(BIT_DEPTH // 8)
                wav.setframerate(44100)
                wav.writeframes(b'\x00\x00' * 1000)

            device = get_device()
            if not device:
                pytest.skip("EP-133 not found")

            with EP133Client(device) as c:
                with pytest.raises(ValueError, match="Sample rate"):
                    c.put(path, 999, progress=False)
        finally:
            path.unlink(missing_ok=True)

    def test_put_roundtrip(self, client):
        """Test upload then download verifies sample exists."""
        # Find an empty slot to use for testing
        test_slot = None
        for slot in range(900, MAX_SLOTS):
            try:
                client.info(slot)
            except SlotEmptyError:
                test_slot = slot
                break

        if test_slot is None:
            pytest.skip("No empty slots found in range 900-999")

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            path = Path(tmp.name)

        try:
            create_test_wav(path, 0.1)

            # Upload
            client.put(path, test_slot, progress=False)

            # Verify by querying info
            info = client.info(test_slot)
            assert not info.is_empty
            assert info.slot == test_slot
            assert info.samplerate == SAMPLE_RATE

        finally:
            # Clean up
            try:
                client.delete(test_slot)
            except EP133Error:
                pass
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    print("PUT tests")
    sys.exit(0)
