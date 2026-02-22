#!/usr/bin/env python3
"""
Decode sample metadata from EP-133.
"""

import sys
import time

try:
    import mido
except ImportError:
    print("Error: mido library not installed")
    sys.exit(1)

def find_ep133():
    for port in mido.get_output_names():
        if 'EP-133' in port:
            return port
    return None

def decode_sample_data(data):
    """Decode sample metadata."""
    print(f"\nRaw data ({len(data)} bytes):")
    print(' '.join(f'{b:02x}' for b in data[:80]))
    
    # Try to extract ASCII strings
    ascii_parts = []
    current = []
    for b in data:
        if 32 <= b < 127:
            current.append(chr(b))
        else:
            if current:
                ascii_parts.append(''.join(current))
                current = []
    if current:
        ascii_parts.append(''.join(current))
    
    print(f"\nASCII strings found:")
    for s in ascii_parts:
        if len(s) > 2:
            print(f"  '{s}'")
    
    # Full ASCII view
    ascii_view = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
    print(f"\nFull ASCII view:")
    print(ascii_view)

def scan_slots():
    port_name = find_ep133()
    if not port_name:
        print("❌ EP-133 not found")
        return
    
    print("📊 Scanning EP-133 sample slots...\n")
    
    outport = mido.open_output(port_name)
    inport = mido.open_input(port_name)
    
    occupied_slots = []
    
    # Scan first 20 slots
    for slot in range(1, 21):
        print(f"\rScanning slot {slot:03d}...", end='', flush=True)
        
        # Request metadata
        outport.send(mido.Message('sysex', data=[
            0x00, 0x20, 0x76, 0x33, 0x40, 0x75, 0x00, slot
        ]))
        time.sleep(0.1)
        
        for msg in inport.iter_pending():
            if msg.type == 'sysex':
                data = list(msg.data)
                if len(data) > 20:  # Has actual data
                    occupied_slots.append((slot, data))
    
    print(f"\n\n{'='*60}")
    print(f"Found {len(occupied_slots)} occupied slots")
    print(f"{'='*60}")
    
    for slot, data in occupied_slots:
        print(f"\n🎵 Slot {slot:03d}:")
        decode_sample_data(data)
    
    outport.close()
    inport.close()

if __name__ == "__main__":
    scan_slots()
