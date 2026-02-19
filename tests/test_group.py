#!/usr/bin/env python3
"""
E2E tests for KO2 group command.

Run with: pytest tests/test_group.py --device EP-133
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from ko2_client import EP133Client, find_device
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


class TestGroup:
    """Test group command."""

    def test_group_returns_mapping(self, client):
        """Test that group returns a mapping dict."""
        mapping = client.group(1, 50, direction='left')
        assert isinstance(mapping, dict)

    def test_group_left_direction(self, client):
        """Test grouping toward left (start)."""
        # Use a range likely to have samples
        mapping = client.group(1, 50, direction='left')

        for old_slot, new_slot in mapping.items():
            # New slots should be in order from start
            assert 1 <= new_slot <= 50

    def test_group_right_direction(self, client):
        """Test grouping toward right (end)."""
        mapping = client.group(700, 750, direction='right')

        for old_slot, new_slot in mapping.items():
            # New slots should be in order toward end
            assert 700 <= new_slot <= 750

    def test_group_invalid_range(self, client):
        """Test group with invalid range."""
        with pytest.raises(ValueError):
            client.group(100, 1)  # start > end

    def test_group_invalid_direction(self, client):
        """Test group with invalid direction."""
        with pytest.raises(ValueError):
            client.group(1, 50, direction='up')


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
        print("Test: group returns mapping...")
        mapping = c.group(1, 50, 'left')
        print(f"  ✅ Found {len(mapping)} samples")
        if mapping:
            for old, new in list(mapping.items())[:5]:
                print(f"     {old} → {new}")
