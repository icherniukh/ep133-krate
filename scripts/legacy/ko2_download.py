#!/usr/bin/env python3
"""
Download sample from EP-133 device using FILE_GET protocol.

Protocol (from PROTOCOL.md):
1. Initialize device (identity request + handshake + file init)
2. Query metadata (0x05 0x07 0x02 GET_METADATA)
3. Trigger download (0x05 0x00 0x03 FILE_GET_INIT)
4. Receive chunks (0x21 → 0x22 → ... → 0x26 progression)
5. Decode 7-bit encoded data
6. Save as WAV (46875 Hz, 16-bit, mono)

Reference: ~/repos/ep_133_sample_tool/PROTOCOL.md
"""

import sys
import time
import struct
from pathlib import Path

try:
    import mido
except ImportError:
    print("Error: mido library not installed")
    sys.exit(1)

from ko2_models import (
    SysExCmd, RspCmd,
    END, DeviceId, FileOp, GetType, MetaType,
    PAT_META_REQ, E_EMPTY,
    SAMPLE_RATE, BIT_DEPTH, CHANNELS, MAX_SLOTS,
    encode_slot, encode_slot_be, decode_slot, build_sysex, parse_json_from_sysex,
    CMD_FILE, FIXED_BYTE, TE_MFG_ID, DEVICE_FAMILY, SYSEX_START, SYSEX_END
)


# --- 7-bit Encoding for MIDI SysEx ---

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
            # Handle remaining partial chunk
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


def find_ep133():
    """Find EP-133 MIDI port."""
    for port in mido.get_output_names():
        if 'EP-133' in port:
            return port
    return None


def query_metadata(outport, inport, slot):
    """Query sample metadata using GET_META command."""
    print(f"📋 Querying metadata for slot {slot}...", end=" ", flush=True)

    # Encode slot
    slot_high, slot_low = encode_slot(slot)

    # Build metadata request: CMD_GET_META [slot] PAT_META_REQ [high] [low] E_EMPTY
    req_data = bytes([
        SysExCmd.GET_META,        # 0x75
        slot & 0x7F,              # Slot byte 1
    ]) + PAT_META_REQ + bytes([slot_high, slot_low]) + E_EMPTY

    outport.send(mido.Message('sysex', data=build_sysex(req_data)[1:-1]))
    time.sleep(0.3)

    # Collect response (expecting RspCmd.META = 0x35)
    metadata = None
    for msg in inport.iter_pending():
        if msg.type == 'sysex':
            data = list(msg.data)
            # Response (after F0): 00 20 76 33 40 RspCmd.META [slot] ...
            # mido strips F0/F7, so data starts at offset 0 with the header
            if len(data) > 10 and data[5] == RspCmd.META:
                # Reconstruct full message for parse_json_from_sysex
                # Try offset 8 first (current format), then 10 (old format)
                full_data = [0xF0] + data + [0xF7]
                metadata = parse_json_from_sysex(full_data, offset=8)
                if not metadata:
                    metadata = parse_json_from_sysex(full_data, offset=10)
                break

    if metadata:
        print(f"✅")
        print(f"   Name: {metadata.get('name', metadata.get('sym', 'N/A'))}")
        print(f"   Sample rate: {metadata.get('samplerate', 'N/A')}")
        print(f"   Format: {metadata.get('format', 'N/A')}")
    else:
        print(f"❌ No metadata (slot may be empty)")

    return metadata


