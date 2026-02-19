#!/usr/bin/env python3
"""Monitor MIDI SysEx messages to/from EP-133."""
import mido
import sys
from datetime import datetime

def find_ep133():
    for port in mido.get_output_names():
        if 'EP-133' in port or 'EP-1320' in port:
            return port
    return None

def main():
    device = find_ep133()
    if not device:
        print("EP-133 not found")
        sys.exit(1)

    print(f"Monitoring: {device}")
    print("Press Ctrl+C to stop\n")

    try:
        inport = mido.open_input(device)
        for msg in inport:
            if msg.type == 'sysex':
                hex_str = ' '.join(f'{b:02X}' for b in msg.data)
                timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                print(f"[{timestamp}] RX ({len(msg.data)} bytes): {hex_str}")
    except KeyboardInterrupt:
        print("\nStopped")

if __name__ == '__main__':
    main()
