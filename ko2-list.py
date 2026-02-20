#!/usr/bin/env python3
"""
List all samples from EP-133 backup (.pak file).
"""

import sys
import zipfile
import json
from pathlib import Path
import wave

def get_wav_info(wav_path):
    """Get WAV file info."""
    try:
        with wave.open(str(wav_path), 'rb') as w:
            channels = "Mono" if w.getnchannels() == 1 else "Stereo"
            duration = w.getnframes() / w.getframerate()
            size_kb = wav_path.stat().st_size / 1024
            return channels, duration, size_kb
    except:
        return "?", 0, 0

def list_samples(pak_file):
    """List all samples from backup."""
    print(f"📊 EP-133 Backup Analysis\n")
    print(f"File: {pak_file.name}")
    print(f"Size: {pak_file.stat().st_size / (1024*1024):.1f} MB\n")
    
    # Extract to temp
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        with zipfile.ZipFile(pak_file, 'r') as z:
            z.extractall(tmppath)
        
        # Read metadata
        meta_file = tmppath / "meta.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text())
            print(f"Device: {meta.get('device_name')} v{meta.get('device_version')}")
            print(f"Backup: {meta.get('generated_at', 'Unknown')}\n")
        
        # List samples
        sounds_dir = tmppath / "sounds"
        if not sounds_dir.exists():
            print("❌ No sounds directory found")
            return
        
        samples = sorted(sounds_dir.glob("*.wav"))
        
        print(f"{'='*80}")
        print(f"{'Slot':<6} {'Name':<40} {'Size':<8} {'Type':<8} {'Duration'}")
        print(f"{'='*80}")
        
        total_size = 0
        for sample in samples:
            # Extract slot number from filename (format: "NNN name.wav")
            filename = sample.name
            
            # Slot is first 3 digits
            if len(filename) >= 3 and filename[:3].isdigit():
                slot = filename[:3]
                # Name is everything after "NNN "
                name = filename[4:-4] if len(filename) > 4 else filename[:-4]
            else:
                slot = "???"
                name = filename[:-4]
            
            channels, duration, size_kb = get_wav_info(sample)
            total_size += size_kb
            
            print(f"{slot:<6} {name[:40]:<40} {size_kb:>6.1f}KB {channels:<8} {duration:>5.2f}s")
        
        print(f"{'='*80}")
        print(f"\n📈 Summary:")
        print(f"   Total samples: {len(samples)}")
        print(f"   Total size: {total_size/1024:.1f} MB")
        print(f"   Empty slots: {999 - len(samples)}")
        print(f"   Memory used: {(total_size/1024) / 128 * 100:.1f}%")

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ['-h', '--help', 'help']:
        print("""ko2-list - List samples from EP-133 backup

Usage: ko2-list <backup.pak>

Displays all samples in the backup with:
  - Slot number (001-999)
  - Sample name
  - File size
  - Type (Mono/Stereo)
  - Duration
  - Memory usage statistics

Example:
  ko2-list "My Backup.pak"
  ko2-list ~/Downloads/backup.pak
""")
        sys.exit(0 if len(sys.argv) > 1 else 1)
    
    pak_file = Path(sys.argv[1])
    if not pak_file.exists():
        print(f"❌ File not found: {pak_file}")
        sys.exit(1)
    
    list_samples(pak_file)
