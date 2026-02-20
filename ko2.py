#!/usr/bin/env python3
"""
KO2 - EP-133 KO-II Command Line Tool

Usage:
    ko2 ls [--page N]          - List samples by pages
    ko2 info <slot|range>      - Show sample metadata
    ko2 get <slot> [file]      - Download sample
    ko2 put <file> <slot>      - Upload sample
    ko2 rm <slot>              - Delete sample
    ko2 squash [--page N]      - Squash samples to fill gaps
    ko2 optimize <slot>        - Optimize single sample
    ko2 optimize-all           - Optimize all oversized samples
"""
import sys
import argparse
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

try:
    from ko2_client import EP133Client, find_device, SampleInfo, EP133Error, SlotEmptyError
    from ko2_protocol import SAMPLE_RATE, MAX_SLOTS
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)


# ANSI colors
class Colors:
    RESET = "\033[0m"
    BRIGHT_GREEN = "\033[48;5;22m"
    GREEN = "\033[48;5;28m"
    YELLOW = "\033[48;5;226m"
    ORANGE = "\033[48;5;208m"
    RED = "\033[48;5;196m"
    BRIGHT_RED = "\033[48;5;88m"
    CYAN = "\033[38;5;39m"
    FG_GRAY = "\033[38;5;245m"
    FG_DIM = "\033[90m"
    FG_GREEN = "\033[38;5;82m"
    FG_YELLOW = "\033[38;5;226m"


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable size."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}K"
    else:
        return f"{size_bytes / (1024 * 1024):.1f}M"


def get_size_color(size_bytes: int) -> str:
    """Get background color based on file size."""
    if size_bytes < 10 * 1024:
        return Colors.BRIGHT_GREEN
    elif size_bytes < 50 * 1024:
        return Colors.GREEN
    elif size_bytes < 100 * 1024:
        return Colors.YELLOW
    elif size_bytes < 200 * 1024:
        return Colors.ORANGE
    elif size_bytes < 500 * 1024:
        return Colors.RED
    else:
        return Colors.BRIGHT_RED


def format_duration(size_bytes: int, samplerate: int = SAMPLE_RATE) -> str:
    """Calculate duration from file size."""
    if size_bytes == 0:
        return "-"
    # 16-bit mono = 2 bytes per sample
    samples = size_bytes // 2
    seconds = samples / samplerate
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    else:
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins}m{secs:.0f}s"


def parse_page(arg: str) -> tuple[int, int] | None:
    """Parse page argument: '1' = slots 1-99, '2' = 100-199, etc."""
    try:
        page = int(arg)
        if not 1 <= page <= 10:
            return None
        start = (page - 1) * 100 + 1
        end = page * 100
        return start, end
    except ValueError:
        return None


def format_table_row(info: SampleInfo) -> str:
    """Format a sample as a table row."""
    size_str = format_size(info.size_bytes) if info.size_bytes else "-"
    color = get_size_color(info.size_bytes) if info.size_bytes else ""
    reset = Colors.RESET if info.size_bytes else ""

    # Stereo indicator
    channels_str = "S" if info.channels == 2 else "M" if info.channels == 1 else "-"
    channels_color = Colors.FG_YELLOW if info.channels == 2 else Colors.FG_DIM

    # Truncate name to fit
    name = info.name[:18]
    if len(info.name) > 18:
        name += "…"

    size_display = f"{color} {size_str:>5} {reset}" if info.size_bytes else f" {size_str:>5} "

    return (
        f"  {Colors.FG_DIM}{info.slot:03d}{Colors.RESET}  "
        f"{name:<18}  "
        f"{channels_color}{channels_str}{Colors.RESET}  "
        f"{size_display}  "
        f"{format_duration(info.size_bytes, info.samplerate):>8}"
    )


def show_progress(current: int, total: int, message: str = ""):
    """Show progress bar."""
    if total <= 0:
        return
    pct = current / total
    bar_len = 30
    filled = int(bar_len * pct)
    bar = "█" * filled + "░" * (bar_len - filled)
    sys.stdout.write(f"\r  {bar} {pct*100:.0f}% {message}")
    sys.stdout.flush()


