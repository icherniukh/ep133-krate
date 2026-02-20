import pytest


pytestmark = pytest.mark.e2e


class TestGroup:
    """Test group command."""

    def test_group_returns_mapping(self, ep133_client):
        """Test that group returns a mapping dict."""
        mapping = ep133_client.group(1, 50, direction='left')
        assert isinstance(mapping, dict)

    def test_group_left_direction(self, ep133_client):
        """Test grouping toward left (start)."""
        # Use a range likely to have samples
        mapping = ep133_client.group(1, 50, direction='left')

        for old_slot, new_slot in mapping.items():
            # New slots should be in order from start
            assert 1 <= new_slot <= 50

    def test_group_right_direction(self, ep133_client):
        """Test grouping toward right (end)."""
        mapping = ep133_client.group(700, 750, direction='right')

        for old_slot, new_slot in mapping.items():
            # New slots should be in order toward end
            assert 700 <= new_slot <= 750

    def test_group_invalid_range(self, ep133_client):
        """Test group with invalid range."""
        with pytest.raises(ValueError):
            ep133_client.group(100, 1)  # start > end

    def test_group_invalid_direction(self, ep133_client):
        """Test group with invalid direction."""
        with pytest.raises(ValueError):
            ep133_client.group(1, 50, direction='up')
