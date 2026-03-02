#!/usr/bin/env python3
"""
KO2 - EP-133 KO-II Command Line Tool

Usage:
    ko2 ls [--page N]          - List samples by pages
    ko2 status                 - Show device status
    ko2 audit                  - Audit metadata mismatches
    ko2 info <slot|range>      - Show sample metadata
    ko2 get <slot> [file]      - Download sample
    ko2 put <file> <slot>      - Upload sample
    ko2 mv <src> <dst>         - Move sample
    ko2 cp <src> <dst>         - Copy sample
    ko2 rm <slot>              - Delete sample
    ko2 squash [--page N]      - Squash samples to fill gaps
    ko2 optimize <slot>        - Optimize single sample
    ko2 optimize-all           - Optimize all oversized samples
"""
import sys
import argparse
import re
import shutil
import json
import importlib
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Optional

try:
    from ko2_client import (
        EP133Client,
        find_device,
        SampleInfo,
        EP133Error,
        SlotEmptyError,
    )
    from ko2_backup import backup_copy
    from ko2_models import SAMPLE_RATE, MAX_SLOTS, decode_node_id, decode_14bit
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)


# ANSI colors
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
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
    FG_RED = "\033[38;5;196m"


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
    if size_bytes <= 0:
        return ""

    def bg(code: int) -> str:
        return f"\033[48;5;{code}m"

    # Subtle palettes per range (darker, lower chroma) with intra-range gradation.
    ranges = [
        (0, 50 * 1024, [22, 28]),            # dark green
        (50 * 1024, 200 * 1024, [28, 34]),    # green -> teal
        (200 * 1024, 500 * 1024, [58, 94]),   # muted yellow
        (500 * 1024, 1024 * 1024, [94, 130]), # yellow -> orange
        (1024 * 1024, 2 * 1024 * 1024, [130, 88]),  # orange -> dark red
        (2 * 1024 * 1024, 10 * 1024 * 1024, [88, 52]),  # deep red
    ]

    for lo, hi, palette in ranges:
        if size_bytes < hi:
            if len(palette) == 1:
                return bg(palette[0])
            ratio = (size_bytes - lo) / (hi - lo)
            idx = min(len(palette) - 1, int(ratio * len(palette)))
            return bg(palette[idx])

    return bg(52)


def format_duration(
    size_bytes: int, samplerate: int = SAMPLE_RATE, channels: int = 1
) -> str:
    """Calculate duration from file size (seconds, 3 decimals)."""
    if size_bytes == 0:
        return "-"
    if channels not in (1, 2):
        channels = 1
    # 16-bit = 2 bytes per sample per channel
    bytes_per_frame = 2 * channels
    samples = size_bytes // bytes_per_frame
    seconds = samples / samplerate
    dur = f"{seconds:.3f}"
    if seconds < 1:
        dur = dur[1:]  # omit leading zero
    return dur


def strip_slot_prefix(name: str, slot: int) -> str:
    prefix = f"{slot:03d} "
    if name.startswith(prefix):
        return name[len(prefix) :].strip()
    return name


def _looks_generic_name(name: str) -> bool:
    if not name:
        return True
    lowered = name.lower().strip()
    if lowered.startswith("slot "):
        return True
    if re.match(r"^\d{3}(\.pcm)?$", lowered):
        return True
    if lowered.endswith(".pcm"):
        return True
    return False


def choose_display_name(
    fs_name: str,
    meta_name: str | None,
    node_name: str | None,
    slot: int,
    source: str,
) -> str:
    fs_clean = strip_slot_prefix(fs_name, slot).strip()
    meta_clean = (meta_name or "").strip()
    node_clean = (node_name or "").strip()
    if source == "fs":
        return fs_clean or node_clean or meta_clean or f"Slot {slot:03d}"
    if source == "node":
        return node_clean or meta_clean or fs_clean or f"Slot {slot:03d}"
    # auto
    if node_clean and _looks_generic_name(fs_clean):
        return node_clean
    if meta_clean and _looks_generic_name(fs_clean):
        return meta_clean
    return fs_clean or node_clean or meta_clean or f"Slot {slot:03d}"


