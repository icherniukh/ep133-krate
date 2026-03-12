import re
import json

from ko2_client import EP133Client
from ko2_models import MAX_SLOTS, decode_14bit, decode_node_id
from ko2_display import View, SampleFormat
from ko2_parser import parse_range
from cli.helpers import (
    parse_page,
    short_text as _short,
    sanitize_field as _sanitize_field,
    format_bar as _format_bar,
    extract_total_memory as _extract_total_memory,
)

def cmd_status(args, view: View):
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

def cmd_fs_ls(args, view: View):
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

def cmd_audit(args, view: View):
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
    elif getattr(args, "all", False):
        start, end = 1, MAX_SLOTS
    else:
        start, end = 1, 99

    if start > end:
        start, end = end, start

    show_all = bool(args.show_all)
    dump_path = getattr(args, "dump", None)
    dump_json = getattr(args, "dump_json", None)
    compare_fields = []
    if getattr(args, "compare", None):
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
