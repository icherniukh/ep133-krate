#!/usr/bin/env python3
"""
Test basic MIDI communication with EP-133.
Sends simple queries and listens for responses.
"""

import sys
import time

try:
    import mido
except ImportError:
    print("Error: mido library not installed")
    print("Install with: pip install mido python-rtmidi")
    sys.exit(1)

def find_ep133():
    """Find EP-133 in MIDI ports."""
    for port in mido.get_output_names():
        if 'EP-133' in port or 'EP133' in port:
            return port
    return None

def test_communication():
    """Test basic MIDI communication."""
    port_name = find_ep133()
    
    if not port_name:
        print("❌ EP-133 not found")
        return
    
    print(f"🎹 Connecting to: {port_name}\n")
    
    try:
        # Open input and output ports
        outport = mido.open_output(port_name)
        inport = mido.open_input(port_name)
        
        print("✅ Connected successfully!\n")
        
        # Test 1: Send identity request (standard MIDI)
        print("Test 1: Sending device identity request...")
        identity_request = mido.Message('sysex', data=[0x7E, 0x7F, 0x06, 0x01])
        outport.send(identity_request)
        
        # Listen for response
        print("Listening for response (3 seconds)...")
        start_time = time.time()
        messages_received = 0
        
        while time.time() - start_time < 3:
            for msg in inport.iter_pending():
                messages_received += 1
                print(f"  📨 Received: {msg}")
                if msg.type == 'sysex':
                    print(f"     SysEx data: {list(msg.data)}")
        
        if messages_received == 0:
            print("  ⚠️  No response received")
        
        print(f"\n📊 Total messages received: {messages_received}")
        
        # Close ports
        outport.close()
        inport.close()
        
        print("\n✅ Test complete!")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_communication()
