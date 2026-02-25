import tempfile
from pathlib import Path

import pytest

from ko2_client import SlotEmptyError
from ko2_models import MAX_SLOTS


pytestmark = pytest.mark.e2e


class TestGet:
    """Test get command."""

    def test_get_empty_slot_raises(self, ep133_client):
        """Test that downloading empty slot raises error."""
        with pytest.raises(SlotEmptyError):
            ep133_client.get(999)

    def test_get_populated_slot(self, ep133_client):
        """Test downloading a populated slot."""
        # Find a populated slot
        target_slot = None
        for slot in range(1, MAX_SLOTS):
            try:
                ep133_client.info(slot)
                target_slot = slot
                break
            except SlotEmptyError:
                continue

        if target_slot is None:
            pytest.skip("No populated slot found on device", allow_module_level=True)

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            result = ep133_client.get(target_slot, tmp_path)
            assert result.exists()
            assert result.stat().st_size > 1000  # At least 1KB
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_get_creates_wav(self, ep133_client):
        """Test that downloaded file is valid WAV."""
        import wave

        # Find a populated slot
        target_slot = None
        for slot in range(1, 100):
            try:
                ep133_client.info(slot)
                target_slot = slot
                break
            except SlotEmptyError:
                continue

        if target_slot is None:
            pytest.skip("No populated slot found", allow_module_level=True)

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            ep133_client.get(target_slot, tmp_path)

            with wave.open(str(tmp_path), 'rb') as wav:
                assert wav.getnchannels() in (1, 2)
                assert wav.getframerate() in (44100, 46875)
                assert wav.getsampwidth() == 2  # 16-bit
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_get_auto_filename(self, ep133_client):
        """Test auto-generated filename when output is None."""
        # Find a populated slot
        target_slot = None
        for slot in range(1, 100):
            try:
                info = ep133_client.info(slot)
                target_slot = slot
                break
            except SlotEmptyError:
                continue

        if target_slot is None:
            pytest.skip("No populated slot found", allow_module_level=True)

        result = ep133_client.get(target_slot)  # No output path
        assert result.exists()
        # Clean up
        result.unlink()
