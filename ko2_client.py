#!/usr/bin/env python3
"""
EP-133 KO-II Device Client

Provides high-level operations for the EP-133 device.
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

from ko2_protocol import (
    SysExCmd,
    GetType,
    SAMPLE_RATE,
    BIT_DEPTH,
    CHANNELS,
    MAX_SLOTS,
    UPLOAD_CHUNK_SIZE,
    UPLOAD_PARENT_NODE,
    UPLOAD_DELAY,
    build_sysex,
    parse_json_from_sysex,
    CMD_FILE,
    FIXED_BYTE,
    TE_MFG_ID,
    DEVICE_FAMILY,
    SYSEX_START,
    SYSEX_END,
    unpack_7bit as decode_7bit,
    slot_from_sound_entry,
    build_info_request,
    build_download_init_request,
    build_download_chunk_request,
    build_upload_init_request,
    build_upload_chunk_request,
    build_upload_end_request,
    build_delete_request,
    build_file_list_request,
    parse_file_list_response,
    build_metadata_get_request,
    build_metadata_set_request,
    parse_file_list_response_raw,
)


@dataclass
class SampleInfo:
    """Sample metadata from device."""

    slot: int
    name: str
    sym: str = ""
    samplerate: int = 46875
    format: str = "s16"
    channels: int = 1
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


class EP133Client:
    """Client for EP-133 KO-II device operations."""

    def __init__(self, device_name: Optional[str] = None):
        self.device_name = device_name or self._find_device()
        if not self.device_name:
            raise DeviceNotFoundError("EP-133 not found. Connect via USB.")

        self._outport: Optional[mido.ports.Output] = None
        self._inport: Optional[mido.ports.Input] = None
        self._seq = 0

    def _find_device(self) -> Optional[str]:
        for port in mido.get_output_names():
            if "EP-133" in port or "EP-1320" in port:
                return port
        return None

    def _next_seq(self) -> int:
        seq = self._seq
        self._seq = (self._seq + 1) & 0x7F
        return seq

    def connect(self):
        """Open MIDI connection to device."""
        self._outport = mido.open_output(self.device_name)
        self._inport = mido.open_input(self.device_name)
        self._initialize()

    def close(self):
        """Close MIDI connection."""
        if self._outport:
            self._outport.close()
        if self._inport:
            self._inport.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    def _initialize(self):
        """Send device initialization sequence."""
        init_messages = [
            bytes([SYSEX_START, 0x7E, 0x7F, 0x06, 0x01, SYSEX_END]),
            bytes(
                [
                    SYSEX_START,
                    *TE_MFG_ID,
                    *DEVICE_FAMILY,
                    SysExCmd.INIT,
                    0x17,
                    0x01,
                    SYSEX_END,
                ]
            ),
            bytes(
                [
                    SYSEX_START,
                    *TE_MFG_ID,
                    *DEVICE_FAMILY,
                    SysExCmd.INIT,
                    0x18,
                    CMD_FILE,
                    FIXED_BYTE,
                    0x01,
                    0x01,
                    0x00,
                    0x40,
                    0x00,
                    0x00,
                    SYSEX_END,
                ]
            ),
        ]
        for msg in init_messages:
            self._outport.send(mido.Message("sysex", data=msg[1:-1]))
            time.sleep(0.05)

    def _send_sysex(self, data: bytes, debug: bool = False) -> None:
        """Send SysEx message to device."""
        if debug:
            hex_str = " ".join(f"{b:02X}" for b in data[:80])  # First 80 bytes
            if len(data) > 80:
                hex_str += "..."
            print(f"  TX: {hex_str}")
        msg = mido.Message("sysex", data=data[1:-1])
        self._outport.send(msg)

    def _send_and_wait(
        self,
        data: bytes,
        timeout: float = 2.0,
        debug: bool = False,
        expect_cmd: int | None = None,
    ) -> bytes | None:
        """Send SysEx and wait for a real TE response.

        The EP-133 emits async notifications; we ignore anything that isn't a
        response (cmd in 0x2x range). If expect_cmd is provided, we only return
        a response with that cmd byte.
        """
        # Drain pending messages first
        for _ in self._inport.iter_pending():
            pass
        self._send_sysex(data, debug=debug)
        deadline = time.time() + timeout
        while time.time() < deadline:
            for msg in self._inport.iter_pending():
                if msg.type == "sysex":
                    raw = bytes([SYSEX_START]) + bytes(msg.data) + bytes([SYSEX_END])
                    # TE responses have cmd in 0x2x range (see references/rcy).
                    if len(raw) < 8:
                        continue
                    if raw[0] != SYSEX_START or raw[-1] != SYSEX_END:
                        continue
                    if raw[1:4] != TE_MFG_ID or raw[4:6] != DEVICE_FAMILY:
                        continue
                    cmd = raw[6]
                    if (cmd & 0xF0) != 0x20:
                        continue
                    if expect_cmd is not None and cmd != (expect_cmd & 0x7F):
                        continue
                    return raw
            time.sleep(0.01)
        return None

    def _check_response_status(self, response: bytes | None) -> int | None:
        """Check response status. Returns 0 on success, other on error, None on no response."""
        if response is None or len(response) < 10:
            return None
        # Response format: F0 00 20 76 33 40 [cmd] [seq] [sub] [status] ... F7
        return response[9] if len(response) > 9 else None

    def _recv_sysex(
        self, timeout: float = 0.5, filter_fn: Optional[Callable] = None
    ) -> list[bytes]:
        """Receive SysEx messages from device."""
        responses = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            for msg in self._inport.iter_pending():
                if msg.type == "sysex":
                    # msg.data is bytes in mido 2.x+
                    data = bytes([SYSEX_START]) + bytes(msg.data) + bytes([SYSEX_END])
                    if filter_fn is None or filter_fn(data):
                        responses.append(data)
            if responses and filter_fn is None:
                break
            time.sleep(0.01)
        return responses

    # ========================================================================
    # INFO - Query sample metadata
    # ========================================================================

    def device_info(self) -> dict | None:
        """Query device info (firmware/model/serial when available)."""
        req_data = bytes([SysExCmd.INFO, 0x14, 0x01])
        for _ in self._inport.iter_pending():
            pass
        self._send_sysex(build_sysex(req_data))
        time.sleep(0.2)

        responses = self._recv_sysex(timeout=0.4)
        candidates: list[bytes] = []
        for resp in responses:
            if len(resp) > 7 and resp[6] in (SysExCmd.RESPONSE, SysExCmd.INFO):
                candidates.append(resp)
        if not candidates and responses:
            candidates = responses

        for resp in candidates:
            data = list(resp)
            info = parse_json_from_sysex(data, offset=8)
            if not info:
                info = parse_json_from_sysex(data, offset=10)
            if info:
                return info
        return None

    def _get_file_size(self, slot: int) -> int | None:
        """Get file size for a slot without downloading the whole file."""
        seq = 0x2E
        # Send GET INIT
        init_req = bytes([SysExCmd.DOWNLOAD, seq]) + build_download_init_request(slot)
        init_msg = build_sysex(init_req)

        for _ in self._inport.iter_pending():
            pass

        self._send_sysex(init_msg)
        time.sleep(0.2)

        # Parse file info response
        for msg in self._inport.iter_pending():
            if msg.type == "sysex":
                data = list(msg.data)
                raw_bytes = bytes(data)
                if len(data) > 20 and (b".pcm" in raw_bytes or b".PCM" in raw_bytes):
                    for start_offset in [9, 10, 11]:
                        encoded = bytes(data[start_offset:])
                        decoded = decode_7bit(encoded)
                        if b".pcm" in decoded or b".PCM" in decoded:
                            if len(decoded) >= 7:
                                file_size = (
                                    (decoded[3] << 24)
                                    | (decoded[4] << 16)
                                    | (decoded[5] << 8)
                                    | decoded[6]
                                )
                                return file_size
        return None

    def _meta_from_get_meta(self, slot: int) -> dict | None:
        # GET_META uses a slot byte after device id (7-bit), then slot in payload.
        req_data = bytes([SysExCmd.GET_META, slot & 0x7F]) + build_info_request(slot)

        for _ in self._inport.iter_pending():
            pass
        self._send_sysex(build_sysex(req_data))
        time.sleep(0.2)

        responses = self._recv_sysex(timeout=0.4)

        matches: list[bytes] = []
        fallback: list[bytes] = []
        for resp in responses:
            data = list(resp)
            if len(data) > 10 and data[6] == 0x35:  # RspCmd.META
                if len(data) > 7 and data[7] == (slot & 0x7F):
                    matches.append(resp)
                else:
                    fallback.append(resp)

        for resp in matches + fallback:
            data = list(resp)
            metadata = parse_json_from_sysex(data, offset=8)
            if not metadata:
                metadata = parse_json_from_sysex(data, offset=10)
            if metadata:
                return metadata

        return None

    def get_meta(self, slot: int) -> dict | None:
        """Return raw GET_META metadata for a slot (may be stale or offset)."""
        if not 1 <= slot <= MAX_SLOTS:
            raise ValueError(f"Slot must be 1-{MAX_SLOTS}, got {slot}")
        return self._meta_from_get_meta(slot)

    def info(
        self,
        slot: int,
        include_size: bool = True,
        node_entry: dict | None = None,
        prefer_node: bool = True,
        allow_get_meta: bool = False,
    ) -> SampleInfo:
        """
        Get metadata for a sample slot.

        Args:
            slot: Slot number (1-999)
            include_size: Whether to fetch file size (adds roundtrip)
            allow_get_meta: Allow GET_META fallback (known stale)

        Returns:
            SampleInfo with metadata

        Raises:
            SlotEmptyError: If slot is empty
        """
        if not 1 <= slot <= MAX_SLOTS:
            raise ValueError(f"Slot must be 1-{MAX_SLOTS}, got {slot}")

        entry = node_entry
        if prefer_node and entry is None:
            try:
                entry = self.list_sounds().get(slot)
            except Exception:
                entry = None

        node_meta = None
        if entry:
            node_id = int(entry.get("node_id") or 0)
            if node_id:
                try:
                    node_meta = self.get_node_metadata(node_id)
                except Exception:
                    node_meta = None

        metadata: dict = {}
        if node_meta:
            metadata.update(node_meta)

        if allow_get_meta:
            meta2 = self._meta_from_get_meta(slot)
            if meta2:
                if slot <= 127:
                    for k, v in meta2.items():
                        metadata.setdefault(k, v)
                else:
                    for k in ("channels", "samplerate", "format"):
                        if k in meta2 and k not in metadata:
                            metadata[k] = meta2[k]

        if not metadata and not entry:
            raise SlotEmptyError(f"Slot {slot} is empty")

        size_bytes = 0
        if include_size:
            if entry and entry.get("size") is not None:
                size_bytes = int(entry.get("size") or 0)
            else:
                size_bytes = self._get_file_size(slot) or 0

        name = (
            metadata.get("name")
            or metadata.get("sym")
            or (entry.get("name") if entry else None)
            or f"Slot {slot:03d}"
        )

        return SampleInfo(
            slot=slot,
            name=name,
            sym=metadata.get("sym", ""),
            samplerate=metadata.get("samplerate", SAMPLE_RATE),
            format=metadata.get("format", "s16"),
            channels=metadata.get("channels", 1),
            size_bytes=size_bytes,
        )

    # ========================================================================
    # LIST - Scan multiple slots
    # ========================================================================

    def list_slots(
        self, start: int = 1, end: int = MAX_SLOTS, progress: bool = False
    ) -> list[SampleInfo]:
        """
        Scan multiple slots and return metadata.

        Args:
            start: First slot to scan (1-999)
            end: Last slot to scan (1-999)
            progress: Show progress indicator

        Returns:
            List of SampleInfo for non-empty slots
        """
        results = []
        for slot in range(start, end + 1):
            if progress and slot % 50 == 0:
                print(f"  Scanning slot {slot}...\r", end="", flush=True)

            try:
                info = self.info(slot)
                results.append(info)
            except SlotEmptyError:
                pass

        if progress:
            print()

        return results

    # ========================================================================
    # GET - Download sample from device
    # ========================================================================

    def get(self, slot: int, output_path: Optional[Path] = None) -> Path:
        """
        Download sample from device to WAV file.

        Args:
            slot: Slot number (1-999)
            output_path: Output file path (auto-generated if None)

        Returns:
            Path to downloaded WAV file
        """
        # Get metadata first
        metadata = self.info(slot)

        if output_path is None:
            name = metadata.sym or f"sample_{slot:03d}"
            output_path = Path(f"{name}_{slot:03d}.wav")

        # Download data
        data = self._download_data(slot)

        # Save as WAV (use metadata for correct header)
        self._save_wav(
            data,
            output_path,
            channels=max(1, int(metadata.channels or 1)),
            samplerate=int(metadata.samplerate or SAMPLE_RATE),
        )

        return output_path

    def _download_data(self, slot: int) -> bytes:
        """Download raw sample data from device."""
        seq = 0x2E
        # Send GET INIT
        init_msg = bytes([SysExCmd.DOWNLOAD, seq]) + build_download_init_request(slot)
        init_msg = build_sysex(init_msg)

        # Clear pending
        for _ in self._inport.iter_pending():
            pass

        self._send_sysex(init_msg)
        time.sleep(0.3)

        # Parse file info response
        file_info = None
        for msg in self._inport.iter_pending():
            if msg.type == "sysex":
                data = list(msg.data)
                raw_bytes = bytes(data)
                if len(data) > 20 and (b".pcm" in raw_bytes or b".PCM" in raw_bytes):
                    for start_offset in [9, 10, 11]:
                        encoded = bytes(data[start_offset:])
                        decoded = decode_7bit(encoded)
                        if b".pcm" in decoded or b".PCM" in decoded:
                            if len(decoded) >= 7:
                                file_size = (
                                    (decoded[3] << 24)
                                    | (decoded[4] << 16)
                                    | (decoded[5] << 8)
                                    | decoded[6]
                                )
                                file_info = {"size": file_size}
                                break
                    break

        if not file_info:
            raise EP133Error("Failed to get file info")

        # Request data chunks
        all_data = []
        page = 0
        received = 0

        while received < file_info["size"]:
            for _ in self._inport.iter_pending():
                pass

            seq = (seq + 1) & 0x7F

            data_req = build_sysex(
                bytes([SysExCmd.DOWNLOAD, seq]) + build_download_chunk_request(page)
            )

            self._send_sysex(data_req)
            time.sleep(0.05)

            # Receive chunk
            chunk_received = False
            timeout_counter = 0
            while timeout_counter < 50 and not chunk_received:
                for msg in self._inport.iter_pending():
                    if msg.type == "sysex":
                        data = list(msg.data)
                        if (
                            len(data) > 12
                            and data[5] in (SysExCmd.RESPONSE, SysExCmd.RESPONSE_ALT)
                            and data[7] == CMD_FILE
                        ):
                            # SysEx structure: [0..4] mfg+dev, [5] resp_type, [6] seq,
                            # [7] CMD_FILE, [8] sub_byte (always 0x00), [9..] 7-bit payload.
                            # The payload always starts at offset 9 — structural, not dynamic.
                            # Each decoded chunk begins with a 2-byte page-number echo
                            # [page_lo, page_hi] followed by BE s16 audio bytes.
                            decoded = decode_7bit(bytes(data[9:]))
                            if decoded and len(decoded) > 2:
                                all_data.extend(decoded[2:])  # strip page prefix
                                received += len(decoded)
                                chunk_received = True
                if chunk_received:
                    break
                time.sleep(0.05)
                timeout_counter += 1

            if not chunk_received:
                break

            page = (page + 1) & 0x3FFF  # 14-bit max (two 7-bit bytes)

        # Device sends BE s16; convert to LE s16 for WAV compatibility.
        be_data = bytes(all_data)
        le_data = bytearray()
        for i in range(0, len(be_data) - 1, 2):
            sample = struct.unpack(">h", be_data[i : i + 2])[0]
            le_data.extend(struct.pack("<h", sample))
        return bytes(le_data)[: file_info["size"]]

    def _save_wav(
        self, data: bytes, output_path: Path, channels: int, samplerate: int
    ) -> None:
        """Save PCM data (or already-formed WAV) to a WAV file."""
        if len(data) >= 4 and data[:4] == b"RIFF":
            output_path.write_bytes(data)
            return

        import wave

        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(BIT_DEPTH // 8)
            wav.setframerate(samplerate)

            # Data from the device is already s16 little-endian PCM. Write as-is.
            if data:
                wav.writeframes(data)

    # ========================================================================
    # FILE LIST - Enumerate /sounds directory (ground truth listing)
    # ========================================================================

    def list_directory(self, node_id: int = UPLOAD_PARENT_NODE) -> list[dict]:
        """List entries in a filesystem directory node (e.g. node 1000 = /sounds/)."""
        all_entries: list[dict] = []
        page = 0

        while True:
            seq = self._next_seq()
            req_data = bytes([0x6A, seq]) + build_file_list_request(node_id, page)
            msg = build_sysex(req_data)

            resp = self._send_and_wait(msg, timeout=2.0, expect_cmd=(0x6A - 0x40))
            status = self._check_response_status(resp)
            if status is None or resp is None:
                break

            encoded_payload = resp[10:-1] if resp and len(resp) > 11 else b""
            payload = decode_7bit(encoded_payload) if encoded_payload else b""
            entries = parse_file_list_response(payload)
            if not entries:
                break

            all_entries.extend(entries)
            page += 1
            if status != 0:
                break
            if page > 200:
                break

        return all_entries

    def list_directory_raw(self, node_id: int = UPLOAD_PARENT_NODE) -> list[dict]:
        """List entries with raw hi/lo bytes (debug)."""
        all_entries: list[dict] = []
        page = 0

        while True:
            seq = self._next_seq()
            req_data = bytes([0x6A, seq]) + build_file_list_request(node_id, page)
            msg = build_sysex(req_data)

            resp = self._send_and_wait(msg, timeout=2.0, expect_cmd=(0x6A - 0x40))
            status = self._check_response_status(resp)
            if status is None or resp is None:
                break

            encoded_payload = resp[10:-1] if resp and len(resp) > 11 else b""
            payload = decode_7bit(encoded_payload) if encoded_payload else b""
            entries = parse_file_list_response_raw(payload)
            if not entries:
                break

            all_entries.extend(entries)
            page += 1
            if status != 0:
                break
            if page > 200:
                break

        return all_entries

    def list_sounds(self) -> dict[int, dict]:
        """Return ground-truth /sounds listing mapped by slot number.

        Uses FILE LIST against node_id=1000 (/sounds). This reflects actual
        stored audio files and is preferred over slot-scan for inventory.
        """
        entries = self.list_directory(UPLOAD_PARENT_NODE)
        by_slot: dict[int, dict] = {}
        for e in entries:
            if e.get("is_dir"):
                continue
            slot = slot_from_sound_entry(e)
            if slot is None:
                continue
            by_slot[slot] = e
        return by_slot

    def get_node_metadata(self, node_id: int) -> dict | None:
        """Fetch metadata JSON for a filesystem node (paged)."""
        import json as _json

        all_bytes = bytearray()
        page = 0
        while True:
            seq = self._next_seq()
            req_data = bytes([0x6A, seq]) + build_metadata_get_request(node_id, page)
            msg = build_sysex(req_data)

            resp = self._send_and_wait(msg, timeout=2.0, expect_cmd=(0x6A - 0x40))
            status = self._check_response_status(resp)
            if status is None or status != 0:
                break

            encoded_payload = resp[10:-1] if resp and len(resp) > 11 else b""
            payload = decode_7bit(encoded_payload) if encoded_payload else b""
            if len(payload) < 2:
                break
            fragment = payload[2:]
            if not fragment or fragment == b"\x00":
                break
            all_bytes.extend(fragment.rstrip(b"\x00"))
            page += 1
            if page > 200:
                break

        if not all_bytes:
            return None

        text = "".join(chr(b) for b in all_bytes if b != 0)
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return _json.loads(text[start : end + 1])
        except Exception:
            return None

    def rename(self, slot: int, new_name: str) -> None:
        """Rename a sound slot by setting filesystem-node metadata.

        Uses /sounds directory listing to resolve slot -> node_id, then attempts
        a METADATA SET on that node.
        """
        sounds = self.list_sounds()
        entry = sounds.get(slot)
        node_id = int(entry.get("node_id") or 0) if entry else 0

        if not node_id:
            raise EP133Error(f"Could not resolve node_id for slot {slot}")

        seq = self._next_seq()
        req_data = bytes([0x6A, seq]) + build_metadata_set_request(
            node_id,
            json.dumps({"name": new_name}, separators=(",", ":"), ensure_ascii=False),
        )
        msg = build_sysex(req_data)
        resp = self._send_and_wait(msg, timeout=2.0, expect_cmd=(0x6A - 0x40))
        status = self._check_response_status(resp)
        if status is None:
            raise EP133Error("No response to rename")
        if status != 0:
            raise EP133Error(f"Rename failed: status={status}")

    # ========================================================================
    # PUT - Upload sample to device
    # ========================================================================

    @staticmethod
    def build_upload_metadata(
        channels: int, samplerate: int, frames: int
    ) -> dict[str, object]:
        meta: dict[str, object] = {
            "channels": channels,
            "samplerate": samplerate,
        }
        loop_end = max(0, frames - 1)
        if loop_end <= 0x1FFFF:
            meta.update(
                {
                    "sound.loopstart": 0,
                    "sound.loopend": loop_end,
                    "sound.rootnote": 60,
                }
            )
        return meta

    def put(
        self,
        input_path: Path,
        slot: int,
        name: Optional[str] = None,
        progress: bool = True,
        debug: bool = False,
    ) -> None:
        """
        Upload sample to device.

        Args:
            input_path: Path to WAV file
            slot: Target slot (1-999)
            name: Sample name (defaults to filename)
            progress: Show progress bar
            debug: Print hex dumps of messages sent
        """
        import wave
        import json as _json

        if not 1 <= slot <= MAX_SLOTS:
            raise ValueError(f"Slot must be 1-{MAX_SLOTS}, got {slot}")

        # Read and validate WAV file
        try:
            with wave.open(str(input_path), "rb") as wav:
                frames = wav.getnframes()
                samplerate = wav.getframerate()
                channels = wav.getnchannels()
                sampwidth = wav.getsampwidth()

                if samplerate <= 0:
                    raise ValueError(f"Invalid sample rate: {samplerate}Hz")
                if channels not in (1, 2):
                    raise ValueError(f"Channels must be 1 or 2, got {channels}")
                if sampwidth != BIT_DEPTH // 8:
                    raise ValueError(f"Must be 16-bit, got {sampwidth * 8}-bit")

                # Read raw audio data
                raw_data = wav.readframes(frames)
        except Exception as e:
            raise EP133Error(f"Failed to read WAV file: {e}")

        # WAV is little-endian s16; device expects big-endian s16
        audio_data = bytearray()
        for i in range(0, len(raw_data) - 1, 2):
            sample = struct.unpack("<h", raw_data[i : i + 2])[0]
            audio_data.extend(struct.pack(">h", sample))

        data_size = len(audio_data)

        if name is None:
            name = input_path.stem

        # Upload uses TE command bytes 0x6C (init + chunks) and 0x6D (end marker),
        # matching the working reference implementation (see UPLOAD_INVESTIGATION.md).
        # The byte after CMD_FILE (0x05) is *7-bit pack flags* (MSB bitmap), not a
        # semantic "operation flags" field.

        # Step 1: Upload Init (0x6C)
        init_seq = self._next_seq()
        init_req = bytes(
            [SysExCmd.UPLOAD_DATA, init_seq, CMD_FILE]
        ) + build_upload_init_request(slot, data_size, channels, samplerate, name)
        init_msg = build_sysex(init_req)

        response = self._send_and_wait(
            init_msg,
            timeout=5.0,
            debug=debug,
            expect_cmd=(SysExCmd.UPLOAD_DATA - 0x40),
        )
        status = self._check_response_status(response)
        if status is None:
            raise EP133Error("No response to upload init")
        if status != 0:
            raise EP133Error(f"Upload init failed: status={status}")

        if progress:
            print(f"  Uploading {data_size} bytes...", end="", flush=True)

        # Step 2: Send data chunks (0x6C)
        # Chunks use an index (not a byte offset), 433 bytes max after unpacking.
        chunk_index = 0
        offset = 0

        while offset < data_size:
            chunk_data = bytes(audio_data[offset : offset + UPLOAD_CHUNK_SIZE])

            # Chunk payload
            chunk_seq = self._next_seq()
            chunk_req = bytes(
                [SysExCmd.UPLOAD_DATA, chunk_seq]
            ) + build_upload_chunk_request(chunk_index, chunk_data)
            chunk_msg = build_sysex(chunk_req)

            response = self._send_and_wait(
                chunk_msg,
                timeout=2.0,
                debug=debug,
                expect_cmd=(SysExCmd.UPLOAD_DATA - 0x40),
            )
            status = self._check_response_status(response)
            if status is None:
                raise EP133Error(f"No response to chunk {chunk_index}")
            if status != 0:
                raise EP133Error(f"Chunk {chunk_index} failed: status={status}")

            time.sleep(UPLOAD_DELAY)  # 20ms delay required by device

            offset += UPLOAD_CHUNK_SIZE
            chunk_index += 1

            if progress and chunk_index % 10 == 0:
                print(".", end="", flush=True)

        if progress:
            print(" done", flush=True)

        # Step 3: End marker (0x6D)
        end_seq = self._next_seq()
        end_req = bytes([SysExCmd.UPLOAD_END, end_seq]) + build_upload_end_request(
            chunk_index
        )
        end_msg = build_sysex(end_req)

        response = self._send_and_wait(
            end_msg,
            timeout=5.0,
            debug=debug,
            expect_cmd=(SysExCmd.UPLOAD_END - 0x40),
        )
        status = self._check_response_status(response)
        if status is None:
            raise EP133Error("No response to upload end marker")
        # Observed: end marker may return non-zero even when the upload persists.
        # Treat it as a warning (rcy only enforces "response exists").
        if status != 0 and debug:
            print(f"  ⚠ Upload end marker status={status} (continuing)")

        # Step 4: Metadata SET (official tool writes channels/samplerate; sometimes loop info)
        meta_payload = self.build_upload_metadata(channels, samplerate, frames)

        try:
            seq = self._next_seq()
            req_data = bytes([0x6A, seq]) + build_metadata_set_request(
                slot,
                _json.dumps(meta_payload, separators=(",", ":"), ensure_ascii=False),
            )
            msg = build_sysex(req_data)
            resp = self._send_and_wait(
                msg, timeout=2.0, debug=debug, expect_cmd=(0x6A - 0x40)
            )
            status = self._check_response_status(resp)
            if status is None or status != 0:
                if debug:
                    print(f"  ⚠ Metadata SET status={status}")
        except EP133Error as e:
            if debug:
                print(f"  ⚠ Metadata SET failed: {e}")

        # Step 5: Sync
        self._initialize()

    # ========================================================================
    # DELETE - Remove sample from device
    # ========================================================================

    def delete(self, slot: int) -> None:
        """
        Delete sample from slot.

        Args:
            slot: Slot number (1-999)
        """
        # F0 00 20 76 33 40 7E [SEQ] 05 00 06 [SLOT_HI] [SLOT_LO] F7
        req_data = bytes([SysExCmd.UPLOAD, self._next_seq()]) + build_delete_request(
            slot
        )
        msg = build_sysex(req_data)

        for _ in self._inport.iter_pending():
            pass

        self._send_sysex(msg)
        time.sleep(0.1)

    # ========================================================================
    # GROUP - Compact samples in range
    # ========================================================================

    def group(self, start: int, end: int, direction: str = "left") -> dict[int, int]:
        """
        Compact samples in a range toward one end, removing gaps.

        Args:
            start: First slot in range (1-999)
            end: Last slot in range (1-999)
            direction: "left" to compact toward start, "right" toward end

        Returns:
            Dict mapping old_slot -> new_slot
        """
        if not 1 <= start <= MAX_SLOTS:
            raise ValueError(f"Invalid start slot: {start}")
        if not 1 <= end <= MAX_SLOTS:
            raise ValueError(f"Invalid end slot: {end}")
        if start > end:
            raise ValueError(f"start ({start}) must be <= end ({end})")
        if direction not in ("left", "right"):
            raise ValueError(f"direction must be 'left' or 'right', got '{direction}'")

        # Scan for occupied slots
        occupied = []
        for slot in range(start, end + 1):
            try:
                info = self.info(slot)
                occupied.append(slot)
            except SlotEmptyError:
                pass

        if not occupied:
            return {}

        # Calculate new positions
        mapping = {}
        if direction == "left":
            for i, old_slot in enumerate(occupied):
                new_slot = start + i
                mapping[old_slot] = new_slot
        else:  # right
            for i, old_slot in enumerate(reversed(occupied)):
                new_slot = end - i
                mapping[old_slot] = new_slot

        # Perform moves (download, delete, upload)
        # For now, return mapping - actual moves need upload working
        return mapping


def find_device() -> Optional[str]:
    """Find connected EP-133 device name."""
    for port in mido.get_output_names():
        if "EP-133" in port or "EP-1320" in port:
            return port
    return None
