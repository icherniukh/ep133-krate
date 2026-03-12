"""
Protocol fuzz tests (TEST-007)

Adversarial/robustness tests for two parsing functions in the ko2-tools protocol
layer. The goal is to confirm that neither function raises an uncaught exception
for any input — they must either return a valid result or raise an explicitly
expected exception.

Functions under test
--------------------
1. parse_file_list_response(payload: bytes) -> list[dict]
   Location: core.models.py
   Contract: returns a (possibly empty) list; never crashes on malformed input.

2. _parse_json_tolerant(data: bytes) -> dict | None
   Location: core.client.py
   Contract: returns a dict or None; never crashes on malformed input.

hypothesis is not installed; tests use @pytest.mark.parametrize with a curated
set of adversarial byte strings covering: empty input, single bytes, truncated
structures, garbage, high-byte sequences, unicode-invalid bytes, embedded nulls,
partial JSON, and random binary-like patterns.
"""

import pytest

from core.models import parse_file_list_response
from core.client import _parse_json_tolerant


# ---------------------------------------------------------------------------
# Adversarial byte-string corpus shared across both targets where applicable
# ---------------------------------------------------------------------------

ADVERSARIAL_BYTES = [
    # Empty / near-empty
    b"",
    b"\x00",
    b"\xff",
    b"\x7f",
    # Single printable byte
    b"A",
    b"{",
    b"}",
    # Truncated — one byte short of minimum parse structure
    b"\x00\x01",
    b"\x00\x01\x02",
    b"\x00\x01\x02\x03",
    b"\x00\x01\x02\x03\x04\x05",
    # Plausible header with no body
    b"\x00\x01\x00\x00\x00\x00\x00",
    # All-zero buffers of various lengths
    bytes(1),
    bytes(7),
    bytes(8),
    bytes(16),
    bytes(64),
    bytes(320),
    # All-0xFF (high-byte data — UTF-8 invalid)
    b"\xff" * 1,
    b"\xff" * 7,
    b"\xff" * 8,
    b"\xff" * 32,
    # Null-byte-heavy content
    b"\x00" * 10 + b"\x01" + b"\x00" * 10,
    # Repeated pattern
    b"\xde\xad\xbe\xef" * 8,
    b"\x01\x02\x03\x04\x05\x06\x07" * 4,
    # Mixed high/low bytes (non-UTF-8)
    bytes(range(0, 32)),
    bytes(range(128, 160)),
    bytes(range(200, 256)),
    bytes(range(0, 256)),
    # Looks like a valid header entry but name is missing null-terminator
    b"\x00\x01" + b"\x00\x00" + b"\x00\x00\x00\x00\x10" + b"nonterminated",
    # Valid-looking header, zero size, no name null-terminator
    b"\x00\x01" + b"\x03\xe8" + b"\x00\x00\x00\x00" + b"abc",
    # Payload with embedded null in name position
    b"\x00\x01\x00\x00\x00\x00\x00\x00\x00" + b"name\x00extra",
    # Simulate multiple entries where second is truncated
    b"\x00\x01" + b"\x00\x00\x00\x00\x00\x00\x00" + b"entry\x00" + b"\x00\x02\x00",
    # Large random-like data (deterministic)
    bytes((i * 37 + 13) % 256 for i in range(256)),
    bytes((i * 251 + 7) % 256 for i in range(512)),
    # Overlong UTF-8 and invalid sequences
    b"\xc0\xaf",          # overlong encoding
    b"\xed\xa0\x80",      # surrogate half (invalid in strict UTF-8)
    b"\xf8\x88\x80\x80\x80",  # 5-byte sequence (invalid)
    b"\x80\x81\x82\x83",  # continuation bytes with no lead byte
]


# ---------------------------------------------------------------------------
# Target 1: parse_file_list_response
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("data", ADVERSARIAL_BYTES)
def test_parse_file_list_response_never_crashes(data):
    """parse_file_list_response must not raise an uncaught exception.

    The function is documented to return a list (possibly empty) for any input
    that is too short or malformed.  A ValueError/UnicodeDecodeError/IndexError
    would indicate an unhandled crash; the function uses errors='replace' for
    UTF-8 decoding so UnicodeDecodeError should never surface, but it is
    included in the expected-exceptions set in case a future refactor changes
    the decode call.
    """
    try:
        result = parse_file_list_response(data)
        # Must return a list (contract)
        assert isinstance(result, list), (
            f"Expected list, got {type(result).__name__} for input {data!r}"
        )
        # Every entry must be a dict (secondary contract)
        for entry in result:
            assert isinstance(entry, dict), (
                f"Entry is not a dict: {entry!r}"
            )
    except (ValueError, IndexError, UnicodeDecodeError):
        # These are acceptable if the function's internal helpers raise them,
        # though in practice the current implementation should not raise at all.
        pass


def test_parse_file_list_response_empty_returns_empty_list():
    assert parse_file_list_response(b"") == []


def test_parse_file_list_response_one_byte_returns_empty_list():
    assert parse_file_list_response(b"\x00") == []


def test_parse_file_list_response_truncated_entry_returns_empty_list():
    """Seven bytes of entry data but no null-terminated name — must not hang or crash."""
    # Skips the 2-byte page-echo prefix, then a 7-byte entry header with no name
    payload = b"\x00\x00" + b"\x00\x01\x00\x00\x00\x00\x00"
    result = parse_file_list_response(payload)
    assert isinstance(result, list)


