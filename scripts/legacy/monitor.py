#!/usr/bin/env python3
"""
Monitor all SysEx messages from EP-133.
Use this to reverse engineer what data we can read.
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
        if "EP-133" in port or "EP133" in port:
            return port
    return None


def monitor_messages(duration=30):
    """Listen to all messages from EP-133."""
    port_name = find_ep133()

    if not port_name:
        print("❌ EP-133 not found")
        return

    print(f"🎹 Monitoring EP-133 for {duration} seconds...")
    print("💡 Try these actions on the device:")
    print("   - Press pads")
    print("   - Switch projects")
    print("   - Load/delete samples")
    print("   - Change settings")
    print("\nListening...\n")

    try:
        inport = mido.open_input(port_name)
        outport = mido.open_output(port_name)

        start_time = time.time()
        message_count = 0

        while time.time() - start_time < duration:
            for msg in inport.iter_pending():
                message_count += 1
                timestamp = time.time() - start_time

                print(f"[{timestamp:.2f}s] {msg.type}", end="")

                if msg.type == "sysex" or msg.type == "SysEx":
                    data = list(msg.data)
                    print(f" | Length: {len(data)}")
                    print(
                        f"         Data: {data[:20]}{'...' if len(data) > 20 else ''}"
                    )

                    # Try to identify message type
                    if len(data) > 2:
                        if data[0] == 0x7E:
                            print(f"         Type: Universal SysEx")
                        elif data[0] == 0x00 and data[1] == 0x20 and data[2] == 0x76:
                            print(f"         Type: Teenage Engineering message")
                else:
                    print(f" | {msg}")

                print()

            time.sleep(0.01)

        print(f"\n📊 Total messages captured: {message_count}")

        inport.close()
        outport.close()

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Monitor EP-133 MIDI messages")
    parser.add_argument(
        "-t", "--time", type=int, default=30, help="Duration in seconds (default: 30)"
    )
    args = parser.parse_args()

    monitor_messages(args.time)
