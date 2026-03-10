"""
ko2_parser.py - Argument parser construction for the ko2 CLI.

Exports:
    build_parser()    -> argparse.ArgumentParser
    validate_slot()   -> int  (argparse type validator)
    parse_range()     -> tuple[int, int] | int
"""
import argparse
import re

try:
    from ko2_models import MAX_SLOTS
except ImportError as e:
    raise ImportError(f"ko2_parser: could not import ko2_models: {e}") from e


def validate_slot(slot) -> int:
    """Validate slot number is within EP-133 range (1-999)."""
    try:
        slot = int(slot)
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError(f"Slot must be an integer 1-{MAX_SLOTS}")
    if not 1 <= slot <= MAX_SLOTS:
        raise argparse.ArgumentTypeError(f"Slot must be 1-{MAX_SLOTS}, got {slot}")
    return slot


def parse_range(arg: str) -> tuple[int, int] | int:
    """Parse range argument: '5', '1-10', or '1..10'."""
    try:
        match = re.match(r"^(\d+)\.\.(\d+)$", arg)
        if match:
            return int(match.group(1)), int(match.group(2))

        match = re.match(r"^(\d+)-(\d+)$", arg)
        if match:
            return int(match.group(1)), int(match.group(2))

        return int(arg)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid range or slot: '{arg}'")