def download_sample_data(outport, inport, slot):
    """Download sample data using FILE_GET protocol.

    Message Structure:
    F0 00 20 76 33 40 [DEVID] [SEQ] 05 00 [OP] [SUBOP] [DATA] F7

    Download uses:
    - DEVID: 0x7D (DeviceId.DOWNLOAD)
    - OP: 0x03 (FileOp.GET)
    - SUBOP: 0x00 (GetType.INIT) or 0x01 (GetType.DATA)

    Protocol:
    1. Send GET INIT: F0 ... 7D [SEQ] 05 00 03 00 [SLOT_HI] [SLOT_LO] [OFFSET*4] F7
    2. Receive file info response
    3. Request pages: F0 ... 7D [SEQ] 05 00 03 01 [PAGE_HI] [PAGE_LO] F7
    4. Receive data chunks until complete
    """
    print(f"🔽 Downloading sample data...")

    # Clear pending messages
    for _ in inport.iter_pending():
        pass

    # Download uses big-endian slot encoding
    slot_high, slot_low = encode_slot_be(slot)  # Big-endian for download

    # Step 1: Send GET INIT request
    seq = 0x2E  # Sequence ID (can be any value 0-127)
    offset = bytes([0x00, 0x00, 0x00, 0x00, 0x00])  # 5-byte offset

    # F0 00 20 76 33 40 7D [SEQ] 05 00 03 00 [SLOT_HI] [SLOT_LO] [OFFSET*5] F7
    init_msg = bytes([
        SYSEX_START,
        *TE_MFG_ID,
        *DEVICE_FAMILY,
        DeviceId.DOWNLOAD,     # 0x7D - download operations
        seq,
        CMD_FILE,              # 0x05 - FILE operations
        FIXED_BYTE,            # 0x00
        FileOp.GET,            # 0x03 - GET operation
        GetType.INIT,          # 0x00 - INIT
        slot_high, slot_low,   # Slot big-endian
    ]) + offset + bytes([SYSEX_END])

    outport.send(mido.Message('sysex', data=init_msg[1:-1]))
    time.sleep(0.3)

    # Step 2: Wait for file info response
    # F0 00 20 76 33 40 37 [SEQ] 05 00 03 00 [FILE_INFO_7BIT] F7
    file_info = None

    # Debug: show all responses
    for msg in inport.iter_pending():
        if msg.type == 'sysex':
            data = list(msg.data)

            # Check for device response with file info
            # Device may respond with different device IDs (0x37, 0x3d observed)
            # Look for .pcm filename in response as indicator of valid file info
            raw_bytes = bytes(data)
            if len(data) > 20 and (b'.pcm' in raw_bytes or b'.PCM' in raw_bytes):
                # Try different starting offsets for 7-bit decode
                # Response structure varies, try finding where data starts
                for start_offset in [9, 10, 11]:
                    encoded_data = bytes(data[start_offset:])
                    decoded = decode_7bit(encoded_data)

                    # Look for filename pattern after decode
                    if b'.pcm' in decoded or b'.PCM' in decoded:

                        # Parse file info structure (after 7-bit decode):
                        # [0-1]: File ID (big-endian)
                        # [2]: Flags
                        # [3-6]: File size (big-endian)
                        # [7+]: Null-terminated filename
                        if len(decoded) >= 7:
                            file_id = (decoded[0] << 8) | decoded[1]
                            flags = decoded[2]
                            file_size = (decoded[3] << 24) | (decoded[4] << 16) | (decoded[5] << 8) | decoded[6]

                            # Extract filename
                            filename_bytes = decoded[7:]
                            filename = ''
                            for b in filename_bytes:
                                if b == 0:
                                    break
                                filename += chr(b)

                            file_info = {
                                'id': file_id,
                                'flags': flags,
                                'size': file_size,
                                'name': filename
                            }
                            print(f"   📦 File: {filename} ({file_size} bytes)")
                        break
            elif len(data) > 10:
                print(f"   [DEBUG] data[5]=0x{data[5]:02x} (expected 0x{DeviceId.RESPONSE:02x} or 0x3d)")
                print(f"   [DEBUG] data[8]=0x{data[8]:02x} (expected 0x{FileOp.GET:02x})")
                # Decode 7-bit data after header
                # Header: 00 20 76 33 40 37 [seq] 05 00 03 00 ...
                encoded_data = bytes(data[10:])  # Skip header
                decoded = decode_7bit(encoded_data)

                # Parse file info structure (after 7-bit decode):
                # [0-1]: File ID (big-endian)
                # [2]: Flags
                # [3-6]: File size (big-endian)
                # [7+]: Null-terminated filename
                if len(decoded) >= 7:
                    file_id = (decoded[0] << 8) | decoded[1]
                    flags = decoded[2]
                    file_size = (decoded[3] << 24) | (decoded[4] << 16) | (decoded[5] << 8) | decoded[6]

                    # Extract filename
                    filename_bytes = decoded[7:]
                    filename = ''
                    for b in filename_bytes:
                        if b == 0:
                            break
                        filename += chr(b)

                    file_info = {
                        'id': file_id,
                        'flags': flags,
                        'size': file_size,
                        'name': filename
                    }
                    print(f"   📦 File: {filename} ({file_size} bytes)")
                break

    if not file_info:
        print(f"   ❌ No file info response")
        return bytes()

    # Step 3: Request data chunks by page number
    all_data = []
    page = 0
    received = 0

    while received < file_info['size']:
        # Clear pending
        for _ in inport.iter_pending():
            pass

        # Build data request
        # F0 00 20 76 33 40 7D [SEQ] 05 00 03 01 [PAGE_HI] [PAGE_LO] F7
        # Use 7-bit encoding for page bytes (MIDI data bytes must be 0-127)
        page_lo = page & 0x7F
        page_hi = (page >> 7) & 0x7F
        seq = (seq + 1) & 0x7F  # Increment sequence

        data_req = bytes([
            SYSEX_START,
            *TE_MFG_ID,
            *DEVICE_FAMILY,
            DeviceId.DOWNLOAD,
            seq,
            CMD_FILE,
            FIXED_BYTE,
            FileOp.GET,
            GetType.DATA,         # 0x01 - DATA request
            page_hi, page_lo,     # Page big-endian
            SYSEX_END
        ])

        outport.send(mido.Message('sysex', data=data_req[1:-1]))
        time.sleep(0.05)

        # Wait for data chunk response
        chunk_received = False
        timeout_counter = 0

        print(f"   [DEBUG] Requesting page {page}...", flush=True)

        while timeout_counter < 50:  # Timeout after ~2.5 seconds
            for msg in inport.iter_pending():
                if msg.type == 'sysex':
                    data = list(msg.data)

                    # Debug: show response for page 0
                    if page == 0 and len(data) > 5:
                        print(f"   [DEBUG] Page response: devid=0x{data[5]:02x}, len={len(data)}")
                        if len(data) < 50:
                            print(f"   [DEBUG] Raw: {' '.join(f'{b:02x}' for b in data[:30])}...")

                    # Accept responses with device ID 0x37 or 0x3d
                    # Response pattern varies - look for valid data after header
                    if len(data) > 12 and data[5] in (DeviceId.RESPONSE, 0x3d):
                        # Try to find data - it may start at different offsets
                        # Look for the pattern: cmd byte 5, seq byte 6, then 05 00 [something]
                        if data[7] == CMD_FILE:
                            # Data chunks start after the response header
                            # Try different offsets based on response type
                            for start_offset in [10, 11, 12, 13]:
                                if start_offset < len(data):
                                    encoded_data = bytes(data[start_offset:])
                                    if encoded_data:
                                        decoded = decode_7bit(encoded_data)
                                        if decoded and len(decoded) > 4:
                                            all_data.extend(decoded)
                                            received += len(decoded)
                                            chunk_received = True

                                            # Progress
                                            pct = min(100, int(received * 100 / file_info['size']))
                                            print(f"   📥 {received}/{file_info['size']} bytes ({pct}%)     ", end='\r', flush=True)
                                            break
                                if chunk_received:
                                    break
                                all_data.extend(decoded)
                                received += len(decoded)
                                chunk_received = True

                                # Progress
                                pct = min(100, int(received * 100 / file_info['size']))
                                print(f"   📥 {received}/{file_info['size']} bytes ({pct}%)     ", end='\r', flush=True)
                        break
            if chunk_received:
                break
            time.sleep(0.05)
            timeout_counter += 1

        if not chunk_received:
            # No more data
            break

        page = (page + 1) & 0x3FFF  # 14-bit max (two 7-bit bytes)

    print()  # New line after progress

    if len(all_data) < 100:
        print(f"   ❌ Download failed - only got {len(all_data)} bytes")
        return bytes()

    print(f"   ✅ Total: {len(all_data)} bytes")
    return bytes(all_data)


