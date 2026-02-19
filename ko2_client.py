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
    DeviceId, FileOp, GetType, MetaType,
    SAMPLE_RATE, BIT_DEPTH, CHANNELS, MAX_SLOTS,
    encode_slot, encode_slot_be, decode_slot, build_sysex, parse_json_from_sysex,
    CMD_FILE, FIXED_BYTE, TE_MFG_ID, DEVICE_FAMILY, SYSEX_START, SYSEX_END,
    PAT_META_REQ, E_EMPTY,
)


def encode_7bit(data: bytes) -> bytes:
    """Encode 8-bit data to 7-bit MIDI SysEx format."""
    result = bytearray()
    i = 0
    while i < len(data):
        chunk = data[i:i+7]
        high_bits = 0
        for j, byte in enumerate(chunk):
            high_bits |= ((byte >> 7) << j)
        result.append(high_bits)
        for byte in chunk:
            result.append(byte & 0x7F)
        i += 7
    return bytes(result)


def decode_7bit(data: bytes) -> bytes:
    """Decode 7-bit MIDI SysEx data back to 8-bit format."""
    result = bytearray()
    i = 0
    while i < len(data):
        if i + 8 > len(data):
            high_bits = data[i]
            for j in range(min(7, len(data) - i - 1)):
                if i + 1 + j < len(data):
                    result.append(data[i + 1 + j] | (((high_bits >> j) & 0x01) << 7))
            break

        high_bits = data[i]
        for j in range(7):
            if i + 1 + j < len(data):
                result.append(data[i + 1 + j] | (((high_bits >> j) & 0x01) << 7))
        i += 8
    return bytes(result)


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
            if 'EP-133' in port or 'EP-1320' in port:
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
            bytes([SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, DeviceId.INIT, 0x17, 0x01, SYSEX_END]),
            bytes([SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, DeviceId.INIT, 0x18,
                   CMD_FILE, FIXED_BYTE, 0x01, 0x01, 0x00, 0x40, 0x00, 0x00, SYSEX_END]),
        ]
        for msg in init_messages:
            self._outport.send(mido.Message('sysex', data=msg[1:-1]))
            time.sleep(0.05)

    def _send_sysex(self, data: bytes, debug: bool = False) -> None:
        """Send SysEx message to device."""
        if debug:
            hex_str = ' '.join(f'{b:02X}' for b in data[:80])  # First 80 bytes
            if len(data) > 80:
                hex_str += '...'
            print(f"  TX: {hex_str}")
        msg = mido.Message('sysex', data=data[1:-1])
        self._outport.send(msg)

    def _recv_sysex(self, timeout: float = 0.5, filter_fn: Optional[Callable] = None) -> list[bytes]:
        """Receive SysEx messages from device."""
        responses = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            for msg in self._inport.iter_pending():
                if msg.type == 'sysex':
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

    def _get_file_size(self, slot: int) -> int | None:
        """Get file size for a slot without downloading the whole file."""
        slot_high, slot_low = encode_slot_be(slot)
        seq = 0x2E
        offset = bytes([0x00, 0x00, 0x00, 0x00, 0x00])

        # Send GET INIT
        init_msg = bytes([
            SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, DeviceId.DOWNLOAD,
            seq, CMD_FILE, FIXED_BYTE, FileOp.GET, GetType.INIT,
            slot_high, slot_low,
        ]) + offset + bytes([SYSEX_END])

        for _ in self._inport.iter_pending():
            pass

        self._send_sysex(init_msg)
        time.sleep(0.2)

        # Parse file info response
        for msg in self._inport.iter_pending():
            if msg.type == 'sysex':
                data = list(msg.data)
                raw_bytes = bytes(data)
                if len(data) > 20 and (b'.pcm' in raw_bytes or b'.PCM' in raw_bytes):
                    for start_offset in [9, 10, 11]:
                        encoded = bytes(data[start_offset:])
                        decoded = decode_7bit(encoded)
                        if b'.pcm' in decoded or b'.PCM' in decoded:
                            if len(decoded) >= 7:
                                file_size = (decoded[3] << 24) | (decoded[4] << 16) | (decoded[5] << 8) | decoded[6]
                                return file_size
        return None

    def info(self, slot: int, include_size: bool = True) -> SampleInfo:
        """
        Get metadata for a sample slot.

        Args:
            slot: Slot number (1-999)
            include_size: Whether to fetch file size (adds roundtrip)

        Returns:
            SampleInfo with metadata

        Raises:
            SlotEmptyError: If slot is empty
        """
        if not 1 <= slot <= MAX_SLOTS:
            raise ValueError(f"Slot must be 1-{MAX_SLOTS}, got {slot}")

        slot_high, slot_low = encode_slot(slot)

        req_data = bytes([
            0x75,  # GET_META command
            slot & 0x7F,
        ]) + PAT_META_REQ + bytes([slot_high, slot_low]) + E_EMPTY

        self._send_sysex(build_sysex(req_data))
        time.sleep(0.2)

        responses = self._recv_sysex(timeout=0.3)

        for resp in responses:
            data = list(resp)
            if len(data) > 10 and data[6] == 0x35:  # RspCmd.META (position 6 after header)
                metadata = parse_json_from_sysex(data, offset=8)
                if metadata:
                    size_bytes = 0
                    if include_size:
                        size_bytes = self._get_file_size(slot) or 0

                    return SampleInfo(
                        slot=slot,
                        name=metadata.get('name', metadata.get('sym', f'Slot {slot:03d}')),
                        sym=metadata.get('sym', ''),
                        samplerate=metadata.get('samplerate', SAMPLE_RATE),
                        format=metadata.get('format', 's16'),
                        channels=metadata.get('channels', 1),
                        size_bytes=size_bytes,
                    )

        raise SlotEmptyError(f"Slot {slot} is empty")

    # ========================================================================
    # LIST - Scan multiple slots
    # ========================================================================

    def list_slots(self, start: int = 1, end: int = MAX_SLOTS,
                   progress: bool = False) -> list[SampleInfo]:
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

        # Save as WAV
        self._save_wav(data, output_path)

        return output_path

    def _download_data(self, slot: int) -> bytes:
        """Download raw sample data from device."""
        slot_high, slot_low = encode_slot_be(slot)
        seq = 0x2E
        offset = bytes([0x00, 0x00, 0x00, 0x00, 0x00])

        # Send GET INIT
        init_msg = bytes([
            SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, DeviceId.DOWNLOAD,
            seq, CMD_FILE, FIXED_BYTE, FileOp.GET, GetType.INIT,
            slot_high, slot_low,
        ]) + offset + bytes([SYSEX_END])

        # Clear pending
        for _ in self._inport.iter_pending():
            pass

        self._send_sysex(init_msg)
        time.sleep(0.3)

        # Parse file info response
        file_info = None
        for msg in self._inport.iter_pending():
            if msg.type == 'sysex':
                data = list(msg.data)
                raw_bytes = bytes(data)
                if len(data) > 20 and (b'.pcm' in raw_bytes or b'.PCM' in raw_bytes):
                    for start_offset in [9, 10, 11]:
                        encoded = bytes(data[start_offset:])
                        decoded = decode_7bit(encoded)
                        if b'.pcm' in decoded or b'.PCM' in decoded:
                            if len(decoded) >= 7:
                                file_size = (decoded[3] << 24) | (decoded[4] << 16) | (decoded[5] << 8) | decoded[6]
                                file_info = {'size': file_size}
                                break
                    break

        if not file_info:
            raise EP133Error("Failed to get file info")

        # Request data chunks
        all_data = []
        page = 0
        received = 0

        while received < file_info['size']:
            for _ in self._inport.iter_pending():
                pass

            # Encode page number using 7-bit values (MIDI data bytes must be 0-127)
            # Uses big-endian like slot encoding in download operations
            page_lo = page & 0x7F
            page_hi = (page >> 7) & 0x7F
            seq = (seq + 1) & 0x7F

            data_req = bytes([
                SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, DeviceId.DOWNLOAD,
                seq, CMD_FILE, FIXED_BYTE, FileOp.GET, GetType.DATA,
                page_hi, page_lo, SYSEX_END
            ])

            self._send_sysex(data_req)
            time.sleep(0.05)

            # Receive chunk
            chunk_received = False
            timeout_counter = 0
            while timeout_counter < 50 and not chunk_received:
                for msg in self._inport.iter_pending():
                    if msg.type == 'sysex':
                        data = list(msg.data)
                        if (len(data) > 12 and
                            data[5] in (DeviceId.RESPONSE, DeviceId.RESPONSE_ALT) and
                            data[7] == CMD_FILE):
                            for start_offset in [10, 11, 12, 13]:
                                if start_offset < len(data):
                                    encoded = bytes(data[start_offset:])
                                    if encoded:
                                        decoded = decode_7bit(encoded)
                                        if decoded and len(decoded) > 4:
                                            all_data.extend(decoded)
                                            received += len(decoded)
                                            chunk_received = True
                                            break
                                if chunk_received:
                                    break
                if chunk_received:
                    break
                time.sleep(0.05)
                timeout_counter += 1

            if not chunk_received:
                break

            page = (page + 1) & 0x3FFF  # 14-bit max (two 7-bit bytes)

        return bytes(all_data)

    def _save_wav(self, data: bytes, output_path: Path) -> None:
        """Save data as WAV file."""
        import wave

        with wave.open(str(output_path), 'wb') as wav:
            wav.setnchannels(CHANNELS)
            wav.setsampwidth(BIT_DEPTH // 8)
            wav.setframerate(SAMPLE_RATE)

            samples = []
            for i in range(0, len(data) - 1, 2):
                if i + 1 < len(data):
                    sample = struct.unpack('<h', bytes([data[i], data[i+1]]))[0]
                    samples.append(struct.pack('<h', sample))

            if samples:
                wav.writeframes(b''.join(samples))

    # ========================================================================
    # PUT - Upload sample to device
    # ========================================================================

    def put(self, input_path: Path, slot: int, name: Optional[str] = None,
            progress: bool = True, debug: bool = False) -> None:
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

        if not 1 <= slot <= MAX_SLOTS:
            raise ValueError(f"Slot must be 1-{MAX_SLOTS}, got {slot}")

        # Read and validate WAV file
        try:
            with wave.open(str(input_path), 'rb') as wav:
                frames = wav.getnframes()
                samplerate = wav.getframerate()
                channels = wav.getnchannels()
                sampwidth = wav.getsampwidth()

                if samplerate != SAMPLE_RATE:
                    raise ValueError(f"Sample rate must be {SAMPLE_RATE}Hz, got {samplerate}Hz")
                if channels != CHANNELS:
                    raise ValueError(f"Must be mono, got {channels} channels")
                if sampwidth != BIT_DEPTH // 8:
                    raise ValueError(f"Must be 16-bit, got {sampwidth * 8}-bit")

                # Read raw audio data
                raw_data = wav.readframes(frames)
        except Exception as e:
            raise EP133Error(f"Failed to read WAV file: {e}")

        # Convert to little-endian 16-bit samples
        audio_data = bytearray()
        for i in range(0, len(raw_data) - 1, 2):
            sample = struct.unpack('<h', raw_data[i:i+2])[0]
            audio_data.extend(struct.pack('<h', sample))

        data_size = len(audio_data)

        # Generate filename
        if name is None:
            name = input_path.stem
        # Sanitize name for EP-133 format (e.g., "1_kick_01")
        filename = f"{slot}_{name[:20]}"

        # Slot encoding for upload init (big-endian: high byte first)
        slot_high = (slot >> 7) & 0x7F
        slot_low = slot & 0x7F

        seq = 0x13  # Starting sequence for uploads (19, as seen in protocol examples)

        # Step 1: Upload Init
        # F0 00 20 76 33 40 6C [SEQ] 05 40 02 00 [TYPE] [SLOT_LO] [SLOT_HI]
        #    [7BIT_ENCODED: SIZE(4) + FILENAME + METADATA] F7
        # Note: Uses UPLOAD_DATA (0x6C) not UPLOAD (0x7E)

        # Build the variable payload that needs 7-bit encoding
        # Size (4 bytes, little-endian) + filename + null + metadata JSON
        size_bytes = struct.pack('<I', data_size)
        filename_bytes = filename.encode('ascii') + b'\x00'
        metadata_json = json.dumps({"channels": 1}, separators=(',', ':'))
        var_payload = size_bytes + filename_bytes + metadata_json.encode('ascii')

        # 7-bit encode the variable payload
        var_payload_encoded = encode_7bit(var_payload)

        # Fixed part of init message (not 7-bit encoded)
        init_fixed = bytes([
            0x05,      # CMD_FILE
            0x40,      # Upload init flags
            FileOp.PUT,
            0x00,      # PUT_INIT sub-operation
            0x05,      # File type (sample)
            slot_high, slot_low,  # Big-endian for upload init
        ])

        init_msg = bytes([SYSEX_START]) + TE_MFG_ID + DEVICE_FAMILY + bytes([
            DeviceId.UPLOAD_DATA, seq
        ]) + init_fixed + var_payload_encoded + bytes([SYSEX_END])

        self._send_sysex(init_msg, debug=debug)
        time.sleep(0.3)

        if progress:
            print(f"  Uploading {data_size} bytes...", end="", flush=True)

        # Step 2: Send data chunks (~500 bytes encoded each)
        chunk_size = 440  # Decoded bytes per chunk
        offset = 0

        while offset < data_size:
            chunk = audio_data[offset:offset + chunk_size]
            encoded_chunk = encode_7bit(bytes(chunk))

            # Calculate FLAGS byte (encodes high bits of offset)
            flags = 0x40 | 0x20 | ((offset >> 7) & 0x1F)

            # Offset bytes (little-endian)
            offset_lo = offset & 0x7F
            offset_hi = (offset >> 7) & 0x7F

            seq = (seq + 1) & 0x7F

            chunk_msg = bytes([
                SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, DeviceId.UPLOAD_DATA, seq,
                0x05,           # CMD_FILE
                flags,          # Encoded offset high bits
                FileOp.PUT,
                0x01,           # PUT_DATA sub-operation
                offset_lo, offset_hi,
            ]) + encoded_chunk + bytes([SYSEX_END])

            self._send_sysex(chunk_msg, debug=debug)
            time.sleep(0.05)

            offset += chunk_size

            if progress and offset % (chunk_size * 10) == 0:
                print(".", end="", flush=True)

        if progress:
            print(" done", flush=True)

        # Step 3: Commit/Verify
        seq = (seq + 1) & 0x7F
        commit_msg = bytes([
            SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, DeviceId.UPLOAD, seq,
            0x05, 0x00, 0x0B, 0x00, 0x01, SYSEX_END
        ])
        self._send_sysex(commit_msg, debug=debug)
        time.sleep(0.1)

        # Step 4: Re-Init (verification)
        seq = (seq + 1) & 0x7F
        reinit_msg = bytes([
            SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, DeviceId.UPLOAD, seq,
            0x05, 0x00, 0x01, 0x01, 0x00, 0x40, 0x00, 0x00, SYSEX_END
        ])
        self._send_sysex(reinit_msg, debug=debug)
        time.sleep(0.1)

        # Step 5: Final Commit
        seq = (seq + 1) & 0x7F
        final_commit_msg = bytes([
            SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, DeviceId.UPLOAD, seq,
            0x05, 0x00, 0x0B, 0x00, 0x01, SYSEX_END
        ])
        self._send_sysex(final_commit_msg, debug=debug)
        time.sleep(0.1)

        # Step 6: Metadata Set/Verify
        seq = (seq + 1) & 0x7F
        meta_msg = bytes([
            SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, DeviceId.UPLOAD, seq,
            0x05, 0x00, 0x07, 0x02, 0x00,
            slot_high, slot_low, 0x00, SYSEX_END
        ])
        self._send_sysex(meta_msg, debug=debug)
        time.sleep(0.1)

        # Step 7: Finalize - send size encoded as 7-bit
        seq = (seq + 1) & 0x7F
        # Size in bytes that need to fit in 7-bit MIDI range
        # Using low 3 bytes of size in little-endian order
        finalize_encoded = encode_7bit(struct.pack('<I', data_size)[:3])
        finalize_msg = bytes([
            SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, DeviceId.UPLOAD, seq,
            0x05, 0x08, FileOp.METADATA, MetaType.SET,
        ]) + finalize_encoded + bytes([SYSEX_END])
        self._send_sysex(finalize_msg, debug=debug)
        time.sleep(0.2)

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
        # Slot encoding: big-endian per external sources (garrettjwilke/ep_133_sysex_thingy)
        # Example: slot 11 = 00 0B
        slot_high = (slot >> 7) & 0x7F
        slot_low = slot & 0x7F

        msg = bytes([
            SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, DeviceId.UPLOAD,
            self._next_seq(), CMD_FILE, FIXED_BYTE, FileOp.DELETE,
            slot_high, slot_low, SYSEX_END
        ])

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
        if 'EP-133' in port or 'EP-1320' in port:
            return port
    return None
