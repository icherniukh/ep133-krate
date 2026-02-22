#!/usr/bin/env python3
"""
Monitor for new backup files and time the download.
"""

import sys
import time
import os
from pathlib import Path

def monitor_downloads():
    """Monitor Downloads folder for new EP-133 backup files."""
    
    downloads = Path.home() / "Downloads"
    
    print("📊 EP-133 Backup Timer")
    print("="*60)
    print(f"Monitoring: {downloads}")
    print("\n💡 Start the backup in the EP Sample Tool now...")
    print("   (This script will detect when the file appears)\n")
    
    # Get initial files
    initial_files = set(downloads.glob("*.zip"))
    
    start_time = time.time()
    last_check = start_time
    
    while True:
        current_files = set(downloads.glob("*.zip"))
        new_files = current_files - initial_files
        
        # Check for EP-133 backup files
        ep_backups = [f for f in new_files if 'ep' in f.name.lower() or 'backup' in f.name.lower()]
        
        if ep_backups:
            elapsed = time.time() - start_time
            backup_file = ep_backups[0]
            size_mb = backup_file.stat().st_size / (1024 * 1024)
            
            print(f"\n✅ Backup detected!")
            print(f"   File: {backup_file.name}")
            print(f"   Size: {size_mb:.2f} MB")
            print(f"   Time: {elapsed:.1f} seconds")
            
            # Wait a bit more to ensure download is complete
            print("\n   Waiting for download to complete...")
            time.sleep(2)
            
            final_size = backup_file.stat().st_size / (1024 * 1024)
            if final_size > size_mb:
                print(f"   Final size: {final_size:.2f} MB")
            
            total_time = time.time() - start_time
            print(f"\n⏱️  Total backup time: {total_time:.1f} seconds")
            
            return backup_file, total_time
        
        # Show progress every 5 seconds
        if time.time() - last_check > 5:
            elapsed = time.time() - start_time
            print(f"   Waiting... ({elapsed:.0f}s)", end='\r')
            last_check = time.time()
        
        time.sleep(0.5)

if __name__ == "__main__":
    try:
        backup_file, duration = monitor_downloads()
        
        print(f"\n{'='*60}")
        print("Summary:")
        print(f"  Backup file: {backup_file}")
        print(f"  Duration: {duration:.1f}s")
        print(f"  Speed: {(backup_file.stat().st_size / (1024 * 1024)) / duration:.2f} MB/s")
        
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled")