def cmd_ls(args):
    """List samples by pages."""
    with EP133Client(args.device) as client:
        # Determine range
        if args.page:
            start, end = parse_page(args.page)
            if start is None:
                print("❌ Page must be 1-10")
                return 1
        elif args.all:
            start, end = 1, MAX_SLOTS
        else:
            start, end = 1, 99  # Default to first page

        # Prefer filesystem listing (/sounds/) for ground truth; fall back to slot scan.
        samples = []
        try:
            entries = client.list_directory()
            by_slot = {}
            for e in entries:
                if e.get("is_dir"):
                    continue
                name = str(e.get("name", ""))
                slot = None
                if len(name) >= 3 and name[:3].isdigit():
                    slot = int(name[:3])
                else:
                    node_id = int(e.get("node_id") or 0)
                    if 1000 < node_id <= 1999:
                        slot = node_id - 1000
                if slot is None or not (1 <= slot <= MAX_SLOTS):
                    continue
                if not (start <= slot <= end):
                    continue
                by_slot[slot] = e

            for slot in sorted(by_slot.keys()):
                e = by_slot[slot]
                samples.append(
                    SampleInfo(
                        slot=slot,
                        name=str(e.get("name", f"Slot {slot:03d}")),
                        samplerate=SAMPLE_RATE,
                        channels=1,
                        size_bytes=int(e.get("size") or 0),
                    )
                )
        except Exception:
            entries = None

        if entries is None:
            print(f"{Colors.CYAN}Scanning slots {start:03d}-{end:03d}...{Colors.RESET}")
            for slot in range(start, end + 1):
                show_progress(slot - start + 1, end - start + 1, f"(slot {slot})")
                try:
                    info = client.info(slot, include_size=True)
                    # Metadata can persist after delete; treat size==0 as empty for listing.
                    if info.size_bytes:
                        samples.append(info)
                except SlotEmptyError:
                    pass
            print()  # Clear progress line

        if not samples:
            print(f"  {Colors.FG_DIM}No samples found{Colors.RESET}")
            return 0

        # Calculate totals
        total_size = sum(s.size_bytes for s in samples)
        total_samples = len(samples)

        # Show summary
        print(f"\n  Found {total_samples} samples, {format_size(total_size)} total\n")

        # Print header
        print(f"  {'Slot':>4}  {'Name':<18}  {'CH':>2}  {'Size':>7}  {'Duration':>8}")
        print(f"  {'-'*4}  {'-'*18}  {'--':>2}  {'-'*7}  {'-'*8}")

        # Print samples
        for info in samples:
            print(format_table_row(info))

        # Show oversized warning
        oversized = [s for s in samples if s.size_bytes > 100 * 1024]
        if oversized:
            print(f"\n  {Colors.FG_YELLOW}⚠ {len(oversized)} samples over 100KB{Colors.RESET}")
            print(f"  Run {Colors.FG_GREEN}ko2 optimize-all{Colors.RESET} to optimize")

    return 0


def cmd_info(args):
    """Show sample metadata for slot or range."""
    slot_spec = parse_range(args.slot)

    with EP133Client(args.device) as client:
        if isinstance(slot_spec, int):
            try:
                info = client.info(slot_spec, include_size=True)
                print(f"📵 Slot {info.slot:03d}")
                print(f"   Name: {info.name}")
                if info.sym:
                    print(f"   Symbol: {info.sym}")
                print(f"   Rate: {info.samplerate} Hz")
                print(f"   Format: {info.format}")
                print(f"   Channels: {info.channels}")
                if info.size_bytes:
                    print(f"   Size: {format_size(info.size_bytes)}")
                    print(f"   Duration: {format_duration(info.size_bytes, info.samplerate)}")
            except SlotEmptyError:
                print(f"Slot {slot_spec} is empty")
                return 1
        else:
            start, end = slot_spec
            if start > end:
                start, end = end, start

            samples = []
            empty_count = 0

            for slot in range(start, end + 1):
                show_progress(slot - start + 1, end - start + 1)
                try:
                    info = client.info(slot, include_size=True)
                    samples.append(info)
                except SlotEmptyError:
                    empty_count += 1
            print()

            total = end - start + 1
            used = len(samples)
            print(f"\nSlots {start:03d}-{end:03d}: {used} used, {empty_count} empty\n")

            if samples:
                for info in samples:
                    print(format_table_row(info))
            else:
                print(f"  {Colors.FG_DIM}(all empty){Colors.RESET}")

    return 0


