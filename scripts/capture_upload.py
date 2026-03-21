#!/usr/bin/env python3
"""Upload a WAV to the device while capturing all SysEx traffic to JSONL.

Uses EP133Client's trace_hook for clean capture without monkey-patching.

Usage:
    python3 scripts/capture_upload.py tests/fixtures/kick-46875hz.wav 990
    python3 scripts/capture_upload.py tests/fixtures/kick-46875hz.wav 990 \
        -o captures/sniffer-upload-kick990.jsonl
"""
import argparse
import json
import wave
from datetime import datetime
from pathlib import Path

from core.client import EP133Client, find_device


def _hex(data: bytes) -> str:
    return "".join(f"{b:02X}" for b in data)


def main():
    parser = argparse.ArgumentParser(description="Upload WAV with SysEx capture")
    parser.add_argument("wav", type=Path, help="WAV file to upload")
    parser.add_argument("slot", type=int, help="Target slot number")
    parser.add_argument("--output", "-o", type=Path, help="Output JSONL file")
    parser.add_argument("--name", help="Sample name (default: WAV filename stem)")
    args = parser.parse_args()

    if not args.wav.exists():
        raise SystemExit(f"WAV not found: {args.wav}")

    port = find_device()
    if not port:
        raise SystemExit("EP-133 not found")

    out_path = args.output or Path("captures") / f"sniffer-upload-{args.wav.stem}-slot{args.slot}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    name = args.name or args.wav.stem

    with wave.open(str(args.wav), "rb") as w:
        ch, rate, frames = w.getnchannels(), w.getframerate(), w.getnframes()
    print(f"Uploading: {args.wav.name} ({ch}ch, {rate}Hz, {frames} frames)")
    print(f"Target: slot {args.slot}, name '{name}'")
    print(f"Capture: {out_path}")

    entries = []

    def trace(direction: str, data: bytes):
        entries.append({
            "ts": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "dir": direction,
            "len": len(data),
            "hex": _hex(data),
        })

    with EP133Client(port, trace_hook=trace) as client:
        client.put(args.wav, args.slot, name=name)

    # Filter to only file operation messages (skip init handshake)
    with open(out_path, "w") as f:
        for e in entries:
            f.write(json.dumps(e, separators=(",", ":")) + "\n")

    tx = sum(1 for e in entries if e["dir"] == "TX")
    rx = sum(1 for e in entries if e["dir"] == "RX")
    print(f"Captured {len(entries)} messages ({tx} TX, {rx} RX)")


if __name__ == "__main__":
    main()
