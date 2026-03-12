import tempfile
from pathlib import Path

from core.client import EP133Client, SlotEmptyError, EP133Error, SampleInfo
from core.models import MAX_SLOTS, SAMPLE_RATE
from cli.display import View
from cli.parser import parse_range

from core.ops import (
    backup_copy,
    resolve_transfer_name,
    move_slot,
    copy_slot,
    squash_scan,
    squash_process,
)
from cli.parser import parse_page
from cli.naming import choose_display_name
from cli.prompts import confirm

from core.client import SampleInfo
from core.models import SAMPLE_RATE
def empty_sample(slot: int) -> SampleInfo:
    return SampleInfo(slot=slot, name='...', samplerate=SAMPLE_RATE, channels=0, size_bytes=0)

def _ls_scan_fs(client, start: int, end: int, name_source: str, view: View) -> tuple[list, bool]:
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
    view.step(f"Scanning slots {start:03d}-{end:03d}...")
    samples = []
    for slot in range(start, end + 1):
        view.progress(slot - start + 1, end - start + 1, f"(slot {slot})")
        try:
            info = client.info(slot, include_size=True)
            if info.size_bytes:
                samples.append(info)
            else:
                samples.append(empty_sample(slot))
        except SlotEmptyError:
            samples.append(empty_sample(slot))
    print()
    return samples

def cmd_ls(args, view: View):
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
        start, end = 1, 99

    source = args.source
    name_source = args.name_source

    with EP133Client(args.device) as client:
        samples = []
        entries = None

        if source in ("auto", "fs"):
            try:
                samples, _ = _ls_scan_fs(client, start, end, name_source, view)
                entries = samples
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
    slot_spec = parse_range(args.slot)

    with EP133Client(args.device) as client:
        if isinstance(slot_spec, int):
            try:
                info = client.info(slot_spec, include_size=True)
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

def cmd_rename(args, view: View):
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

def cmd_delete(args, view: View):
    with EP133Client(args.device) as client:
        try:
            info = client.info(args.slot)
            prompt = f"Delete slot {args.slot:03d} ({info.name})?"
            if not confirm(prompt, bool(args.yes)):
                view.step("Cancelled")
                return 0
            view.step(f"Deleting {info.name} from slot {args.slot}")
            client.delete(args.slot)
            view.success(f"Deleted slot {args.slot}")
        except SlotEmptyError:
            view.info(f"Slot {args.slot} is already empty")
            return 1

    return 0

def cmd_move(args, view: View):
    src = int(args.src)
    dst = int(args.dst)
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

        src_name = resolve_transfer_name(client, src, src_entry, bool(args.raw))
        dst_name = resolve_transfer_name(client, dst, dst_entry, bool(args.raw)) if dst_entry else ""

        if dst_entry:
            prompt = f"Swap slot {src:03d} ({src_name}) with {dst:03d} ({dst_name})?"
        else:
            prompt = f"Move slot {src:03d} ({src_name}) → {dst:03d}?"

        if not confirm(prompt, assume_yes):
            view.step("Cancelled")
            return 0

        def _progress(curr: int, total: int, msg: str) -> None:
            view.progress(curr, total, msg)

        try:
            msg = move_slot(client, src, dst, raw=bool(args.raw), progress=_progress)
            view.success(msg)
        except Exception as e:
            view.error(f"Move failed: {e}")
            return 1

    return 0

def cmd_copy(args, view: View):
    src = int(args.src)
    dst = int(args.dst)
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

        src_name = resolve_transfer_name(client, src, src_entry, bool(args.raw))
        dst_name = resolve_transfer_name(client, dst, dst_entry, bool(args.raw)) if dst_entry else ""

        if dst_entry:
            prompt = f"Overwrite slot {dst:03d} ({dst_name}) with {src:03d} ({src_name})?"
        else:
            prompt = f"Copy slot {src:03d} ({src_name}) → {dst:03d}?"

        if not confirm(prompt, assume_yes):
            view.step("Cancelled")
            return 0

        def _progress(curr: int, total: int, msg: str) -> None:
            view.progress(curr, total, msg)

        try:
            msg = copy_slot(client, src, dst, raw=bool(args.raw), progress=_progress)
            view.success(msg)
        except Exception as e:
            view.error(f"Copy failed: {e}")
            return 1

    return 0

def _squash_process_with_view(mapping: dict, sounds: dict, client, raw: bool, view: View) -> None:
    total = len(mapping)
    done = [0]
    def _progress(current: int, _total: int, message: str) -> None:
        done[0] = current

    try:
        squash_process(mapping, sounds, client, raw=raw, progress=_progress)
    except EP133Error as e:
        view.error(f"Squash failed at step {done[0]}/{total}: {e}")
        return

    for old_slot, new_slot in mapping.items():
        view.step(f"[{old_slot:03d} → {new_slot:03d}] ✓")

def _squash_report(mapping: dict, view: View) -> None:
    view.success("Squash complete")
    view.step(f"Freed {len(mapping)} slots")

def cmd_squash(args, view: View):
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
        start, end = 1, 99

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

        mapping = squash_scan(sounds, start, end)

        if not mapping:
            view.success("Already compacted")
            return 0

        view.info(f"Will move {len(mapping)} samples:")
        print()
        for old_slot, new_slot in mapping.items():
            entry = sounds.get(old_slot)
            name = resolve_transfer_name(client, old_slot, entry, raw)
            print(f"    {old_slot:03d} → {new_slot:03d}  {name[:30]:<30}")

        if dry_run:
            print()
            view.warn("Preview mode")
            print(f"  Run with --execute to apply changes")
            return 0

        if not confirm(f"Execute squash for {len(mapping)} moves?", assume_yes):
            view.step("Cancelled")
            return 0

        print()
        view.section("Executing...")
        print()

        _squash_process_with_view(mapping, sounds, client, raw, view)
        _squash_report(mapping, view)

    return 0

def cmd_group(args, view: View):
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
