import wave
import hashlib
import tempfile
from pathlib import Path

from core.client import EP133Client, SlotEmptyError, EP133Error
from core.models import Sample, MAX_SAMPLE_RATE
from core.ops import optimize_sample, backup_copy
from cli.display import View
from cli.parser import validate_slot
from cli.prompts import confirm

def cmd_optimize(args, view: View):
    slot = args.slot
    downsample_rate = getattr(args, 'rate', None)
    speed = getattr(args, 'speed', None)
    pitch = getattr(args, 'pitch', 0.0)
    mono = not getattr(args, 'keep_stereo', False)

    with EP133Client(args.device) as client:
        try:
            info = client.info(slot, include_size=False)
        except SlotEmptyError:
            view.error(f"Slot {slot} is empty")
            return 1

        if not confirm(f"Optimize slot {slot:03d} ({info.name})?", bool(args.yes)):
            view.step("Cancelled")
            return 0

        view.step("Downloading...")
        with tempfile.TemporaryDirectory(prefix=f"krate-slot{slot:03d}-") as td:
            temp_path = Path(td) / f"slot{slot:03d}.wav"
            try:
                client.get(slot, temp_path)
            except EP133Error as e:
                view.error(f"Download failed: {e}")
                return 1

            with wave.open(str(temp_path)) as w:
                original_size = temp_path.stat().st_size
                in_channels = w.getnchannels()
                in_rate = w.getframerate()
                in_depth = w.getsampwidth() * 8
                duration = w.getnframes() / w.getframerate()

            print(
                f"  {in_channels}ch  {in_rate} Hz  {in_depth}-bit  "
                f"{Sample.format_size(original_size)}  {duration:.2f}s"
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
            print(f"  {Sample.format_size(original_size)} → {Sample.format_size(opt_size)}  ({savings_pct:.1f}% saved)")

            if savings < 5 * 1024 and speed is None and downsample_rate is None:
                view.warn("Savings too small (<5KB), skipping upload")
                return 0

            opt_path = temp_path.with_suffix(".opt.wav")
            view.step("Uploading...")
            try:
                client.put(opt_path, slot, name=info.name, pitch=pitch)
                view.success("Done")
            except EP133Error as e:
                view.error(f"Upload failed: {e}")
                return 1

    return 0

def _optimize_all_scan(sounds: dict, client, min_size: int, view: View) -> list:
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

def _optimize_all_process(candidates: list, client, view: View) -> tuple[int, int]:
    optimized = 0
    total_savings = 0

    for i, info in enumerate(candidates, 1):
        view.section(f"[{i}/{len(candidates)}] Slot {info.slot}: {info.name}")

        with tempfile.TemporaryDirectory(prefix=f"krate-slot{info.slot:03d}-") as td:
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
                print(f"  ⊘ Skipped (savings: {Sample.format_size(savings)})")
                continue

            try:
                client.put(opt_path, info.slot, name=info.name)
                view.success(f"Saved {Sample.format_size(savings)} ({savings/original_size*100:.1f}%)")
                optimized += 1
                total_savings += savings
            except EP133Error as e:
                view.error(f"Upload failed: {e}")

    return optimized, total_savings

def _optimize_all_report(optimized: int, total: int, total_savings: int, view: View) -> None:
    view.section("=" * 40)
    print(f"  Optimized: {optimized}/{total} samples")
    print(f"  Total savings: {Sample.format_size(total_savings)}")

def _optimize_all_display_candidates(candidates: list, view: View) -> int:
    """Print candidate table; return total original size in bytes."""
    total_original = 0
    for info in candidates:
        total_original += info.size_bytes
        print(
            f"    Slot {info.slot:03d}: {info.name[:30]:<30} {Sample.format_size(info.size_bytes)}"
        )
    return total_original


def cmd_optimize_all(args, view: View):
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
        total_original = _optimize_all_display_candidates(candidates, view)
        print(f"\n  Total: {Sample.format_size(total_original)}")

        assume_yes = bool(args.yes)
        if not confirm(f"Optimize {len(candidates)} samples?", assume_yes):
            view.step("Cancelled")
            return 0

        print()
        optimized, total_savings = _optimize_all_process(candidates, client, view)
        _optimize_all_report(optimized, len(candidates), total_savings, view)

    return 0

def cmd_audition(args, view: View):
    with EP133Client(args.device) as client:
        try:
            view.step(f"Auditioning slot {args.slot:03d}")
            client.audition(args.slot)
            view.success(f"Auditioning slot {args.slot:03d}")
        except EP133Error as e:
            view.error(f"Audition failed: {e}")
            return 1
    return 0

def _extract_waveform_bins_for_wav(wav_path: Path, width: int) -> dict:
    from core.audio import extract_waveform_bins
    wav_bytes = wav_path.read_bytes()
    bins = extract_waveform_bins(wav_bytes, width=max(64, int(width)))
    if not isinstance(bins, dict):
        raise ValueError("Failed to extract waveform bins")
    return bins

def _build_wav_fingerprint(wav_path: Path, width: int) -> dict:
    with wave.open(str(wav_path), "rb") as wf:
        channels = int(wf.getnchannels() or 1)
        sample_width = int(wf.getsampwidth() or 2)
        samplerate = int(wf.getframerate() or MAX_SAMPLE_RATE)
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
    from core.waveform_store import WaveformStore

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

        with tempfile.TemporaryDirectory(prefix=f"krate-fp-{slot:03d}-") as td:
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
                    "krate.fp.v": 1,
                    "krate.fp.sha256": fp["sha256"],
                    "krate.fp.frames": int(fp["frames"]),
                    "krate.fp.channels": int(fp["channels"]),
                    "krate.fp.samplerate": int(fp["samplerate"]),
                    "krate.fp.duration_s": round(float(fp["duration_s"]), 6),
                    "krate.fp.width": int(width),
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