def empty_sample(slot: int) -> SampleInfo:
    return SampleInfo(
        slot=slot,
        name="...",
        samplerate=SAMPLE_RATE,
        channels=0,
        size_bytes=0,
    )


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
    if info.channels == 2:
        channels_color = f"{Colors.BOLD}{Colors.FG_RED}"
    else:
        channels_color = Colors.FG_DIM

    # Truncate name to fit (keep width 18)
    name = info.name
    if len(name) > 18:
        name = name[:15] + "..."

    size_width = 7
    size_display = (
        f"{color}{size_str:>{size_width}}{reset}"
        if info.size_bytes
        else f"{size_str:>{size_width}}"
    )
    duration_width = 7

    return (
        f"  {Colors.FG_DIM}{info.slot:03d}{Colors.RESET}  "
        f"{name:<18}  "
        f"{channels_color}{channels_str}{Colors.RESET}  "
        f"{size_display}  "
        f"{format_duration(info.size_bytes, info.samplerate, info.channels):>{duration_width}}"
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
        if args.range:
            range_spec = parse_range(args.range)
            if isinstance(range_spec, int):
                start, end = range_spec, range_spec
            else:
                start, end = range_spec
            if start > end:
                start, end = end, start
            if start < 1 or end > MAX_SLOTS:
                print(f"❌ Range must be within 1-{MAX_SLOTS}")
                return 1
        elif args.page:
            page_range = parse_page(args.page)
            if page_range is None:
                print("❌ Page must be 1-10")
                return 1
            start, end = page_range
        elif args.all:
            start, end = 1, MAX_SLOTS
        else:
            start, end = 1, 99  # Default to first page

        source = args.source
        stream = args.stream
        name_source = args.name_source
        # Prefer filesystem listing (/sounds/) for ground truth; slot-scan can be stale.
        samples = []
        entries = None
        if source in ("auto", "fs"):
            try:
                print(f"{Colors.CYAN}Fetching /sounds listing...{Colors.RESET}")
                sounds = client.list_sounds()
                entries = list(sounds.values())
                all_slots = list(range(start, end + 1))
                total_slots = len(all_slots)
                if stream:
                    print(
                        f"\n  {'Slot':>4}  {'Name':<18}  {'CH':>2}  {'Size':>7}  {'s':>7}"
                    )
                    print(f"  {'-'*4}  {'-'*18}  {'--':>2}  {'-'*7}  {'-'*7}")
                for idx, slot in enumerate(all_slots, 1):
                    if total_slots:
                        if stream:
                            print(
                                f"  {Colors.FG_DIM}{idx:>3}/{total_slots:<3}{Colors.RESET} ",
                                end="",
                            )
                        else:
                            show_progress(idx, total_slots, f"(slot {slot})")
                    e = sounds.get(slot)
                    if not e:
                        samples.append(empty_sample(slot))
                        if stream:
                            print(format_table_row(samples[-1]))
                        continue

                    size_bytes = int(e.get("size") or 0)
                    fs_name = str(e.get("name", f"Slot {slot:03d}"))
                    meta_name = None
                    node_name = None
                    samplerate = SAMPLE_RATE
                    channels = 0

                    node_id = int(e.get("node_id") or 0)
                    node_meta = None
                    if name_source in ("auto", "node"):
                        try:
                            if node_id:
                                node_meta = client.get_node_metadata(node_id)
                        except Exception:
                            node_meta = None
                        if node_meta:
                            node_name = node_meta.get("name") or node_meta.get("sym")
                            if "samplerate" in node_meta:
                                samplerate = int(
                                    node_meta.get("samplerate") or SAMPLE_RATE
                                )
                            if "channels" in node_meta:
                                channels = int(node_meta.get("channels") or 0)

                    need_info = node_meta is None or channels == 0
                    if need_info:
                        try:
                            meta = client.info(
                                slot,
                                include_size=False,
                                node_entry=e,
                            )
                            samplerate = int(meta.samplerate or samplerate or SAMPLE_RATE)
                            channels = int(meta.channels or channels or 0)
                            meta_name = meta.name
                        except Exception:
                            pass

                    name = choose_display_name(
                        fs_name, meta_name, node_name, slot, name_source
                    )
                    samples.append(
                        SampleInfo(
                            slot=slot,
                            name=name,
                            samplerate=samplerate,
                            channels=channels,
                            size_bytes=size_bytes,
                        )
                    )
                    if stream:
                        print(format_table_row(samples[-1]))
                if total_slots and not stream:
                    print()
            except Exception as e:
                if source == "fs":
                    print(f"❌ Failed to list /sounds via filesystem API: {e}")
                    return 1
                entries = None

        if entries is None:
            if source == "auto":
                print(
                    f"{Colors.FG_YELLOW}⚠ Falling back to slot-scan (may be stale).{Colors.RESET}"
                )
            elif source == "scan":
                pass
            else:
                print("❌ Invalid source")
                return 1

        if entries is None and source in ("auto", "scan"):
            print(f"{Colors.CYAN}Scanning slots {start:03d}-{end:03d}...{Colors.RESET}")
            if stream:
                print(
                    f"\n  {'Slot':>4}  {'Name':<18}  {'CH':>2}  {'Size':>7}  {'s':>7}"
                )
                print(f"  {'-'*4}  {'-'*18}  {'--':>2}  {'-'*7}  {'-'*7}")
            for slot in range(start, end + 1):
                if stream:
                    print(
                        f"  {Colors.FG_DIM}{slot - start + 1:>3}/{end - start + 1:<3}{Colors.RESET} ",
                        end="",
                    )
                else:
                    show_progress(slot - start + 1, end - start + 1, f"(slot {slot})")
                try:
                    info = client.info(
                        slot,
                        include_size=True,
                    )
                    # Metadata can persist after delete; treat size==0 as empty for listing.
                    if info.size_bytes:
                        samples.append(info)
                    else:
                        samples.append(empty_sample(slot))
                except SlotEmptyError:
                    samples.append(empty_sample(slot))
                if stream:
                    print(format_table_row(samples[-1]))
            if not stream:
                print()  # Clear progress line

        samples = [s for s in samples if start <= s.slot <= end]

        # Calculate totals
        used_samples = [s for s in samples if s.size_bytes]
        total_size = sum(s.size_bytes for s in used_samples)
        total_samples = len(used_samples)

        # Show summary
        print(f"\n  Slots {start:03d}-{end:03d}")
        print(f"  Found {total_samples} samples, {format_size(total_size)} total\n")

        if not stream:
            # Print header
            print(
                f"  {'Slot':>4}  {'Name':<18}  {'CH':>2}  {'Size':>7}  {'s':>7}"
            )
            print(f"  {'-'*4}  {'-'*18}  {'--':>2}  {'-'*7}  {'-'*7}")

        # Print samples (including empty slots)
        if not stream:
            for info in samples:
                print(format_table_row(info))

        # Show oversized warning
        oversized = [s for s in used_samples if s.size_bytes > 100 * 1024]
        if oversized:
            print(
                f"\n  {Colors.FG_YELLOW}⚠ {len(oversized)} samples over 100KB{Colors.RESET}"
            )
            print(f"  Run {Colors.FG_GREEN}ko2 optimize-all{Colors.RESET} to optimize")

    return 0


def cmd_info(args):
    """Show sample metadata for slot or range."""
    slot_spec = parse_range(args.slot)

    with EP133Client(args.device) as client:
        if isinstance(slot_spec, int):
            try:
                info = client.info(slot_spec, include_size=True)
                # Prefer filesystem node metadata for name/format if available.
                try:
                    sounds = client.list_sounds()
                    entry = sounds.get(slot_spec)
                    node_id = int(entry.get("node_id") or 0) if entry else 0
                    if node_id:
                        node_meta = client.get_node_metadata(node_id)
                        if node_meta:
                            if node_meta.get("name") or node_meta.get("sym"):
                                info.name = node_meta.get("name") or node_meta.get("sym")
                            if node_meta.get("sym"):
                                info.sym = node_meta.get("sym")
                            if "samplerate" in node_meta:
                                info.samplerate = int(node_meta.get("samplerate") or info.samplerate)
                            if "channels" in node_meta:
                                info.channels = int(node_meta.get("channels") or info.channels)
                            if "format" in node_meta:
                                info.format = str(node_meta.get("format") or info.format)
                except Exception:
                    pass
                print(f"📵 Slot {info.slot:03d}")
                print(f"   Name: {info.name}")
                if info.sym:
                    print(f"   Symbol: {info.sym}")
                print(f"   Rate: {info.samplerate} Hz")
                print(f"   Format: {info.format}")
                print(f"   Channels: {info.channels}")
                if info.size_bytes:
                    print(f"   Size: {format_size(info.size_bytes)}")
                    print(
                        f"   Duration: {format_duration(info.size_bytes, info.samplerate, info.channels)}s"
                    )
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


def _print_kv(label: str, value: str) -> None:
    print(f"  {label:<14} {value}")


def _confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        resp = input(f"{prompt} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return resp in ("y", "yes")


def _short(text: str, width: int) -> str:
    if text is None:
        text = ""
    text = str(text)
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def _sanitize_field(text: str) -> str:
    if text is None:
        return ""
    return str(text).replace("\t", " ").replace("\n", " ").replace("\r", " ")


def _resolve_transfer_name(
    client: EP133Client, slot: int, entry: dict | None, raw: bool
) -> str:
    fs_name = str(entry.get("name") if entry else f"{slot:03d}.pcm")
    if raw:
        return fs_name

    node_name = None
    node_id = int(entry.get("node_id") or 0) if entry else 0
    if node_id:
        try:
            node_meta = client.get_node_metadata(node_id)
        except Exception:
            node_meta = None
        if node_meta:
            node_name = node_meta.get("name") or node_meta.get("sym")
            if node_name:
                return str(node_name)

    try:
        meta = client.info(
            slot, include_size=False, node_entry=entry
        )
        if meta.name:
            return meta.name
    except Exception:
        pass

    return fs_name


def _format_bar(used: int, total: int, width: int = 28) -> str:
    if total <= 0:
        return ""
    ratio = min(1.0, max(0.0, used / total))
    filled = int(round(ratio * width))
    return "█" * filled + "░" * (width - filled)


def _extract_total_memory(info: dict | None) -> int | None:
    if not info:
        return None
    keys = [
        "memory_total_bytes",
        "mem_total_bytes",
        "total_memory_bytes",
        "memory_bytes",
        "mem_bytes",
    ]
    for key in keys:
        val = info.get(key)
        if isinstance(val, (int, float)) and val > 0:
            return int(val)
        if isinstance(val, str) and val.isdigit():
            return int(val)
    return None


def cmd_status(args):
    """Show quick device status."""
    with EP133Client(args.device) as client:
        print(f"{Colors.CYAN}Device status{Colors.RESET}")

        info = None
        try:
            info = client.device_info()
        except Exception:
            info = None

        if info:
            name = info.get("device_name") or info.get("model") or info.get("name")
            version = info.get("device_version") or info.get("firmware") or info.get("version")
            serial = info.get("serial") or info.get("serial_number")
            sku = info.get("device_sku") or info.get("sku")
            _print_kv("Device", str(name) if name else "(unknown)")
            if version:
                _print_kv("Firmware", str(version))
            if sku:
                _print_kv("SKU", str(sku))
            if serial:
                _print_kv("Serial", str(serial))

            # Print any remaining keys as extras
            extras = {}
            for k, v in info.items():
                if k in {
                    "device_name",
                    "model",
                    "name",
                    "device_version",
                    "firmware",
                    "version",
                    "serial",
                    "serial_number",
                    "device_sku",
                    "sku",
                }:
                    continue
                extras[k] = v
            if extras:
                for k in sorted(extras.keys()):
                    _print_kv(k, str(extras[k]))
        else:
            _print_kv("Device", "(info unavailable)")

        try:
            sounds = client.list_sounds()
        except Exception as e:
            _print_kv("Samples", f"(list failed: {e})")
            return 1

        used = len(sounds)
        total_size = sum(int(e.get("size") or 0) for e in sounds.values())
        empty = MAX_SLOTS - used
        _print_kv("Samples", f"{used} used, {empty} empty")

        total_mem = _extract_total_memory(info)
        assumed = False
        if total_mem is None:
            total_mem = 64 * 1024 * 1024
            assumed = True
        pct = (total_size / total_mem) * 100 if total_mem else 0.0
        _print_kv(
            "Memory",
            f"{format_size(total_size)} / {format_size(total_mem)} ({pct:.0f}%)"
            + (" (assumed total)" if assumed else ""),
        )
        bar = _format_bar(total_size, total_mem)
        if bar:
            print(f"  {'':<14} {bar}")

    return 0


def cmd_tui(args):
    """Launch Textual TUI."""
    try:
        module = importlib.import_module("ko2_tui.app")
        app_cls = getattr(module, "KO2TUIApp")
    except ImportError:
        print("  ❌ TUI dependencies are missing. Install `textual` and try again.")
        return 1
    except AttributeError:
        print("  ❌ TUI module is installed but missing KO2TUIApp.")
        return 1

    debug_arg = getattr(args, "debug", None)
    debug_enabled = debug_arg is not None
    debug_path = None if debug_arg in (None, "__AUTO__") else debug_arg

    app = app_cls(
        device_name=args.device,
        debug=debug_enabled,
        debug_log=debug_path,
    )
    app.run()
    return 0


def cmd_audit(args):
    """Compare metadata sources for mismatches."""
    if args.range:
        slot_spec = parse_range(args.range)
        if isinstance(slot_spec, int):
            start = end = slot_spec
        else:
            start, end = slot_spec
    elif args.page:
        page_range = parse_page(args.page)
        if page_range is None:
            print("❌ Page must be 1-10")
            return 1
        start, end = page_range
    elif args.all:
        start, end = 1, MAX_SLOTS
    else:
        start, end = 1, 99

    if start > end:
        start, end = end, start

    show_all = bool(args.show_all)
    dump_path = args.dump
    dump_json = args.dump_json
    compare_fields = []
    if args.compare:
        compare_fields = [f.strip() for f in args.compare.split(",") if f.strip()]

    with EP133Client(args.device) as client:
        sounds = client.list_sounds()

        print(f"{Colors.CYAN}Metadata audit {start:03d}-{end:03d}{Colors.RESET}\n")
        print(
            f"  {'Slot':>4}  {'FS Name':<18}  {'Node Name':<18}  {'Meta Name':<18}  Flags"
        )
        print(f"  {'-'*4}  {'-'*18}  {'-'*18}  {'-'*18}  {'-'*12}")

        rows = 0
        dump_rows = []
        dump_json_rows = []
        stale = 0
        field_mismatch = 0
        node_missing = 0
        node_name_empty = 0

        for slot in range(start, end + 1):
            entry = sounds.get(slot)
            fs_name = str(entry.get("name") or "") if entry else ""

            flags = []
            node_name = ""
            node_meta = None
            if entry:
                node_id = int(entry.get("node_id") or 0)
                if node_id:
                    try:
                        node_meta = client.get_node_metadata(node_id)
                    except Exception:
                        node_meta = None
                if node_meta:
                    node_name = str(node_meta.get("name") or node_meta.get("sym") or "")
                    if not node_name:
                        flags.append("node-name-empty")
                        node_name_empty += 1
                else:
                    flags.append("node-meta-miss")
                    node_missing += 1

            meta_name = ""
            try:
                meta = client.get_meta_legacy(slot)
            except Exception:
                meta = None
            if meta:
                meta_name = str(meta.get("name") or meta.get("sym") or "")

            if not entry and meta_name:
                flags.append("stale")
                stale += 1
            if compare_fields and node_meta and meta:
                has_field_diff = False
                for field in compare_fields:
                    node_val = node_meta.get(field)
                    meta_val = meta.get(field)
                    if node_val is None and meta_val is None:
                        continue
                    if node_val != meta_val:
                        flags.append(f"{field}:diff")
                        has_field_diff = True
                if has_field_diff:
                    field_mismatch += 1

            issue = bool(flags)
            if show_all or issue:
                rows += 1
                print(
                    f"  {slot:>4}  "
                    f"{_short(fs_name, 18):<18}  "
                    f"{_short(node_name, 18):<18}  "
                    f"{_short(meta_name, 18):<18}  "
                    f"{', '.join(flags)}"
                )
            if dump_path:
                dump_rows.append(
                    (
                        slot,
                        _sanitize_field(fs_name),
                        _sanitize_field(node_name),
                        _sanitize_field(meta_name),
                        ",".join(flags),
                    )
                )
            if dump_json:
                dump_json_rows.append(
                    {
                        "slot": slot,
                        "fs": entry or None,
                        "node": node_meta or None,
                        "meta": meta or None,
                        "flags": flags,
                    }
                )

        print()
        print(f"  Slots scanned: {end - start + 1}")
        print(f"  Rows shown:    {rows}")
        print(f"  Stale meta:    {stale}")
        print(f"  Node meta missing: {node_missing}")
        print(f"  Node name empty:  {node_name_empty}")
        if compare_fields:
            print(f"  Field mismatch: {field_mismatch}")

        if dump_path:
            try:
                with open(dump_path, "w", encoding="utf-8") as f:
                    f.write("slot\tfs_name\tnode_name\tmeta_name\tflags\n")
                    for slot, fs_name, node_name, meta_name, flags in dump_rows:
                        f.write(
                            f"{slot}\t{fs_name}\t{node_name}\t{meta_name}\t{flags}\n"
                        )
                print(f"\n  Wrote audit file: {dump_path}")
            except OSError as e:
                print(f"\n  ❌ Failed to write audit file: {e}")

        if dump_json:
            try:
                with open(dump_json, "w", encoding="utf-8") as f:
                    for row in dump_json_rows:
                        f.write(
                            json.dumps(row, sort_keys=True, separators=(",", ":"))
                            + "\n"
                        )
                print(f"\n  Wrote audit JSONL: {dump_json}")
            except OSError as e:
                print(f"\n  ❌ Failed to write audit JSONL: {e}")

    return 0


def optimize_sample(
    input_path: Path, output_path: Optional[Path] = None
) -> tuple[bool, str, int, int]:
    """
    Optimize a WAV file for EP-133 using audio2ko2 or sox.

    Downmixes stereo to mono, and downsamples only if rate > SAMPLE_RATE (46875 Hz).
    The device stores samples below 46875 Hz at their original rate (firmware OS 2.0+),
    so there is no reason to upsample.

    Returns:
        (success, message, original_size, optimized_size)
    """
    original_size = input_path.stat().st_size

    if output_path is None:
        output_path = input_path.with_suffix(".opt.wav")

    with wave.open(str(input_path)) as w:
        in_channels = w.getnchannels()
        in_rate = w.getframerate()
        in_depth = w.getsampwidth() * 8

    needs_downmix = in_channels > 1
    needs_resample = in_rate > SAMPLE_RATE
    needs_requantize = in_depth > 16

    if not needs_downmix and not needs_resample and not needs_requantize:
        return True, "already optimal", original_size, original_size

    # Try audio2ko2 first
    audio2ko2 = Path.home() / "proj" / "audio2ko2" / "audio2ko2"
    if audio2ko2.exists():
        try:
            result = subprocess.run(
                [str(audio2ko2), str(input_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                # audio2ko2 creates output with _ko2 suffix
                ko2_output = input_path.with_stem(input_path.stem + "_ko2")
                if ko2_output.exists():
                    shutil.move(ko2_output, output_path)
                    opt_size = output_path.stat().st_size
                    return True, "optimized with audio2ko2", original_size, opt_size
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # Fall back to sox — only pass flags for what actually needs changing
    sox_args = ["sox", str(input_path)]
    if needs_downmix:
        sox_args += ["-c", "1"]
    if needs_resample:
        sox_args += ["-r", str(SAMPLE_RATE)]
    if needs_requantize:
        sox_args += ["-b", "16"]
    sox_args.append(str(output_path))

    try:
        subprocess.run(sox_args, capture_output=True, check=True, timeout=30)
        opt_size = output_path.stat().st_size
        return True, "optimized with sox", original_size, opt_size
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ) as e:
        return False, f"error: {e}", original_size, 0


def cmd_optimize(args):
    """Optimize a single sample on device."""
    slot = args.slot

    with EP133Client(args.device) as client:
        # Lightweight check: slot exists and get the name for display/re-upload.
        # No include_size to avoid triggering a DownloadInitRequest here.
        try:
            info = client.info(slot, include_size=False)
        except SlotEmptyError:
            print(f"❌ Slot {slot} is empty")
            return 1

        if not _confirm(f"Optimize slot {slot:03d} ({info.name})?", bool(args.yes)):
            print("  Cancelled")
            return 0

        print(f"  {Colors.FG_DIM}Downloading...{Colors.RESET}")
        with tempfile.TemporaryDirectory(prefix=f"ko2-slot{slot:03d}-") as td:
            temp_path = Path(td) / f"slot{slot:03d}.wav"
            try:
                client.get(slot, temp_path)
            except EP133Error as e:
                print(f"  ❌ Download failed: {e}")
                return 1

            # Evaluate the file independently — no metadata involved from here on.
            with wave.open(str(temp_path)) as w:
                original_size = temp_path.stat().st_size
                in_channels = w.getnchannels()
                in_rate = w.getframerate()
                in_depth = w.getsampwidth() * 8
                duration = w.getnframes() / w.getframerate()

            print(
                f"  {in_channels}ch  {in_rate} Hz  {in_depth}-bit  "
                f"{format_size(original_size)}  {duration:.2f}s"
            )

            print(f"  {Colors.FG_DIM}Optimizing...{Colors.RESET}")
            success, msg, _, opt_size = optimize_sample(temp_path)

            if not success:
                print(f"  ❌ {msg}")
                return 1

            if msg == "already optimal":
                print(f"  {Colors.FG_GREEN}✓ Already optimal{Colors.RESET}")
                return 0

            savings = original_size - opt_size
            savings_pct = (savings / original_size) * 100

            backup_path = backup_copy(temp_path, slot=slot, name_hint=info.name)
            print(f"  {Colors.FG_DIM}Backup:{Colors.RESET} {backup_path}")
            print(f"  {format_size(original_size)} → {format_size(opt_size)}  ({savings_pct:.1f}% saved)")

            if savings < 5 * 1024:
                print(f"  {Colors.FG_YELLOW}⚠ Savings too small (<5KB), skipping upload{Colors.RESET}")
                return 0

            opt_path = temp_path.with_suffix(".opt.wav")
            print(f"  {Colors.FG_DIM}Uploading...{Colors.RESET}")
            try:
                client.put(opt_path, slot, name=info.name, progress=False)
                print(f"  {Colors.FG_GREEN}✓ Done{Colors.RESET}")
            except EP133Error as e:
                print(f"  ❌ Upload failed: {e}")
                return 1

    return 0


def cmd_optimize_all(args):
    """Optimize stereo samples on device (downmix to mono).

    Scan phase:
      - Samples with confirmed metadata (channels_known=True): use channels > 1 directly.
      - Samples with null/missing metadata (channels_known=False): probe with a
        single-chunk partial download and _detect_channels heuristic.
    """
    min_size = args.min * 1024 if args.min else 0
    slot_filter = getattr(args, "slot", None)

    with EP133Client(args.device) as client:
        print(f"{Colors.CYAN}Scanning...{Colors.RESET}\n")

        sounds = client.list_sounds()
        if slot_filter is not None:
            sounds = {k: v for k, v in sounds.items() if k == slot_filter}

        meta_stereo = []
        to_probe = []

        for slot, e in sorted(sounds.items()):
            size_bytes = int(e.get("size") or 0)
            if min_size and size_bytes <= min_size:
                continue
            try:
                info = client.info(slot, include_size=False, node_entry=e)
            except Exception:
                continue

            if info.channels_known:
                if info.channels > 1:
                    info.size_bytes = size_bytes
                    meta_stereo.append(info)
                # else: metadata confirmed mono, skip
            else:
                info.size_bytes = size_bytes
                to_probe.append(info)

        probe_stereo = []
        if to_probe:
            print(f"  {len(to_probe)} samples without channel metadata — probing...\n")
            for info in to_probe:
                channels, probed_size = client.probe_channels(info.slot)
                if probed_size:
                    info.size_bytes = probed_size
                if channels > 1:
                    info.channels = 2
                    probe_stereo.append(info)
                    print(f"    Slot {info.slot:03d}: {info.name[:30]:<30} stereo detected")

        candidates = meta_stereo + probe_stereo

        if not candidates:
            print(f"  {Colors.FG_GREEN}No stereo samples found{Colors.RESET}")
            return 0

        print(f"\n  Found {len(candidates)} stereo samples:\n")
        total_original = 0
        for info in candidates:
            total_original += info.size_bytes
            print(
                f"    Slot {info.slot:03d}: {info.name[:30]:<30} {format_size(info.size_bytes)}"
            )

        print(f"\n  Total: {format_size(total_original)}")

        assume_yes = bool(args.yes)
        if not _confirm(f"Optimize {len(candidates)} samples?", assume_yes):
            print("  Cancelled")
            return 0

        # Process each sample
        print()
        optimized = 0
        total_savings = 0

        for i, info in enumerate(candidates, 1):
            print(f"\n[{i}/{len(candidates)}] Slot {info.slot}: {info.name}")

            with tempfile.TemporaryDirectory(prefix=f"ko2-slot{info.slot:03d}-") as td:
                temp_path = Path(td) / f"slot{info.slot:03d}.wav"
                opt_path = temp_path.with_suffix(".opt.wav")

                # Download
                try:
                    client.get(info.slot, temp_path)
                except EP133Error as e:
                    print(f"  ❌ Download failed: {e}")
                    continue

                original_size = temp_path.stat().st_size

                # Backup
                backup_path = backup_copy(temp_path, slot=info.slot, name_hint=info.name)
                print(f"  {Colors.FG_DIM}Backup:{Colors.RESET} {backup_path}")

                # Optimize
                success, msg, _, opt_size = optimize_sample(temp_path, output_path=opt_path)

                if not success:
                    print(f"  ❌ {msg}")
                    continue

                if msg == "already optimal":
                    print(f"  ⊘ Already optimal (channel count confirmed in WAV header)")
                    continue

                savings = original_size - opt_size

                # Skip if savings too small
                if savings < 5 * 1024:
                    print(f"  ⊘ Skipped (savings: {format_size(savings)})")
                    continue

                # Upload
                try:
                    client.put(opt_path, info.slot, name=info.name, progress=False)
                    print(
                        f"  {Colors.FG_GREEN}✓ Saved {format_size(savings)} ({savings/original_size*100:.1f}%){Colors.RESET}"
                    )
                    optimized += 1
                    total_savings += savings
                except EP133Error as e:
                    print(f"  ❌ Upload failed: {e}")

        print(f"\n{Colors.CYAN}{'='*40}{Colors.RESET}")
        print(f"  Optimized: {optimized}/{len(candidates)} samples")
        print(f"  Total savings: {format_size(total_savings)}")

    return 0


def cmd_get(args):
    """Download sample from device."""
    slot = validate_slot(args.slot)
    output = Path(args.output) if args.output else None

    # Determine final output path to check for existence
    if output and output.exists():
        if not _confirm(f"File '{output}' already exists. Overwrite?", bool(getattr(args, "yes", False))):
            print("  Cancelled")
            return 0

    with EP133Client(args.device) as client:
        try:
            print(f"  Downloading slot {slot}...")
            # If output is None, client.get will generate a name based on metadata
            result_path = client.get(slot, output)
            print(f"  {Colors.FG_GREEN}✓{Colors.RESET} Downloaded to {result_path}")
        except SlotEmptyError:
            print(f"  ❌ Slot {slot} is empty")
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


def _download_to_path(client: EP133Client, slot: int, path: Path) -> None:
    client.get(slot, path)


def cmd_move(args):
    """Move sample between slots (swap if destination occupied)."""
    src = int(args.src)
    dst = int(args.dst)
    raw = bool(args.raw)
    assume_yes = bool(args.yes)

    if src == dst:
        print("  No-op: source and destination are the same")
        return 0

    with EP133Client(args.device) as client:
        sounds = client.list_sounds()
        src_entry = sounds.get(src)
        if not src_entry:
            print(f"  ❌ Slot {src:03d} is empty")
            return 1
        dst_entry = sounds.get(dst)

        src_name = _resolve_transfer_name(client, src, src_entry, raw)
        dst_name = _resolve_transfer_name(client, dst, dst_entry, raw) if dst_entry else ""

        if dst_entry:
            prompt = (
                f"Swap slot {src:03d} ({src_name}) with {dst:03d} ({dst_name})?"
            )
        else:
            prompt = f"Move slot {src:03d} ({src_name}) → {dst:03d}?"

        if not _confirm(prompt, assume_yes):
            print("  Cancelled")
            return 0

        with tempfile.TemporaryDirectory(prefix="ko2-move-") as td:
            temp_dir = Path(td)
            src_path = temp_dir / f"slot{src:03d}.wav"
            dst_path = temp_dir / f"slot{dst:03d}.wav"

            try:
                _download_to_path(client, src, src_path)
                backup_copy(src_path, slot=src, name_hint=src_name)

                if dst_entry:
                    _download_to_path(client, dst, dst_path)
                    backup_copy(dst_path, slot=dst, name_hint=dst_name)

                if dst_entry:
                    client.delete(src)
                    client.delete(dst)
                    client.put(src_path, dst, name=src_name, progress=False)
                    client.put(dst_path, src, name=dst_name, progress=False)
                    print(
                        f"  {Colors.FG_GREEN}✓{Colors.RESET} Swapped {src:03d} ↔ {dst:03d}"
                    )
                else:
                    client.put(src_path, dst, name=src_name, progress=False)
                    client.delete(src)
                    print(
                        f"  {Colors.FG_GREEN}✓{Colors.RESET} Moved {src:03d} → {dst:03d}"
                    )
            except EP133Error as e:
                if dst_entry:
                    try:
                        client.put(src_path, src, name=src_name, progress=False)
                    except Exception:
                        pass
                    try:
                        client.put(dst_path, dst, name=dst_name, progress=False)
                    except Exception:
                        pass
                print(f"  ❌ Move failed: {e}")
                return 1

    return 0


def cmd_copy(args):
    """Copy sample between slots."""
    src = int(args.src)
    dst = int(args.dst)
    raw = bool(args.raw)
    assume_yes = bool(args.yes)

    if src == dst:
        print("  No-op: source and destination are the same")
        return 0

    with EP133Client(args.device) as client:
        sounds = client.list_sounds()
        src_entry = sounds.get(src)
        if not src_entry:
            print(f"  ❌ Slot {src:03d} is empty")
            return 1
        dst_entry = sounds.get(dst)

        src_name = _resolve_transfer_name(client, src, src_entry, raw)
        dst_name = _resolve_transfer_name(client, dst, dst_entry, raw) if dst_entry else ""

        if dst_entry:
            prompt = (
                f"Overwrite slot {dst:03d} ({dst_name}) with {src:03d} ({src_name})?"
            )
        else:
            prompt = f"Copy slot {src:03d} ({src_name}) → {dst:03d}?"

        if not _confirm(prompt, assume_yes):
            print("  Cancelled")
            return 0

        with tempfile.TemporaryDirectory(prefix="ko2-copy-") as td:
            temp_dir = Path(td)
            src_path = temp_dir / f"slot{src:03d}.wav"
            dst_path = temp_dir / f"slot{dst:03d}.wav"

            try:
                _download_to_path(client, src, src_path)
                backup_copy(src_path, slot=src, name_hint=src_name)

                if dst_entry:
                    _download_to_path(client, dst, dst_path)
                    backup_copy(dst_path, slot=dst, name_hint=dst_name)
                    client.delete(dst)

                client.put(src_path, dst, name=src_name, progress=False)
                print(
                    f"  {Colors.FG_GREEN}✓{Colors.RESET} Copied {src:03d} → {dst:03d}"
                )
            except EP133Error as e:
                if dst_entry:
                    try:
                        client.put(dst_path, dst, name=dst_name, progress=False)
                    except Exception:
                        pass
                print(f"  ❌ Copy failed: {e}")
                return 1

    return 0


def cmd_delete(args):
    """Delete sample from slot."""
    with EP133Client(args.device) as client:
        try:
            info = client.info(args.slot)
            prompt = f"Delete slot {args.slot:03d} ({info.name})?"
            if not _confirm(prompt, bool(args.yes)):
                print("  Cancelled")
                return 0
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
        page_range = parse_page(args.page)
        if page_range is None:
            print("  ❌ Page must be 1-10")
            return 1
        start, end = page_range
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
    raw = bool(args.raw)
    assume_yes = bool(args.yes)

    print(f"{Colors.CYAN}Squashing slots {start:03d}-{end:03d}...{Colors.RESET}")
    if dry_run:
        print(
            f"  {Colors.FG_YELLOW}DRY RUN MODE{Colors.RESET} (use --execute to apply)"
        )

    with EP133Client(args.device) as client:
        sounds = client.list_sounds()
        used_slots = [s for s in sorted(sounds.keys()) if start <= s <= end]

        if not used_slots:
            print(f"  {Colors.FG_DIM}No samples found{Colors.RESET}")
            return 0

        # Calculate squash mapping
        mapping = {}  # old_slot -> new_slot
        target_slot = start

        for slot in used_slots:
            if slot != target_slot:
                mapping[slot] = target_slot
            target_slot += 1

        if not mapping:
            print(f"  {Colors.FG_GREEN}✓ Already compacted{Colors.RESET}")
            return 0

        # Show mapping
        print(f"  Will move {len(mapping)} samples:\n")
        for old_slot, new_slot in mapping.items():
            entry = sounds.get(old_slot)
            name = _resolve_transfer_name(client, old_slot, entry, raw)
            print(f"    {old_slot:03d} → {new_slot:03d}  {name[:30]:<30}")

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
            print(
                f"\n  {Colors.FG_DIM}NOTE: Project pad references are NOT updated.{Colors.RESET}"
            )
            print(
                f"  {Colors.FG_DIM}      (project update protocol not yet available){Colors.RESET}"
            )
            return 0

        if not _confirm(f"Execute squash for {len(mapping)} moves?", assume_yes):
            print("  Cancelled")
            return 0

        # Execute squash
        print(f"\n  {Colors.CYAN}Executing...{Colors.RESET}\n")

        for old_slot, new_slot in mapping.items():
            # Download from old slot
            print(f"  [{old_slot:03d} → {new_slot:03d}] ", end="", flush=True)
            try:
                entry = sounds.get(old_slot)
                name = _resolve_transfer_name(client, old_slot, entry, raw)
                with tempfile.TemporaryDirectory(
                    prefix=f"ko2-move{old_slot:03d}-"
                ) as td:
                    temp_path = Path(td) / f"slot{old_slot:03d}.wav"
                    client.get(old_slot, temp_path)
                    backup_copy(temp_path, slot=old_slot, name_hint=name)

                    deleted = False
                    try:
                        # Delete old slot
                        client.delete(old_slot)
                        deleted = True

                        # Upload to new slot
                        client.put(temp_path, new_slot, name=name, progress=False)
                    except EP133Error:
                        if deleted:
                            try:
                                client.put(
                                    temp_path, old_slot, name=name, progress=False
                                )
                                print(
                                    f"\n  {Colors.FG_YELLOW}⚠ Restored slot {old_slot:03d} after failure{Colors.RESET}"
                                )
                            except Exception:
                                pass
                        raise
                print(f"{Colors.FG_GREEN}✓{Colors.RESET}")
            except EP133Error as e:
                print(f"{Colors.FG_RED}✗ {e}{Colors.RESET}")

        print(f"\n  {Colors.FG_GREEN}✓ Squash complete{Colors.RESET}")
        print(f"  {Colors.FG_DIM}Freed {len(mapping)} slots{Colors.RESET}")

    return 0


def cmd_fs_ls(args):
    """Debug: list filesystem entries (FILE LIST) for a node (default: /sounds)."""
    node_id = int(args.node)
    slot_spec = parse_range(args.range) if args.range else None
    if slot_spec is None:
        start, end = 1, MAX_SLOTS
    elif isinstance(slot_spec, int):
        start = end = slot_spec
    else:
        start, end = slot_spec

    with EP133Client(args.device) as client:
        if args.raw:
            entries = client.list_directory_raw(node_id=node_id)
            if not entries:
                print("  (no entries)")
                return 0

            print(f"  Node {node_id}: {len(entries)} entries (raw)\n")
            print(
                f"  {'Hi':>2}  {'Lo':>2}  {'N14':>5}  {'N16':>5}  {'Dec':>5}  {'Slot':>4}  {'Flags':>5}  {'Size':>7}  Name"
            )
            print(
                f"  {'-'*2}  {'-'*2}  {'-'*5}  {'-'*5}  {'-'*5}  {'-'*4}  {'-'*5}  {'-'*7}  {'-'*30}"
            )

            for e in entries:
                is_dir = bool(e.get("is_dir"))
                hi = int(e.get("hi") or 0)
                lo = int(e.get("lo") or 0)
                flags = int(e.get("flags") or 0)
                size = int(e.get("size") or 0)
                name = str(e.get("name") or "")
                n14 = decode_14bit(hi, lo)
                n16 = (hi << 8) | lo
                dec = decode_node_id(hi, lo, name)
                slot = dec - 1000 if (1001 <= dec <= 1999) else 0

                slot_from_name = 0
                m = re.match(r"^(\d{1,3})", name)
                if m:
                    slot_from_name = int(m.group(1))
                slot_display = slot_from_name or slot
                if not is_dir and not (start <= slot_display <= end):
                    continue
                slot_str = f"{slot_display:03d}" if not is_dir and slot_display else "DIR"
                print(
                    f"  {hi:02X}  {lo:02X}  {n14:>5}  {n16:>5}  {dec:>5}  {slot_str:>4}  0x{flags:02X}  {format_size(size):>7}  {name}"
                )
        else:
            entries = client.list_directory(node_id=node_id)
            if not entries:
                print("  (no entries)")
                return 0

            print(f"  Node {node_id}: {len(entries)} entries\n")
            print(f"  {'Slot':>4}  {'Node':>4}  {'Flags':>5}  {'Size':>7}  Name")
            print(f"  {'-'*4}  {'-'*4}  {'-'*5}  {'-'*7}  {'-'*30}")

            for e in entries:
                is_dir = bool(e.get("is_dir"))
                nid = int(e.get("node_id") or 0)
                flags = int(e.get("flags") or 0)
                size = int(e.get("size") or 0)
                name = str(e.get("name") or "")
                slot = nid - 1000 if (1001 <= nid <= 1999) else 0
                if not is_dir and not (start <= slot <= end):
                    continue
                slot_str = f"{slot:03d}" if not is_dir and slot else "DIR"
                print(
                    f"  {slot_str:>4}  {nid:>4}  0x{flags:02X}  {format_size(size):>7}  {name}"
                )

    return 0


def cmd_rename(args):
    """Rename a sample slot via filesystem metadata (backs up audio first)."""
    slot = int(args.slot)
    new_name = str(args.name)

    with EP133Client(args.device) as client:
        try:
            info = client.info(slot, include_size=False)
        except SlotEmptyError:
            print(f"  ❌ Slot {slot:03d} is empty")
            return 1

        with tempfile.TemporaryDirectory(prefix=f"ko2-rename{slot:03d}-") as td:
            temp_path = Path(td) / f"slot{slot:03d}.wav"
            client.get(slot, temp_path)
            backup_path = backup_copy(temp_path, slot=slot, name_hint=info.name)
            print(f"  {Colors.FG_DIM}Backup:{Colors.RESET} {backup_path}")

        client.rename(slot, new_name)
        print(
            f"  {Colors.FG_GREEN}✓{Colors.RESET} Renamed slot {slot:03d} → {new_name}"
        )

    return 0


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


def main():
    parser = argparse.ArgumentParser(
        description="KO2 - EP-133 KO-II Command Line Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    status_parser = subparsers.add_parser(
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

    # move
    mv_parser = subparsers.add_parser("mv", help="Move sample between slots")
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

    move_parser = subparsers.add_parser("move", help="Move sample between slots")
    move_parser.add_argument("src", type=validate_slot, help="Source slot (1-999)")
    move_parser.add_argument("dst", type=validate_slot, help="Destination slot (1-999)")
    move_parser.add_argument(
        "--raw", "--original", dest="raw", action="store_true", help="Use raw filename"
    )
    move_parser.add_argument(
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
    cp_parser = subparsers.add_parser("cp", help="Copy sample between slots")
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

    copy_parser = subparsers.add_parser("copy", help="Copy sample between slots")
    copy_parser.add_argument("src", type=validate_slot, help="Source slot (1-999)")
    copy_parser.add_argument("dst", type=validate_slot, help="Destination slot (1-999)")
    copy_parser.add_argument(
        "--raw", "--original", dest="raw", action="store_true", help="Use raw filename"
    )
    copy_parser.add_argument(
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
    delete_parser = subparsers.add_parser("delete", help="Delete sample")
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

    # rm: alias for delete
    rm_parser = subparsers.add_parser("rm", help="Delete sample (alias)")
    rm_parser.add_argument("slot", type=validate_slot, help="Slot number (1-999)")
    rm_parser.add_argument(
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

    # remove: alias for delete
    remove_parser = subparsers.add_parser("remove", help="Delete sample (alias)")
    remove_parser.add_argument("slot", type=validate_slot, help="Slot number (1-999)")
    remove_parser.add_argument(
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

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Auto-select device for all commands.
    device = find_device()
    if not device:
        print("  ❌ EP-133 not found. Connect via USB.")
        return 1
    args.device = device

    # Dispatch
    commands = {
        "ls": cmd_ls,
        "info": cmd_info,
        "status": cmd_status,
        "audit": cmd_audit,
        "get": cmd_get,
        "put": cmd_put,
        "mv": cmd_move,
        "move": cmd_move,
        "cp": cmd_copy,
        "copy": cmd_copy,
        "delete": cmd_delete,
        "rm": cmd_delete,  # Alias
        "remove": cmd_delete,
        "optimize": cmd_optimize,
        "optimize-all": cmd_optimize_all,
        "group": cmd_group,
        "squash": cmd_squash,
        "fs-ls": cmd_fs_ls,
        "rename": cmd_rename,
        "tui": cmd_tui,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