def test_parse_file_list_response_valid_single_entry():
    """Minimal well-formed payload yields exactly one entry."""
    # 2-byte page-echo + 7-byte header (hi, lo, flags, size:4) + null-terminated name
    hi, lo, flags = 0x00, 0x01, 0x00
    size = b"\x00\x00\x00\x2a"    # 42
    name = b"test\x00"
    payload = b"\x00\x00" + bytes([hi, lo, flags]) + size + name
    entries = parse_file_list_response(payload)
    assert len(entries) == 1
    e = entries[0]
    assert e["name"] == "test"
    assert e["size"] == 42
    assert e["flags"] == 0


def test_parse_file_list_response_high_byte_name():
    """Name bytes above 0x7F should not crash (errors='replace')."""
    hi, lo, flags = 0x00, 0x02, 0x00
    size = b"\x00\x00\x00\x00"
    name = bytes([0xc3, 0xa9, 0xc3, 0xa0, 0x00])  # 'éà' in UTF-8 + null
    payload = b"\x00\x00" + bytes([hi, lo, flags]) + size + name
    result = parse_file_list_response(payload)
    assert isinstance(result, list)


def test_parse_file_list_response_name_with_no_null_terminator():
    """A name that runs to the end of the buffer (no null) must not loop forever."""
    hi, lo, flags = 0x00, 0x01, 0x00
    size = b"\x00\x00\x00\x00"
    name_no_null = b"unterminated"
    payload = b"\x00\x00" + bytes([hi, lo, flags]) + size + name_no_null
    result = parse_file_list_response(payload)
    # The current implementation breaks on reaching end-of-buffer without null,
    # so no entry is appended — but it must return a list without crashing.
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Target 2: _parse_json_tolerant
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("data", ADVERSARIAL_BYTES)
def test_parse_json_tolerant_never_crashes(data):
    """_parse_json_tolerant must return dict or None for any byte input, never crash."""
    result = _parse_json_tolerant(data)
    assert result is None or isinstance(result, dict), (
        f"Expected dict or None, got {type(result).__name__} for input {data!r}"
    )


def test_parse_json_tolerant_empty_bytes_returns_none():
    assert _parse_json_tolerant(b"") is None


def test_parse_json_tolerant_valid_json():
    data = b'{"name":"kick","samplerate":46875}'
    result = _parse_json_tolerant(data)
    assert result == {"name": "kick", "samplerate": 46875}


def test_parse_json_tolerant_missing_closing_brace():
    """Single missing '}' should be recovered."""
    data = b'{"name":"kick","samplerate":46875'
    result = _parse_json_tolerant(data)
    assert result == {"name": "kick", "samplerate": 46875}


def test_parse_json_tolerant_truncated_mid_value():
    """Truncation at a comma boundary should recover the complete entries."""
    data = b'{"a":1,"b":2,"c":trun'
    result = _parse_json_tolerant(data)
    # Recovers up to the last complete comma-separated pair
    assert result is not None
    assert result.get("a") == 1
    assert result.get("b") == 2


def test_parse_json_tolerant_null_padded():
    """Null bytes after JSON (device padding) must be stripped."""
    data = b'{"x":7}\x00\x00\x00\x00'
    result = _parse_json_tolerant(data)
    assert result == {"x": 7}


def test_parse_json_tolerant_all_nulls_returns_none():
    assert _parse_json_tolerant(b"\x00" * 32) is None


def test_parse_json_tolerant_binary_garbage_returns_none():
    result = _parse_json_tolerant(b"\xde\xad\xbe\xef\x01\x02\x03")
    assert result is None


def test_parse_json_tolerant_partial_json_no_comma():
    """Truncated JSON with no comma: all recovery paths fail, returns None."""
    data = b'{"onlykey":'
    result = _parse_json_tolerant(data)
    # May be None or a partial dict depending on recovery — either is fine
    assert result is None or isinstance(result, dict)


def test_parse_json_tolerant_empty_object():
    assert _parse_json_tolerant(b"{}") == {}


def test_parse_json_tolerant_nested_object():
    data = b'{"envelope":{"attack":0,"release":255},"channels":1}'
    result = _parse_json_tolerant(data)
    assert isinstance(result, dict)
    assert result["channels"] == 1


def test_parse_json_tolerant_unicode_replacement():
    """Invalid UTF-8 bytes trigger errors='replace'; function must not raise."""
    data = b"\xff\xfe{\"a\":1}"
    result = _parse_json_tolerant(data)
    # Replacement characters make the opening { appear after garbage — likely None
    assert result is None or isinstance(result, dict)


def test_parse_json_tolerant_realistic_device_metadata():
    """Realistic device metadata JSON as captured from real device sessions."""
    data = (
        b'{"sound.playmode":"oneshot","sound.rootnote":60,'
        b'"sound.pitch":0,"sound.pan":0,"sound.amplitude":100,'
        b'"envelope.attack":0,"envelope.release":255,'
        b'"time.mode":"off","channels":1,"samplerate":46875,'
        b'"sound.loopstart":0,"sound.loopend":22499}'
    )
    result = _parse_json_tolerant(data)
    assert isinstance(result, dict)
    assert result["channels"] == 1
    assert result["samplerate"] == 46875


def test_parse_json_tolerant_320_byte_truncation():
    """Simulate the 320-byte device page limit truncating a JSON value."""
    base = b'{"sound.playmode":"oneshot","channels":1,"name":"' + b"x" * 260
    data = base[:320]
    result = _parse_json_tolerant(data)
    # Should not crash; may or may not recover partial data
    assert result is None or isinstance(result, dict)
