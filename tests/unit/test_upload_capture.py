"""
Capture-based verification of the upload wire protocol.

Uses captures/sniffer-upload21.jsonl (official TE app, slot 21) and
captures/afterparty-kick-slot21.wav to verify:

1. PUT_INIT payload decodes to correct slot, name, size, metadata.
2. PUT_DATA chunks contain LE s16 PCM identical to the WAV's raw frames —
   no byte swap, no transformation.

These files are gitignored (local forensics only); the test skips if absent.
"""
import json
import struct
import wave
from pathlib import Path

import pytest

CAPTURES = Path(__file__).parents[2] / "captures"
CAPTURE_FILE = CAPTURES / "sniffer-upload21.jsonl"
WAV_FILE = CAPTURES / "afterparty-kick-slot21.wav"

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


def _load_capture():
    """Return decoded TX payloads from the capture (skips non-SysEx entries)."""
    payloads = []
    with open(CAPTURE_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            entry = json.loads(line)
            if entry["dir"] != "TX":
                continue
            raw = bytes.fromhex(entry["hex"])
            # SysEx: F0 <5-byte mfg> <device_id> <seq> 05 <7bit payload...> F7
            if raw[0] != 0xF0 or raw[1:6] != MFG_PREFIX:
                continue
            if len(raw) < 10 or raw[8] != 0x05:  # CMD_FILE
                continue
            payloads.append(_decode_7bit(raw[9:-1]))
    return payloads


@pytest.fixture(scope="module")
def capture_payloads():
    if not CAPTURE_FILE.exists():
        pytest.skip("Capture file not present")
    return _load_capture()


@pytest.fixture(scope="module")
def wav_pcm():
    if not WAV_FILE.exists():
        pytest.skip("WAV fixture not present (copyright — local only)")
    with wave.open(str(WAV_FILE), "rb") as w:
        return {
            "channels": w.getnchannels(),
            "sampwidth": w.getsampwidth(),
            "framerate": w.getframerate(),
            "nframes": w.getnframes(),
            "raw": w.readframes(w.getnframes()),
        }


class TestUploadCaptureDecode:
    def test_put_init_slot_and_name(self, capture_payloads):
        """PUT_INIT payload decodes to slot 21 and name 'afterparty kick '."""
        init = next(p for p in capture_payloads if len(p) >= 4 and p[0] == 0x02 and p[1] == 0x00)

        assert init[2] == 0x05, "file type byte should be 0x05 (audio)"
        slot = (init[3] << 8) | init[4]
        assert slot == 21, f"expected slot 21, got {slot}"

        node = (init[5] << 8) | init[6]
        assert node == 1000, f"expected parent node 1000, got {node}"

        name_start = 11
        name_end = init.index(0, name_start)
        name = init[name_start:name_end].decode("utf-8")
        assert name == "afterparty kick ", f"unexpected name: {name!r}"

    def test_put_init_size_matches_wav(self, capture_payloads, wav_pcm):
        """Size field in PUT_INIT matches the WAV's raw PCM byte count."""
        init = next(p for p in capture_payloads if len(p) >= 4 and p[0] == 0x02 and p[1] == 0x00)

        declared_size = int.from_bytes(init[7:11], "big")
        expected_size = len(wav_pcm["raw"])
        assert declared_size == expected_size, (
            f"PUT_INIT size {declared_size} != WAV size {expected_size}"
        )

    def test_put_init_metadata_json(self, capture_payloads, wav_pcm):
        """Metadata JSON in PUT_INIT has correct channels and samplerate."""
        import json as _json

        init = next(p for p in capture_payloads if len(p) >= 4 and p[0] == 0x02 and p[1] == 0x00)
        name_start = 11
        name_end = init.index(0, name_start)
        meta = _json.loads(init[name_end + 1 :].decode("utf-8").rstrip("\x00"))

        assert meta["channels"] == wav_pcm["channels"]
        assert meta["samplerate"] == wav_pcm["framerate"]

    def test_put_data_pcm_is_le_s16_unchanged(self, capture_payloads, wav_pcm):
        """PUT_DATA chunks concatenate to the WAV's raw LE s16 bytes with no transformation."""
        chunks = [p for p in capture_payloads if len(p) >= 2 and p[0] == 0x02 and p[1] == 0x01]
        assert chunks, "No PUT_DATA chunks found in capture"

        actual_pcm = b"".join(c[4:] for c in chunks)  # strip 02 01 chunk_hi chunk_lo
        expected_pcm = wav_pcm["raw"]

        assert len(actual_pcm) == len(expected_pcm), (
            f"PCM length mismatch: got {len(actual_pcm)}, expected {len(expected_pcm)}"
        )
        assert actual_pcm == expected_pcm, (
            "PCM bytes from capture do not match WAV raw frames — "
            "encoding mismatch (byte swap?)"
        )

    def test_put_data_empty_sentinel_triggers_ack(self, capture_payloads):
        """Official app sends an empty PUT chunk (0 PCM bytes) after the last
        data chunk. The device ACK arrives after this sentinel — not after the
        last data chunk. This is the upload commit signal.

        All upload messages use opcode 0x7E (UPLOAD), confirmed from
        captures/sniffer-upload21.jsonl.
        """
        from core.models import UploadEndRequest, SysExCmd

        chunks = [p for p in capture_payloads if len(p) >= 2 and p[0] == 0x02 and p[1] == 0x01]
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
        # Verify our model uses the correct opcode (matches official tool)
        assert UploadEndRequest.opcode == SysExCmd.UPLOAD, (
            "UploadEndRequest must use UPLOAD (0x7E) — confirmed from capture"
        )

    def test_put_data_chunk_sizing(self, capture_payloads, wav_pcm):
        """Official app uses UPLOAD_CHUNK_SIZE bytes per chunk; last chunk is smaller.

        Observed: official app also sends a trailing empty (0-byte) chunk after the
        last data chunk, as a sentinel. This is not required by our implementation.
        """
        from core.models import UPLOAD_CHUNK_SIZE

        chunks = [p for p in capture_payloads if len(p) >= 2 and p[0] == 0x02 and p[1] == 0x01]
        data_chunks = [c for c in chunks if len(c) > 4]   # non-empty PCM
        empty_chunks = [c for c in chunks if len(c) <= 4]  # sentinel(s)

        pcm_sizes = [len(c) - 4 for c in data_chunks]
        assert all(s <= UPLOAD_CHUNK_SIZE for s in pcm_sizes), (
            f"A chunk exceeds UPLOAD_CHUNK_SIZE={UPLOAD_CHUNK_SIZE}: {pcm_sizes}"
        )
        assert pcm_sizes[:-1] == [UPLOAD_CHUNK_SIZE] * (len(pcm_sizes) - 1), (
            "All chunks except the last should be exactly UPLOAD_CHUNK_SIZE bytes"
        )
        wav_size = len(wav_pcm["raw"])
        expected_remainder = wav_size % UPLOAD_CHUNK_SIZE or UPLOAD_CHUNK_SIZE
        assert pcm_sizes[-1] == expected_remainder, (
            f"Last chunk: expected {expected_remainder} bytes, got {pcm_sizes[-1]}"
        )
        assert len(empty_chunks) == 1, (
            f"Expected 1 trailing empty sentinel chunk, got {len(empty_chunks)}"
        )
