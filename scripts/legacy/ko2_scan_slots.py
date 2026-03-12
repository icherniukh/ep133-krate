#!/usr/bin/env python3
"""
Scan all EP-133 slots to find which ones contain samples.
"""

import sys
import time
from pathlib import Path

try:
    import mido
except ImportError:
    print("Error: mido library not installed")
    sys.exit(1)

from core.models import (
    SysExCmd, RspCmd,
    HDR_TE, END,
    PAT_META_REQ, E_EMPTY,
    MAX_SLOTS,
    encode_slot, build_sysex, parse_json_from_sysex
)


def find_ep133():
    """Find EP-133 MIDI port."""
    for port in mido.get_output_names():
        if 'EP-133' in port:
            return port
    return None


def query_slot(outport, inport, slot):
    """Query a single slot for metadata."""
    slot_high, slot_low = encode_slot(slot)

    # Build metadata request
    req_data = bytes([
        SysExCmd.GET_META,
        slot & 0x7F,
    ]) + PAT_META_REQ + bytes([slot_high, slot_low]) + E_EMPTY

    outport.send(mido.Message('sysex', data=build_sysex(req_data)[1:-1]))
    time.sleep(0.05)

    # Check for response
    for msg in inport.iter_pending():
        if msg.type == 'sysex':
            data = list(msg.data)
            if len(data) > 10 and data[0] == 0xF0 and data[5] == RspCmd.META:
                metadata = parse_json_from_sysex(data)
                if metadata:
                    name = metadata.get('sym', 'unnamed')
                    return name

    return None


def scan_slots():
    """Scan slots to find samples."""
    port_name = find_ep133()
    if not port_name:
        print("❌ EP-133 not found")
        return False

    print(f"🔍 Scanning EP-133 for samples...")
    print(f"{'='*60}\n")

    outport = mido.open_output(port_name)
    inport = mido.open_input(port_name)

    try:
        found = []
        # Scan first 100 slots (common range)
        for slot in range(1, 101):
            name = query_slot(outport, inport, slot)
            if name:
                found.append((slot, name))
                print(f"  Slot {slot:03d}: {name}")

        print(f"\n{'='*60}")
        print(f"✅ Found {len(found)} samples in slots 1-100")

        if found:
            print(f"\nPopulated slots:")
            for slot, name in found:
                print(f"  {slot:03d}: {name}")

        return True

    finally:
        outport.close()
        inport.close()


if __name__ == "__main__":
    success = scan_slots()
    sys.exit(0 if success else 1)
