import struct

from core.client import _detect_channels


def _pcm_bytes(samples: list[int]) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


def test_detect_channels_defaults_to_mono_for_tiny_buffers():
    assert _detect_channels(b"\x00\x01\x02\x03\x04\x05") == 1


def test_detect_channels_defaults_to_mono_for_silence():
    assert _detect_channels(_pcm_bytes([0, 0, 0, 0, 0, 0, 0, 0])) == 1


def test_detect_channels_recognizes_correlated_pcm_as_mono():
    mono_like = _pcm_bytes([1000, 1005, 1010, 1015, 1020, 1025, 1030, 1035])

    assert _detect_channels(mono_like) == 1


def test_detect_channels_recognizes_interleaved_stereo_pcm():
    stereo = _pcm_bytes([1200, -1200, 1000, -1000, 800, -800, 600, -600])

    assert _detect_channels(stereo) == 2
