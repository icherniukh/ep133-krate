#!/usr/bin/env python3
"""
Optimize all samples in EP-133 backup using audio2ko2.
"""

import sys
import zipfile
import json
import subprocess
import tempfile
from pathlib import Path

def optimize_backup(pak_file, output_file):
    """Optimize all samples in backup."""
    print(f"🔧 Optimizing EP-133 backup...\n")
    print(f"Input:  {pak_file.name}")
    print(f"Output: {output_file.name}\n")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        extract_dir = tmppath / "extracted"
        optimized_dir = tmppath / "optimized"
        
        extract_dir.mkdir()
        optimized_dir.mkdir()
        
        # Extract backup
        print("📦 Extracting backup...")
        with zipfile.ZipFile(pak_file, 'r') as z:
            z.extractall(extract_dir)
        
        # Copy structure
        (optimized_dir / "projects").mkdir()
        (optimized_dir / "sounds").mkdir()
        
        # Copy metadata
        meta_file = extract_dir / "meta.json"
        if meta_file.exists():
            (optimized_dir / "meta.json").write_text(meta_file.read_text())
        
        # Copy projects
        for proj in (extract_dir / "projects").glob("*.tar"):
            (optimized_dir / "projects" / proj.name).write_bytes(proj.read_bytes())
        
        # Optimize samples
        sounds_dir = extract_dir / "sounds"
        samples = sorted(sounds_dir.glob("*.wav"))
        
        print(f"🎵 Optimizing {len(samples)} samples...\n")
        
        total_before = 0
        total_after = 0
        optimized_count = 0
        
        for i, sample in enumerate(samples, 1):
            print(f"[{i}/{len(samples)}] {sample.name[:50]}", end="... ", flush=True)
            
            size_before = sample.stat().st_size
            total_before += size_before
            
            # Run audio2ko2
            output_path = optimized_dir / "sounds" / sample.name
            
            try:
                result = subprocess.run(
                    ["/Users/ivan/proj/dotfiles-stow/scripts/.scripts/audio2ko2", 
                     str(sample)],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                # Find the generated .wav file
                generated = sample.parent / f"{sample.stem}_ko2.wav"
                if generated.exists():
                    # Move to optimized location with original name
                    output_path.write_bytes(generated.read_bytes())
                    generated.unlink()
                    
                    size_after = output_path.stat().st_size
                    total_after += size_after
                    
                    saved = size_before - size_after
                    if saved > 0:
                        print(f"✅ -{saved/1024:.1f}KB")
                        optimized_count += 1
                    else:
                        print(f"✅ +{-saved/1024:.1f}KB")
                else:
                    # Copy original if conversion failed
                    output_path.write_bytes(sample.read_bytes())
                    total_after += size_before
                    print("⚠️  kept original")
                
                # Clean up backup file
                backup_file = sample.parent / f"{sample.name}.bak"
                if backup_file.exists():
                    backup_file.unlink()
                    
            except Exception as e:
                print(f"❌ {e}")
                # Copy original on error
                output_path.write_bytes(sample.read_bytes())
                total_after += size_before
        
        # Create optimized backup
        print(f"\n📦 Creating optimized backup...")
        with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as z:
            # Add metadata
            z.write(optimized_dir / "meta.json", "meta.json")
            
            # Add projects
            for proj in (optimized_dir / "projects").glob("*.tar"):
                z.write(proj, f"projects/{proj.name}")
            
            # Add sounds
            for sound in (optimized_dir / "sounds").glob("*.wav"):
                z.write(sound, f"sounds/{sound.name}")
        
        # Summary
        print(f"\n{'='*60}")
        print(f"📊 Optimization Summary")
        print(f"{'='*60}")
        print(f"Samples processed: {len(samples)}")
        print(f"Samples optimized: {optimized_count}")
        print(f"Original size: {total_before/1024/1024:.1f} MB")
        print(f"Optimized size: {total_after/1024/1024:.1f} MB")
        print(f"Space saved: {(total_before-total_after)/1024/1024:.1f} MB ({(total_before-total_after)/total_before*100:.1f}%)")
        print(f"\n✅ Optimized backup saved: {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ['-h', '--help', 'help']:
        print("""ko2-optimize - Optimize EP-133 backup samples

Usage: ko2-optimize <input.pak> [output.pak]

Optimizes all samples in backup using audio2ko2:
  - Converts to 46.875 kHz, 16-bit, mono WAV
  - Shows progress for each sample
  - Displays before/after statistics
  - Creates new optimized backup

If output.pak not specified, creates:
  input_optimized.pak

Example:
  ko2-optimize "My Backup.pak"
  ko2-optimize old.pak new.pak

Note: Requires audio2ko2 to be installed
""")
        sys.exit(0 if len(sys.argv) > 1 else 1)
    
    input_pak = Path(sys.argv[1])
    if not input_pak.exists():
        print(f"❌ File not found: {input_pak}")
        sys.exit(1)
    
    output_pak = Path(sys.argv[2]) if len(sys.argv) > 2 else input_pak.parent / f"{input_pak.stem}_optimized.pak"
    
    optimize_backup(input_pak, output_pak)
