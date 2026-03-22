from __future__ import annotations

import array
import hashlib
import io
import os
import tempfile
import threading
import time
import wave
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable

from core.client import EP133Client, DownloadCancelledError, SlotEmptyError
from core.models import MAX_SAMPLE_RATE

import sys
from pathlib import Path as _Path
_src = str(_Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from core.audio import extract_waveform_bins, extract_fingerprint
from core.ops import (
    backup_copy,
    copy_slot,
    move_slot,
    optimize_sample,
    resolve_transfer_name,
    squash_scan,
    squash_process,
)

from .actions import WorkerRequest
from .debug_log import DebugLogger


@dataclass
class WorkerEvent:
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


class DeviceWorker(threading.Thread):
    def __init__(
        self,
        device_name: str | None,
        request_queue: Queue[WorkerRequest],
        event_queue: Queue[WorkerEvent],
        client_factory: Callable[..., EP133Client] = EP133Client,
        debug_logger: DebugLogger | None = None,
        waveform_cache_checker: Callable[[int], bool] | None = None,
    ):
        super().__init__(daemon=True)
        self.device_name = device_name
        self._request_queue = request_queue
        self._event_queue = event_queue
        self._client_factory = client_factory
        self._client: EP133Client | None = None
        self._debug_logger = debug_logger
        self._waveform_cache_checker = waveform_cache_checker
        self._op_samples: dict[str, list[float]] = {}
        self._waveform_precalc_slots: list[int] = []
        self._waveform_precalc_max_load = _env_float("KO2_TUI_WAVEFORM_PRECALC_MAX_LOAD", 0.75)
        self._waveform_precalc_mode = _env_mode("KO2_TUI_WAVEFORM_PRECALC_MODE", "single")
        self._waveform_render_pool: ThreadPoolExecutor | None = None
        self._user_request_pending = threading.Event()
        self._waveform_render_futures: dict[Future[dict[str, Any] | None], tuple[int, dict[str, Any] | None]] = {}
        if self._waveform_precalc_mode == "threaded":
            workers = max(1, min(4, (os.cpu_count() or 2) // 2))
            self._waveform_render_pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ko2-wave")

    def submit(self, request: WorkerRequest) -> None:
        self._user_request_pending.set()
        self._request_queue.put(request)

    def run(self) -> None:
        try:
            while True:
                try:
                    req = self._request_queue.get(timeout=0.05)
                except Empty:
                    self._drain_waveform_render_futures()
                    self._maybe_run_waveform_precalc_step()
                    continue
                if req.op == "stop":
                    break
                self._process_request(req)
        finally:
            self._drain_waveform_render_futures()
            if self._waveform_render_pool is not None:
                self._waveform_render_pool.shutdown(wait=False, cancel_futures=True)
                self._waveform_render_pool = None
            self._close_client()

    def _process_request(self, req: WorkerRequest) -> None:
        self._user_request_pending.clear()
        t_start = time.perf_counter()
        phases: dict[str, float] = {}
        self._emit("busy", op=req.op)
        try:
            client = self._timed("client.ensure", phases, self._ensure_client)

            if req.op == "refresh_inventory":
                self._emit_inventory(client, phases=phases)
            elif req.op == "fetch_details":
                slot = int(req.payload["slot"])
                info = self._timed("device.info", phases, client.info, slot, include_size=True)
                self._emit("details", slot=slot, details=_sampleinfo_to_dict(info))
            elif req.op == "download":
                slot = int(req.payload["slot"])
                output_path = Path(str(req.payload["output_path"]))
                self._emit_progress(req.op, 1, 2, f"Downloading slot {slot:03d}")
                result = self._timed("device.get", phases, client.get, slot, output_path)
                self._emit_success(f"Downloaded slot {slot:03d} to {result}", started_at=t_start)
            elif req.op == "upload":
                slot = int(req.payload["slot"])
                input_path = Path(str(req.payload["input_path"]))
                if not input_path.exists():
                    raise FileNotFoundError(f"File not found: {input_path}")
                name = req.payload.get("name")
                self._emit_progress(req.op, 1, 2, f"Uploading to slot {slot:03d}")
                self._timed("device.put", phases, client.put, input_path, slot, name=name, progress=False)
                self._emit_success(f"Uploaded {input_path.name} to slot {slot:03d}", started_at=t_start)
                self._emit_inventory(client, hydrate_slots={slot}, phases=phases)
            elif req.op == "rename":
                slot = int(req.payload["slot"])
                new_name = str(req.payload["new_name"])
                self._timed("device.rename", phases, client.rename, slot, new_name)
                self._emit_success(f"Renamed slot {slot:03d} to '{new_name}'", started_at=t_start)
                # Slot still exists — skip list_sounds + get_node_metadata; patch directly.
                self._emit("inventory_enriched", updates={slot: {"name": new_name}})
            elif req.op == "copy":
                self._handle_copy(req, client, phases, t_start)
            elif req.op == "move":
                self._handle_move(req, client, phases, t_start)
            elif req.op == "audition":
                slot = int(req.payload["slot"])
                duration_s = float(req.payload.get("duration_s") or 0.0)
                self._timed("device.audition", phases, client.audition, slot)
                if duration_s > 0:
                    self._emit("audition_started", slot=slot, duration_s=duration_s)
                self._emit_success(f"Auditioning slot {slot:03d}", started_at=t_start)
            elif req.op == "delete":
                slot = int(req.payload["slot"])
                self._timed("device.delete", phases, client.delete, slot)
                self._emit_success(f"Deleted slot {slot:03d}", started_at=t_start)
                # Slot is gone — skip list_sounds; clear it directly.
                self._emit("slot_removed", slot=slot)
            elif req.op == "bulk_delete":
                slots = [int(s) for s in req.payload["slots"]]
                n = len(slots)
                for idx, slot in enumerate(slots, start=1):
                    self._emit_progress(req.op, idx, n, f"Deleting slot {slot:03d}")
                    self._timed("device.delete", phases, client.delete, slot)
                self._emit_success(f"Deleted {n} slot{'s' if n != 1 else ''}", started_at=t_start)
                self._emit_inventory(client, hydrate_slots=set(slots), phases=phases)
            elif req.op == "batch_upload":
                pairs = [(Path(p), int(s)) for p, s in req.payload["files_and_slots"]]
                n = len(pairs)
                uploaded = 0
                for idx, (input_path, slot) in enumerate(pairs, start=1):
                    if not input_path.exists():
                        self._emit("log", message=f"Skipped {input_path.name}: file not found")
                        continue
                    self._emit_progress(req.op, idx, n, f"Uploading [{idx}/{n}] {input_path.name} → slot {slot:03d}")
                    self._timed("device.put", phases, client.put, input_path, slot, progress=False)
                    self._emit_slot_refresh(client, slot, phases=phases)
                    uploaded += 1
                self._emit_success(f"Uploaded {uploaded} of {n} file{'s' if n != 1 else ''}", started_at=t_start)
                self._emit_inventory(client, hydrate_slots={s for _, s in pairs}, phases=phases)
            elif req.op == "squash":
                self._handle_squash(req, client, phases, t_start)
            elif req.op == "optimize":
                self._handle_optimize(req, client, phases, t_start)
            elif req.op == "optimize_all":
                self._handle_optimize_all(req, client, phases, t_start)
            elif req.op == "waveform":
                slot = int(req.payload["slot"])
                width = int(req.payload.get("width") or 60)
                height = int(req.payload.get("height") or 9)
                self._waveform_precalc_slots = [s for s in self._waveform_precalc_slots if s != slot]
                preview = self._build_waveform_preview(client, slot=slot, width=width, height=height, phases=phases)
                if preview:
                    self._emit("waveform", slot=slot, bins=preview.get("bins"), fp=preview.get("fp"))
                else:
                    self._emit("waveform", slot=slot, bins=None, fp=None)
            else:
                raise ValueError(f"Unknown operation: {req.op}")
        except Exception as exc:
            self._emit("error", op=req.op, message=str(exc))
            self._close_client()
        finally:
            total = time.perf_counter() - t_start
            stats = self._update_op_stats(req.op, total)
            self._emit(
                "op_timing",
                op=req.op,
                total_s=total,
                phases=phases,
                count=stats["count"],
                p50_s=stats["p50_s"],
                p95_s=stats["p95_s"],
            )
            self._emit("idle", op=req.op)

    def _handle_copy(self, req: WorkerRequest, client: EP133Client, phases: dict[str, float], t_start: float) -> None:
        src = int(req.payload["src"])
        dst = int(req.payload["dst"])

        def _progress(curr: int, total: int, msg: str) -> None:
            self._emit_progress(req.op, curr, total, msg)

        try:
            msg = self._timed(
                "local.copy_slot",
                phases,
                copy_slot,
                client, src, dst, progress=_progress
            )
            self._emit_success(msg, started_at=t_start)
        except Exception as exc:
            self._emit("error", op=req.op, message=str(exc))
        finally:
            self._emit_inventory(client, hydrate_slots={dst}, phases=phases)

    def _handle_move(self, req: WorkerRequest, client: EP133Client, phases: dict[str, float], t_start: float) -> None:
        src = int(req.payload["src"])
        dst = int(req.payload["dst"])
        if src == dst:
            self._emit_success("Move skipped (same slot)", started_at=t_start)
            return

        def _progress(curr: int, total: int, msg: str) -> None:
            self._emit_progress(req.op, curr, total, msg)

        try:
            msg = self._timed(
                "local.move_slot",
                phases,
                move_slot,
                client, src, dst, progress=_progress
            )
            self._emit_success(msg, started_at=t_start)
        except Exception as exc:
            self._emit("error", op=req.op, message=str(exc))
        finally:
            self._emit_inventory(client, hydrate_slots={src, dst}, phases=phases)

    def _handle_squash(self, req: WorkerRequest, client: EP133Client, phases: dict[str, float], t_start: float) -> None:
        start = int(req.payload.get("start", 1))
        end = int(req.payload.get("end", 999))
        sounds = self._timed("device.list_sounds", phases, client.list_sounds)
        
        mapping = squash_scan(sounds, start, end)

        if not mapping:
            self._emit_success("Already compacted", started_at=t_start)
            return

        total = len(mapping)

        def _progress(curr: int, total: int, msg: str) -> None:
            self._emit_progress(req.op, curr, total, msg)

        try:
            self._emit("busy", op=f"Squashing {total} slots...")
            self._timed(
                "local.squash_process",
                phases,
                squash_process,
                mapping, sounds, client, raw=False, progress=_progress
            )
            self._emit_success(f"Squashed {total} slots", started_at=t_start)
        except Exception as exc:
            self._emit("error", op=req.op, message=f"Squash failed: {exc}")
        finally:
            changed = set(mapping.keys()) | set(mapping.values())
            self._emit_inventory(client, hydrate_slots=changed, phases=phases)

    def _handle_optimize(self, req: WorkerRequest, client: EP133Client, phases: dict[str, float], t_start: float) -> None:
        slots = req.payload["slots"]
        rate = req.payload.get("rate")
        speed = req.payload.get("speed")
        pitch = req.payload.get("pitch", 0.0)

        total = len(slots)
        done = 0
        optimized_count = 0
        for slot in slots:
            self._emit_progress(req.op, done + 1, total, f"Optimizing slot {slot:03d}")
            try:
                info = self._timed("device.info", phases, client.info, slot, include_size=False)
            except SlotEmptyError:
                done += 1
                continue
            except Exception as exc:
                self._emit("error", op=req.op, message=f"Skipping slot {slot:03d}: {exc}")
                done += 1
                continue
            name = info.name

            with tempfile.TemporaryDirectory() as td:
                temp_path = Path(td) / f"slot{slot:03d}.wav"
                self._emit("busy", op=f"Optimizing ({done+1}/{total}): {slot:03d}")

                try:
                    self._timed("device.get", phases, client.get, slot, temp_path)

                    opt_path = temp_path.with_suffix(".opt.wav")
                    success, msg, orig_size, opt_size = self._timed(
                        "local.optimize_sample",
                        phases,
                        optimize_sample,
                        temp_path,
                        output_path=opt_path,
                        downsample_rate=rate,
                        speed=speed,
                    )

                    if not success:
                        self._emit("error", op=req.op, message=f"Failed to optimize slot {slot:03d}: {msg}")
                        done += 1
                        continue

                    upload_path = opt_path if opt_path.exists() else temp_path
                    savings = orig_size - opt_size

                    # If no size savings and no speed/rate parameter was explicitly provided,
                    # and pitch is 0, we can skip
                    if savings < 5 * 1024 and speed is None and rate is None and pitch == 0.0:
                        done += 1
                        continue

                    # Backup
                    self._timed("local.backup_copy", phases, backup_copy, temp_path, slot=slot, name_hint=name)

                    self._timed(
                        "device.put",
                        phases,
                        client.put,
                        upload_path,
                        slot,
                        name=name,
                        progress=False,
                        pitch=pitch,
                    )
                    optimized_count += 1
                except Exception as e:
                    self._emit("error", op=req.op, message=f"Error on slot {slot:03d}: {e}")
                finally:
                    self._emit_slot_refresh(client, slot, phases=phases)
            done += 1

        self._emit_success(f"Optimized {optimized_count} of {total} slots", started_at=t_start)
        self._emit_inventory(client, hydrate_slots=set(slots), phases=phases)

    def _handle_optimize_all(self, req: WorkerRequest, client: EP133Client, phases: dict[str, float], t_start: float) -> None:
        min_size = int(req.payload.get("min_size", 0))


        self._emit_progress(req.op, 0, 1, "Scanning for stereo samples...")
        sounds = self._timed("device.list_sounds", phases, client.list_sounds)

        candidates: list[Any] = []
        for slot, entry in sorted(sounds.items()):
            size_bytes = int(entry.get("size") or 0)
            if min_size and size_bytes <= min_size:
                continue
            try:
                info = self._timed("device.info", phases, client.info, slot, include_size=False)
            except Exception:
                continue

            if info.channels_known:
                if info.channels > 1:
                    info.size_bytes = size_bytes
                    candidates.append(info)
            else:
                # Probe for channel count when metadata is unavailable.
                try:
                    channels, probed_size = self._timed(
                        "device.probe_channels", phases, client.probe_channels, slot
                    )
                except Exception:
                    continue
                if probed_size:
                    info.size_bytes = probed_size
                if channels > 1:
                    info.channels = 2
                    candidates.append(info)

        if not candidates:
            self._emit_success("No stereo samples found", started_at=t_start)
            self._emit_inventory(client, phases=phases)
            return

        total = len(candidates)
        optimized_count = 0
        changed_slots: set[int] = set()

        for idx, info in enumerate(candidates, 1):
            slot = info.slot
            name = info.name
            self._emit_progress(req.op, idx, total, f"Optimizing slot {slot:03d} ({idx}/{total})")

            with tempfile.TemporaryDirectory() as td:
                temp_path = Path(td) / f"slot{slot:03d}.wav"
                opt_path = temp_path.with_suffix(".opt.wav")
                self._emit("busy", op=f"Optimizing ({idx}/{total}): {slot:03d}")

                try:
                    self._timed("device.get", phases, client.get, slot, temp_path)

                    success, msg, orig_size, opt_size = self._timed(
                        "local.optimize_sample",
                        phases,
                        optimize_sample,
                        temp_path,
                        output_path=opt_path,
                    )

                    if not success:
                        self._emit("error", op=req.op, message=f"Failed to optimize slot {slot:03d}: {msg}")
                        continue

                    if msg == "already optimal":
                        continue

                    savings = orig_size - opt_size
                    if savings < 5 * 1024:
                        continue

                    self._timed("local.backup_copy", phases, backup_copy, temp_path, slot=slot, name_hint=name)

                    upload_path = opt_path if opt_path.exists() else temp_path
                    self._timed(
                        "device.put",
                        phases,
                        client.put,
                        upload_path,
                        slot,
                        name=name,
                        pitch=0.0,
                        progress=False,
                    )
                    optimized_count += 1
                    changed_slots.add(slot)
                except Exception as exc:
                    self._emit("error", op=req.op, message=f"Error on slot {slot:03d}: {exc}")
                finally:
                    self._emit_slot_refresh(client, slot, phases=phases)

        self._emit_success(f"Optimized {optimized_count} of {total} stereo slots", started_at=t_start)
        self._emit_inventory(client, hydrate_slots=changed_slots if changed_slots else None, phases=phases)

    def _ensure_client(self) -> EP133Client:
        if self._client is not None:
            return self._client

        trace_hook = self._trace_hook if self._debug_logger else None
        try:
            client = self._client_factory(self.device_name, trace_hook=trace_hook)
        except TypeError:
            client = self._client_factory(self.device_name)

        if hasattr(client, "connect"):
            client.connect()
        self._client = client
        return self._client

    def _close_client(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def _timed(self, phase: str, phases: dict[str, float], fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        t0 = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            phases[phase] = phases.get(phase, 0.0) + (time.perf_counter() - t0)

    def _update_op_stats(self, op: str, total_s: float) -> dict[str, float | int]:
        samples = self._op_samples.setdefault(op, [])
        samples.append(float(total_s))
        if len(samples) > 200:
            samples.pop(0)
        sorted_samples = sorted(samples)
        return {
            "count": len(sorted_samples),
            "p50_s": _percentile(sorted_samples, 0.50),
            "p95_s": _percentile(sorted_samples, 0.95),
        }

    def _emit_inventory(
        self,
        client: EP133Client,
        *,
        hydrate_slots: set[int] | None = None,
        phases: dict[str, float] | None = None,
    ) -> None:
        if phases is None:
            phases = {}
        sounds = self._timed("device.list_sounds", phases, client.list_sounds)
        self._schedule_waveform_precalc(sounds)
        self._emit("inventory", sounds=sounds)
        self._emit_inventory_name_hydration(client, sounds, hydrate_slots=hydrate_slots, phases=phases)

    def _emit_inventory_name_hydration(
        self,
        client: EP133Client,
        sounds: dict[int, dict],
        *,
        hydrate_slots: set[int] | None = None,
        phases: dict[str, float] | None = None,
    ) -> None:
        if phases is None:
            phases = {}
        if hydrate_slots is None:
            slots_to_hydrate = set(sounds.keys())
        else:
            slots_to_hydrate = set(hydrate_slots) & set(sounds.keys())

        if not slots_to_hydrate:
            return

        updates: dict[int, dict[str, Any]] = {}
        for slot in sorted(slots_to_hydrate):
            entry = sounds.get(slot, {})
            patch: dict[str, Any] = {}
            try:
                node_id = int(entry.get("node_id") or slot)
                meta = self._timed("device.get_node_metadata", phases, client.get_node_metadata, node_id)
                if not meta and node_id != slot:
                    meta = self._timed("device.get_node_metadata", phases, client.get_node_metadata, slot)
                if not meta:
                    continue
                display_name = str(meta.get("name") or meta.get("sym") or "").strip()
                if display_name:
                    patch["name"] = display_name
                channels = int(meta.get("channels") or 0)
                if "channels" in meta:
                    patch["channels"] = channels
                samplerate = int(meta.get("samplerate") or 0)
                if "samplerate" in meta:
                    patch["samplerate"] = samplerate
            except Exception as exc:
                self._emit("log", message=f"hydration failed for slot {slot}: {exc}")
                continue

            if not patch:
                continue
            updates[int(slot)] = patch
            if len(updates) >= 40:
                self._emit("inventory_enriched", updates=updates)
                updates = {}

            # Preload details so the app can show them without waiting for user selection.
            size_bytes = int(entry.get("size") or 0)
            sr = samplerate if samplerate > 0 else MAX_SAMPLE_RATE
            ch = channels if channels > 0 else 1
            duration = size_bytes / (sr * ch * 2) if size_bytes > 0 else 0.0
            self._emit(
                "details",
                slot=int(slot),
                preload=True,
                details={
                    "name": patch.get("name", ""),
                    "size_bytes": size_bytes,
                    "channels": channels,
                    "samplerate": samplerate,
                    "duration": duration,
                    "is_empty": False,
                },
            )

        if updates:
            self._emit("inventory_enriched", updates=updates)

    def _emit_slot_refresh(
        self,
        client: EP133Client,
        slot: int,
        *,
        phases: dict[str, float] | None = None,
    ) -> None:
        if phases is None:
            phases = {}
        try:
            info = self._timed("device.info", phases, client.info, int(slot), include_size=True)
        except Exception as exc:
            self._emit("log", message=f"slot_refresh failed for slot {slot:03d}: {exc}")
            return
        self._emit("slot_refresh", slot=int(slot), details=_sampleinfo_to_dict(info))

    def _build_waveform_preview(
        self,
        client: EP133Client,
        *,
        slot: int,
        width: int,
        height: int,
        phases: dict[str, float],
    ) -> dict[str, Any] | None:
        width = max(96, min(640, int(width)))
        _ = int(height)  # Reserved for future render-specific hinting.
        wav_bytes = self._download_slot_wav_bytes(client, slot=slot, phases=phases)
        if not wav_bytes:
            return None
        bins = extract_waveform_bins(wav_bytes, width=width)
        if not bins:
            return None
        fp = extract_fingerprint(wav_bytes)
        return {"bins": bins, "fp": fp}

    def _download_slot_wav_bytes(
        self,
        client: EP133Client,
        *,
        slot: int,
        phases: dict[str, float],
        cancel_check: Callable[[], bool] | None = None,
    ) -> bytes | None:
        try:
            with tempfile.TemporaryDirectory() as td:
                wav_path = Path(td) / f"slot{slot:03d}.wav"
                self._timed("device.get", phases, client.get, int(slot), wav_path, cancel_check=cancel_check)
                return wav_path.read_bytes()
        except DownloadCancelledError:
            return None
        except Exception as exc:
            self._emit("log", message=f"waveform download failed for slot {slot:03d}: {exc}")
            return None

    def _schedule_waveform_precalc(self, sounds: dict[int, dict]) -> None:
        ordered = sorted(
            ((int(slot), int(entry.get("size") or 0)) for slot, entry in sounds.items()),
            key=lambda item: item[1],
        )
        checker = self._waveform_cache_checker
        self._waveform_precalc_slots = [
            slot for slot, _size in ordered
            if slot > 0 and not (checker is not None and checker(slot))
        ]

    def _maybe_run_waveform_precalc_step(self) -> None:
        self._drain_waveform_render_futures()
        if not self._waveform_precalc_slots:
            return
        if self._user_request_pending.is_set():
            return
        if self._load_ratio() > self._waveform_precalc_max_load:
            return

        # Peek at the next slot without popping, so we can check the cache
        # before opening any MIDI connection.
        slot = int(self._waveform_precalc_slots[0])

        # Skip MIDI traffic entirely when the app already has valid cached bins.
        if self._waveform_cache_checker is not None and self._waveform_cache_checker(slot):
            self._waveform_precalc_slots.pop(0)
            return

        self._waveform_precalc_slots.pop(0)

        try:
            client = self._ensure_client()
        except Exception:
            self._waveform_precalc_slots.clear()
            return

        phases: dict[str, float] = {}
        self._emit("busy", op="waveform")
        try:
            wav_bytes = self._download_slot_wav_bytes(
                client, slot=slot, phases=phases,
                cancel_check=self._user_request_pending.is_set,
            )
        finally:
            self._emit("idle", op="waveform")
        if not wav_bytes:
            # Cancelled or failed — re-insert so it's retried later
            if slot not in self._waveform_precalc_slots:
                self._waveform_precalc_slots.append(slot)
            return

        width = 320
        fp = extract_fingerprint(wav_bytes)
        if self._waveform_render_pool is None:
            bins = extract_waveform_bins(wav_bytes, width=width)
            if bins:
                self._emit("waveform", slot=slot, bins=bins, fp=fp)
            return

        future = self._waveform_render_pool.submit(
            extract_waveform_bins,
            wav_bytes,
            width,
        )
        self._waveform_render_futures[future] = (slot, fp)

    def _drain_waveform_render_futures(self) -> None:
        if not self._waveform_render_futures:
            return
        done = [f for f in self._waveform_render_futures.keys() if f.done()]
        for future in done:
            item = self._waveform_render_futures.pop(future, None)
            if item is None:
                continue
            slot, fp = item
            try:
                bins = future.result()
            except Exception as exc:
                self._emit("log", message=f"waveform render failed for slot {slot:03d}: {exc}")
                continue
            if bins:
                self._emit("waveform", slot=int(slot), bins=bins, fp=fp)

    def _load_ratio(self) -> float:
        try:
            load1, _load5, _load15 = os.getloadavg()
            cpus = max(1, int(os.cpu_count() or 1))
            return float(load1) / float(cpus)
        except Exception:
            return 0.0

    def _trace_hook(self, direction: str, raw: bytes) -> None:
        if not self._debug_logger:
            return
        # Record to JSONL file only — don't flood the UI event queue.
        # The log pane shows high-level operations (success/error/progress),
        # not individual SysEx messages.
        self._debug_logger.record(direction, raw)

    def _emit_success(self, message: str, *, started_at: float) -> None:
        elapsed = max(0.0, time.perf_counter() - float(started_at))
        self._emit("success", message=f"{message} ({elapsed:.2f}s)")

    def _emit_progress(self, op: str, current: int, total: int, message: str = "") -> None:
        self._emit(
            "progress",
            op=op,
            current=int(current),
            total=max(1, int(total)),
            message=message,
        )

    def _emit(self, kind: str, **payload: Any) -> None:
        self._event_queue.put(WorkerEvent(kind=kind, payload=payload))


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    idx = (len(sorted_values) - 1) * q
    lo = int(idx)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = idx - lo
    return float(sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac)


def _sampleinfo_to_dict(info: Any) -> dict[str, Any]:
    return {
        "slot": int(getattr(info, "slot", 0)),
        "name": str(getattr(info, "name", "")),
        "sym": str(getattr(info, "sym", "")),
        "samplerate": int(getattr(info, "samplerate", 0) or 0),
        "format": str(getattr(info, "format", "")),
        "channels": int(getattr(info, "channels", 0) or 0),
        "size_bytes": int(getattr(info, "size_bytes", 0) or 0),
        "duration": float(getattr(info, "duration", 0.0) or 0.0),
        "is_empty": bool(getattr(info, "is_empty", False)),
    }


def _env_mode(name: str, default: str) -> str:
    raw = str(os.getenv(name, default)).strip().lower()
    if raw in {"single", "threaded"}:
        return raw
    return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return float(default)
    try:
        return float(raw)
    except Exception:
        return float(default)
