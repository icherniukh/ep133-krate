#!/usr/bin/env python3
"""
Try downloading with proper init sequence.
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

def send_init(outport, inport):
    """Send init sequence from repo."""
    print("Sending init sequence...")
    
    # Init 1: Device identity
    outport.send(mido.Message('sysex', data=[0x7E, 0x7F, 0x06, 0x01]))
    time.sleep(0.2)
    
    # Init 2
    outport.send(mido.Message('sysex', data=[
        0x00, 0x20, 0x76, 0x33, 0x40, 0x61, 0x17, 0x01
    ]))
    time.sleep(0.2)
    
    # Init 3
    outport.send(mido.Message('sysex', data=[
        0x00, 0x20, 0x76, 0x33, 0x40, 0x61, 0x18, 0x05, 0x00, 0x01, 0x01, 0x00, 0x40, 0x00, 0x00
    ]))
    time.sleep(0.2)
    
    # Clear any responses
    for msg in inport.iter_pending():
        pass
    
    print("✅ Init complete\n")

def download_with_init(slot):
    port_name = find_ep133()
    if not port_name:
        print("❌ EP-133 not found")
        return
    
    print(f"🔽 Downloading slot {slot:03d} with init sequence...\n")
    
    outport = mido.open_output(port_name)
    inport = mido.open_input(port_name)
    
    # Send init
    send_init(outport, inport)
    
    # Encode slot
    slot_low = slot & 0x7F
    slot_high = (slot >> 7) & 0x7F
    
    # Try download command
    print(f"Requesting sample data...")
    outport.send(mido.Message('sysex', data=[
        0x00, 0x20, 0x76, 0x33, 0x40, 0x75, slot_high, slot_low
    ]))
    
    # Wait longer for potential large response
    time.sleep(1.0)
    
    all_data = []
    for msg in inport.iter_pending():
        if msg.type == 'sysex':
            data = list(msg.data)
            all_data.append(data)
            print(f"✅ Got {len(data)} bytes")
            
            if len(data) > 20:
                print(f"   Hex: {' '.join(f'{b:02x}' for b in data[:40])}")
    
    outport.close()
    inport.close()
    
    if not all_data or all(len(d) <= 10 for d in all_data):
        print("\n❌ Still no sample data")
        print("The device likely doesn't support direct sample downloads via SysEx.")
        print("Recommendation: Use backup file approach instead.")
    else:
        print(f"\n✅ Total responses: {len(all_data)}")
        print(f"Total bytes: {sum(len(d) for d in all_data)}")

if __name__ == "__main__":
    slot = int(sys.argv[1]) if len(sys.argv) > 1 else 724
    download_with_init(slot)
