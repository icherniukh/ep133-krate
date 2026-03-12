"""
Verify upload audio encoding: WAV LE s16 frames must reach the device unchanged.

Previously a LE->BE byte swap was applied (d5bd406), confirmed wrong by comparing
the official TE app's sniffer capture (sniffer-upload21.jsonl) against the original
WAV file (Afterparty Kick.wav) — exact byte-for-byte match with LE, not BE.
"""
import struct
import wave
import tempfile
from pathlib import Path

from core.operations import UploadTransaction


def _write_known_wav(path: Path) -> bytes:
    """Write a WAV with known non-trivial LE s16 samples. Returns raw PCM bytes."""
    samples = [0, 100, -100, 32767, -32768, 256, -256, 1, -1]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(46875)
        raw = b"".join(struct.pack("<h", s) for s in samples)
        w.writeframes(raw)
    return raw


class _FakeClient:
    """Captures chunk data sent via _send_msg."""

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
        from types import SimpleNamespace
        return SimpleNamespace(status=0)

    def _drain_pending(self):
        pass

    def _initialize(self):
        pass


def test_upload_sends_le_pcm_unchanged():
    """UploadTransaction must send WAV PCM bytes as-is (LE s16), with no byte swap."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = Path(f.name)

    try:
        expected_pcm = _write_known_wav(path)
        client = _FakeClient()
        tx = UploadTransaction(client, path, slot=42, name="test")
        tx.execute()

        # Collect all UploadChunkRequest data payloads
        from core.models import UploadChunkRequest
        chunk_calls = [c for c in client.calls if isinstance(c, UploadChunkRequest)]
        assert chunk_calls, "No UploadChunkRequests were sent"

        actual_pcm = b"".join(c.data for c in chunk_calls)
        assert actual_pcm == expected_pcm, (
            "Upload byte-swapped the audio data. "
            f"Expected LE: {expected_pcm.hex()}, got: {actual_pcm.hex()}"
        )
    finally:
        path.unlink(missing_ok=True)
