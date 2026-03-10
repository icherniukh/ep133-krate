#!/usr/bin/env python3
"""
EP-133 KO-II Device Client

Provides a thin transport layer for sending and receiving protocol messages.
"""

from __future__ import annotations

import sys
import time
import json
from pathlib import Path
from dataclasses import dataclass
from queue import Empty
from typing import Any, Mapping, Optional, Callable

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
    FileListRequest, InfoRequest, DeleteRequest, AuditionRequest
)
from ko2_types import Packed7, U14LE
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


def _extract_download_file_size(payload: bytes) -> int | None:
    """Extract PCM byte size from unpacked DOWNLOAD INIT payload."""
    if not payload:
        return None

    # Primary structure from captures: 03 00 05 <size:4> ...
    if len(payload) >= 7 and payload[:3] == b"\x03\x00\x05":
        size = int.from_bytes(payload[3:7], "big")
        if 0 < size < (512 * 1024 * 1024):
            return size

    # Fallbacks for capture variants.
    for off in (3, 2, 4, 1):
        if len(payload) >= off + 4:
            size = int.from_bytes(payload[off : off + 4], "big")
            if 0 < size < (512 * 1024 * 1024):
                return size

    # Last-resort heuristic for malformed payloads that still include filename.
    dot_pcm = payload.find(b".pcm")
    if dot_pcm >= 4:
        size = int.from_bytes(payload[dot_pcm - 4 : dot_pcm], "big")
        if 0 < size < (512 * 1024 * 1024):
            return size
    return None


