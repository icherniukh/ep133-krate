import pytest

from ko2_client import SlotEmptyError
from ko2_models import MAX_SLOTS, SAMPLE_RATE


pytestmark = pytest.mark.e2e


class TestInfo:
    """Test info command."""

    def test_info_populated_slot(self, ep133_client):
        """Test getting info from a populated slot."""
        # First find a populated slot
        info = None
        for slot in range(1, MAX_SLOTS):
            try:
                info = ep133_client.info(slot)
                break
            except SlotEmptyError:
                continue

        # Device may be empty - verify behavior instead
        if info is None:
            # At least verify we can query empty slots without crash
            for slot in range(1, 10):
                try:
                    ep133_client.info(slot)
                except SlotEmptyError:
                    pass  # Expected for empty slot
            pytest.skip("Device is empty - cannot test populated slot", allow_module_level=True)

        assert info.slot >= 1
        assert info.slot <= 999
        assert info.name != "(empty)"
        assert not info.is_empty

    def test_info_empty_slot(self, ep133_client):
        """Test that empty slot raises error."""
        sounds = ep133_client.list_sounds()
        empty_slot = next((s for s in range(1, MAX_SLOTS) if s not in sounds), None)
        if empty_slot is None:
            pytest.skip("No empty slots available on device", allow_module_level=True)

        with pytest.raises(SlotEmptyError):
            ep133_client.info(empty_slot)

    def test_info_sample_rate(self, ep133_client):
        """Test that sample rate is correct."""
        for slot in range(1, 100):
            try:
                info = ep133_client.info(slot)
                assert info.samplerate in (44100, SAMPLE_RATE)
                break
            except SlotEmptyError:
                continue

    def test_info_format(self, ep133_client):
        """Test format field is present."""
        for slot in range(1, 100):
            try:
                info = ep133_client.info(slot)
                assert info.format in ('s16', 's24', 'unknown')
                break
            except SlotEmptyError:
                continue
