#!/usr/bin/env python3
"""
Monitor for new backup files and time the download.
Watches the Downloads folder for new .pak files.
"""

import sys
import time
from pathlib import Path

def monitor_backup(output_dir):
    """Monitor Downloads folder for new EP-133 backup files."""
    
    downloads = Path.home() / "Downloads"
    output_path = Path(output_dir)
    
    print("⏱️  EP-133 Backup Timer")
    print("="*60)
    print(f"Monitoring: {downloads}")
    print(f"Will copy to: {output_path}")
    print("\n💡 Start the backup in the EP Sample Tool now...")
    print("   (This script will detect when the file appears)\n")
    
    # Get initial files
    initial_files = set(downloads.glob("*.pak"))
    
    start_time = time.time()
    last_check = start_time
    
    try:
        while True:
            current_files = set(downloads.glob("*.pak"))
            new_files = current_files - initial_files
            
            if new_files:
                elapsed = time.time() - start_time
                backup_file = sorted(new_files, key=lambda x: x.stat().st_mtime)[-1]  # Most recent
                
                print(f"\n✅ Backup detected!")
                print(f"   File: {backup_file.name}")
                
                # Wait for download to complete
                print(f"   Waiting for download to complete...", end="", flush=True)
                time.sleep(2)
                
                prev_size = 0
                stable_count = 0
                while stable_count < 3:
                    current_size = backup_file.stat().st_size
                    if current_size == prev_size:
                        stable_count += 1
                    else:
                        stable_count = 0
                    prev_size = current_size
                    time.sleep(0.5)
                    print(".", end="", flush=True)
                
                print(" done!")
                
                size_mb = backup_file.stat().st_size / (1024 * 1024)
                total_time = time.time() - start_time
                
                print(f"   Size: {size_mb:.2f} MB")
                print(f"   Time: {total_time:.1f} seconds")
                
                # Copy to output directory
                dest = output_path / backup_file.name
                dest.write_bytes(backup_file.read_bytes())
                print(f"   Copied to: {dest}")
                
                print(f"\n{'='*60}")
                print(f"📊 Summary")
                print(f"{'='*60}")
                print(f"Backup file: {backup_file.name}")
                print(f"Size: {size_mb:.2f} MB")
                print(f"Duration: {total_time:.1f}s")
                print(f"Speed: {size_mb / total_time:.2f} MB/s")
                
                return dest, total_time
            
            # Show progress every 5 seconds
            if time.time() - last_check > 5:
                elapsed = time.time() - start_time
                print(f"   Waiting... ({elapsed:.0f}s)", end='\r', flush=True)
                last_check = time.time()
            
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled")
        sys.exit(1)

if __name__ == "__main__":
    output_dir = sys.argv[1] if len(sys.argv) > 1 else "./tmp"
    monitor_backup(output_dir)
