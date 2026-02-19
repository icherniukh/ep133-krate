#!/usr/bin/env python3
"""
E2E tests for KO2 get command.

Run with: pytest tests/test_get.py --device EP-133
"""
import pytest
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from ko2_client import EP133Client, find_device, SlotEmptyError, MAX_SLOTS
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


class TestGet:
    """Test get command."""

    def test_get_empty_slot_raises(self, client):
        """Test that downloading empty slot raises error."""
        with pytest.raises(SlotEmptyError):
            client.get(999)

    def test_get_populated_slot(self, client):
        """Test downloading a populated slot."""
        # Find a populated slot
        target_slot = None
        for slot in range(1, MAX_SLOTS):
            try:
                client.info(slot)
                target_slot = slot
                break
            except SlotEmptyError:
                continue

        if target_slot is None:
            pytest.skip("No populated slot found on device")

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            result = client.get(target_slot, tmp_path)
            assert result.exists()
            assert result.stat().st_size > 1000  # At least 1KB
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_get_creates_wav(self, client):
        """Test that downloaded file is valid WAV."""
        import wave

        # Find a populated slot
        target_slot = None
        for slot in range(1, 100):
            try:
                client.info(slot)
                target_slot = slot
                break
            except SlotEmptyError:
                continue

        if target_slot is None:
            pytest.skip("No populated slot found")

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            client.get(target_slot, tmp_path)

            with wave.open(str(tmp_path), 'rb') as wav:
                assert wav.getnchannels() in (1, 2)
                assert wav.getframerate() == 46875
                assert wav.getsampwidth() == 2  # 16-bit
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_get_auto_filename(self, client):
        """Test auto-generated filename when output is None."""
        # Find a populated slot
        target_slot = None
        for slot in range(1, 100):
            try:
                info = client.info(slot)
                target_slot = slot
                break
            except SlotEmptyError:
                continue

        if target_slot is None:
            pytest.skip("No populated slot found")

        result = client.get(target_slot)  # No output path
        assert result.exists()
        # Clean up
        result.unlink()

    def test_get_empty_slot_raises(self, client):
        """Test that downloading empty slot raises error."""
        with pytest.raises(SlotEmptyError):
            client.get(999)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', help='MIDI device name')
    args = parser.parse_args()

    device = args.device or find_device()
    if not device:
        print("EP-133 not found")
        sys.exit(1)

    with EP133Client(device) as c:
        print("Test: get populated slot...")

        target_slot = None
        for slot in range(1, 100):
            try:
                c.info(slot)
                target_slot = slot
                break
            except SlotEmptyError:
                continue

        if target_slot:
            result = c.get(target_slot)
            print(f"  ✅ Downloaded slot {target_slot} to {result}")
            print(f"     Size: {result.stat().st_size} bytes")

            # Verify WAV
            import wave
            with wave.open(str(result), 'rb') as wav:
                print(f"     Rate: {wav.getframerate()} Hz")
                print(f"     Channels: {wav.getnchannels()}")

            result.unlink()
        else:
            print("  ⚠️  No populated slot found")
