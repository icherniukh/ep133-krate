"""
EP-133 Protocol Transactions

Encapsulates multi-step stateful operations (like file transfers) to keep the client thin.
"""

import time
from pathlib import Path
from typing import Optional, Callable
from ko2_models import (
    UPLOAD_CHUNK_SIZE, UPLOAD_DELAY,
    UploadInitRequest, UploadChunkRequest, UploadEndRequest, MetadataSetRequest
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
        import struct
        import json

        # 1. Read and validate WAV
        with wave.open(str(self.input_path), "rb") as wav:
            frames = wav.getnframes()
            samplerate = wav.getframerate()
            channels = wav.getnchannels()
            raw_data = wav.readframes(frames)

        # Convert to Big-Endian s16 for device
        audio_data = bytearray()
        for i in range(0, len(raw_data) - 1, 2):
            sample = struct.unpack("<h", raw_data[i : i + 2])[0]
            audio_data.extend(struct.pack(">h", sample))
        
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
        if not resp or resp.status != 0:
            raise Exception(f"Upload init failed: {resp}")

        # 3. Data Chunks
        chunk_index = 0
        offset = 0
        while offset < data_size:
            chunk_data = bytes(audio_data[offset : offset + UPLOAD_CHUNK_SIZE])
            chunk_req = UploadChunkRequest(chunk_index=chunk_index, data=chunk_data)
            
            resp = self.client._send_and_wait_msg(chunk_req, timeout=2.0)
            if not resp or resp.status != 0:
                raise Exception(f"Chunk {chunk_index} failed")

            time.sleep(UPLOAD_DELAY)
            offset += UPLOAD_CHUNK_SIZE
            chunk_index += 1
            
            if self.progress_callback:
                self.progress_callback(offset, data_size)

        # 4. End Marker
        end_req = UploadEndRequest(chunk_index=chunk_index)
        self.client._send_and_wait_msg(end_req, timeout=5.0)

        # 5. Metadata Sync
        if self.metadata:
            import json
            meta_payload = {
                "channels": self.metadata.get("channels", 1),
                "samplerate": self.metadata.get("samplerate", 46875),
            }
            # Add loop info if frames provided
            frames_count = self.metadata.get("frames")
            if frames_count:
                loop_end = max(0, frames_count - 1)
                if loop_end <= 0x1FFFF:
                    meta_payload.update({
                        "sound.loopstart": 0,
                        "sound.loopend": loop_end,
                        "sound.rootnote": 60,
                    })
            
            meta_json = json.dumps(meta_payload, separators=(",", ":"), ensure_ascii=False)
            meta_req = MetadataSetRequest(node_id=self.slot, metadata_json=meta_json)
            self.client._send_and_wait_msg(meta_req, timeout=2.0)
