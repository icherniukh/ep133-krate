#!/usr/bin/env python3
"""
Decode sample list and memory info from EP-133.
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

def decode_response(data, name):
    print(f"\n{'='*60}")
    print(f"{name}")
    print(f"{'='*60}")
    print(f"Length: {len(data)} bytes")
    print(f"Hex: {' '.join(f'{b:02x}' for b in data[:40])}")
    if len(data) > 40:
        print(f"     ... ({len(data)-40} more bytes)")
    
    # Try to find ASCII strings
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
    if any(c != '.' for c in ascii_str):
        print(f"ASCII: {ascii_str[:80]}")
    
    return data

def query_device():
    port_name = find_ep133()
    if not port_name:
        print("❌ EP-133 not found")
        return
    
    print("📊 Querying EP-133 device information...\n")
    
    outport = mido.open_output(port_name)
    inport = mido.open_input(port_name)
    
    # Query 1: List samples (0x79)
    print("Sending: List samples command...")
    outport.send(mido.Message('sysex', data=[0x00, 0x20, 0x76, 0x33, 0x40, 0x79, 0x00, 0x00]))
    time.sleep(0.5)
    
    for msg in inport.iter_pending():
        if msg.type == 'sysex':
            decode_response(list(msg.data), "📋 Sample List Response")
    
    # Query 2: Memory info (0x7A)
    print("\nSending: Memory info command...")
    outport.send(mido.Message('sysex', data=[0x00, 0x20, 0x76, 0x33, 0x40, 0x7A, 0x00, 0x00]))
    time.sleep(0.3)
    
    for msg in inport.iter_pending():
        if msg.type == 'sysex':
            decode_response(list(msg.data), "💾 Memory Info Response")
    
    # Query 3: Sample count (0x7B)
    print("\nSending: Sample count command...")
    outport.send(mido.Message('sysex', data=[0x00, 0x20, 0x76, 0x33, 0x40, 0x7B, 0x00, 0x00]))
    time.sleep(0.3)
    
    for msg in inport.iter_pending():
        if msg.type == 'sysex':
            decode_response(list(msg.data), "🔢 Sample Count Response")
    
    outport.close()
    inport.close()

if __name__ == "__main__":
    query_device()
