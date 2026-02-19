#!/usr/bin/env python3
"""Capture all MIDI SysEx traffic to/from EP-133 by monkey-patching mido."""
import mido
import sys
from datetime import datetime

_original_send = None

def find_ep133():
    for port in mido.get_output_names():
        if 'EP-133' in port or 'EP-1320' in port:
            return port
    return None

def instrumented_send(self, msg):
    """Instrumented send that logs SysEx messages."""
    if hasattr(msg, 'type') and msg.type == 'sysex':
        hex_str = ' '.join(f'{b:02X}' for b in msg.data)
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        print(f"[{timestamp}] TX ({len(msg.data)} bytes): F0 {hex_str} F7")
    return _original_send(self, msg)

def main():
    global _original_send

    device = find_ep133()
    if not device:
        print("EP-133 not found")
        sys.exit(1)

    print(f"Capturing traffic for: {device}")
    print("Press Ctrl+C to stop\n")
    print("Open EP-133 Sample Tool app to capture upload traffic...\n")

    # Monkey-patch the Output.send method
    from mido.ports import Output
    _original_send = Output.send
    Output.send = instrumented_send

    try:
        # Also monitor incoming messages
        inport = mido.open_input(device)
        for msg in inport:
            if msg.type == 'sysex':
                hex_str = ' '.join(f'{b:02X}' for b in msg.data)
                timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                print(f"[{timestamp}] RX ({len(msg.data)} bytes): F0 {hex_str} F7")
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        Output.send = _original_send

if __name__ == '__main__':
    main()
