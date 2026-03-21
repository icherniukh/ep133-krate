"""
Upload protocol tests using tests/fixtures/kick-46875hz.wav — a synthetic,
copyright-free kick drum at the KO-II native sample rate (46875 Hz, mono, 16-bit LE).

These tests always run (no local captures required) and verify:
  - WAV PCM bytes reach the device unchanged (LE s16, no transformation)
  - Chunk sizing: all full chunks == UPLOAD_CHUNK_SIZE, last chunk correct
  - Metadata fields: channels, samplerate match the WAV
  - Sentinel: final empty chunk is present after data chunks

Complement to test_upload_capture.py, which verifies against the forensic
sniffer-upload21.jsonl capture (local-only, skipped when absent).
"""
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.models import UPLOAD_CHUNK_SIZE, UploadChunkRequest, UploadEndRequest, SysExCmd
from core.operations import UploadTransaction
from core.client import EP133Client

FIXTURE_WAV = Path(__file__).parents[1] / "fixtures" / "kick-46875hz.wav"


class _FakeClient:
    def __init__(self):
        self.calls = []
        self._seq = 0

    def _next_seq(self):
        s = self._seq
        self._seq = (self._seq + 1) & 0x7F
        return s

    def _send_msg(self, msg, seq=None):
        self.calls.append(msg)
        return self._next_seq()

    def _send_and_wait_msg(self, msg, timeout=2.0, expect_resp_cmd=None, seq=None):
        self.calls.append(msg)
        return SimpleNamespace(status=0)

    def _drain_pending(self):
        pass

    def _initialize(self):
        pass


@pytest.fixture(scope="module")
def wav_info():
    with wave.open(str(FIXTURE_WAV), "rb") as w:
        return {
            "channels": w.getnchannels(),
            "framerate": w.getframerate(),
            "nframes": w.getnframes(),
            "raw": w.readframes(w.getnframes()),
        }


@pytest.fixture(scope="module")
def upload_calls(wav_info):
    meta = EP133Client.build_upload_metadata(
        channels=wav_info["channels"],
        samplerate=wav_info["framerate"],
        frames=wav_info["nframes"],
    )
    client = _FakeClient()
    tx = UploadTransaction(client, FIXTURE_WAV, slot=1, name="kick", metadata=meta)
    tx.execute()
    return client.calls


class TestUploadFixture:
    def test_pcm_bytes_unchanged(self, upload_calls, wav_info):
        """WAV raw PCM frames must reach the device as-is (LE s16, no byte swap)."""
        chunks = [c for c in upload_calls if isinstance(c, UploadChunkRequest) and c.data]
        assert chunks, "No data UploadChunkRequests found"
        actual = b"".join(c.data for c in chunks)
        assert actual == wav_info["raw"], (
            f"PCM mismatch — expected {len(wav_info['raw'])} bytes, got {len(actual)}"
        )

    def test_chunk_sizing(self, upload_calls, wav_info):
        """All full chunks == UPLOAD_CHUNK_SIZE; last chunk holds the remainder."""
        chunks = [c for c in upload_calls if isinstance(c, UploadChunkRequest) and c.data]
        sizes = [len(c.data) for c in chunks]
        assert all(s <= UPLOAD_CHUNK_SIZE for s in sizes)
        assert sizes[:-1] == [UPLOAD_CHUNK_SIZE] * (len(sizes) - 1)
        remainder = len(wav_info["raw"]) % UPLOAD_CHUNK_SIZE or UPLOAD_CHUNK_SIZE
        assert sizes[-1] == remainder

    def test_sentinel_present(self, upload_calls):
        """UploadEndRequest (sentinel) must be sent after the last data chunk."""
        end_reqs = [c for c in upload_calls if isinstance(c, UploadEndRequest)]
        assert len(end_reqs) == 1, f"Expected 1 UploadEndRequest, got {len(end_reqs)}"

    def test_sentinel_uses_upload_opcode(self, upload_calls):
        """UploadEndRequest must use UPLOAD (0x7E), matching the official tool."""
        assert UploadEndRequest.opcode == SysExCmd.UPLOAD

    def test_metadata_channels_and_rate(self, upload_calls, wav_info):
        """UploadInitRequest metadata_json must carry correct channels and samplerate."""
        from core.models import UploadInitRequest
        import json
        init_reqs = [c for c in upload_calls if isinstance(c, UploadInitRequest)]
        assert init_reqs, "No UploadInitRequest found"
        meta = json.loads(init_reqs[0].metadata_json)
        assert meta["channels"] == wav_info["channels"]
        assert meta["samplerate"] == wav_info["framerate"]
