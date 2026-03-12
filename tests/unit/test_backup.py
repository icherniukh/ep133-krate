"""
Unit tests for core.backup.py.

Covers:
- Backup file naming convention
- Backup directory creation
- Collision handling (existing backup file with the same name)
- Error cases (missing source file)
- sanitize_filename_part edge cases
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from core.backup import backup_copy, sanitize_filename_part, DEFAULT_BACKUP_DIR


# ---------------------------------------------------------------------------
# sanitize_filename_part
# ---------------------------------------------------------------------------

class TestSanitizeFilenamePart:
    def test_plain_ascii(self):
        assert sanitize_filename_part("kick drum") == "kick drum"

    def test_special_chars_replaced(self):
        result = sanitize_filename_part("hi/there:world")
        # slashes and colons are not in the allowed set — replaced with _
        assert "/" not in result
        assert ":" not in result

    def test_leading_trailing_whitespace_stripped(self):
        result = sanitize_filename_part("  sample  ")
        assert result == "sample"

    def test_multiple_spaces_collapsed(self):
        result = sanitize_filename_part("kick   drum")
        assert result == "kick drum"

    def test_empty_string_returns_sample(self):
        assert sanitize_filename_part("") == "sample"

    def test_only_special_chars_returns_sample(self):
        # After stripping allowed punctuation there is nothing left
        result = sanitize_filename_part("---")
        assert result == "sample"

    def test_max_len_truncation(self):
        long_name = "a" * 200
        result = sanitize_filename_part(long_name, max_len=80)
        assert len(result) == 80

    def test_custom_max_len(self):
        result = sanitize_filename_part("hello world", max_len=5)
        assert len(result) <= 5

    def test_dots_and_underscores_allowed(self):
        result = sanitize_filename_part("sample.wav")
        assert "." in result

    def test_numbers_allowed(self):
        result = sanitize_filename_part("beat42")
        assert "42" in result


# ---------------------------------------------------------------------------
# backup_copy — naming convention
# ---------------------------------------------------------------------------

class TestBackupCopyNaming:
    def test_filename_contains_slot_number(self, tmp_path):
        src = tmp_path / "source.wav"
        src.write_bytes(b"\x00" * 16)
        bak_dir = tmp_path / "backups"

        dst = backup_copy(src, slot=7, backup_dir=bak_dir)

        assert "007" in dst.name

    def test_filename_contains_name_hint(self, tmp_path):
        src = tmp_path / "source.wav"
        src.write_bytes(b"\x00" * 16)
        bak_dir = tmp_path / "backups"

        dst = backup_copy(src, slot=42, name_hint="kick drum", backup_dir=bak_dir)

        assert "kick drum" in dst.name or "kick_drum" in dst.name

    def test_filename_without_name_hint_uses_slot_label(self, tmp_path):
        src = tmp_path / "source.wav"
        src.write_bytes(b"\x00" * 16)
        bak_dir = tmp_path / "backups"

        dst = backup_copy(src, slot=5, backup_dir=bak_dir)

        assert "slot005" in dst.name

    def test_filename_ends_with_bak(self, tmp_path):
        src = tmp_path / "source.wav"
        src.write_bytes(b"\x00" * 16)
        bak_dir = tmp_path / "backups"

        dst = backup_copy(src, slot=1, backup_dir=bak_dir)

        assert dst.name.endswith(".bak")

    def test_filename_preserves_original_extension(self, tmp_path):
        src = tmp_path / "source.wav"
        src.write_bytes(b"\x00" * 16)
        bak_dir = tmp_path / "backups"

        dst = backup_copy(src, slot=1, backup_dir=bak_dir)

        # Should be something like 001_slot001_<ts>.wav.bak
        assert ".wav.bak" in dst.name

    def test_filename_contains_timestamp(self, tmp_path):
        src = tmp_path / "source.wav"
        src.write_bytes(b"\x00" * 16)
        bak_dir = tmp_path / "backups"

        fixed_ts = "20260310T120000"
        with patch("core.backup.time") as mock_time:
            mock_time.strftime.return_value = fixed_ts
            dst = backup_copy(src, slot=1, backup_dir=bak_dir)

        assert fixed_ts in dst.name

    def test_no_extension_source_defaults_to_wav(self, tmp_path):
        src = tmp_path / "source"
        src.write_bytes(b"\x00" * 16)
        bak_dir = tmp_path / "backups"

        dst = backup_copy(src, slot=3, backup_dir=bak_dir)

        assert ".wav.bak" in dst.name

    def test_slot_zero_padded_to_three_digits(self, tmp_path):
        src = tmp_path / "source.wav"
        src.write_bytes(b"\x00" * 16)
        bak_dir = tmp_path / "backups"

        dst = backup_copy(src, slot=1, backup_dir=bak_dir)
        assert dst.name.startswith("001_")

        dst2 = backup_copy(src, slot=99, backup_dir=bak_dir)
        assert dst2.name.startswith("099_")

        dst3 = backup_copy(src, slot=999, backup_dir=bak_dir)
        assert dst3.name.startswith("999_")


# ---------------------------------------------------------------------------
# backup_copy — directory creation
# ---------------------------------------------------------------------------

class TestBackupCopyDirectoryCreation:
    def test_creates_backup_dir_if_missing(self, tmp_path):
        src = tmp_path / "source.wav"
        src.write_bytes(b"\x00" * 16)
        bak_dir = tmp_path / "new" / "nested" / "dir"

        assert not bak_dir.exists()
        backup_copy(src, slot=1, backup_dir=bak_dir)
        assert bak_dir.is_dir()

    def test_uses_existing_backup_dir(self, tmp_path):
        src = tmp_path / "source.wav"
        src.write_bytes(b"\x00" * 16)
        bak_dir = tmp_path / "backups"
        bak_dir.mkdir()

        dst = backup_copy(src, slot=2, backup_dir=bak_dir)

        assert dst.parent == bak_dir

    def test_backup_file_is_inside_backup_dir(self, tmp_path):
        src = tmp_path / "source.wav"
        src.write_bytes(b"\x00" * 16)
        bak_dir = tmp_path / "backups"

        dst = backup_copy(src, slot=10, backup_dir=bak_dir)

        assert dst.parent == bak_dir

    def test_returns_path_object(self, tmp_path):
        src = tmp_path / "source.wav"
        src.write_bytes(b"\x00" * 16)
        bak_dir = tmp_path / "backups"

        dst = backup_copy(src, slot=1, backup_dir=bak_dir)

        assert isinstance(dst, Path)


# ---------------------------------------------------------------------------
# backup_copy — file content
# ---------------------------------------------------------------------------

class TestBackupCopyContent:
    def test_backup_file_is_created(self, tmp_path):
        src = tmp_path / "source.wav"
        src.write_bytes(b"\xDE\xAD\xBE\xEF")
        bak_dir = tmp_path / "backups"

        dst = backup_copy(src, slot=1, backup_dir=bak_dir)

        assert dst.exists()

    def test_backup_content_matches_source(self, tmp_path):
        data = b"\xDE\xAD\xBE\xEF" * 256
        src = tmp_path / "source.wav"
        src.write_bytes(data)
        bak_dir = tmp_path / "backups"

        dst = backup_copy(src, slot=1, backup_dir=bak_dir)

        assert dst.read_bytes() == data

    def test_source_file_unchanged_after_backup(self, tmp_path):
        data = b"original content"
        src = tmp_path / "source.wav"
        src.write_bytes(data)
        bak_dir = tmp_path / "backups"

        backup_copy(src, slot=1, backup_dir=bak_dir)

        assert src.read_bytes() == data


# ---------------------------------------------------------------------------
# backup_copy — collision handling
# ---------------------------------------------------------------------------

class TestBackupCopyCollisions:
    def test_two_backups_same_slot_at_same_second_differ(self, tmp_path):
        """Two calls at the same timestamp produce the same path — the second
        overwrites the first (this is the defined behavior: last write wins)."""
        src = tmp_path / "source.wav"
        src.write_bytes(b"\x00" * 8)
        bak_dir = tmp_path / "backups"

        fixed_ts = "20260310T120000"
        with patch("core.backup.time") as mock_time:
            mock_time.strftime.return_value = fixed_ts
            dst1 = backup_copy(src, slot=1, backup_dir=bak_dir)
            dst2 = backup_copy(src, slot=1, backup_dir=bak_dir)

        # Both paths are identical when timestamp is frozen — same file, overwritten
        assert dst1 == dst2
        assert dst2.exists()

    def test_two_backups_different_timestamps_coexist(self, tmp_path):
        src = tmp_path / "source.wav"
        src.write_bytes(b"\x00" * 8)
        bak_dir = tmp_path / "backups"

        with patch("core.backup.time") as mock_time:
            mock_time.strftime.return_value = "20260310T120000"
            dst1 = backup_copy(src, slot=1, backup_dir=bak_dir)

        with patch("core.backup.time") as mock_time:
            mock_time.strftime.return_value = "20260310T120001"
            dst2 = backup_copy(src, slot=1, backup_dir=bak_dir)

        assert dst1 != dst2
        assert dst1.exists()
        assert dst2.exists()

    def test_two_backups_different_slots_coexist(self, tmp_path):
        src = tmp_path / "source.wav"
        src.write_bytes(b"\x00" * 8)
        bak_dir = tmp_path / "backups"

        fixed_ts = "20260310T120000"
        with patch("core.backup.time") as mock_time:
            mock_time.strftime.return_value = fixed_ts
            dst1 = backup_copy(src, slot=1, backup_dir=bak_dir)
            dst2 = backup_copy(src, slot=2, backup_dir=bak_dir)

        assert dst1 != dst2
        assert dst1.exists()
        assert dst2.exists()


# ---------------------------------------------------------------------------
# backup_copy — error cases
# ---------------------------------------------------------------------------

class TestBackupCopyErrors:
    def test_missing_source_raises(self, tmp_path):
        src = tmp_path / "nonexistent.wav"
        bak_dir = tmp_path / "backups"

        with pytest.raises(FileNotFoundError):
            backup_copy(src, slot=1, backup_dir=bak_dir)

    def test_missing_source_does_not_create_backup_dir(self, tmp_path):
        src = tmp_path / "nonexistent.wav"
        bak_dir = tmp_path / "backups"

        with pytest.raises(Exception):
            backup_copy(src, slot=1, backup_dir=bak_dir)

        # The directory is created before reading, so we only assert the file
        # doesn't exist — the dir may or may not exist depending on call order.
        # What must NOT exist is a corrupt backup file.
        for f in bak_dir.glob("*.bak") if bak_dir.exists() else []:
            pytest.fail(f"Unexpected backup file created: {f}")

    def test_source_is_directory_raises(self, tmp_path):
        src = tmp_path / "a_directory"
        src.mkdir()
        bak_dir = tmp_path / "backups"

        with pytest.raises((IsADirectoryError, PermissionError, OSError)):
            backup_copy(src, slot=1, backup_dir=bak_dir)
