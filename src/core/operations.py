"""
EP-133 Protocol Transactions

Encapsulates multi-step stateful operations (like file transfers) to keep the client thin.
"""

from pathlib import Path
from typing import Optional, Callable
from .models import (
    UPLOAD_CHUNK_SIZE,
    UploadInitRequest, UploadChunkRequest, UploadEndRequest,
    UploadVerifyRequest, MetadataSetRequest,
    EP133Error,
)


class Transaction:
    """Base class for multi-step protocol operations."""
    def __init__(self, client):
        self.client = client


class UploadTransaction(Transaction):
    """Manages the full lifecycle of a file upload."""

    def __init__(
        self,
        client,
        input_path: Path,
        slot: int,
        name: Optional[str] = None,
        metadata: Optional[dict] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ):
        super().__init__(client)
        self.input_path = input_path
        self.slot = slot
        self.name = name or input_path.stem
        self.metadata = metadata or {}
        self.progress_callback = progress_callback

    def execute(self) -> None:
        """Run the multi-step upload process."""
        import wave
        import json

        # 1. Read and validate WAV
        with wave.open(str(self.input_path), "rb") as wav:
            frames = wav.getnframes()
            samplerate = wav.getframerate()
            channels = wav.getnchannels()
            raw_data = wav.readframes(frames)

        audio_data = raw_data
        data_size = len(audio_data)

        # 2. Upload Init
        meta_str = json.dumps(self.metadata, separators=(",", ":"), ensure_ascii=False)
        init_req = UploadInitRequest(
            slot=self.slot,
            file_size=data_size,
            name=self.name,
            metadata_json=meta_str
        )
        
        resp = self.client._send_and_wait_msg(init_req, timeout=5.0)
        if not resp:
            raise EP133Error("Upload init failed: No response")

        # 3. Data Chunks — pipelined (matches official TE app behavior).
        # The device ACKs each chunk with ~6ms lag, which equals the MIDI transmission
        # time for a 510-byte SysEx frame. Waiting for each ACK before sending the next
        # (stop-and-wait) plus an extra 20ms sleep made upload ~5-6x slower than download.
        # Instead: fire all chunks without waiting for individual ACKs, then drain them all.
        chunk_index = 0
        offset = 0
        while offset < data_size:
            chunk_data = bytes(audio_data[offset : offset + UPLOAD_CHUNK_SIZE])
            chunk_req = UploadChunkRequest(chunk_index=chunk_index, data=chunk_data)
            self.client._send_msg(chunk_req)
            offset += UPLOAD_CHUNK_SIZE
            chunk_index += 1

            if self.progress_callback:
                self.progress_callback(min(offset, data_size), data_size)

        # Drain all pending chunk ACKs before proceeding to the end sentinel.
        self.client._drain_pending()

        # 4. End Marker (empty PUT_DATA sentinel — triggers device ACK)
        end_req = UploadEndRequest(chunk_index=chunk_index)
        self.client._send_and_wait_msg(end_req, timeout=5.0)

        # 5. Verify → Metadata Set → Verify
        # Official sequence from tests/fixtures/sniffer-upload21.jsonl:
        # empty sentinel → ACK → VERIFY → METADATA SET → ACK → VERIFY
        verify_req = UploadVerifyRequest(slot=self.slot)
        self.client._send_and_wait_msg(verify_req, timeout=2.0)

        if self.metadata:
            meta_json = json.dumps(self.metadata, separators=(",", ":"), ensure_ascii=False)
            meta_req = MetadataSetRequest(node_id=self.slot, metadata_json=meta_json)
            self.client._send_and_wait_msg(meta_req, timeout=2.0)

        self.client._send_and_wait_msg(UploadVerifyRequest(slot=self.slot), timeout=2.0)
