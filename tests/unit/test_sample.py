import pytest
from core.models import Sample, MAX_SAMPLE_RATE


class TestSampleFormatting:
    def test_formatted_size_zero(self):
        s = Sample(slot=1, name="x", size_bytes=0)
        assert s.formatted_size == "-"

    def test_formatted_size_bytes(self):
        s = Sample(slot=1, name="x", size_bytes=512)
        assert s.formatted_size == "  512B"

    def test_formatted_size_kilobytes(self):
        s = Sample(slot=1, name="x", size_bytes=51200)
        assert s.formatted_size == "  50.00K"

    def test_formatted_size_megabytes(self):
        s = Sample(slot=1, name="x", size_bytes=2 * 1024 * 1024)
        assert s.formatted_size == "   2.00M"

    def test_duration_str_one_second(self):
        # 1 second of mono 16-bit at 46875 Hz = 93750 bytes
        s = Sample(slot=1, name="x", size_bytes=93750, samplerate=MAX_SAMPLE_RATE, channels=1)
        assert s.duration_str == "1.000"

    def test_duration_str_zero(self):
        s = Sample(slot=1, name="x", size_bytes=0)
        assert s.duration_str == "-"

    def test_duration_str_stereo(self):
        s = Sample(slot=1, name="x", size_bytes=93750 * 2, samplerate=MAX_SAMPLE_RATE, channels=2)
        assert s.duration_str == "1.000"

    def test_channels_abbr_mono(self):
        s = Sample(slot=1, name="x", channels=1)
        assert s.channels_abbr == "M"

    def test_channels_abbr_stereo(self):
        s = Sample(slot=1, name="x", channels=2)
        assert s.channels_abbr == "S"

    def test_channels_abbr_unknown(self):
        s = Sample(slot=1, name="x", channels=0)
        assert s.channels_abbr == "-"

    def test_slot_id(self):
        s = Sample(slot=7, name="x")
        assert s.slot_id == "007"

    def test_size_band_zero(self):
        s = Sample(slot=1, name="x", size_bytes=0)
        assert s.size_band is None

    def test_size_band_small(self):
        s = Sample(slot=1, name="x", size_bytes=25 * 1024)
        band = s.size_band
        assert band is not None
        assert band[0] == 0

    def test_size_band_large(self):
        s = Sample(slot=1, name="x", size_bytes=5 * 1024 * 1024)
        band = s.size_band
        assert band is not None
        assert band[0] == 5


class TestSampleFactory:
    def test_empty(self):
        s = Sample.empty(42)
        assert s.slot == 42
        assert s.is_empty is True
        assert s.name == "(empty)"
        assert s.formatted_size == "-"

    def test_defaults(self):
        s = Sample(slot=1, name="kick")
        assert s.samplerate == MAX_SAMPLE_RATE
        assert s.channels == 1
        assert s.size_bytes == 0
        assert s.is_empty is False


class TestSampleStaticHelpers:
    def test_format_size_standalone(self):
        assert Sample.format_size(51200) == "  50.00K"
        assert Sample.format_size(0) == "-"

    def test_format_duration_standalone(self):
        assert Sample.format_duration(93750, MAX_SAMPLE_RATE, 1) == "1.000"
        assert Sample.format_duration(0) == "-"

    def test_channels_label_standalone(self):
        assert Sample.channels_label(1) == "M"
        assert Sample.channels_label(2) == "S"
        assert Sample.channels_label(0) == "-"

    def test_size_band_for_standalone(self):
        assert Sample.size_band_for(0) is None
        band = Sample.size_band_for(25 * 1024)
        assert band is not None
        assert band[0] == 0