def optimize_sample(input_path: Path, output_path: Optional[Path] = None) -> tuple[bool, str, int, int]:
    """
    Optimize a WAV file for EP-133 using audio2ko2 or sox.

    Returns:
        (success, message, original_size, optimized_size)
    """
    original_size = input_path.stat().st_size

    if output_path is None:
        output_path = input_path.with_suffix('.opt.wav')

    # Try audio2ko2 first
    audio2ko2 = Path.home() / 'proj' / 'audio2ko2' / 'audio2ko2'
    if audio2ko2.exists():
        try:
            result = subprocess.run(
                [str(audio2ko2), str(input_path)],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                # audio2ko2 creates output with _ko2 suffix
                ko2_output = input_path.with_stem(input_path.stem + '_ko2')
                if ko2_output.exists():
                    shutil.move(ko2_output, output_path)
                    opt_size = output_path.stat().st_size_size
                    return True, "optimized with audio2ko2", original_size, opt_size
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # Fall back to sox
    try:
        subprocess.run([
            'sox', str(input_path), '-c', '1', '-r', str(SAMPLE_RATE),
            '-b', '16', str(output_path)
        ], capture_output=True, check=True, timeout=30)
        opt_size = output_path.stat().st_size
        return True, "optimized with sox", original_size, opt_size
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, f"error: {e}", original_size, 0


def cmd_optimize(args):
    """Optimize a single sample on device."""
    slot = args.slot

    with EP133Client(args.device) as client:
        # Get sample info
        try:
            info = client.info(slot, include_size=True)
        except SlotEmptyError:
            print(f"❌ Slot {slot} is empty")
            return 1

        original_size = info.size_bytes
        print(f"Slot {slot}: {info.name}")
        print(f"  Size: {format_size(original_size)}")

        # Check if already optimized
        if original_size < 50 * 1024:
            print(f"  {Colors.FG_GREEN}✓ Already optimized (small file){Colors.RESET}")
            return 0

        # Download sample
        print(f"  {Colors.FG_DIM}Downloading...{Colors.RESET}")
        temp_path = client.get(slot, None)

        # Backup original
        backup_path = Path(str(temp_path) + '.bak')
        shutil.copy(temp_path, backup_path)

        # Optimize
        print(f"  {Colors.FG_DIM}Optimizing...{Colors.RESET}")
        success, msg, _, opt_size = optimize_sample(temp_path)

        if not success:
            print(f"  ❌ {msg}")
            return 1

        savings = original_size - opt_size
        savings_pct = (savings / original_size) * 100

        print(f"  Optimized: {format_size(opt_size)}")
        print(f"  Savings: {format_size(savings)} ({savings_pct:.1f}%)")

        # Check if savings are meaningful
        if savings < 5 * 1024:  # Less than 5KB savings
            print(f"  {Colors.FG_YELLOW}⚠ Savings too small (<5KB), skipping upload{Colors.RESET}")
            # Restore backup
            shutil.copy(backup_path, temp_path)
            return 0

        # Re-upload optimized version
        print(f"  {Colors.FG_DIM}Uploading optimized version...{Colors.RESET}")
        try:
            client.put(temp_path, slot, name=info.name, progress=False)
            print(f"  {Colors.FG_GREEN}✓ Optimized and replaced{Colors.RESET}")

            # Cleanup
            temp_path.unlink(missing_ok=True)
            backup_path.unlink(missing_ok=True)
        except EP133Error as e:
            print(f"  ❌ Upload failed: {e}")
            # Restore backup
            shutil.copy(backup_path, temp_path)
            return 1

    return 0


def cmd_optimize_all(args):
    """Optimize all oversized samples on device."""
    min_size = args.min * 1024 if args.min else 100 * 1024

    with EP133Client(args.device) as client:
        print(f"{Colors.CYAN}Scanning for samples over {format_size(min_size)}...{Colors.RESET}\n")

        # Scan all slots
        candidates = []
        for slot in range(1, MAX_SLOTS + 1):
            show_progress(slot, MAX_SLOTS)
            try:
                info = client.info(slot, include_size=True)
                if info.size_bytes > min_size:
                    candidates.append(info)
            except SlotEmptyError:
                pass
        print()

        if not candidates:
            print(f"  {Colors.FG_GREEN}No samples over {format_size(min_size)} found{Colors.RESET}")
            return 0

        print(f"  Found {len(candidates)} candidates:\n")
        total_original = 0
        for info in candidates:
            total_original += info.size_bytes
            print(f"    Slot {info.slot:03d}: {info.name[:30]:<30} {format_size(info.size_bytes)}")

        print(f"\n  Total: {format_size(total_original)}")

        if not args.force:
            response = input(f"\n  Optimize {len(candidates)} samples? [y/N] ")
            if response.lower() != 'y':
                print("  Cancelled")
                return 0

        # Process each sample
        print()
        optimized = 0
        total_savings = 0

        for i, info in enumerate(candidates, 1):
            print(f"\n[{i}/{len(candidates)}] Slot {info.slot}: {info.name}")

            # Download
            try:
                temp_path = client.get(info.slot, None)
            except EP133Error as e:
                print(f"  ❌ Download failed: {e}")
                continue

            # Backup
            backup_path = Path(str(temp_path) + '.bak')
            shutil.copy(temp_path, backup_path)

            # Optimize
            success, msg, _, opt_size = optimize_sample(temp_path)

            if not success:
                print(f"  ❌ {msg}")
                temp_path.unlink(missing_ok=True)
                continue

            savings = info.size_bytes - opt_size

            # Skip if savings too small
            if savings < 5 * 1024:
                print(f"  ⊘ Skipped (savings: {format_size(savings)})")
                shutil.copy(backup_path, temp_path)
                temp_path.unlink(missing_ok=True)
                backup_path.unlink(missing_ok=True)
                continue

            # Upload
            try:
                client.put(temp_path, info.slot, name=info.name, progress=False)
                print(f"  {Colors.FG_GREEN}✓ Saved {format_size(savings)} ({savings/info.size_bytes*100:.1f}%){Colors.RESET}")
                optimized += 1
                total_savings += savings
            except EP133Error as e:
                print(f"  ❌ Upload failed: {e}")
                shutil.copy(backup_path, temp_path)

            # Cleanup
            temp_path.unlink(missing_ok=True)
            backup_path.unlink(missing_ok=True)

        print(f"\n{Colors.CYAN}{'='*40}{Colors.RESET}")
        print(f"  Optimized: {optimized}/{len(candidates)} samples")
        print(f"  Total savings: {format_size(total_savings)}")

    return 0


def cmd_get(args):
    """Download sample from device."""
    output = Path(args.output) if args.output else None

    with EP133Client(args.device) as client:
        try:
            print(f"  Downloading slot {args.slot}...")
            result_path = client.get(args.slot, output)
            print(f"  {Colors.FG_GREEN}✓{Colors.RESET} Downloaded to {result_path}")
        except SlotEmptyError:
            print(f"  ❌ Slot {args.slot} is empty")
            return 1
        except EP133Error as e:
            print(f"  ❌ Error: {e}")
            return 1

    return 0


def cmd_put(args):
    """Upload sample to device."""
    input_path = Path(args.file)

    if not input_path.exists():
        print(f"  ❌ File not found: {input_path}")
        return 1

    with EP133Client(args.device) as client:
        try:
            name = args.name if args.name else None
            print(f"  Uploading {input_path.name} → slot {args.slot}...")
            client.put(input_path, args.slot, name=name, progress=True)
            print(f"  {Colors.FG_GREEN}✓{Colors.RESET} Uploaded to slot {args.slot}")
        except EP133Error as e:
            print(f"  ❌ Error: {e}")
            return 1
        except ValueError as e:
            print(f"  ❌ Invalid file: {e}")
            return 1

    return 0


def cmd_delete(args):
    """Delete sample from slot."""
    with EP133Client(args.device) as client:
        try:
            info = client.info(args.slot)
            print(f"  Deleting: {info.name} from slot {args.slot}")
            client.delete(args.slot)
            print(f"  {Colors.FG_GREEN}✓{Colors.RESET} Deleted slot {args.slot}")
        except SlotEmptyError:
            print(f"  Slot {args.slot} is already empty")
            return 1

    return 0


def cmd_group(args):
    """Compact samples in range toward one end."""
    start, end = parse_range(args.range)
    if start > end:
        start, end = end, start

    direction = "right" if args.reverse else "left"

    with EP133Client(args.device) as client:
        mapping = client.group(start, end, direction)

        if not mapping:
            print(f"  No samples found in range {start:03d}-{end:03d}")
            return 0

        print(f"  Grouping {direction}:")
        for old_slot, new_slot in mapping.items():
            print(f"    {old_slot:03d} → {new_slot:03d}")

        print(f"\n  {Colors.FG_YELLOW}⚠ Preview only{Colors.RESET}")
        print(f"  (requires download/re-upload to execute)")

    return 0


def cmd_squash(args):
    """Squash samples in page/group to fill slots sequentially."""
    # Determine range
    if args.page:
        start, end = parse_page(args.page)
        if start is None:
            print("  ❌ Page must be 1-10")
            return 1
    elif args.range:
        slot_spec = parse_range(args.range)
        if isinstance(slot_spec, int):
            start = end = slot_spec
        else:
            start, end = slot_spec
    else:
        start, end = 1, 99  # Default to page 1

    if start > end:
        start, end = end, start

    dry_run = not args.execute

    print(f"{Colors.CYAN}Squashing slots {start:03d}-{end:03d}...{Colors.RESET}")
    if dry_run:
        print(f"  {Colors.FG_YELLOW}DR RUN MODE{Colors.RESET} (use --execute to apply)")

    with EP133Client(args.device) as client:
        # Scan all samples in range
        print(f"  Scanning...")
        samples = []
        for slot in range(start, end + 1):
            show_progress(slot - start + 1, end - start + 1)
            try:
                info = client.info(slot, include_size=True)
                samples.append(info)
            except SlotEmptyError:
                pass
        print()

        if not samples:
            print(f"  {Colors.FG_DIM}No samples found{Colors.RESET}")
            return 0

        # Calculate squash mapping
        mapping = {}  # old_slot -> new_slot
        target_slot = start

        for info in samples:
            if info.slot != target_slot:
                mapping[info.slot] = target_slot
            target_slot += 1

        if not mapping:
            print(f"  {Colors.FG_GREEN}✓ Already compacted{Colors.RESET}")
            return 0

        # Show mapping
        print(f"  Will move {len(mapping)} samples:\n")
        for old_slot, new_slot in mapping.items():
            info = next(s for s in samples if s.slot == old_slot)
            savings = (old_slot - new_slot) * (end - start + 1)
            print(f"    {old_slot:03d} → {new_slot:03d}  {info.name[:30]:<30}")

        # TODO: Project reference update
        # This would require:
        # 1. Querying project patterns to find references to moved samples
        # 2. Updating pad assignments in project TAR files
        # 3. Re-uploading project data via SysEx (if protocol exists)
        #
        # Pseudo-code:
        # for project in [1..16]:
        #     patterns = download_project_patterns(project)
        #     for pattern in patterns:
        #         for event in pattern.events:
        #             if event.sample_slot in mapping:
        #                 event.sample_slot = mapping[event.sample_slot]
        #     upload_project_patterns(project, patterns)

        if dry_run:
            print(f"\n  {Colors.FG_YELLOW}⚠ Preview mode{Colors.RESET}")
            print(f"  Run with --execute to apply changes")
            print(f"\n  {Colors.FG_DIM}NOTE: Project pad references are NOT updated.{Colors.RESET}")
            print(f"  {Colors.FG_DIM}      (project update protocol not yet available){Colors.RESET}")
            return 0

        # Execute squash
        print(f"\n  {Colors.FG_CYAN}Executing...{Colors.RESET}\n")

        for old_slot, new_slot in mapping.items():
            # Download from old slot
            print(f"  [{old_slot:03d} → {new_slot:03d}] ", end="", flush=True)
            try:
                temp_path = client.get(old_slot, None)

                # Delete old slot
                client.delete(old_slot)

                # Upload to new slot
                client.put(temp_path, new_slot, progress=False)

                # Cleanup
                temp_path.unlink(missing_ok=True)
                print(f"{Colors.FG_GREEN}✓{Colors.RESET}")
            except EP133Error as e:
                print(f"{Colors.FG_RED}✗ {e}{Colors.RESET}")

        print(f"\n  {Colors.FG_GREEN}✓ Squash complete{Colors.RESET}")
        print(f"  {Colors.FG_DIM}Freed {len(mapping)} slots{Colors.RESET}")

    return 0


def parse_range(arg: str) -> tuple[int, int] | int:
    """Parse range argument: '5', '1-10', or '1..10'."""
    match = re.match(r'^(\d+)\.\.(\d+)$', arg)
    if match:
        return int(match.group(1)), int(match.group(2))

    match = re.match(r'^(\d+)-(\d+)$', arg)
    if match:
        return int(match.group(1)), int(match.group(2))

    return int(arg)


def main():
    parser = argparse.ArgumentParser(
        description="KO2 - EP-133 KO-II Command Line Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--device', help='MIDI device name (auto-detect if omitted)')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # ls: list by pages
    ls_parser = subparsers.add_parser('ls', help='List samples by pages')
    ls_group = ls_parser.add_mutually_exclusive_group()
    ls_group.add_argument('--page', type=int, metavar='N', help='Show page N (1-10)')
    ls_group.add_argument('--all', '-a', action='store_true', help='List all samples')

    # info: slot or range
    info_parser = subparsers.add_parser('info', help='Show sample metadata')
    info_parser.add_argument('slot', help='Slot (5) or range (1-10, 1..10)')

    # get
    get_parser = subparsers.add_parser('get', help='Download sample')
    get_parser.add_argument('slot', type=int, help='Slot number (1-999)')
    get_parser.add_argument('output', nargs='?', help='Output filename')

    # put
    put_parser = subparsers.add_parser('put', help='Upload sample')
    put_parser.add_argument('file', help='WAV file to upload')
    put_parser.add_argument('slot', type=int, help='Target slot (1-999)')
    put_parser.add_argument('--name', help='Sample name')

    # delete
    delete_parser = subparsers.add_parser('delete', help='Delete sample')
    delete_parser.add_argument('slot', type=int, help='Slot number (1-999)')

    # rm: alias for delete
    rm_parser = subparsers.add_parser('rm', help='Delete sample (alias)')
    rm_parser.add_argument('slot', type=int, help='Slot number (1-999)')

    # optimize
    opt_parser = subparsers.add_parser('optimize', help='Optimize single sample')
    opt_parser.add_argument('slot', type=int, help='Slot number (1-999)')

    # optimize-all
    optall_parser = subparsers.add_parser('optimize-all', help='Optimize all oversized samples')
    optall_parser.add_argument('--min', type=int, metavar='KB', default=100,
                               help='Minimum size to consider (KB, default: 100)')
    optall_parser.add_argument('--force', '-f', action='store_true',
                               help='Skip confirmation')

    # group
    group_parser = subparsers.add_parser('group', help='Compact samples in range (preview)')
    group_parser.add_argument('range', help='Range like 1-50 or 10..100')
    group_parser.add_argument('-r', '--reverse', action='store_true',
                            help='Compact toward right (default: left)')

    # squash
    squash_parser = subparsers.add_parser('squash', help='Squash samples to fill gaps')
    squash_group = squash_parser.add_mutually_exclusive_group()
    squash_group.add_argument('--page', type=int, metavar='N', help='Page to squash (1-10)')
    squash_group.add_argument('--range', metavar='N', help='Range like 1-50 or 10..100')
    squash_parser.add_argument('--execute', action='store_true',
                               help='Actually perform the move (default: dry-run)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Find device
    if args.device:
        device = args.device
    else:
        device = find_device()
        if not device:
            print("  ❌ EP-133 not found. Connect via USB.")
            return 1

    # Dispatch
    commands = {
        'ls': cmd_ls,
        'info': cmd_info,
        'get': cmd_get,
        'put': cmd_put,
        'delete': cmd_delete,
        'rm': cmd_delete,  # Alias
        'optimize': cmd_optimize,
        'optimize-all': cmd_optimize_all,
        'group': cmd_group,
        'squash': cmd_squash,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)

    return 0


if __name__ == '__main__':
    sys.exit(main())