def build_parser() -> argparse.ArgumentParser:
    """Build and return the ko2 CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="KO2 - EP-133 KO-II Command Line Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--json", action="store_true", help="Machine-readable JSON output"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress non-essential output"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ls: list by pages
    ls_parser = subparsers.add_parser("ls", help="List samples by pages")
    ls_group = ls_parser.add_mutually_exclusive_group()
    ls_group.add_argument("--page", type=int, metavar="N", help="Show page N (1-10)")
    ls_group.add_argument("--all", "-a", action="store_true", help="List all samples")
    ls_group.add_argument(
        "--range", help="Slot range (e.g. 100-160 or 100..160)"
    )
    ls_parser.add_argument(
        "--source",
        choices=("auto", "fs", "scan"),
        default="auto",
        help="Listing source: filesystem (/sounds), slot-scan, or auto (default: auto)",
    )
    ls_parser.add_argument(
        "--name-source",
        choices=("auto", "fs", "node"),
        default="auto",
        help="Name source: auto (default), fs (/sounds filename), or node (filesystem metadata)",
    )
    ls_parser.add_argument(
        "--stream",
        action="store_true",
        help="Print samples as they are discovered (disables progress bar)",
    )
    # info: slot or range
    info_parser = subparsers.add_parser("info", help="Show sample metadata")
    info_parser.add_argument("slot", help="Slot (5) or range (1-10, 1..10)")

    # status: quick device status
    subparsers.add_parser(
        "status", help="Show device status (info + sample memory)"
    )

    # audit: compare metadata sources
    audit_parser = subparsers.add_parser(
        "audit", help="Audit metadata mismatches across sources"
    )
    audit_group = audit_parser.add_mutually_exclusive_group()
    audit_group.add_argument("--page", type=int, metavar="N", help="Page (1-10)")
    audit_group.add_argument("--range", metavar="N", help="Range like 1-50 or 10..100")
    audit_group.add_argument(
        "--all", "-a", action="store_true", help="Audit all slots"
    )
    audit_parser.add_argument(
        "--show-all", action="store_true", help="Show slots without issues"
    )
    audit_parser.add_argument(
        "--dump",
        metavar="FILE",
        help="Write a diff-friendly TSV file (includes all slots)",
    )
    audit_parser.add_argument(
        "--dump-json",
        metavar="FILE",
        help="Write raw fs/node/meta JSONL for each slot",
    )
    audit_parser.add_argument(
        "--compare",
        metavar="FIELDS",
        default="name,sym,channels,samplerate,format",
        help="Comma-separated fields to compare between node and GET_META",
    )

    # get
    get_parser = subparsers.add_parser("get", help="Download sample")
    get_parser.add_argument("slot", type=int, help="Slot number (1-999)")
    get_parser.add_argument("output", nargs="?", help="Output filename")
    get_parser.add_argument("-y", "--yes", action="store_true", help="Overwrite if exists")

    # put
    put_parser = subparsers.add_parser("put", help="Upload sample")
    put_parser.add_argument("file", help="WAV file to upload")
    put_parser.add_argument("slot", type=validate_slot, help="Target slot (1-999)")
    put_parser.add_argument("--name", help="Sample name")
    put_parser.add_argument("--pitch", type=float, default=0.0, help="Pitch offset in semitones (e.g. -12.0)")

    # move
    mv_parser = subparsers.add_parser("mv", aliases=["move"], help="Move sample between slots")
    mv_parser.add_argument("src", type=validate_slot, help="Source slot (1-999)")
    mv_parser.add_argument("dst", type=validate_slot, help="Destination slot (1-999)")
    mv_parser.add_argument(
        "--raw", "--original", dest="raw", action="store_true", help="Use raw filename"
    )
    mv_parser.add_argument(
        "-y",
        "--yes",
        "-f",
        "--force",
        "-q",
        "--quiet",
        dest="yes",
        action="store_true",
        help="Skip confirmation",
    )

    # copy
    cp_parser = subparsers.add_parser("cp", aliases=["copy"], help="Copy sample between slots")
    cp_parser.add_argument("src", type=validate_slot, help="Source slot (1-999)")
    cp_parser.add_argument("dst", type=validate_slot, help="Destination slot (1-999)")
    cp_parser.add_argument(
        "--raw", "--original", dest="raw", action="store_true", help="Use raw filename"
    )
    cp_parser.add_argument(
        "-y",
        "--yes",
        "-f",
        "--force",
        "-q",
        "--quiet",
        dest="yes",
        action="store_true",
        help="Skip confirmation",
    )

    # delete
    delete_parser = subparsers.add_parser("delete", aliases=["rm", "remove"], help="Delete sample")
    delete_parser.add_argument("slot", type=validate_slot, help="Slot number (1-999)")
    delete_parser.add_argument(
        "-y",
        "--yes",
        "-f",
        "--force",
        "-q",
        "--quiet",
        dest="yes",
        action="store_true",
        help="Skip confirmation",
    )

    # audition
    audition_parser = subparsers.add_parser("audition", aliases=["play"], help="Trigger on-device sample preview")
    audition_parser.add_argument("slot", type=validate_slot, help="Slot number (1-999)")

    # optimize
    opt_parser = subparsers.add_parser("optimize", help="Optimize single sample")
    opt_parser.add_argument("slot", type=validate_slot, help="Slot number (1-999)")
    opt_parser.add_argument(
        "-y",
        "--yes",
        "-f",
        "--force",
        "-q",
        "--quiet",
        dest="yes",
        action="store_true",
        help="Skip confirmation",
    )
    opt_parser.add_argument("--rate", type=int, help="Target downsample rate (e.g. 22050 or 11025)")
    opt_parser.add_argument("--speed", type=float, help="Time stretch speed multiplier (e.g. 2.0 for double speed)")
    opt_parser.add_argument("--pitch", type=float, default=0.0, help="Pitch offset in semitones (e.g. -12.0) applied after speed")
    opt_parser.add_argument("--keep-stereo", action="store_true", help="Do not downmix stereo to mono")

    # optimize-all
    optall_parser = subparsers.add_parser(
        "optimize-all", help="Optimize stereo samples (downmix to mono)"
    )
    optall_parser.add_argument(
        "-y",
        "--yes",
        "-f",
        "--force",
        "-q",
        "--quiet",
        dest="yes",
        action="store_true",
        help="Skip confirmation",
    )
    optall_parser.add_argument(
        "--min",
        type=int,
        metavar="KB",
        default=None,
        help="Skip samples smaller than KB",
    )
    optall_parser.add_argument(
        "--slot",
        type=validate_slot,
        metavar="SLOT",
        default=None,
        help="Run on a single slot instead of scanning all",
    )

    # group
    group_parser = subparsers.add_parser(
        "group", help="Compact samples in range (preview)"
    )
    group_parser.add_argument("range", help="Range like 1-50 or 10..100")
    group_parser.add_argument(
        "-r",
        "--reverse",
        action="store_true",
        help="Compact toward right (default: left)",
    )

    # squash
    squash_parser = subparsers.add_parser("squash", help="Squash samples to fill gaps")
    squash_group = squash_parser.add_mutually_exclusive_group()
    squash_group.add_argument(
        "--page", type=int, metavar="N", help="Page to squash (1-10)"
    )
    squash_group.add_argument("--range", metavar="N", help="Range like 1-50 or 10..100")
    squash_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform the move (default: dry-run)",
    )
    squash_parser.add_argument(
        "--raw", "--original", dest="raw", action="store_true", help="Use raw filename"
    )
    squash_parser.add_argument(
        "-y",
        "--yes",
        "-f",
        "--force",
        "-q",
        "--quiet",
        dest="yes",
        action="store_true",
        help="Skip confirmation",
    )

    # fs-ls: debug filesystem listing
    fs_parser = subparsers.add_parser("fs-ls", help="List filesystem entries (debug)")
    fs_parser.add_argument(
        "--node",
        type=int,
        default=1000,
        help="Node ID to list (default: 1000 = /sounds)",
    )
    fs_parser.add_argument(
        "--range", metavar="N", help="Filter slots like 1-50 or 10..100 (files only)"
    )
    fs_parser.add_argument(
        "--raw", action="store_true", help="Show raw hi/lo and decoded node IDs"
    )

    # rename
    rename_parser = subparsers.add_parser(
        "rename", help="Rename a sample slot (backs up first)"
    )
    rename_parser.add_argument("slot", type=validate_slot, help="Slot number (1-999)")
    rename_parser.add_argument("name", help="New name")

    # fingerprint: local KV waveform + hash records
    fp_parser = subparsers.add_parser(
        "fingerprint", help="Manage waveform fingerprint KV cache"
    )
    fp_sub = fp_parser.add_subparsers(dest="fp_action", required=True)

    fp_write = fp_sub.add_parser("write", help="Download slot and write fingerprint to KV store")
    fp_write.add_argument("slot", type=validate_slot, help="Slot number (1-999)")
    fp_write.add_argument(
        "--width",
        type=int,
        default=320,
        help="Waveform bin width to store (default: 320)",
    )
    fp_write.add_argument(
        "--store",
        default=None,
        metavar="PATH",
        help="KV store path (default: captures/waveform-kv.json)",
    )
    fp_write.add_argument(
        "--no-meta",
        action="store_true",
        help="Do not write ko2.fp.* hash fields into device metadata",
    )

    fp_read = fp_sub.add_parser("read", help="Read cached fingerprint info for slot")
    fp_read.add_argument("slot", type=validate_slot, help="Slot number (1-999)")
    fp_read.add_argument(
        "--store",
        default=None,
        metavar="PATH",
        help="KV store path (default: captures/waveform-kv.json)",
    )
    fp_read.add_argument(
        "--width",
        type=int,
        default=320,
        help="Reserved for output compatibility",
    )

    fp_verify = fp_sub.add_parser("verify", help="Verify slot hash matches cached fingerprint")
    fp_verify.add_argument("slot", type=validate_slot, help="Slot number (1-999)")
    fp_verify.add_argument(
        "file",
        nargs="?",
        help="Optional WAV file to compare against cached hash",
    )
    fp_verify.add_argument(
        "--width",
        type=int,
        default=320,
        help="Waveform bin width for hash extraction (default: 320)",
    )
    fp_verify.add_argument(
        "--store",
        default=None,
        metavar="PATH",
        help="KV store path (default: captures/waveform-kv.json)",
    )

    # tui
    tui_parser = subparsers.add_parser("tui", help="Launch interactive TUI")
    tui_parser.add_argument(
        "--debug",
        nargs="?",
        const="__AUTO__",
        default=None,
        metavar="PATH",
        help=(
            "Enable in-app raw MIDI debug log and JSONL capture. "
            "Optionally provide PATH (default: captures/tui-*.jsonl)."
        ),
    )
    tui_parser.add_argument(
        "--dialog-log",
        default=None,
        metavar="PATH",
        help=(
            "Dialog/status message log path used with --debug "
            "(default: captures/tui-dialog-*.log)."
        ),
    )

    return parser
