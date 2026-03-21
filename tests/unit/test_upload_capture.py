"""
Capture-based verification of the upload wire protocol.

Two test classes:

1. TestOfficialCapture — verifies protocol understanding against the official TE app's
   upload of sniffer-upload21.jsonl (slot 21, copyrighted WAV — no WAV file needed).
   Tests validate internal consistency of the capture only.

2. TestOfficialKickCapture — verifies the official TE app's upload of our copyright-free
   kick-46875hz.wav (slot 97, captured via sniffer-upload-kick-official.jsonl). Full PCM
   roundtrip comparison — proves the official tool sends WAV bytes unchanged, and our
   protocol decoding is correct.
"""
import json
import wave
from pathlib import Path

import pytest

from core.models import UPLOAD_CHUNK_SIZE, UploadEndRequest, SysExCmd

CAPTURES = Path(__file__).parents[2] / "captures"
FIXTURES = Path(__file__).parents[1] / "fixtures"

MFG_PREFIX = bytes([0x00, 0x20, 0x76, 0x33, 0x40])


def _decode_7bit(wire: bytes) -> bytes:
    """Decode TE 7-bit packed payload into raw bytes."""
    out = bytearray()
    i = 0
    while i < len(wire):
        flags = wire[i]
        i += 1
        group = wire[i : i + 7]
        for j, b in enumerate(group):
            out.append(b | 0x80 if (flags >> j) & 1 else b)
        i += len(group)
    return bytes(out)


def _load_capture(path: Path) -> list[bytes]:
    """Return decoded TX file-op payloads from a JSONL capture."""
    payloads = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            entry = json.loads(line)
            if entry["dir"] != "TX":
                continue
            raw = bytes.fromhex(entry["hex"])
            if raw[0] != 0xF0 or raw[1:6] != MFG_PREFIX:
                continue
            if len(raw) < 10 or raw[8] != 0x05:  # CMD_FILE
                continue
            payloads.append(_decode_7bit(raw[9:-1]))
    return payloads


def _extract_put_init(payloads: list[bytes]) -> bytes:
    return next(p for p in payloads if len(p) >= 4 and p[0] == 0x02 and p[1] == 0x00)


def _extract_put_data(payloads: list[bytes]) -> list[bytes]:
    return [p for p in payloads if len(p) >= 2 and p[0] == 0x02 and p[1] == 0x01]


# ---------------------------------------------------------------------------
# Official TE app capture — copyrighted WAV (sniffer-upload21.jsonl, slot 21)
# ---------------------------------------------------------------------------

OFFICIAL_CAPTURE = CAPTURES / "sniffer-upload21.jsonl"


@pytest.fixture(scope="module")
def official_payloads():
    if not OFFICIAL_CAPTURE.exists():
        pytest.skip("Official capture file not present")
    return _load_capture(OFFICIAL_CAPTURE)


class TestOfficialCapture:
    """Verify protocol understanding against official TE app upload (slot 21).

    Self-contained — validates internal consistency without the original WAV.
    """

    def test_put_init_slot_and_name(self, official_payloads):
        """PUT_INIT decodes to slot 21, name 'afterparty kick '."""
        init = _extract_put_init(official_payloads)

        assert init[2] == 0x05, "file type byte should be 0x05 (audio)"
        slot = (init[3] << 8) | init[4]
        assert slot == 21, f"expected slot 21, got {slot}"

        node = (init[5] << 8) | init[6]
        assert node == 1000, f"expected parent node 1000, got {node}"

        name_start = 11
        name_end = init.index(0, name_start)
        name = init[name_start:name_end].decode("utf-8")
        assert name == "afterparty kick ", f"unexpected name: {name!r}"

    def test_put_init_size_matches_chunk_data(self, official_payloads):
        """Declared size in PUT_INIT matches total PCM bytes in PUT_DATA chunks."""
        init = _extract_put_init(official_payloads)
        declared_size = int.from_bytes(init[7:11], "big")

        chunks = _extract_put_data(official_payloads)
        data_chunks = [c for c in chunks if len(c) > 4]
        actual_size = sum(len(c) - 4 for c in data_chunks)

        assert declared_size == actual_size, (
            f"PUT_INIT size {declared_size} != chunk data total {actual_size}"
        )

    def test_put_init_metadata_json(self, official_payloads):
        """Metadata JSON has valid channels and samplerate fields."""
        init = _extract_put_init(official_payloads)
        name_start = 11
        name_end = init.index(0, name_start)
        meta = json.loads(init[name_end + 1 :].decode("utf-8").rstrip("\x00"))

        assert meta["channels"] in (1, 2), f"unexpected channels: {meta['channels']}"
        assert meta["samplerate"] > 0, f"unexpected samplerate: {meta['samplerate']}"

    def test_put_data_empty_sentinel(self, official_payloads):
        """Last PUT_DATA chunk is an empty sentinel (0 PCM bytes)."""
        chunks = _extract_put_data(official_payloads)
        last = chunks[-1]
        assert len(last) == 4, (
            f"Last PUT chunk should have 0 PCM bytes (sentinel), got {len(last)-4}"
        )
        sentinel_ci = (last[2] << 8) | last[3]
        data_chunks = chunks[:-1]
        last_data_ci = (data_chunks[-1][2] << 8) | data_chunks[-1][3]
        assert sentinel_ci == last_data_ci + 1, (
            f"Sentinel chunk_index {sentinel_ci} should be last_data_ci+1={last_data_ci+1}"
        )

    def test_put_data_chunk_sizing(self, official_payloads):
        """All full chunks == UPLOAD_CHUNK_SIZE; last data chunk holds remainder."""
        chunks = _extract_put_data(official_payloads)
        data_chunks = [c for c in chunks if len(c) > 4]
        empty_chunks = [c for c in chunks if len(c) <= 4]

        pcm_sizes = [len(c) - 4 for c in data_chunks]
        assert all(s <= UPLOAD_CHUNK_SIZE for s in pcm_sizes)
        assert pcm_sizes[:-1] == [UPLOAD_CHUNK_SIZE] * (len(pcm_sizes) - 1)

        init = _extract_put_init(official_payloads)
        total_size = int.from_bytes(init[7:11], "big")
        expected_remainder = total_size % UPLOAD_CHUNK_SIZE or UPLOAD_CHUNK_SIZE
        assert pcm_sizes[-1] == expected_remainder
        assert len(empty_chunks) == 1

    def test_upload_opcode_is_0x7e(self, official_payloads):
        """All upload messages use opcode 0x7E (UPLOAD)."""
        assert UploadEndRequest.opcode == SysExCmd.UPLOAD


