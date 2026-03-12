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
    ko2 fingerprint ...        - Fingerprint/cache waveform hashes in KV store
"""
import sys
import re
import shutil
import json
import hashlib
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

    import sys
    from pathlib import Path as _Path
    _src = str(_Path(__file__).resolve().parent / "src")
    if _src not in sys.path:
        sys.path.insert(0, _src)
    from core.ops import (
        optimize_sample,
        resolve_transfer_name as _resolve_transfer_name,
        squash_scan as _squash_scan,
        squash_process as _squash_process,
    )
    from ko2_display import View, TerminalView, SilentView, JsonView, SampleFormat
    from ko2_parser import build_parser, validate_slot, parse_range
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)


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



def _ls_scan_fs(
    client, start: int, end: int, name_source: str, view: View
) -> tuple[list, bool]:
    """Fetch /sounds filesystem listing and build SampleInfo list for start..end.

    Returns (samples, success).  On failure returns ([], False) so the caller
    can fall back to slot-scan.  If source='fs' the caller should treat False
    as a hard error.
    """
    view.step("Fetching /sounds listing...")
    sounds = client.list_sounds()
    all_slots = list(range(start, end + 1))
    total_slots = len(all_slots)
    samples = []

    for idx, slot in enumerate(all_slots, 1):
        if total_slots:
            view.progress(idx, total_slots, f"(slot {slot})")
        e = sounds.get(slot)
        if not e:
            samples.append(empty_sample(slot))
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
                    samplerate = int(node_meta.get("samplerate") or SAMPLE_RATE)
                if "channels" in node_meta:
                    channels = int(node_meta.get("channels") or 0)

        need_info = node_meta is None or channels == 0
        if need_info:
            try:
                meta = client.info(slot, include_size=False, node_entry=e)
                samplerate = int(meta.samplerate or samplerate or SAMPLE_RATE)
                channels = int(meta.channels or channels or 0)
                meta_name = meta.name
            except Exception:
                pass

        name = choose_display_name(fs_name, meta_name, node_name, slot, name_source)
        samples.append(
            SampleInfo(
                slot=slot,
                name=name,
                samplerate=samplerate,
                channels=channels,
                size_bytes=size_bytes,
            )
        )

    if total_slots:
        print()

    return samples, True


def _ls_scan_slots(client, start: int, end: int, view: View) -> list:
    """Probe each slot individually and return a SampleInfo list for start..end."""
    view.step(f"Scanning slots {start:03d}-{end:03d}...")
    samples = []
    for slot in range(start, end + 1):
        view.progress(slot - start + 1, end - start + 1, f"(slot {slot})")
        try:
            info = client.info(slot, include_size=True)
            # Metadata can persist after delete; treat size==0 as empty for listing.
            if info.size_bytes:
                samples.append(info)
            else:
                samples.append(empty_sample(slot))
        except SlotEmptyError:
            samples.append(empty_sample(slot))
    print()  # Clear progress line
    return samples


def cmd_ls(args, view: View):
    """List samples by pages."""
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
            view.error(f"Range must be within 1-{MAX_SLOTS}")
            return 1
    elif args.page:
        page_range = parse_page(args.page)
        if page_range is None:
            view.error("Page must be 1-10")
            return 1
        start, end = page_range
    elif args.all:
        start, end = 1, MAX_SLOTS
    else:
        start, end = 1, 99  # Default to first page

    source = args.source
    name_source = args.name_source

    with EP133Client(args.device) as client:
        # Prefer filesystem listing (/sounds/) for ground truth; slot-scan can be stale.
        samples = []
        entries = None

        if source in ("auto", "fs"):
            try:
                samples, _ = _ls_scan_fs(client, start, end, name_source, view)
                entries = samples  # non-None signals fs path succeeded
            except Exception as e:
                if source == "fs":
                    view.error(f"Failed to list /sounds via filesystem API: {e}")
                    return 1
                entries = None

        if entries is None:
            if source == "auto":
                view.warn("Falling back to slot-scan (may be stale).")
            elif source == "scan":
                pass
            else:
                view.error("Invalid source")
                return 1

        if entries is None and source in ("auto", "scan"):
            samples = _ls_scan_slots(client, start, end, view)

        samples = [s for s in samples if start <= s.slot <= end]
        view.render_samples(samples, start, end)

    return 0


def cmd_info(args, view: View):
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
                view.sample_detail(info)
            except SlotEmptyError:
                view.error(f"Slot {slot_spec} is empty")
                return 1
        else:
            start, end = slot_spec
            if start > end:
                start, end = end, start

            samples = []
            empty_count = 0

            for slot in range(start, end + 1):
                view.progress(slot - start + 1, end - start + 1)
                try:
                    info = client.info(slot, include_size=True)
                    samples.append(info)
                except SlotEmptyError:
                    empty_count += 1
            print()

            if samples:
                view.render_samples(samples, start, end)
            else:
                view.step("(all empty)")

    return 0


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


# _resolve_transfer_name imported from core.ops above


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


def cmd_status(args, view: View):
    """Show quick device status."""
    with EP133Client(args.device) as client:
        view.section("Device status")

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
            view.kv("Device", str(name) if name else "(unknown)")
            if version:
                view.kv("Firmware", str(version))
            if sku:
                view.kv("SKU", str(sku))
            if serial:
                view.kv("Serial", str(serial))

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
                    view.kv(k, str(extras[k]))
        else:
            view.kv("Device", "(info unavailable)")

        try:
            sounds = client.list_sounds()
        except Exception as e:
            view.kv("Samples", f"(list failed: {e})")
            return 1

        used = len(sounds)
        total_size = sum(int(e.get("size") or 0) for e in sounds.values())
        empty = MAX_SLOTS - used
        view.kv("Samples", f"{used} used, {empty} empty")

        total_mem = _extract_total_memory(info)
        assumed = False
        if total_mem is None:
            total_mem = 64 * 1024 * 1024
            assumed = True
        pct = (total_size / total_mem) * 100 if total_mem else 0.0
        view.kv(
            "Memory",
            f"{SampleFormat.size(total_size)} / {SampleFormat.size(total_mem)} ({pct:.0f}%)"
            + (" (assumed total)" if assumed else ""),
        )
        bar = _format_bar(total_size, total_mem)
        if bar:
            view.kv("", bar)

    return 0


def cmd_tui(args, view: View):
    """Launch Textual TUI."""
    try:
        module = importlib.import_module("ko2_tui.app")
        app_cls = getattr(module, "TUIApp")
    except ImportError:
        view.error("TUI dependencies are missing. Install `textual` and try again.")
        return 1
    except AttributeError:
        view.error("TUI module is installed but missing TUIApp.")
        return 1

    debug_arg = getattr(args, "debug", None)
    debug_enabled = debug_arg is not None
    debug_path = None if debug_arg in (None, "__AUTO__") else debug_arg

    app = app_cls(
        device_name=args.device,
        debug=debug_enabled,
        debug_log=debug_path,
        dialog_log=getattr(args, "dialog_log", None),
    )
    app.run()
    return 0


def cmd_audit(args, view: View):
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
            view.error("Page must be 1-10")
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

        view.section(f"Metadata audit {start:03d}-{end:03d}")
        print()
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


# optimize_sample imported from core.ops above


def cmd_optimize(args, view: View):
    """Optimize a single sample on device."""
    slot = args.slot
    downsample_rate = getattr(args, 'rate', None)
    speed = getattr(args, 'speed', None)
    pitch = getattr(args, 'pitch', 0.0)
    mono = not getattr(args, 'keep_stereo', False)

    with EP133Client(args.device) as client:
        # Lightweight check: slot exists and get the name for display/re-upload.
        # No include_size to avoid triggering a DownloadInitRequest here.
        try:
            info = client.info(slot, include_size=False)
        except SlotEmptyError:
            view.error(f"Slot {slot} is empty")
            return 1

        if not _confirm(f"Optimize slot {slot:03d} ({info.name})?", bool(args.yes)):
            view.step("Cancelled")
            return 0

        view.step("Downloading...")
        with tempfile.TemporaryDirectory(prefix=f"ko2-slot{slot:03d}-") as td:
            temp_path = Path(td) / f"slot{slot:03d}.wav"
            try:
                client.get(slot, temp_path)
            except EP133Error as e:
                view.error(f"Download failed: {e}")
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
                f"{SampleFormat.size(original_size)}  {duration:.2f}s"
            )

            view.step("Optimizing...")
            success, msg, _, opt_size = optimize_sample(temp_path, downsample_rate=downsample_rate, speed=speed, mono=mono)

            if not success:
                view.error(msg)
                return 1

            if msg == "already optimal":
                view.success("Already optimal")
                return 0

            savings = original_size - opt_size
            savings_pct = (savings / original_size) * 100

            backup_path = backup_copy(temp_path, slot=slot, name_hint=info.name)
            view.kv("Backup:", str(backup_path))
            print(f"  {SampleFormat.size(original_size)} → {SampleFormat.size(opt_size)}  ({savings_pct:.1f}% saved)")

            if savings < 5 * 1024 and speed is None and downsample_rate is None:
                view.warn("Savings too small (<5KB), skipping upload")
                return 0

            opt_path = temp_path.with_suffix(".opt.wav")
            view.step("Uploading...")
            try:
                client.put(opt_path, slot, name=info.name, progress=False, pitch=pitch)
                view.success("Done")
            except EP133Error as e:
                view.error(f"Upload failed: {e}")
                return 1

    return 0


def _optimize_all_scan(
    sounds: dict, client, min_size: int, view: View
) -> list:
    """Return list of SampleInfo candidates that are stereo (or unconfirmed).

    Two-pass strategy:
      1. Slots with confirmed metadata (channels_known=True): include if channels > 1.
      2. Slots with missing channel metadata: probe via a partial download and heuristic.
    """
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
            # else: metadata confirmed mono — skip
        else:
            info.size_bytes = size_bytes
            to_probe.append(info)

    probe_stereo = []
    if to_probe:
        view.step(f"{len(to_probe)} samples without channel metadata — probing...")
        print()
        for info in to_probe:
            channels, probed_size = client.probe_channels(info.slot)
            if probed_size:
                info.size_bytes = probed_size
            if channels > 1:
                info.channels = 2
                probe_stereo.append(info)
                print(f"    Slot {info.slot:03d}: {info.name[:30]:<30} stereo detected")

    return meta_stereo + probe_stereo


def _optimize_all_process(
    candidates: list, client, view: View
) -> tuple[int, int]:
    """Optimize each candidate: download, backup, optimize, upload if worthwhile.

    Returns (optimized_count, total_savings_bytes).
    """
    optimized = 0
    total_savings = 0

    for i, info in enumerate(candidates, 1):
        view.section(f"[{i}/{len(candidates)}] Slot {info.slot}: {info.name}")

        with tempfile.TemporaryDirectory(prefix=f"ko2-slot{info.slot:03d}-") as td:
            temp_path = Path(td) / f"slot{info.slot:03d}.wav"
            opt_path = temp_path.with_suffix(".opt.wav")

            try:
                client.get(info.slot, temp_path)
            except EP133Error as e:
                view.error(f"Download failed: {e}")
                continue

            original_size = temp_path.stat().st_size

            backup_path = backup_copy(temp_path, slot=info.slot, name_hint=info.name)
            view.kv("Backup:", str(backup_path))

            success, msg, _, opt_size = optimize_sample(temp_path, output_path=opt_path)

            if not success:
                view.error(msg)
                continue

            if msg == "already optimal":
                print(f"  ⊘ Already optimal (channel count confirmed in WAV header)")
                continue

            savings = original_size - opt_size

            if savings < 5 * 1024:
                print(f"  ⊘ Skipped (savings: {SampleFormat.size(savings)})")
                continue

            try:
                client.put(opt_path, info.slot, name=info.name, progress=False)
                view.success(f"Saved {SampleFormat.size(savings)} ({savings/original_size*100:.1f}%)")
                optimized += 1
                total_savings += savings
            except EP133Error as e:
                view.error(f"Upload failed: {e}")

    return optimized, total_savings


def _optimize_all_report(
    optimized: int, total: int, total_savings: int, view: View
) -> None:
    """Display batch optimization summary."""
    view.section("=" * 40)
    print(f"  Optimized: {optimized}/{total} samples")
    print(f"  Total savings: {SampleFormat.size(total_savings)}")


def cmd_optimize_all(args, view: View):
    """Optimize stereo samples on device (downmix to mono).

    Scan phase:
      - Samples with confirmed metadata (channels_known=True): use channels > 1 directly.
      - Samples with null/missing metadata (channels_known=False): probe with a
        single-chunk partial download and _detect_channels heuristic.
    """
    min_size = args.min * 1024 if args.min else 0
    slot_filter = getattr(args, "slot", None)

    with EP133Client(args.device) as client:
        view.section("Scanning...")
        print()

        sounds = client.list_sounds()
        if slot_filter is not None:
            sounds = {k: v for k, v in sounds.items() if k == slot_filter}

        candidates = _optimize_all_scan(sounds, client, min_size, view)

        if not candidates:
            view.success("No stereo samples found")
            return 0

        print(f"\n  Found {len(candidates)} stereo samples:\n")
        total_original = 0
        for info in candidates:
            total_original += info.size_bytes
            print(
                f"    Slot {info.slot:03d}: {info.name[:30]:<30} {SampleFormat.size(info.size_bytes)}"
            )

        print(f"\n  Total: {SampleFormat.size(total_original)}")

        assume_yes = bool(args.yes)
        if not _confirm(f"Optimize {len(candidates)} samples?", assume_yes):
            view.step("Cancelled")
            return 0

        print()
        optimized, total_savings = _optimize_all_process(candidates, client, view)
        _optimize_all_report(optimized, len(candidates), total_savings, view)

    return 0


def cmd_get(args, view: View):
    """Download sample from device."""
    slot = validate_slot(args.slot)
    output = Path(args.output) if args.output else None

    # Determine final output path to check for existence
    if output and output.exists():
        if not _confirm(f"File '{output}' already exists. Overwrite?", bool(getattr(args, "yes", False))):
            view.step("Cancelled")
            return 0

    with EP133Client(args.device) as client:
        try:
            view.step(f"Downloading slot {slot}...")
            # If output is None, client.get will generate a name based on metadata
            result_path = client.get(slot, output)
            view.success(f"Downloaded to {result_path}")
        except SlotEmptyError:
            view.error(f"Slot {slot} is empty")
            return 1
        except EP133Error as e:
            view.error(f"Error: {e}")
            return 1

    return 0


def cmd_put(args, view: View):
    """Upload sample to device."""
    input_path = Path(args.file)

    if not input_path.exists():
        view.error(f"File not found: {input_path}")
        return 1

    with EP133Client(args.device) as client:
        try:
            name = args.name if args.name else None
            pitch = getattr(args, 'pitch', 0)
            view.step(f"Uploading {input_path.name} → slot {args.slot}...")
            client.put(input_path, args.slot, name=name, progress=True, pitch=pitch)
            view.success(f"Uploaded to slot {args.slot}")
        except EP133Error as e:
            view.error(f"Error: {e}")
            return 1
        except ValueError as e:
            view.error(f"Invalid file: {e}")
            return 1

    return 0


def _download_to_path(client: EP133Client, slot: int, path: Path) -> None:
    client.get(slot, path)


def cmd_move(args, view: View):
    """Move sample between slots (swap if destination occupied)."""
    src = int(args.src)
    dst = int(args.dst)
    raw = bool(args.raw)
    assume_yes = bool(args.yes)

    if src == dst:
        view.info("No-op: source and destination are the same")
        return 0

    with EP133Client(args.device) as client:
        sounds = client.list_sounds()
        src_entry = sounds.get(src)
        if not src_entry:
            view.error(f"Slot {src:03d} is empty")
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
            view.step("Cancelled")
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
                    client.put(src_path, dst, name=src_name, progress=False)
                    client.put(dst_path, src, name=dst_name, progress=False)
                    view.success(f"Swapped {src:03d} ↔ {dst:03d}")
                else:
                    client.put(src_path, dst, name=src_name, progress=False)
                    client.delete(src)
                    view.success(f"Moved {src:03d} → {dst:03d}")
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
                view.error(f"Move failed: {e}")
                return 1

    return 0


def cmd_copy(args, view: View):
    """Copy sample between slots."""
    src = int(args.src)
    dst = int(args.dst)
    raw = bool(args.raw)
    assume_yes = bool(args.yes)

    if src == dst:
        view.info("No-op: source and destination are the same")
        return 0

    with EP133Client(args.device) as client:
        sounds = client.list_sounds()
        src_entry = sounds.get(src)
        if not src_entry:
            view.error(f"Slot {src:03d} is empty")
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
            view.step("Cancelled")
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
                view.success(f"Copied {src:03d} → {dst:03d}")
            except EP133Error as e:
                if dst_entry:
                    try:
                        client.put(dst_path, dst, name=dst_name, progress=False)
                    except Exception:
                        pass
                view.error(f"Copy failed: {e}")
                return 1

    return 0


def cmd_delete(args, view: View):
    """Delete sample from slot."""
    with EP133Client(args.device) as client:
        try:
            info = client.info(args.slot)
            prompt = f"Delete slot {args.slot:03d} ({info.name})?"
            if not _confirm(prompt, bool(args.yes)):
                view.step("Cancelled")
                return 0
            view.step(f"Deleting {info.name} from slot {args.slot}")
            client.delete(args.slot)
            view.success(f"Deleted slot {args.slot}")
        except SlotEmptyError:
            view.info(f"Slot {args.slot} is already empty")
            return 1

    return 0


def cmd_audition(args, view: View):
    """Trigger on-device sample preview."""
    with EP133Client(args.device) as client:
        try:
            view.step(f"Auditioning slot {args.slot:03d}")
            client.audition(args.slot)
            view.success(f"Auditioning slot {args.slot:03d}")
        except EP133Error as e:
            view.error(f"Audition failed: {e}")
            return 1
    return 0


def cmd_group(args, view: View):
    """Compact samples in range toward one end."""
    start, end = parse_range(args.range)
    if start > end:
        start, end = end, start

    direction = "right" if args.reverse else "left"

    with EP133Client(args.device) as client:
        mapping = client.group(start, end, direction)

        if not mapping:
            view.info(f"No samples found in range {start:03d}-{end:03d}")
            return 0

        view.info(f"Grouping {direction}:")
        for old_slot, new_slot in mapping.items():
            print(f"    {old_slot:03d} → {new_slot:03d}")

        view.warn("Preview only")
        print(f"  (requires download/re-upload to execute)")

    return 0


# _squash_scan imported from core.ops above


def _squash_process_with_view(
    mapping: dict, sounds: dict, client, raw: bool, view: View
) -> None:
    """Wrapper around core.ops.squash_process with view-based progress output."""
    total = len(mapping)
    done = [0]

    def _progress(current: int, _total: int, message: str) -> None:
        done[0] = current

    try:
        _squash_process(
            mapping, sounds, client,
            raw=raw,
            progress=_progress,
        )
    except EP133Error as e:
        view.error(f"Squash failed at step {done[0]}/{total}: {e}")
        return

    for old_slot, new_slot in mapping.items():
        view.step(f"[{old_slot:03d} → {new_slot:03d}] ✓")


def _squash_report(mapping: dict, view: View) -> None:
    """Display squash completion summary."""
    view.success("Squash complete")
    view.step(f"Freed {len(mapping)} slots")


def cmd_squash(args, view: View):
    """Squash samples in page/group to fill slots sequentially."""
    # Determine range
    if args.page:
        page_range = parse_page(args.page)
        if page_range is None:
            view.error("Page must be 1-10")
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

    view.section(f"Squashing slots {start:03d}-{end:03d}...")
    if dry_run:
        view.warn("DRY RUN MODE (use --execute to apply)")

    with EP133Client(args.device) as client:
        sounds = client.list_sounds()
        used_slots = [s for s in sorted(sounds.keys()) if start <= s <= end]

        if not used_slots:
            view.step("No samples found")
            return 0

        mapping = _squash_scan(sounds, start, end)

        if not mapping:
            view.success("Already compacted")
            return 0

        # Show mapping
        view.info(f"Will move {len(mapping)} samples:")
        print()
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
            print()
            view.warn("Preview mode")
            print(f"  Run with --execute to apply changes")
            print(f"  NOTE: Project pad references are NOT updated.")
            print(f"        (project update protocol not yet available)")
            return 0

        if not _confirm(f"Execute squash for {len(mapping)} moves?", assume_yes):
            view.step("Cancelled")
            return 0

        print()
        view.section("Executing...")
        print()

        _squash_process_with_view(mapping, sounds, client, raw, view)
        _squash_report(mapping, view)

    return 0


def cmd_fs_ls(args, view: View):
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
                    f"  {hi:02X}  {lo:02X}  {n14:>5}  {n16:>5}  {dec:>5}  {slot_str:>4}  0x{flags:02X}  {SampleFormat.size(size):>7}  {name}"
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
                    f"  {slot_str:>4}  {nid:>4}  0x{flags:02X}  {SampleFormat.size(size):>7}  {name}"
                )

    return 0


def cmd_rename(args, view: View):
    """Rename a sample slot via filesystem metadata (backs up audio first)."""
    slot = int(args.slot)
    new_name = str(args.name)

    with EP133Client(args.device) as client:
        try:
            info = client.info(slot, include_size=False)
        except SlotEmptyError:
            view.error(f"Slot {slot:03d} is empty")
            return 1

        with tempfile.TemporaryDirectory(prefix=f"ko2-rename{slot:03d}-") as td:
            temp_path = Path(td) / f"slot{slot:03d}.wav"
            client.get(slot, temp_path)
            backup_path = backup_copy(temp_path, slot=slot, name_hint=info.name)
            view.kv("Backup:", str(backup_path))

        client.rename(slot, new_name)
        view.success(f"Renamed slot {slot:03d} → {new_name}")

    return 0


def _extract_waveform_bins_for_wav(wav_path: Path, width: int) -> dict:
    from ko2_tui.worker import _extract_waveform_bins_from_wav_bytes

    wav_bytes = wav_path.read_bytes()
    bins = _extract_waveform_bins_from_wav_bytes(wav_bytes, width=max(64, int(width)))
    if not isinstance(bins, dict):
        raise ValueError("Failed to extract waveform bins")
    return bins


def _build_wav_fingerprint(wav_path: Path, width: int) -> dict:
    with wave.open(str(wav_path), "rb") as wf:
        channels = int(wf.getnchannels() or 1)
        sample_width = int(wf.getsampwidth() or 2)
        samplerate = int(wf.getframerate() or SAMPLE_RATE)
        frames = int(wf.getnframes() or 0)
        pcm_bytes = wf.readframes(frames)

    if not pcm_bytes:
        raise ValueError("Empty WAV data")

    bins = _extract_waveform_bins_for_wav(wav_path, width=width)
    duration_s = (frames / samplerate) if samplerate > 0 else 0.0
    sha256 = hashlib.sha256(pcm_bytes).hexdigest()
    return {
        "sha256": sha256,
        "frames": frames,
        "channels": channels,
        "samplerate": samplerate,
        "sample_width": sample_width,
        "duration_s": duration_s,
        "bins": bins,
    }


def _slot_signature(name: str, size_bytes: int, channels: int, samplerate: int) -> dict:
    return {
        "name": str(name or ""),
        "size_bytes": int(size_bytes or 0),
        "channels": int(channels or 0),
        "samplerate": int(samplerate or 0),
    }


def cmd_fingerprint(args, view: View):
    """Manage local waveform fingerprint KV records and optional device hash metadata."""
    from ko2_tui.waveform_store import WaveformStore

    action = str(getattr(args, "fp_action", "") or "").strip().lower()
    if action not in {"write", "read", "verify"}:
        view.error("Invalid fingerprint action")
        return 1

    store = WaveformStore(path=getattr(args, "store", None))
    slot = int(getattr(args, "slot"))
    width = max(64, int(getattr(args, "width", 320)))

    with EP133Client(args.device) as client:
        try:
            info = client.info(slot, include_size=True)
        except SlotEmptyError:
            view.error(f"Slot {slot:03d} is empty")
            return 1

        if action == "read":
            sig = _slot_signature(info.name, info.size_bytes, info.channels, info.samplerate)
            entry = store.get_entry_for_slot(slot, sig)
            if entry is None:
                entry = store.get_entry_for_slot(slot, None)
                if entry is not None:
                    view.warn("Signature changed since cache write; showing latest slot entry anyway.")
            if entry is None:
                view.error(f"No cached waveform/fingerprint for slot {slot:03d}")
                return 1

            fp = entry.get("fp") if isinstance(entry.get("fp"), dict) else {}
            bins = entry.get("bins") if isinstance(entry.get("bins"), dict) else {}
            view.section(f"Fingerprint slot {slot:03d}")
            if fp.get("sha256"):
                view.kv("Hash", str(fp.get("sha256")))
            view.kv("Bins", str(len(bins.get("mins") or [])))
            if fp.get("duration_s") is not None:
                view.kv("Duration", f"{float(fp.get('duration_s') or 0.0):.3f}s")
            if fp.get("samplerate"):
                view.kv("Rate", str(int(fp.get("samplerate") or 0)))
            if fp.get("channels"):
                view.kv("Channels", str(int(fp.get("channels") or 0)))
            return 0

        with tempfile.TemporaryDirectory(prefix=f"ko2-fp-{slot:03d}-") as td:
            wav_path = Path(td) / f"slot{slot:03d}.wav"
            client.get(slot, wav_path)
            fp = _build_wav_fingerprint(wav_path, width=width)

            if action == "verify":
                sig = _slot_signature(
                    info.name,
                    info.size_bytes,
                    int(fp.get("channels") or 0),
                    int(fp.get("samplerate") or 0),
                )
                entry = store.get_entry_for_slot(slot, sig)
                if entry is None:
                    entry = store.get_entry_for_slot(slot, None)
                if entry is None:
                    view.error(f"No cached fingerprint for slot {slot:03d}")
                    return 1

                cached_fp = entry.get("fp") if isinstance(entry.get("fp"), dict) else {}
                expected = str(cached_fp.get("sha256") or "").strip().lower()
                if not expected:
                    view.error(f"Cached entry for slot {slot:03d} has no hash")
                    return 1

                observed = str(fp.get("sha256") or "").strip().lower()
                if observed != expected:
                    view.error(f"Mismatch for slot {slot:03d}: {observed[:12]} != {expected[:12]}")
                    return 2

                compare_file = getattr(args, "file", None)
                if compare_file:
                    file_fp = _build_wav_fingerprint(Path(compare_file), width=width)
                    file_hash = str(file_fp.get("sha256") or "").strip().lower()
                    if file_hash != expected:
                        view.error(f"File mismatch: {file_hash[:12]} != {expected[:12]}")
                        return 2
                    view.kv("File hash", file_hash)

                view.success(f"Fingerprint verified for slot {slot:03d}")
                view.kv("Hash", observed)
                return 0

            # write
            sig = _slot_signature(
                info.name,
                info.size_bytes,
                int(fp.get("channels") or 0),
                int(fp.get("samplerate") or 0),
            )
            fp_summary = {
                "sha256": fp["sha256"],
                "frames": int(fp["frames"]),
                "channels": int(fp["channels"]),
                "samplerate": int(fp["samplerate"]),
                "duration_s": float(fp["duration_s"]),
            }
            store.set_for_slot(slot, sig, fp["bins"], fingerprint=fp_summary)
            store.set_fingerprint(
                fp["sha256"],
                {
                    **fp_summary,
                    "slot": int(slot),
                    "name": str(info.name),
                    "size_bytes": int(info.size_bytes or 0),
                    "bins": fp["bins"],
                },
            )

            if not bool(getattr(args, "no_meta", False)):
                patch = {
                    "ko2.fp.v": 1,
                    "ko2.fp.sha256": fp["sha256"],
                    "ko2.fp.frames": int(fp["frames"]),
                    "ko2.fp.channels": int(fp["channels"]),
                    "ko2.fp.samplerate": int(fp["samplerate"]),
                    "ko2.fp.duration_s": round(float(fp["duration_s"]), 6),
                    "ko2.fp.width": int(width),
                }
                try:
                    client.update_slot_metadata(slot, patch)
                except Exception as exc:
                    view.warn(f"Fingerprint stored locally, but metadata update failed: {exc}")

            view.success(f"Fingerprint cached for slot {slot:03d}")
            view.kv("Hash", str(fp["sha256"]))
            view.kv("Bins", str(len(fp["bins"].get("mins") or [])))
            view.kv("Store", str(store.path))
            return 0


def main():

    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    view: View = (
        JsonView() if args.json else SilentView() if args.quiet else TerminalView()
    )

    # Auto-select device. TUI handles a missing device gracefully; other commands fail fast.
    device = find_device()
    if not device and args.command != "tui":
        view.error("EP-133 not found. Connect via USB.")
        return 1
    args.device = device  # None for TUI when device not yet connected

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
        "audition": cmd_audition,
        "play": cmd_audition,  # Alias
        "optimize": cmd_optimize,
        "optimize-all": cmd_optimize_all,
        "group": cmd_group,
        "squash": cmd_squash,
        "fs-ls": cmd_fs_ls,
        "rename": cmd_rename,
        "fingerprint": cmd_fingerprint,
        "tui": cmd_tui,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args, view)

    return 0


if __name__ == "__main__":
    sys.exit(main())
