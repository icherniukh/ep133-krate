import pytest


pytestmark = pytest.mark.e2e


class TestPut:
    """Test put command."""

    def test_put_roundtrip(self, ep133_client):
        """Test upload then download verifies sample exists."""
        from pathlib import Path
        import tempfile

        from ko2_models import MAX_SLOTS, SAMPLE_RATE
        from ko2_client import EP133Error, SlotEmptyError
        from tests.helpers import create_test_wav

        # Find an empty slot to use for testing
        test_slot = None
        for slot in range(900, MAX_SLOTS):
            try:
                ep133_client.info(slot)
            except SlotEmptyError:
                test_slot = slot
                break

        if test_slot is None:
            pytest.skip(
                "No empty slots found in range 900-999", allow_module_level=True
            )

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            path = Path(tmp.name)

        try:
            create_test_wav(path, 0.1)

            # Upload
            ep133_client.put(path, test_slot, progress=False)

            # Verify by querying info
            info = ep133_client.info(test_slot)
            assert not info.is_empty
            assert info.slot == test_slot
            assert info.samplerate == SAMPLE_RATE

        finally:
            # Clean up
            try:
                ep133_client.delete(test_slot)
            except EP133Error:
                pass
            path.unlink(missing_ok=True)