def save_wav(data, metadata, output_path):
    """Save downloaded data as WAV file."""
    import wave

    with wave.open(str(output_path), 'wb') as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(BIT_DEPTH // 8)
        wav.setframerate(SAMPLE_RATE)

        # Convert bytes to 16-bit samples
        samples = []
        for i in range(0, len(data) - 1, 2):
            if i + 1 < len(data):
                sample = struct.unpack('<h', bytes([data[i], data[i+1]]))[0]
                samples.append(struct.pack('<h', sample))

        if samples:
            wav.writeframes(b''.join(samples))

    print(f"💾 Saved: {output_path}")


def init_device(outport):
    """Send device initialization sequence."""
    # From ep_133_sysex_thingy/syx/init.syx
    init_messages = [
        bytes([0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7]),  # Universal Device Inquiry
        bytes([0xF0, 0x00, 0x20, 0x76, 0x33, 0x40, 0x61, 0x17, 0x01, 0xF7]),  # TE Init 1
        bytes([0xF0, 0x00, 0x20, 0x76, 0x33, 0x40, 0x61, 0x18, 0x05, 0x00, 0x01, 0x01, 0x00, 0x40, 0x00, 0x00, 0xF7]),  # TE Init 2
    ]

    for msg in init_messages:
        outport.send(mido.Message('sysex', data=msg[1:-1]))
        time.sleep(0.05)


def download_sample(slot, output_file=None):
    """Download sample from device."""
    port_name = find_ep133()
    if not port_name:
        print(f"❌ EP-133 not found")
        return False

    print(f"🎵 EP-133 Sample Downloader")
    print(f"{'='*60}\n")

    outport = mido.open_output(port_name)
    inport = mido.open_input(port_name)

    try:
        # Initialize device
        print(f"🔧 Initializing device...")
        init_device(outport)
        time.sleep(0.2)

        # Step 1: Query metadata
        metadata = query_metadata(outport, inport, slot)
        if not metadata:
            print(f"\n❌ Cannot download from empty slot {slot}")
            return False

        # Step 2: Download sample data
        sample_data = download_sample_data(outport, inport, slot)

        if len(sample_data) < 100:
            print(f"\n❌ Download failed - not enough data received")
            return False

        # Step 3: Save as WAV
        if output_file is None:
            sample_name = metadata.get('sym', f'sample_{slot:03d}')
            output_file = Path(f"{sample_name}_{slot:03d}.wav")
        else:
            output_file = Path(output_file)

        save_wav(sample_data, metadata, output_file)

        print(f"\n✅ Download complete!")
        return True

    finally:
        outport.close()
        inport.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("""ko2_download - Download samples from EP-133

Usage: ko2_download <slot> [output.wav]

Downloads a sample from the specified slot (1-999).

Examples:
  ko2_download 724                    # Auto-generate filename
  ko2_download 724 kick.wav           # Specify output file

Note: Requires EP-133 to be connected via USB
""")
        sys.exit(1)

    slot = int(sys.argv[1])
    if not (1 <= slot <= MAX_SLOTS):
        print(f"❌ Invalid slot number: {slot} (must be 1-{MAX_SLOTS})")
        sys.exit(1)

    output = sys.argv[2] if len(sys.argv) > 2 else None

    success = download_sample(slot, output)
    sys.exit(0 if success else 1)
