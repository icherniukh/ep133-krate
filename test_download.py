#!/usr/bin/env python3
"""
Test if we can download individual samples from specific slots.
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

def request_sample(outport, inport, slot):
    """Try to request a sample from a specific slot."""
    print(f"\n{'='*60}")
    print(f"Requesting sample from slot {slot:03d}")
    print(f"{'='*60}")
    
    # Try different command patterns for requesting sample data
    
    # Pattern 1: Request sample metadata
    print(f"Try 1: Request metadata (cmd 0x75)...")
    outport.send(mido.Message('sysex', data=[
        0x00, 0x20, 0x76, 0x33, 0x40, 0x75, 0x00, slot
    ]))
    time.sleep(0.5)
    
    responses = []
    for msg in inport.iter_pending():
        if msg.type == 'sysex':
            data = list(msg.data)
            responses.append(data)
            print(f"  ✅ Got {len(data)} bytes: {data[:20]}")
    
    # Pattern 2: Request sample data
    print(f"Try 2: Request data (cmd 0x76)...")
    outport.send(mido.Message('sysex', data=[
        0x00, 0x20, 0x76, 0x33, 0x40, 0x76, 0x00, slot
    ]))
    time.sleep(0.5)
    
    for msg in inport.iter_pending():
        if msg.type == 'sysex':
            data = list(msg.data)
            responses.append(data)
            print(f"  ✅ Got {len(data)} bytes: {data[:20]}")
    
    # Pattern 3: Get sample info
    print(f"Try 3: Get info (cmd 0x78)...")
    outport.send(mido.Message('sysex', data=[
        0x00, 0x20, 0x76, 0x33, 0x40, 0x78, 0x05, 0x00, slot
    ]))
    time.sleep(0.5)
    
    for msg in inport.iter_pending():
        if msg.type == 'sysex':
            data = list(msg.data)
            responses.append(data)
            print(f"  ✅ Got {len(data)} bytes: {data[:20]}")
    
    if not responses:
        print("  ❌ No responses to any pattern")
    
    return responses

def test_download():
    port_name = find_ep133()
    if not port_name:
        print("❌ EP-133 not found")
        return
    
    print("🔽 Testing sample download from device...\n")
    print("💡 Make sure you have samples loaded in slots 1-5")
    
    outport = mido.open_output(port_name)
    inport = mido.open_input(port_name)
    
    # Test slots 1, 2, and 3
    for slot in [1, 2, 3]:
        request_sample(outport, inport, slot)
    
    outport.close()
    inport.close()
    
    print(f"\n{'='*60}")
    print("Summary:")
    print("If we got large responses (>100 bytes), we can download samples!")
    print("If only small responses (~9 bytes), device doesn't support reads.")

if __name__ == "__main__":
    test_download()
