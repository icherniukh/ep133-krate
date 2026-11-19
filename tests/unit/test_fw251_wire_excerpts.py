"""Check the OS 2.5.1 wire facts that PROTOCOL.md cites from the excerpt fixture."""

import json
from pathlib import Path

from core.types import Packed7

FIXTURE = Path(__file__).parents[1] / "fixtures" / "fw251-wire-excerpts.jsonl"
HEADER = bytes.fromhex("F00020763340")


def _frames():
    return [json.loads(line) for line in FIXTURE.read_text().splitlines()]


def _body(frame):
    raw = bytes.fromhex(frame["hex"])
    assert raw[:6] == HEADER
    if raw[6] & 0x40:
        return Packed7.unpack(raw[9:-1])
    assert raw[9] == 0, "reply status"
    return Packed7.unpack(raw[10:-1])


def test_init_reply_reports_512_byte_chunks():
    frames = _frames()
    assert _body(frames[3]) == bytes.fromhex("010100400000")
    assert _body(frames[4]) == bytes.fromhex("0C00000200")


def test_sounds_formats_reply():
    reply = json.loads(_body(_frames()[6])[2:].rstrip(b"\x00"))
    assert reply["formats"] == [{
        "type": "pcm",
        "formats": [{
            "samplerate.range": [1, 65535],
            "samplerate.native": 46875,
            "channels": [1, 2],
            "format": ["s16"],
        }],
    }]


def test_root_lists_only_sounds_and_projects():
    frames = _frames()
    assert _body(frames[7]) == bytes.fromhex("0400000000")
    body = _body(frames[8])
    assert body == bytes.fromhex("0000" "03E80E00000000") + b"sounds\x00" + \
        bytes.fromhex("07D00E00000000") + b"projects\x00"
    assert _body(frames[10]) == bytes.fromhex("0001")


def test_whole_file_get_uses_8_byte_open_and_be16_pages():
    frames = _frames()
    assert _body(frames[11]) == bytes.fromhex("030000F800000000")
    reply = _body(frames[12])
    assert len(reply) == 64
    assert reply[:3] == bytes.fromhex("00F81D")
    assert int.from_bytes(reply[3:7], "big") == 148628
    assert reply[7:15] == b"248.pcm\x00"
    pages = [_body(f)[2:] for f in frames[13:17]]
    assert pages == [bytes.fromhex(p) for p in ("0000", "0001", "0080", "0100")]


def test_preview_open_layout():
    frames = _frames()
    body = _body(frames[17])
    assert body[:8] == bytes.fromhex("0300000C00000000")
    assert body[8:16] == bytes(8)
    assert body[16:] == bytes.fromhex("01" "0006" "07D0")
    assert int.from_bytes(_body(frames[18])[3:7], "big") == 8000
