#!/usr/bin/env python3
"""
Send various query commands to EP-133 to discover what we can read.
Based on reverse engineering from garrettjwilke's work.
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

def send_and_listen(outport, inport, message, description, wait_time=0.5):
    """Send a SysEx message and listen for response."""
    print(f"\n{'='*60}")
    print(f"Test: {description}")
    print(f"Sending: {list(message.data)}")
    
    outport.send(message)
    time.sleep(wait_time)
    
    responses = []
    for msg in inport.iter_pending():
        responses.append(msg)
        if msg.type == 'sysex':
            data = list(msg.data)
            print(f"✅ Response: {data[:30]}{'...' if len(data) > 30 else ''}")
            print(f"   Length: {len(data)} bytes")
        else:
            print(f"✅ Response: {msg}")
    
    if not responses:
        print("❌ No response")
    
    return responses

def probe_device():
    """Try various commands to discover readable data."""
    port_name = find_ep133()
    
    if not port_name:
        print("❌ EP-133 not found")
        return
    
    print(f"🎹 Probing EP-133...\n")
    
    try:
        outport = mido.open_output(port_name)
        inport = mido.open_input(port_name)
        
        # Test 1: Device Identity (we know this works)
        send_and_listen(
            outport, inport,
            mido.Message('sysex', data=[0x7E, 0x7F, 0x06, 0x01]),
            "Device Identity Request"
        )
        
        # Test 2: Teenage Engineering manufacturer ID query
        # Format: F0 00 20 76 [device] [command] F7
        send_and_listen(
            outport, inport,
            mido.Message('sysex', data=[0x00, 0x20, 0x76, 0x00, 0x01]),
            "TE Device Query (command 0x01)"
        )
        
        # Test 3: Try to query sample list
        send_and_listen(
            outport, inport,
            mido.Message('sysex', data=[0x00, 0x20, 0x76, 0x00, 0x10]),
            "Sample List Query (command 0x10)"
        )
        
        # Test 4: Try to query memory status
        send_and_listen(
            outport, inport,
            mido.Message('sysex', data=[0x00, 0x20, 0x76, 0x00, 0x20]),
            "Memory Status Query (command 0x20)"
        )
        
        # Test 5: Try to query current project
        send_and_listen(
            outport, inport,
            mido.Message('sysex', data=[0x00, 0x20, 0x76, 0x00, 0x30]),
            "Current Project Query (command 0x30)"
        )
        
        # Test 6: Try various other command bytes
        for cmd in [0x02, 0x03, 0x04, 0x05, 0x11, 0x12, 0x21, 0x31]:
            send_and_listen(
                outport, inport,
                mido.Message('sysex', data=[0x00, 0x20, 0x76, 0x00, cmd]),
                f"Probe command 0x{cmd:02X}",
                wait_time=0.3
            )
        
        print(f"\n{'='*60}")
        print("✅ Probe complete!")
        print("\nNote: The official sample tool uses a web interface.")
        print("We may need to analyze the tool's JavaScript to find commands.")
        
        outport.close()
        inport.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    probe_device()
