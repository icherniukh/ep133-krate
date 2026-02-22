#!/usr/bin/env python3
"""
Try to query sample information from EP-133.
Test various commands to see if we can read sample metadata.
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

def send_and_wait(outport, inport, data, desc):
    print(f"\n{desc}")
    msg = mido.Message('sysex', data=data)
    outport.send(msg)
    time.sleep(0.3)
    
    responses = []
    for r in inport.iter_pending():
        if r.type == 'sysex':
            responses.append(list(r.data))
            print(f"✅ Got {len(r.data)} bytes")
    
    if not responses:
        print("❌ No response")
    return responses

def query_samples():
    port_name = find_ep133()
    if not port_name:
        print("❌ EP-133 not found")
        return
    
    print("🔍 Attempting to query sample information...\n")
    
    outport = mido.open_output(port_name)
    inport = mido.open_input(port_name)
    
    # Try various command patterns to query samples
    
    # Pattern 1: Query slot 1
    send_and_wait(outport, inport,
        [0x00, 0x20, 0x76, 0x33, 0x40, 0x78, 0x00, 0x01],
        "Query slot 001 (cmd 0x78)"
    )
    
    # Pattern 2: List samples command
    send_and_wait(outport, inport,
        [0x00, 0x20, 0x76, 0x33, 0x40, 0x79, 0x00, 0x00],
        "List samples (cmd 0x79)"
    )
    
    # Pattern 3: Get memory info
    send_and_wait(outport, inport,
        [0x00, 0x20, 0x76, 0x33, 0x40, 0x7A, 0x00, 0x00],
        "Memory info (cmd 0x7A)"
    )
    
    # Pattern 4: Sample count
    send_and_wait(outport, inport,
        [0x00, 0x20, 0x76, 0x33, 0x40, 0x7B, 0x00, 0x00],
        "Sample count (cmd 0x7B)"
    )
    
    outport.close()
    inport.close()
    
    print("\n" + "="*60)
    print("⚠️  If no responses, the device may not support read operations")
    print("    for sample data. We may need to work with backup files instead.")

if __name__ == "__main__":
    query_samples()
