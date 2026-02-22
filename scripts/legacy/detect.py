#!/usr/bin/env python3
"""
Simple EP-133 KO-II device detection and info script.
Tests basic MIDI communication without modifying anything.
"""

import sys

try:
    import mido
except ImportError:
    print("Error: mido library not installed")
    print("Install with: pip install mido python-rtmidi")
    sys.exit(1)

def find_ep133():
    """Find EP-133 device in available MIDI ports."""
    ports = mido.get_output_names()
    
    for port in ports:
        if 'EP-133' in port or 'EP133' in port:
            return port
    return None

def main():
    print("🎹 EP-133 KO-II Device Scanner\n")
    
    # List all MIDI devices
    print("Available MIDI devices:")
    for port in mido.get_output_names():
        print(f"  - {port}")
    
    print()
    
    # Find EP-133
    ep133_port = find_ep133()
    
    if ep133_port:
        print(f"✅ EP-133 found: {ep133_port}")
        print("\nDevice is ready for communication!")
    else:
        print("❌ EP-133 not found")
        print("\nMake sure:")
        print("  1. Device is powered on")
        print("  2. USB-C cable is connected")
        print("  3. Device is not in use by another application")

if __name__ == "__main__":
    main()
