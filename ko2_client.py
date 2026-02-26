#!/usr/bin/env python3
"""
EP-133 KO-II Device Client

Provides a thin transport layer for sending and receiving protocol messages.
"""

from __future__ import annotations

import sys
import time
import struct
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Callable

try:
    import mido
except ImportError:
    print("Error: mido library not installed. Run: pip install mido")
    sys.exit(1)

from ko2_models import (
    SysExCmd, GetType, SAMPLE_RATE, BIT_DEPTH, CHANNELS, MAX_SLOTS,
    SYSEX_START, SYSEX_END, TE_MFG_ID, DEVICE_FAMILY, CMD_FILE,
    slot_from_sound_entry, decode_node_id,
    SysExMessage, SysExResponse, 
    DownloadInitRequest, DownloadChunkRequest,
    MetadataGetLegacyRequest, MetadataGetRequest, MetadataSetRequest,
    FileListRequest, InfoRequest, DeleteRequest
)
from ko2_types import Packed7
from ko2_operations import UploadTransaction


def find_device() -> Optional[str]:
    """Find EP-133 device in available MIDI output ports."""
    for port in mido.get_output_names():
        if "EP-133" in port or "EP-1320" in port:
            return port
    return None


@dataclass
class SampleInfo:
    """Sample metadata from device."""
    slot: int
    name: str
    sym: str = ""
    samplerate: int = 46875
    format: str = "s16"
    channels: int = 1
    channels_known: bool = False
    size_bytes: int = 0
    duration: float = 0.0
    is_empty: bool = False

    @classmethod
    def empty(cls, slot: int) -> "SampleInfo":
        return cls(slot=slot, name="(empty)", is_empty=True)


class EP133Error(Exception):
    """Base exception for EP-133 errors."""
    pass


class DeviceNotFoundError(EP133Error):
    """EP-133 device not found."""
    pass


class SlotEmptyError(EP133Error):
    """Slot is empty."""
    pass


