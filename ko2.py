#!/usr/bin/env python3
"""
KO2 - EP-133 KO-II Command Line Tool

Usage:
    ko2 info <slot|range>    - Show sample metadata (5, 1-10, 1..10)
    ko2 group <range>        - Compact samples (default: left, --reverse for right)
    ko2 get <slot> [file]     - Download sample
    ko2 put <file> <slot>     - Upload sample
    ko2 delete <slot>         - Delete sample
"""
import sys
import argparse
import re
from pathlib import Path

try:
    from ko2_client import EP133Client, find_device, SampleInfo, EP133Error, SlotEmptyError
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)


# ANSI colors for size highlighting
class Colors:
    RESET = "\033[0m"
    BRIGHT_GREEN = "\033[48;5;22m"     # Small files
    GREEN = "\033[48;5;28m"            # Small-medium
    YELLOW = "\033[48;5;226m"          # Medium
    ORANGE = "\033[48;5;208m"          # Medium-large
    RED = "\033[48;5;196m"             # Large
    BRIGHT_RED = "\033[48;5;88m"       # Very large
    FG_GRAY = "\033[38;5;245m"
    FG_DIM = "\033[90m"


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
    if size_bytes < 10 * 1024:          # < 10KB
        return Colors.BRIGHT_GREEN
    elif size_bytes < 50 * 1024:        # < 50KB
        return Colors.GREEN
    elif size_bytes < 100 * 1024:       # < 100KB
        return Colors.YELLOW
    elif size_bytes < 200 * 1024:       # < 200KB
        return Colors.ORANGE
    elif size_bytes < 500 * 1024:       # < 500KB
        return Colors.RED
    else:                               # >= 500KB
        return Colors.BRIGHT_RED


def format_info_line(info: SampleInfo, show_size: bool = False) -> str:
    """Format a single slot info line with color coding."""
    size_str = ""
    if show_size and info.size_bytes:
        color = get_size_color(info.size_bytes)
        size_str = f" {color} {format_size(info.size_bytes)} {Colors.RESET}"

    sym = f" [{info.sym}]" if info.sym else ""
    return f"  {info.slot:03d}: {info.name}{sym}{size_str}"


def parse_range(arg: str) -> tuple[int, int] | int:
    """Parse range argument: '5', '1-10', or '1..10'."""
    # Try .. syntax
    match = re.match(r'^(\d+)\.\.(\d+)$', arg)
    if match:
        return int(match.group(1)), int(match.group(2))

    # Try - syntax
    match = re.match(r'^(\d+)-(\d+)$', arg)
    if match:
        return int(match.group(1)), int(match.group(2))

    # Single slot
    return int(arg)


def cmd_info(args):
    """Show sample metadata for slot or range."""
    slot_spec = parse_range(args.slot)

    with EP133Client(args.device) as client:
        if isinstance(slot_spec, int):
            # Single slot
            try:
                info = client.info(slot_spec)
                print(f"📵 Slot {info.slot:03d}")
                print(f"   Name: {info.name}")
                if info.sym:
                    print(f"   Symbol: {info.sym}")
                print(f"   Rate: {info.samplerate} Hz")
                print(f"   Format: {info.format}")
                print(f"   Channels: {info.channels}")
                if info.size_bytes:
                    print(f"   Size: {format_size(info.size_bytes)}")
            except SlotEmptyError:
                print(f"Slot {slot_spec} is empty")
                return 1
        else:
            # Range: show compact list with size colors
            start, end = slot_spec
            if start > end:
                start, end = end, start

            samples = []
            empty_count = 0

            for slot in range(start, end + 1):
                try:
                    info = client.info(slot)
                    samples.append(info)
                except SlotEmptyError:
                    empty_count += 1

            # Print header
            total = end - start + 1
            used = len(samples)
            print(f"Slots {start:03d}-{end:03d}: {used} used, {empty_count} empty\n")

            # Group samples by continuous ranges
            if samples:
                for info in samples:
                    print(format_info_line(info, show_size=True))
            else:
                print(f"  {Colors.FG_DIM}(all empty){Colors.RESET}")

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
            print(f"No samples found in range {start:03d}-{end:03d}")
            return 0

        print(f"Grouping {direction}:")
        for old_slot, new_slot in mapping.items():
            print(f"  {old_slot:03d} → {new_slot:03d}")

        # Note: Actual moving requires upload to work
        print(f"\n⚠️  Preview only. Execute after upload is fixed.")

    return 0


def cmd_get(args):
    """Download sample from device."""
    output = Path(args.output) if args.output else None

    with EP133Client(args.device) as client:
        try:
            result_path = client.get(args.slot, output)
            print(f"✅ Downloaded to {result_path}")
        except SlotEmptyError:
            print(f"❌ Slot {args.slot} is empty")
            return 1
        except EP133Error as e:
            print(f"❌ Error: {e}")
            return 1

    return 0


def cmd_put(args):
    """Upload sample to device."""
    input_path = Path(args.file)

    if not input_path.exists():
        print(f"❌ File not found: {input_path}")
        return 1

    with EP133Client(args.device) as client:
        try:
            name = args.name if args.name else None
            client.put(input_path, args.slot, name=name, progress=not args.quiet)
            print(f"✅ Uploaded to slot {args.slot}")
        except EP133Error as e:
            print(f"❌ Error: {e}")
            return 1
        except ValueError as e:
            print(f"❌ Invalid file: {e}")
            return 1

    return 0


def cmd_delete(args):
    """Delete sample from slot."""
    with EP133Client(args.device) as client:
        try:
            info = client.info(args.slot)
            print(f"Deleting: {info.name} from slot {args.slot}")
            client.delete(args.slot)
            print(f"✅ Deleted slot {args.slot}")
        except SlotEmptyError:
            print(f"Slot {args.slot} is already empty")
            return 1

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="KO2 - EP-133 KO-II Command Line Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--device', help='MIDI device name (auto-detect if omitted)')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # info: slot or range
    info_parser = subparsers.add_parser('info', help='Show sample metadata')
    info_parser.add_argument('slot', help='Slot (5) or range (1-10, 1..10)')

    # group: range only, with --reverse flag
    group_parser = subparsers.add_parser('group', help='Compact samples in range')
    group_parser.add_argument('range', help='Range like 1-50 or 10..100')
    group_parser.add_argument('-r', '--reverse', action='store_true',
                            help='Compact toward right (default: left)')

    # get
    get_parser = subparsers.add_parser('get', help='Download sample from device')
    get_parser.add_argument('slot', type=int, help='Slot number (1-999)')
    get_parser.add_argument('output', nargs='?', help='Output filename (auto-generated if omitted)')

    # delete
    delete_parser = subparsers.add_parser('delete', help='Delete sample from slot')
    delete_parser.add_argument('slot', type=int, help='Slot number (1-999)')

    # put
    put_parser = subparsers.add_parser('put', help='Upload sample to device')
    put_parser.add_argument('file', help='WAV file to upload')
    put_parser.add_argument('slot', type=int, help='Target slot (1-999)')
    put_parser.add_argument('--name', help='Sample name (default: filename)')
    put_parser.add_argument('--quiet', '-q', action='store_true',
                           help='Suppress progress output')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Check device connection
    if args.device:
        pass  # Use specified device
    else:
        device = find_device()
        if not device:
            print("❌ EP-133 not found. Connect via USB.")
            return 1
        args.device = device

    # Dispatch command
    commands = {
        'info': cmd_info,
        'group': cmd_group,
        'get': cmd_get,
        'put': cmd_put,
        'delete': cmd_delete,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)

    return 0


if __name__ == '__main__':
    sys.exit(main())