class EP133Client:
    """Client for EP-133 KO-II device transport."""

    def __init__(
        self,
        device_name: Optional[str] = None,
        trace_hook: Optional[Callable[[str, bytes], None]] = None,
    ):
        self.device_name = device_name or find_device()
        if not self.device_name:
            raise DeviceNotFoundError("EP-133 not found. Connect via USB.")

        self._outport: Optional[mido.ports.Output] = None
        self._inport: Optional[mido.ports.Input] = None
        self._seq = 0
        self._trace_hook = trace_hook

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
        self._device_info = None
        
        self._drain_pending()
        
        # 1. Identity Request
        msg1 = bytes([SYSEX_START, 0x7E, 0x7F, 0x06, 0x01, SYSEX_END])
        self._emit_trace("TX", msg1)
        self._outport.send(mido.Message("sysex", data=msg1[1:-1]))
        # Read the Identity Response so it doesn't block the next command
        self._recv_sysex(timeout=0.2)
        
        # 2. INIT 1 (Triggers product info response)
        msg2 = bytes([SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, SysExCmd.INIT, 0x17, 0x01, SYSEX_END])
        self._emit_trace("TX", msg2)
        self._outport.send(mido.Message("sysex", data=msg2[1:-1]))
        
        responses = self._recv_sysex(timeout=0.6)
        for resp in responses:
            if len(resp) > 8 and resp[6] == 0x21:
                chars = []
                for byte in resp[9:-1]:
                    if 32 <= byte <= 126:
                        chars.append(chr(byte))
                text = "".join(chars)
                info = {}
                for pair in text.split(";"):
                    if ":" in pair:
                        k, v = pair.split(":", 1)
                        info[k.strip()] = v.strip()
                if info and "product" in info:
                    self._device_info = {
                        "device_name": info.get("product"),
                        "device_version": info.get("sw_version") or info.get("os_version"),
                        "device_sku": info.get("sku"),
                        "serial": info.get("serial"),
                        "raw_info": info
                    }
                    
        # 3. INIT 2
        msg3 = bytes([SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, SysExCmd.INIT, 0x18, 0x05, 0x00, 0x01, 0x01, 0x00, 0x40, 0x00, 0x00, SYSEX_END])
        self._emit_trace("TX", msg3)
        self._outport.send(mido.Message("sysex", data=msg3[1:-1]))
        self._recv_sysex(timeout=0.2)

    def _emit_trace(self, direction: str, data: bytes) -> None:
        trace_hook = getattr(self, "_trace_hook", None)
        if trace_hook is None:
            return
        try:
            trace_hook(direction, data)
        except Exception:
            # Tracing should never interrupt protocol operations.
            pass

    def _send_sysex(self, data: bytes, debug: bool = False) -> None:
        if debug:
            hx = " ".join(f"{b:02X}" for b in data[:80])
            print(f"  TX: {hx}...")
        self._emit_trace("TX", data)
        self._outport.send(mido.Message("sysex", data=data[1:-1]))

    def _send_msg(self, msg: SysExMessage, seq: Optional[int] = None) -> int:
        s = seq if seq is not None else self._next_seq()
        self._send_sysex(msg.build(seq=s))
        return s

    def _drain_pending(self) -> None:
        self._prefetched_msgs = []
        for _ in self._inport.iter_pending():
            pass

    def _iter_pending_messages(self):
        prefetched = getattr(self, "_prefetched_msgs", [])
        pending = list(self._inport.iter_pending())
        if pending:
            prefetched.extend(pending)
        while prefetched:
            yield prefetched.pop(0)

    def _iter_pending_sysex(self):
        for msg in self._iter_pending_messages():
            if msg.type != "sysex":
                continue
            raw = bytes([SYSEX_START]) + bytes(msg.data) + bytes([SYSEX_END])
            self._emit_trace("RX", raw)
            yield raw

    def _recv_message_blocking(self, timeout: float) -> Optional[mido.Message]:
        """Receive one MIDI message with timeout, using backend queue blocking when available."""
        if timeout <= 0:
            return None
        prefetched = getattr(self, "_prefetched_msgs", [])
        if prefetched:
            return prefetched.pop(0)

        # Fast path for mido.rtmidi Input: block on the underlying queue with timeout.
        parser_queue = getattr(self._inport, "_queue", None)
        raw_queue = getattr(parser_queue, "_queue", None)
        if raw_queue is not None and hasattr(raw_queue, "get"):
            try:
                return raw_queue.get(timeout=timeout)
            except Empty:
                return None

        # Backend-agnostic fallback with light sleep to avoid hot spinning.
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if hasattr(self._inport, "receive"):
                msg = self._inport.receive(block=False)
                if msg is not None:
                    return msg
            else:
                pending = list(self._inport.iter_pending())
                if pending:
                    if len(pending) > 1:
                        prefetched.extend(pending[1:])
                    return pending[0]
            time.sleep(0.001)
        return None

    def _recv_next_sysex(self, timeout: float) -> bytes | None:
        """Receive the next SysEx frame within timeout, returning raw bytes including F0/F7."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for raw in self._iter_pending_sysex():
                return raw
            remaining = deadline - time.monotonic()
            msg = self._recv_message_blocking(remaining)
            if msg is None:
                return None
            if msg.type != "sysex":
                continue
            raw = bytes([SYSEX_START]) + bytes(msg.data) + bytes([SYSEX_END])
            self._emit_trace("RX", raw)
            return raw
        return None

    def _send_and_wait(self, data: bytes, timeout: float = 2.0, expect_cmd: int | None = None) -> bytes | None:
        self._drain_pending()
        self._emit_trace("TX", data)
        self._outport.send(mido.Message("sysex", data=data[1:-1]))
        return self._recv_matching(timeout=timeout, expect_cmd=expect_cmd)

    def _send_and_wait_msg(
        self,
        msg: SysExMessage,
        timeout: float = 2.0,
        expect_resp_cmd: Optional[int] = None,
        seq: Optional[int] = None,
    ) -> Optional[SysExResponse]:
        # Drain stale responses first, then send once and read the single response.
        # Historically this sent twice (send in _send_msg + drain + resend in _send_and_wait),
        # which reset the device's page cursor for stateful paginated commands (METADATA GET).
        self._drain_pending()
        seq = self._send_msg(msg, seq=seq)
        expected = expect_resp_cmd or (msg.opcode - 0x40)
        raw = self._recv_matching(timeout=timeout, expect_cmd=expected)
        return SysExResponse.from_sysex(raw) if raw else None

    def _recv_matching(self, timeout: float = 2.0, expect_cmd: int | None = None) -> bytes | None:
        """Read the next TE SysEx response matching expect_cmd, without sending anything."""
        deadline = time.monotonic() + timeout
        expected = (expect_cmd & 0x7F) if expect_cmd is not None else None
        while time.monotonic() < deadline:
            raw = self._recv_next_sysex(deadline - time.monotonic())
            if raw is None:
                return None
            if len(raw) < 8 or raw[1:4] != TE_MFG_ID or raw[4:6] != DEVICE_FAMILY:
                continue
            cmd = raw[6]
            # Accept both 0x2x and 0x3x device response classes.
            if (cmd & 0xE0) != 0x20:
                continue
            if expected is not None and cmd != expected:
                continue
            return raw
        return None

    def _recv_sysex(self, timeout: float = 0.5, filter_fn: Optional[Callable] = None) -> list[bytes]:
        responses, deadline = [], time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = self._recv_next_sysex(deadline - time.monotonic())
            if data is None:
                break
            if filter_fn is None or filter_fn(data):
                responses.append(data)
            if responses and filter_fn is None:
                break
        return responses

    def _send_file_request(
        self,
        msg: SysExMessage,
        timeout: float = 2.0,
        expect_resp_cmd: Optional[int] = None,
        seq: Optional[int] = None,
    ) -> tuple[int, bytes] | None:
        """Send a file-group request and return (status, unpacked_payload)."""
        self._drain_pending()
        self._send_msg(msg, seq=seq)
        expected = expect_resp_cmd or (msg.opcode - 0x40)
        raw = self._recv_matching(timeout=timeout, expect_cmd=expected)
        if not raw:
            return None

        # Response body: [mfg(3),family(2),cmd,seq,file_cmd,status,packed_payload...]
        body = raw[1:-1]
        if len(body) < 9 or body[7] != CMD_FILE:
            return None
        status = int(body[8])
        unpacked = Packed7.unpack(body[9:])
        return status, unpacked

    def device_info(self) -> dict | None:
        """Get product information captured during initialization."""
        return getattr(self, "_device_info", None)

    def _get_file_size(self, slot: int) -> int | None:
        resp = self._send_file_request(
            DownloadInitRequest(slot=slot),
            timeout=2.0,
            expect_resp_cmd=(SysExCmd.DOWNLOAD - 0x40),
            seq=0x2E,
        )
        if not resp:
            return None
        _status, payload = resp
        return _extract_download_file_size(payload)

    def get_meta_legacy(self, slot: int) -> dict | None:
        self._send_msg(MetadataGetLegacyRequest(slot=slot), seq=slot & 0x7F)
        responses = self._recv_sysex(timeout=0.6)
        for resp in responses:
            if len(resp) > 8 and resp[6] == 0x35:
                payload = Packed7.unpack(resp[8:-1])
                try:
                    return json.loads(payload[4:].rstrip(b"\x00").decode("utf-8"))
                except: pass
        return None

    def info(self, slot: int, include_size: bool = True, node_entry: dict | None = None) -> SampleInfo:
        if node_entry is not None:
            entry = node_entry
        else:
            sounds = self.list_sounds()
            entry = sounds.get(slot)
        
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
            resp = self._send_file_request(
                FileListRequest(node_id=node_id, page=page),
                expect_resp_cmd=(SysExCmd.LIST_FILES - 0x40),
            )
            if not resp:
                break
            _status, payload = resp
            from ko2_models import parse_file_list_response
            entries = parse_file_list_response(payload)
            if not entries:
                break
            all_entries.extend(entries)
            page += 1
        return all_entries

    def get_node_metadata(self, node_id: int) -> dict | None:
        all_bytes, page = bytearray(), 0
        while page < 100:
            resp = self._send_file_request(
                MetadataGetRequest(node_id=node_id, page=page),
                expect_resp_cmd=(SysExCmd.LIST_FILES - 0x40),
            )
            if not resp:
                break
            _status, payload = resp
            if len(payload) <= 2:
                break
            # First 2 bytes are the page echo; the rest is JSON content
            content = payload[2:].rstrip(b"\x00")
            if not content:
                break
            all_bytes.extend(content)
            if b"}" in all_bytes:
                try: return json.loads(all_bytes.decode("utf-8"))
                except: pass
            page += 1
        return _parse_json_tolerant(bytes(all_bytes))

    @staticmethod
    def build_upload_metadata(channels: int, samplerate: int, frames: int, pitch: float = 0) -> dict:
        meta = {
            "sound.playmode": "oneshot",
            "sound.rootnote": 60,
            "sound.pitch": pitch,
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

    def put(self, input_path: Path, slot: int, name: Optional[str] = None, progress: bool = True, pitch: float = 0) -> None:
        import wave
        with wave.open(str(input_path), "rb") as wav:
            frames, rate, channels = wav.getnframes(), wav.getframerate(), wav.getnchannels()
        def _cb(curr, total):
            if progress: print(f"\r  Uploading... {curr/total*100:.1f}%", end="", flush=True)
        meta = self.build_upload_metadata(channels, rate, frames, pitch)
        tx = UploadTransaction(self, input_path, slot, name, meta, _cb)
        tx.execute()
        if progress: print(" done")
        self._initialize()

    def delete(self, slot: int) -> None:
        resp = self._send_file_request(
            DeleteRequest(slot=slot),
            timeout=2.0,
        )
        if not resp:
            raise EP133Error("Delete failed: no response")
        status, _payload = resp
        if status != 0:
            raise EP133Error(f"Delete failed: status=0x{status:02X}")

    def audition(self, slot: int) -> None:
        """Trigger on-device playback preview of the sample at slot."""
        resp = self._send_file_request(
            AuditionRequest(slot=slot),
            timeout=2.0,
        )
        if not resp:
            raise EP133Error("Audition failed: no response")
        status, _payload = resp
        if status != 0:
            raise EP133Error(f"Audition failed: status=0x{status:02X}")

    def set_node_metadata(self, node_id: int, metadata: Mapping[str, Any]) -> None:
        msg = MetadataSetRequest(
            node_id=int(node_id),
            metadata_json=json.dumps(dict(metadata), separators=(",", ":"), ensure_ascii=False),
        )
        resp = self._send_file_request(
            msg,
            timeout=2.0,
            expect_resp_cmd=(SysExCmd.LIST_FILES - 0x40),
        )
        if not resp:
            raise EP133Error("Metadata set failed: no response")
        status, _payload = resp
        if status != 0:
            raise EP133Error(f"Metadata set failed: status=0x{status:02X}")

    def update_slot_metadata(self, slot: int, patch: Mapping[str, Any]) -> dict[str, Any]:
        """Merge metadata patch into the slot node and write back."""
        sounds = self.list_sounds()
        entry = sounds.get(int(slot))
        if not entry:
            raise SlotEmptyError(f"Slot {int(slot)} is empty")
        node_id = int(entry.get("node_id") or int(slot))
        current = self.get_node_metadata(node_id) or {}
        if not isinstance(current, dict):
            current = {}
        merged = dict(current)
        merged.update(dict(patch))
        self.set_node_metadata(node_id, merged)
        return merged

    def rename(self, slot: int, new_name: str) -> None:
        sounds = self.list_sounds()
        entry = sounds.get(slot)
        if not entry: raise Exception(f"Slot {slot} empty")
        node_id = int(entry.get("node_id") or slot)
        self.set_node_metadata(node_id, {"name": new_name})

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

        # Reset device state after download so subsequent commands (e.g. delete)
        # are processed. Without this the device stays in download mode and
        # silently ignores the next command. Confirmed from TUI capture analysis:
        # DELETE sent immediately after _download_data receives stale GET responses
        # instead of a DELETE ACK. put() has always called _initialize() for the
        # same reason.
        self._initialize()

        return output_path

    def _download_data(self, slot: int, debug: bool = False) -> bytes:
        seq = 0x2E
        init_resp = self._send_file_request(
            DownloadInitRequest(slot=slot),
            timeout=2.0,
            expect_resp_cmd=(SysExCmd.DOWNLOAD - 0x40),
            seq=seq,
        )

        file_info = None
        if init_resp:
            _status, payload = init_resp
            size = _extract_download_file_size(payload)
            if size is not None:
                file_info = {"size": size}

        if not file_info:
            raise EP133Error("Failed to get file info")

        all_data = bytearray()
        page = 0
        received = 0

        while received < file_info["size"]:
            self._drain_pending()
            seq = (seq + 1) & 0x7F
            self._send_msg(DownloadChunkRequest(page=page), seq=seq)
            chunk = self._recv_download_chunk(page=page, timeout=2.5, debug=debug)
            if chunk is None:
                break
            all_data.extend(chunk)
            received += len(chunk)
            page = (page + 1) & 0x3FFF

        return bytes(all_data)[: file_info["size"]]

    def _recv_download_chunk(self, page: int, timeout: float = 2.5, debug: bool = False) -> bytes | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = self._recv_next_sysex(deadline - time.monotonic())
            if raw is None:
                return None
            body = raw[1:-1]
            if (
                len(body) <= 12
                or body[5] not in (SysExCmd.RESPONSE, SysExCmd.RESPONSE_ALT)
                or body[7] != CMD_FILE
            ):
                continue
            decoded = Packed7.unpack(body[9:])
            if len(decoded) <= 2:
                continue
            echo_page, _ = U14LE.decode(decoded[:2])
            if int(echo_page) != page:
                if debug:
                    print(f"  ⚠ Page mismatch: expected {page}, got {int(echo_page)}")
                continue
            return bytes(decoded[2:])
        return None

    def probe_channels(self, slot: int) -> tuple[int, int]:
        """Probe channel count and size via a single-chunk partial download.

        Sends DownloadInitRequest (to get file size) then one DownloadChunkRequest
        (page 0). Runs _detect_channels on the decoded first chunk.

        Returns (channels, size_bytes).  channels is 1 or 2.  size_bytes is the
        raw PCM byte count from the init response, or 0 on failure.
        Does NOT complete the download — the device silently discards the session.
        """
        seq = 0x2E
        init_resp = self._send_file_request(
            DownloadInitRequest(slot=slot),
            timeout=2.0,
            expect_resp_cmd=(SysExCmd.DOWNLOAD - 0x40),
            seq=seq,
        )

        file_info = None
        if init_resp:
            _status, payload = init_resp
            size = _extract_download_file_size(payload)
            if size is not None:
                file_info = {"size": size}

        if not file_info:
            return 1, 0

        # Request just page 0
        self._drain_pending()
        seq = (seq + 1) & 0x7F
        self._send_msg(DownloadChunkRequest(page=0), seq=seq)
        chunk_data = self._recv_download_chunk(page=0, timeout=2.5)

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
