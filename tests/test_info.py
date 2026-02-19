#!/usr/bin/env python3
"""
E2E tests for KO2 info command.

Run with: pytest tests/test_info.py --device EP-133
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from ko2_client import EP133Client, find_device, SlotEmptyError
    MAX_SLOTS = 999
except ImportError as e:
    pytest.skip(f"Import error: {e}")


def get_device():
    """Get device from pytest fixture or auto-detect."""
    # Check if pytest --device was used
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', default=None)
    args, _ = parser.parse_known_args()
    return args.device or find_device()


@pytest.fixture(scope='module')
def client():
    """Shared client for all tests."""
    device = get_device()
    if not device:
        pytest.skip("EP-133 not found. Connect via USB.")
    with EP133Client(device) as c:
        yield c


class TestInfo:
    """Test info command."""

    def test_info_populated_slot(self, client):
        """Test getting info from a populated slot."""
        # First find a populated slot
        info = None
        for slot in range(1, MAX_SLOTS):
            try:
                info = client.info(slot)
                break
            except SlotEmptyError:
                continue

        # Device may be empty - verify behavior instead
        if info is None:
            # At least verify we can query empty slots without crash
            for slot in range(1, 10):
                try:
                    client.info(slot)
                except SlotEmptyError:
                    pass  # Expected for empty slot
            pytest.skip("Device is empty - cannot test populated slot")

        assert info.slot >= 1
        assert info.slot <= 999
        assert info.name != "(empty)"
        assert not info.is_empty

    def test_info_empty_slot(self, client):
        """Test that empty slot raises error."""
        # Find likely empty slot (high numbers often empty)
        with pytest.raises(SlotEmptyError):
            client.info(999)

    def test_info_sample_rate(self, client):
        """Test that sample rate is correct."""
        for slot in range(1, 100):
            try:
                info = client.info(slot)
                assert info.samplerate == 46875
                break
            except SlotEmptyError:
                continue

    def test_info_format(self, client):
        """Test format field is present."""
        for slot in range(1, 100):
            try:
                info = client.info(slot)
                assert info.format in ('s16', 's24', 'unknown')
                break
            except SlotEmptyError:
                continue


if __name__ == '__main__':
    # Run tests directly
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', help='MIDI device name')
    args = parser.parse_args()

    if args.device:
        device = args.device
    else:
        device = find_device()
        if not device:
            print("EP-133 not found")
            sys.exit(1)

    with EP133Client(device) as c:
        # Test populated slot
        print("Test: info populated slot...")
        for slot in range(1, 100):
            try:
                info = c.info(slot)
                print(f"  ✅ Slot {slot}: {info.name} @ {info.samplerate}Hz")
                break
            except SlotEmptyError:
                pass

        # Test empty slot
        print("Test: info empty slot...")
        try:
            c.info(999)
            print("  ❌ Should have raised error")
        except SlotEmptyError:
            print("  ✅ Correctly raises SlotEmptyError")