# ---------------------------------------------------------------------------
# Official TE app capture — copyright-free kick WAV (slot 97)
# ---------------------------------------------------------------------------

KICK_CAPTURE = CAPTURES / "sniffer-upload-kick-official.jsonl"
KICK_WAV = FIXTURES / "kick-46875hz.wav"


@pytest.fixture(scope="module")
def kick_payloads():
    if not KICK_CAPTURE.exists():
        pytest.skip("kick capture not present")
    return _load_capture(KICK_CAPTURE)


@pytest.fixture(scope="module")
def kick_wav():
    with wave.open(str(KICK_WAV), "rb") as w:
        return {
            "channels": w.getnchannels(),
            "framerate": w.getframerate(),
            "nframes": w.getnframes(),
            "raw": w.readframes(w.getnframes()),
        }


class TestOfficialKickCapture:
    """Verify official TE app upload of our copyright-free kick WAV.

    Full PCM comparison — proves official tool sends WAV bytes unchanged,
    validating our protocol decoding.
    """

    def test_put_init_slot_and_name(self, kick_payloads):
        """PUT_INIT decodes to slot 97, name 'kick-46875hz'."""
        init = _extract_put_init(kick_payloads)
        slot = (init[3] << 8) | init[4]
        assert slot == 97, f"expected slot 97, got {slot}"

        name_start = 11
        name_end = init.index(0, name_start)
        name = init[name_start:name_end].decode("utf-8")
        assert name == "kick-46875hz", f"unexpected name: {name!r}"

    def test_put_init_size_matches_wav(self, kick_payloads, kick_wav):
        """PUT_INIT size field matches the WAV's raw PCM byte count."""
        init = _extract_put_init(kick_payloads)
        declared_size = int.from_bytes(init[7:11], "big")
        assert declared_size == len(kick_wav["raw"])

    def test_put_init_metadata(self, kick_payloads, kick_wav):
        """Metadata JSON carries correct channels and samplerate."""
        init = _extract_put_init(kick_payloads)
        name_start = 11
        name_end = init.index(0, name_start)
        meta = json.loads(init[name_end + 1 :].decode("utf-8").rstrip("\x00"))

        assert meta["channels"] == kick_wav["channels"]
        assert meta["samplerate"] == kick_wav["framerate"]

    def test_pcm_bytes_unchanged(self, kick_payloads, kick_wav):
        """PUT_DATA chunks concatenate to the WAV's raw LE s16 bytes unchanged."""
        chunks = _extract_put_data(kick_payloads)
        data_chunks = [c for c in chunks if len(c) > 4]
        actual_pcm = b"".join(c[4:] for c in data_chunks)

        assert len(actual_pcm) == len(kick_wav["raw"]), (
            f"PCM length mismatch: got {len(actual_pcm)}, expected {len(kick_wav['raw'])}"
        )
        assert actual_pcm == kick_wav["raw"], (
            "PCM bytes from capture do not match WAV raw frames — encoding mismatch"
        )

    def test_sentinel_and_chunk_sizing(self, kick_payloads, kick_wav):
        """Chunk sizing matches UPLOAD_CHUNK_SIZE; sentinel present."""
        chunks = _extract_put_data(kick_payloads)
        data_chunks = [c for c in chunks if len(c) > 4]
        empty_chunks = [c for c in chunks if len(c) <= 4]

        pcm_sizes = [len(c) - 4 for c in data_chunks]
        assert all(s <= UPLOAD_CHUNK_SIZE for s in pcm_sizes)
        assert pcm_sizes[:-1] == [UPLOAD_CHUNK_SIZE] * (len(pcm_sizes) - 1)

        expected_remainder = len(kick_wav["raw"]) % UPLOAD_CHUNK_SIZE or UPLOAD_CHUNK_SIZE
        assert pcm_sizes[-1] == expected_remainder
        assert len(empty_chunks) == 1
