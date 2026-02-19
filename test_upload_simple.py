#!/usr/bin/env python3
"""Test upload with response capture."""
import mido
import time
import wave
import array
from pathlib import Path

SYSEX_START = 0xF0
SYSEX_END = 0xF7
TE_MFG_ID = bytes([0x00, 0x20, 0x76])
DEVICE_FAMILY = bytes([0x33, 0x40])

def find_ep133():
    for port in mido.get_output_names():
        if 'EP-133' in port or 'EP-1320' in port:
            return port
    return None

def main():
    device = find_ep133()
    if not device:
        print("EP-133 not found")
        return

    print(f"Device: {device}")

    outport = mido.open_output(device)
    inport = mido.open_input(device)

    # Create test WAV
    test_path = Path('/tmp/test_probe.wav')
    with wave.open(str(test_path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(46875)
        data = array.array('h', [10000] * 500 + [-10000] * 500)
        wav.writeframes(data.tobytes())

    # Read raw data
    with wave.open(str(test_path), 'rb') as wav:
        raw_data = wav.readframes(wav.getnframes())

    # Send init
    print("Sending init...")
    init1 = bytes([SYSEX_START, 0x7E, 0x7F, 0x06, 0x01, SYSEX_END])
    init2 = bytes([SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, 0x61, 0x17, 0x01, SYSEX_END])
    init3 = bytes([SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, 0x61, 0x18, 0x05, 0x00, 0x01, 0x01, 0x00, 0x40, 0x00, 0x00, SYSEX_END])

    for msg in [init1, init2, init3]:
        outport.send(mido.Message('sysex', data=msg[1:-1]))
        time.sleep(0.1)

    # Clear responses
    for _ in inport.iter_pending():
        pass

    # Test simple upload init for slot 999
    slot = 999
    slot_high = (slot >> 7) & 0x7F  # = 7
    slot_low = slot & 0x7F           # = 75
    seq = 0x13

    # Build upload init exactly as protocol shows
    init_msg = bytes([
        SYSEX_START, *TE_MFG_ID, *DEVICE_FAMILY, 0x6C, seq,  # header with device 0x6C
        0x05, 0x40, 0x02, 0x00, 0x05,  # CMD_FILE, flags, PUT, PUT_INIT, type
        slot_high, slot_low,  # slot in big-endian
    ])

    # Add payload (size + filename + metadata, 7-bit encoded)
    import struct
    import json
    size_bytes = struct.pack('<I', len(raw_data))
    filename = '999_test\0'
    metadata = '{"channels":1}'
    payload = size_bytes + filename.encode() + metadata.encode()

    # 7-bit encode
    def encode_7bit(data):
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

    encoded = encode_7bit(payload)
    init_msg += encoded + bytes([SYSEX_END])

    print(f"Sending upload init ({len(init_msg)} bytes)...")
    outport.send(mido.Message('sysex', data=init_msg[1:-1]))

    # Wait for and capture responses
    time.sleep(0.5)
    responses = list(inport.iter_pending())
    print(f"Received {len(responses)} responses")

    for i, resp in enumerate(responses):
        if resp.type == 'sysex':
            hex_str = ' '.join(f'{b:02X}' for b in resp.data[:40])
            print(f"  Response {i+1}: {hex_str}")

    outport.close()
    inport.close()

if __name__ == '__main__':
    main()
