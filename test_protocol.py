#!/usr/bin/env python3
"""
Test EP-133 commands with correct protocol format.
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
        if 'EP-133' in port or 'EP133' in port:
            return port
    return None

def send_command(outport, inport, data, description):
    """Send SysEx and wait for response."""
    print(f"\n{description}")
    print(f"Sending: {[hex(b) for b in data]}")
    
    msg = mido.Message('sysex', data=data)
    outport.send(msg)
    time.sleep(0.5)
    
    for response in inport.iter_pending():
        if response.type == 'sysex':
            print(f"✅ Response: {[hex(b) for b in response.data[:20]]}")
            return response
    
    print("❌ No response")
    return None

def test_protocol():
    port_name = find_ep133()
    if not port_name:
        print("❌ EP-133 not found")
        return
    
    print(f"🎹 Testing EP-133 protocol...\n")
    
    outport = mido.open_output(port_name)
    inport = mido.open_input(port_name)
    
    # Test 1: Device info (from get_device_info.syx)
    send_command(
        outport, inport,
        [0x00, 0x20, 0x76, 0x33, 0x40, 0x77, 0x14, 0x01],
        "📋 Get Device Info"
    )
    
    # Test 2: Device identity (we know this works)
    send_command(
        outport, inport,
        [0x7E, 0x7F, 0x06, 0x01],
        "🆔 Device Identity"
    )
    
    outport.close()
    inport.close()
    
    print("\n✅ Test complete!")

if __name__ == "__main__":
    test_protocol()