def _detect_channels(data: bytes, sample_check: int = 4000) -> int:
    """Detect mono vs stereo from raw s16 LE PCM data.

    For stereo interleaved PCM, even-indexed (L) and odd-indexed (R) samples
    are from independent channels and differ substantially. For mono PCM,
    adjacent samples are highly correlated (smooth waveform), so |L-R| is
    small relative to the signal amplitude.

    Returns 2 if mean(|L-R|) / mean(|sample|) > 1.0, else 1.
    """
    import struct
    if len(data) < 8:
        return 1
    n = min(len(data) // 2, sample_check)
    values = struct.unpack(f"<{n}h", data[: n * 2])
    mean_abs = sum(abs(v) for v in values) / n
    if mean_abs == 0:
        return 1
    mean_lr_diff = sum(abs(values[i] - values[i + 1]) for i in range(0, n - 1, 2)) / (n // 2)
    return 2 if (mean_lr_diff / mean_abs) > 1.0 else 1


def _parse_json_tolerant(data: bytes) -> dict | None:
    """Parse a potentially truncated JSON response.

    The device returns at most 320 bytes of JSON per page. When the metadata JSON
    exceeds 320 bytes, the device repeats the first page for all subsequent page
    requests. This function handles the resulting truncation by progressively
    relaxing the parse:
      1. Direct parse (works for complete JSON).
      2. Append missing closing brace (works when only "}" is missing).
      3. Truncate at the last complete comma-separated entry (works when the last
         key-value pair is partially cut off mid-write).
    """
    if not data:
        return None
    text = data.rstrip(b"\x00").decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(text + "}")
    except json.JSONDecodeError:
        pass
    last_comma = text.rfind(",")
    if last_comma > 0:
        try:
            return json.loads(text[:last_comma] + "}")
        except json.JSONDecodeError:
            pass
    return None


class EP133Client:
    """Client for EP-133 KO-II device transport."""

    def __init__(self, device_name: Optional[str] = None):
        self.device_name = device_name or find_device()
        if not self.device_name:
            raise DeviceNotFoundError("EP-133 not found. Connect via USB.")

        self._outport: Optional[mido.ports.Output] = None
        self._inport: Optional[mido.ports.Input] = None
        self._seq = 0

    def connect(self):
        """Open MIDI connection to device."""
        self._outport = mido.open_output(self.device_name)
        self._inport = mido.open_input(self.device_name)
        self._initialize()

    def close(self):
        """Close MIDI connection."""
        if self._outport: self._outport.close()
        if self._inport: self._inport.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    def _next_seq(self) -> int:
        seq = self._seq
        self._seq = (self._seq + 1) & 0x7F
        return seq

    def _initialize(self):
        """Send device initialization sequence."""
        init_msgs = [
            bytes([SYSEX_START, 0x7E, 0x7F, 0x06, 0x01, SYSEX_END]),
            bytes([SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, SysExCmd.INIT, 0x17, 0x01, SYSEX_END]),
            bytes([SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, SysExCmd.INIT, 0x18, 0x05, 0x00, 0x01, 0x01, 0x00, 0x40, 0x00, 0x00, SYSEX_END]),
        ]
        for msg in init_msgs:
            self._outport.send(mido.Message("sysex", data=msg[1:-1]))
            time.sleep(0.05)

    def _send_sysex(self, data: bytes, debug: bool = False) -> None:
        if debug:
            hx = " ".join(f"{b:02X}" for b in data[:80])
            print(f"  TX: {hx}...")
        self._outport.send(mido.Message("sysex", data=data[1:-1]))

    def _send_msg(self, msg: SysExMessage, seq: Optional[int] = None) -> int:
        s = seq if seq is not None else self._next_seq()
        self._send_sysex(msg.build(seq=s))
        return s

    def _send_and_wait(self, data: bytes, timeout: float = 2.0, expect_cmd: int | None = None) -> bytes | None:
        for _ in self._inport.iter_pending(): pass
        self._outport.send(mido.Message("sysex", data=data[1:-1]))
        deadline = time.time() + timeout
        while time.time() < deadline:
            for msg in self._inport.iter_pending():
                if msg.type == "sysex":
                    raw = bytes([SYSEX_START]) + bytes(msg.data) + bytes([SYSEX_END])
                    if len(raw) < 8 or raw[1:4] != TE_MFG_ID or raw[4:6] != DEVICE_FAMILY: continue
                    cmd = raw[6]
                    if (cmd & 0xF0) != 0x20: continue
                    if expect_cmd is not None and cmd != (expect_cmd & 0x7F): continue
                    return raw
            time.sleep(0.01)
        return None

    def _send_and_wait_msg(self, msg: SysExMessage, timeout: float = 2.0, expect_resp_cmd: Optional[int] = None) -> Optional[SysExResponse]:
        # Drain stale responses first, then send once and read the single response.
        # Historically this sent twice (send in _send_msg + drain + resend in _send_and_wait),
        # which reset the device's page cursor for stateful paginated commands (METADATA GET).
        for _ in self._inport.iter_pending(): pass
        seq = self._send_msg(msg)
        expected = expect_resp_cmd or (msg.opcode - 0x40)
        raw = self._recv_matching(timeout=timeout, expect_cmd=expected)
        return SysExResponse.from_sysex(raw) if raw else None

    def _recv_matching(self, timeout: float = 2.0, expect_cmd: int | None = None) -> bytes | None:
        """Read the next TE SysEx response matching expect_cmd, without sending anything."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            for msg in self._inport.iter_pending():
                if msg.type == "sysex":
                    raw = bytes([SYSEX_START]) + bytes(msg.data) + bytes([SYSEX_END])
                    if len(raw) < 8 or raw[1:4] != TE_MFG_ID or raw[4:6] != DEVICE_FAMILY: continue
                    cmd = raw[6]
                    if (cmd & 0xF0) != 0x20: continue
                    if expect_cmd is not None and cmd != (expect_cmd & 0x7F): continue
                    return raw
            time.sleep(0.01)
        return None

    def _recv_sysex(self, timeout: float = 0.5, filter_fn: Optional[Callable] = None) -> list[bytes]:
        responses, deadline = [], time.time() + timeout
        while time.time() < deadline:
            for msg in self._inport.iter_pending():
                if msg.type == "sysex":
                    data = bytes([SYSEX_START]) + bytes(msg.data) + bytes([SYSEX_END])
                    if filter_fn is None or filter_fn(data): responses.append(data)
            if responses and filter_fn is None: break
            time.sleep(0.01)
        return responses

    def device_info(self) -> dict | None:
        self._send_msg(InfoRequest())
        time.sleep(0.2)
        responses = self._recv_sysex(timeout=0.4)
        for resp in responses:
            if len(resp) > 7 and resp[6] in (0x37, SysExCmd.INFO):
                # ... JSON parse logic ...
                pass
        return None

    def _get_file_size(self, slot: int) -> int | None:
        self._send_msg(DownloadInitRequest(slot=slot), seq=0x2E)
        time.sleep(0.2)
        for msg in self._inport.iter_pending():
            if msg.type == "sysex":
                data = list(msg.data)
                if len(data) > 20 and (b".pcm" in bytes(data) or b".PCM" in bytes(data)):
                    for start_offset in [9, 10, 11]:
                        decoded = Packed7.unpack(bytes(data[start_offset:]))
                        if b".pcm" in decoded or b".PCM" in decoded:
                            if len(decoded) >= 7: return int.from_bytes(decoded[3:7], "big")
        return None

    def _meta_from_get_meta(self, slot: int) -> dict | None:
        self._send_msg(MetadataGetLegacyRequest(slot=slot), seq=slot & 0x7F)
        time.sleep(0.2)
        responses = self._recv_sysex(timeout=0.4)
        for resp in responses:
            if len(resp) > 8 and resp[6] == 0x35:
                payload = Packed7.unpack(resp[8:-1])
                try:
                    return json.loads(payload[4:].rstrip(b"\x00").decode("utf-8"))
                except: pass
        return None

    def info(self, slot: int, include_size: bool = True, node_entry: dict | None = None, prefer_node: bool = True, allow_get_meta: bool = False) -> SampleInfo:
        sounds = self.list_sounds()
        entry = node_entry or sounds.get(slot)
        
        info = SampleInfo.empty(slot)
        if entry:
            info.is_empty = False
            info.name = entry.get("name", info.name)
            info.size_bytes = entry.get("size", 0)
            
            node_id = entry.get("node_id")
            if node_id:
                meta = self.get_node_metadata(node_id)
                if meta:
                    info.name = meta.get("name", info.name)
                    channels_from_meta = meta.get("channels")
                    if channels_from_meta is not None:
                        info.channels = channels_from_meta
                        info.channels_known = True
                    info.samplerate = meta.get("samplerate", info.samplerate)
        
        if allow_get_meta:
            legacy = self._meta_from_get_meta(slot)
            if legacy:
                info.is_empty = False
                if not entry or not prefer_node:
                    info.name = legacy.get("name", info.name)
                info.channels = legacy.get("channels", info.channels)
                info.samplerate = legacy.get("samplerate", info.samplerate)

        if include_size and info.size_bytes == 0 and not info.is_empty:
            info.size_bytes = self._get_file_size(slot) or 0
            
        if info.is_empty:
            raise SlotEmptyError(f"Slot {slot} is empty")
            
        return info

    def list_sounds(self) -> dict[int, dict]:
        entries = self.list_directory(1000)
        by_slot: dict[int, dict] = {}
        for e in entries:
            if e.get("is_dir"): continue
            slot = slot_from_sound_entry(e)
            if slot: by_slot[slot] = e
        return by_slot

    def list_directory(self, node_id: int = 1000) -> list[dict]:
        all_entries, page = [], 0
        while True:
            resp = self._send_and_wait_msg(FileListRequest(node_id=node_id, page=page))
            if not resp: break
            from ko2_models import parse_file_list_response
            entries = parse_file_list_response(resp.payload)
            if not entries: break
            all_entries.extend(entries)
            page += 1
        return all_entries

    def get_node_metadata(self, node_id: int) -> dict | None:
        all_bytes, page = bytearray(), 0
        while page < 100:
            resp = self._send_and_wait_msg(MetadataGetRequest(node_id=node_id, page=page))
            if not resp or len(resp.payload) <= 2: break
            # First 2 bytes are the page echo; the rest is JSON content
            content = resp.payload[2:].rstrip(b"\x00")
            if not content: break
            all_bytes.extend(content)
            if b"}" in all_bytes:
                try: return json.loads(all_bytes.decode("utf-8"))
                except: pass
            page += 1
        return _parse_json_tolerant(bytes(all_bytes))

    @staticmethod
    def build_upload_metadata(channels: int, samplerate: int, frames: int) -> dict:
        meta = {
            "sound.playmode": "oneshot",
            "sound.rootnote": 60,
            "sound.pitch": 0,
            "sound.pan": 0,
            "sound.amplitude": 100,
            "envelope.attack": 0,
            "envelope.release": 255,
            "time.mode": "off",
            "channels": channels,
            "samplerate": samplerate,
        }
        loop_end = max(0, frames - 1)
        if loop_end <= 0x1FFFF:
            meta.update({"sound.loopstart": 0, "sound.loopend": loop_end})
        return meta

    def put(self, input_path: Path, slot: int, name: Optional[str] = None, progress: bool = True) -> None:
        import wave
        with wave.open(str(input_path), "rb") as wav:
            frames, rate, channels = wav.getnframes(), wav.getframerate(), wav.getnchannels()
        def _cb(curr, total):
            if progress: print(f"\r  Uploading... {curr/total*100:.1f}%", end="", flush=True)
        meta = self.build_upload_metadata(channels, rate, frames)
        tx = UploadTransaction(self, input_path, slot, name, meta, _cb)
        tx.execute()
        if progress: print(" done")
        self._initialize()

    def delete(self, slot: int) -> None:
        self._send_msg(DeleteRequest(slot=slot))
        time.sleep(0.1)

    def rename(self, slot: int, new_name: str) -> None:
        sounds = self.list_sounds()
        entry = sounds.get(slot)
        if not entry: raise Exception(f"Slot {slot} empty")
        node_id = entry["node_id"]
        msg = MetadataSetRequest(node_id=node_id, metadata_json=json.dumps({"name": new_name}))
        resp = self._send_and_wait_msg(msg)
        if not resp or resp.status != 0: raise Exception("Rename failed")

    def get(self, slot: int, output_path: Optional[Path] = None, debug: bool = False) -> Path:
        from ko2_models import SAMPLE_RATE
        info = self.info(slot)
        if info.is_empty or info.size_bytes == 0:
            raise SlotEmptyError(f"Slot {slot} is empty or has no size")

        if output_path is None:
            name = info.sym or f"sample_{slot:03d}"
            output_path = Path(f"{name}_{slot:03d}.wav")

        data = self._download_data(slot, debug=debug)

        # Metadata channels is unreliable for samples not uploaded by this tool
        # (e.g. official TE app, on-device recordings have no JSON metadata).
        # When metadata says mono, verify against the raw PCM before writing.
        channels = max(1, int(info.channels or 1))
        if channels == 1:
            channels = _detect_channels(data)

        self._save_wav(
            data,
            output_path,
            channels=channels,
            samplerate=int(info.samplerate or SAMPLE_RATE),
        )

        return output_path

    def _download_data(self, slot: int, debug: bool = False) -> bytes:
        import struct
        seq = 0x2E
        self._send_msg(DownloadInitRequest(slot=slot), seq=seq)
        time.sleep(0.3)

        file_info = None
        for msg in self._inport.iter_pending():
            if msg.type == "sysex":
                data = list(msg.data)
                raw_bytes = bytes(data)
                if len(data) > 20 and (b".pcm" in raw_bytes or b".PCM" in raw_bytes):
                    for start_offset in [9, 10, 11]:
                        encoded = bytes(data[start_offset:])
                        decoded = Packed7.unpack(encoded)
                        if b".pcm" in decoded or b".PCM" in decoded:
                            if len(decoded) >= 7:
                                file_size = int.from_bytes(decoded[3:7], "big")
                                file_info = {"size": file_size}
                                break
                    break

        if not file_info:
            raise EP133Error("Failed to get file info")

        all_data = []
        page = 0
        received = 0

        while received < file_info["size"]:
            for _ in self._inport.iter_pending(): pass
            
            seq = (seq + 1) & 0x7F
            self._send_msg(DownloadChunkRequest(page=page), seq=seq)
            time.sleep(0.05)

            chunk_received = False
            timeout_counter = 0
            while timeout_counter < 50 and not chunk_received:
                for msg in self._inport.iter_pending():
                    if msg.type == "sysex":
                        data = list(msg.data)
                        if len(data) > 12 and data[5] in (SysExCmd.RESPONSE, SysExCmd.RESPONSE_ALT) and data[7] == CMD_FILE:
                            decoded = Packed7.unpack(bytes(data[9:]))
                            if decoded and len(decoded) > 2:
                                from ko2_types import U14LE
                                echo_page, _ = U14LE.decode(decoded[:2])
                                if int(echo_page) != page:
                                    if debug: print(f"  ⚠ Page mismatch: expected {page}, got {int(echo_page)}")
                                    continue
                                all_data.extend(decoded[2:])
                                received += len(decoded) - 2
                                chunk_received = True
                if chunk_received: break
                time.sleep(0.05)
                timeout_counter += 1

            if not chunk_received: break
            page = (page + 1) & 0x3FFF

        return bytes(all_data)[: file_info["size"]]

    def probe_channels(self, slot: int) -> tuple[int, int]:
        """Probe channel count and size via a single-chunk partial download.

        Sends DownloadInitRequest (to get file size) then one DownloadChunkRequest
        (page 0). Runs _detect_channels on the decoded first chunk.

        Returns (channels, size_bytes).  channels is 1 or 2.  size_bytes is the
        raw PCM byte count from the init response, or 0 on failure.
        Does NOT complete the download — the device silently discards the session.
        """
        import struct
        seq = 0x2E
        self._send_msg(DownloadInitRequest(slot=slot), seq=seq)
        time.sleep(0.3)

        file_info = None
        for msg in self._inport.iter_pending():
            if msg.type == "sysex":
                data = list(msg.data)
                raw_bytes = bytes(data)
                if len(data) > 20 and (b".pcm" in raw_bytes or b".PCM" in raw_bytes):
                    for start_offset in [9, 10, 11]:
                        encoded = bytes(data[start_offset:])
                        decoded = Packed7.unpack(encoded)
                        if b".pcm" in decoded or b".PCM" in decoded:
                            if len(decoded) >= 7:
                                file_size = int.from_bytes(decoded[3:7], "big")
                                file_info = {"size": file_size}
                                break
                    break

        if not file_info:
            return 1, 0

        # Request just page 0
        for _ in self._inport.iter_pending():
            pass
        seq = (seq + 1) & 0x7F
        self._send_msg(DownloadChunkRequest(page=0), seq=seq)
        time.sleep(0.05)

        chunk_data = None
        timeout_counter = 0
        while timeout_counter < 50:
            for msg in self._inport.iter_pending():
                if msg.type == "sysex":
                    data = list(msg.data)
                    if len(data) > 12 and data[5] in (SysExCmd.RESPONSE, SysExCmd.RESPONSE_ALT) and data[7] == CMD_FILE:
                        decoded = Packed7.unpack(bytes(data[9:]))
                        if decoded and len(decoded) > 2:
                            from ko2_types import U14LE
                            echo_page, _ = U14LE.decode(decoded[:2])
                            if int(echo_page) == 0:
                                chunk_data = bytes(decoded[2:])
                                break
            if chunk_data is not None:
                break
            time.sleep(0.05)
            timeout_counter += 1

        if not chunk_data:
            return 1, file_info["size"]

        return _detect_channels(chunk_data), file_info["size"]

    def _save_wav(self, data: bytes, output_path: Path, channels: int, samplerate: int) -> None:
        if len(data) >= 4 and data[:4] == b"RIFF":
            output_path.write_bytes(data)
            return
        import wave
        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(channels)
            from ko2_models import BIT_DEPTH
            wav.setsampwidth(BIT_DEPTH // 8)
            wav.setframerate(samplerate)
            if data: wav.writeframes(data)

