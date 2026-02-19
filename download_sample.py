#!/usr/bin/env python3
"""
Download sample from specific slot.
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

def download_sample(slot):
    port_name = find_ep133()
    if not port_name:
        print("❌ EP-133 not found")
        return
    
    print(f"🔽 Attempting to download sample from slot {slot:03d}...\n")
    
    outport = mido.open_output(port_name)
    inport = mido.open_input(port_name)
    
    # Encode slot for MIDI (7-bit chunks)
    slot_low = slot & 0x7F
    slot_high = (slot >> 7) & 0x7F
    
    # Try command 0x75 (metadata)
    print(f"Requesting metadata (cmd 0x75)...")
    outport.send(mido.Message('sysex', data=[
        0x00, 0x20, 0x76, 0x33, 0x40, 0x75, slot_high, slot_low
    ]))
    time.sleep(0.5)
    
    responses = []
    for msg in inport.iter_pending():
        if msg.type == 'sysex':
            data = list(msg.data)
            responses.append(data)
            print(f"✅ Response: {len(data)} bytes")
            
            if len(data) > 20:
                # Show hex
                print(f"Hex: {' '.join(f'{b:02x}' for b in data[:40])}")
                # Show ASCII
                ascii_view = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[:80])
                print(f"ASCII: {ascii_view}")
    
    # Try command 0x76 (data)
    print(f"\nRequesting data (cmd 0x76)...")
    outport.send(mido.Message('sysex', data=[
        0x00, 0x20, 0x76, 0x33, 0x40, 0x76, slot_high, slot_low
    ]))
    time.sleep(0.5)
    
    for msg in inport.iter_pending():
        if msg.type == 'sysex':
            data = list(msg.data)
            responses.append(data)
            print(f"✅ Response: {len(data)} bytes")
            
            if len(data) > 20:
                print(f"Hex: {' '.join(f'{b:02x}' for b in data[:40])}")
                ascii_view = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[:80])
                print(f"ASCII: {ascii_view}")
    
    outport.close()
    inport.close()
    
    if not responses or all(len(r) <= 10 for r in responses):
        print("\n❌ No sample data received (slot may be empty or command incorrect)")
    else:
        print(f"\n✅ Got {len(responses)} responses")

if __name__ == "__main__":
    slot = int(sys.argv[1]) if len(sys.argv) > 1 else 724
    download_sample(slot)
