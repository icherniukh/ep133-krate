#!/usr/bin/env python3
"""
Quick scan of all EP-133 slots to find loaded samples.
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

def quick_scan():
    port_name = find_ep133()
    if not port_name:
        print("❌ EP-133 not found")
        return
    
    print("🔍 Quick scanning all 999 slots for samples...")
    print("(This will take ~2 minutes)\n")
    
    outport = mido.open_output(port_name)
    inport = mido.open_input(port_name)
    
    occupied = []
    
    for slot in range(1, 1000):
        if slot % 50 == 0:
            print(f"Progress: {slot}/999 slots scanned... ({len(occupied)} found)")
        
        # Request metadata (encode slot properly for MIDI)
        slot_low = slot & 0x7F
        slot_high = (slot >> 7) & 0x7F
        outport.send(mido.Message('sysex', data=[
            0x00, 0x20, 0x76, 0x33, 0x40, 0x75, slot_high, slot_low
        ]))
        time.sleep(0.05)  # Fast scan
        
        for msg in inport.iter_pending():
            if msg.type == 'sysex':
                data = list(msg.data)
                if len(data) > 20:  # Has data
                    occupied.append(slot)
                    print(f"  ✅ Slot {slot:03d} - {len(data)} bytes")
    
    print(f"\n{'='*60}")
    print(f"📊 Scan complete!")
    print(f"{'='*60}")
    print(f"Occupied slots: {len(occupied)}")
    print(f"Empty slots: {999 - len(occupied)}")
    print(f"Memory used: ~{len(occupied) * 50}KB (estimated)")
    
    if occupied:
        print(f"\nOccupied slot numbers:")
        for i in range(0, len(occupied), 10):
            print(f"  {', '.join(f'{s:03d}' for s in occupied[i:i+10])}")
    
    outport.close()
    inport.close()
    
    return occupied

if __name__ == "__main__":
    quick_scan()
