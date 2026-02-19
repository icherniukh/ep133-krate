#!/usr/bin/env python3
"""
Monitor all MIDI traffic to/from EP-133.
Logs all SysEx messages to understand backup protocol.
"""

import sys
import time
from datetime import datetime

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

def log_message(direction, msg, data=None):
    """Log MIDI message with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    
    if msg.type == 'sysex':
        data_bytes = list(msg.data) if data is None else data
        
        # Identify message type
        msg_type = "Unknown"
        if len(data_bytes) > 5:
            if data_bytes[0:3] == [0x00, 0x20, 0x76]:  # TE manufacturer
                if data_bytes[3] == 0x33 and data_bytes[4] == 0x40:  # EP-133
                    cmd = data_bytes[5]
                    msg_type = {
                        0x77: "Device Info",
                        0x7E: "Delete/Upload",
                        0x7C: "Switch Project",
                        0x75: "Query Sample?",
                        0x76: "Get Sample?",
                        0x6C: "Upload Sample",
                        0x7D: "Unknown Tool Cmd",
                    }.get(cmd, f"Command 0x{cmd:02X}")
        
        # Format output
        print(f"[{timestamp}] {direction} SysEx ({len(data_bytes)} bytes) - {msg_type}")
        
        # Show first 20 bytes
        hex_str = ' '.join(f'{b:02x}' for b in data_bytes[:20])
        if len(data_bytes) > 20:
            hex_str += f" ... (+{len(data_bytes)-20} bytes)"
        print(f"           {hex_str}")
        
        # Try to find ASCII strings
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data_bytes[:40])
        if any(c != '.' for c in ascii_str):
            print(f"           ASCII: {ascii_str}")
        
        print()
    else:
        print(f"[{timestamp}] {direction} {msg.type}: {msg}")

def monitor():
    """Monitor all MIDI traffic."""
    port_name = find_ep133()
    if not port_name:
        print("❌ EP-133 not found")
        return
    
    print(f"🎹 Monitoring MIDI traffic on: {port_name}")
    print("="*70)
    print("💡 Now use the EP Sample Tool to trigger a backup")
    print("   Watch for SysEx messages that might trigger download")
    print("="*70)
    print()
    
    try:
        inport = mido.open_input(port_name)
        outport = mido.open_output(port_name)
        
        # Monitor incoming messages
        while True:
            for msg in inport.iter_pending():
                log_message("← IN ", msg)
            
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        print("\n\n✅ Monitoring stopped")
    finally:
        inport.close()
        outport.close()

if __name__ == "__main__":
    monitor()
