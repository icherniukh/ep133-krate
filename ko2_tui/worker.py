from __future__ import annotations

import tempfile
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from queue import Queue
from typing import Any, Callable

from ko2_client import EP133Client

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
    ):
        super().__init__(daemon=True)
        self.device_name = device_name
        self._request_queue = request_queue
        self._event_queue = event_queue
        self._client_factory = client_factory
        self._client: EP133Client | None = None
        self._debug_logger = debug_logger

    def submit(self, request: WorkerRequest) -> None:
        self._request_queue.put(request)

    def run(self) -> None:
        try:
            while True:
                req = self._request_queue.get()
                if req.op == "stop":
                    break
                self._process_request(req)
        finally:
            self._close_client()

    def _process_request(self, req: WorkerRequest) -> None:
        self._emit("busy", op=req.op)
        try:
            client = self._ensure_client()

            if req.op == "refresh_inventory":
                self._emit_inventory(client)
            elif req.op == "fetch_details":
                slot = int(req.payload["slot"])
                info = client.info(slot, include_size=True)
                self._emit("details", slot=slot, details=_sampleinfo_to_dict(info))
            elif req.op == "download":
                slot = int(req.payload["slot"])
                output_path = Path(str(req.payload["output_path"]))
                result = client.get(slot, output_path)
                self._emit("success", message=f"Downloaded slot {slot:03d} to {result}")
            elif req.op == "upload":
                slot = int(req.payload["slot"])
                input_path = Path(str(req.payload["input_path"]))
                if not input_path.exists():
                    raise FileNotFoundError(f"File not found: {input_path}")
                name = req.payload.get("name")
                client.put(input_path, slot, name=name, progress=False)
                self._emit("success", message=f"Uploaded {input_path.name} to slot {slot:03d}")
                self._emit_inventory(client)
            elif req.op == "rename":
                slot = int(req.payload["slot"])
                new_name = str(req.payload["new_name"])
                client.rename(slot, new_name)
                self._emit("success", message=f"Renamed slot {slot:03d} to '{new_name}'")
                self._emit_inventory(client)
            elif req.op == "copy":
                src = int(req.payload["src"])
                dst = int(req.payload["dst"])
                info = client.info(src, include_size=False)
                name = info.name

                with tempfile.TemporaryDirectory() as td:
                    temp_path = Path(td) / f"slot{src:03d}.wav"
                    self._emit("busy", op=f"Copying {src:03d} -> {dst:03d}")
                    client.get(src, temp_path)

                    dst_info = None
                    try:
                        dst_info = client.info(dst, include_size=False)
                    except Exception:
                        pass
                    
                    if dst_info:
                        client.delete(dst)
                    
                    client.put(temp_path, dst, name=name, progress=False)

                self._emit("success", message=f"Copied slot {src:03d} to {dst:03d}")
                self._emit_inventory(client)
            elif req.op == "move":
                src = int(req.payload["src"])
                dst = int(req.payload["dst"])
                if src == dst:
                    self._emit("success", message="Move skipped (same slot)")
                    return

                src_info = client.info(src, include_size=False)
                src_name = src_info.name

                dst_info = None
                try:
                    dst_info = client.info(dst, include_size=False)
                except Exception:
                    pass

                with tempfile.TemporaryDirectory() as td:
                    temp_path = Path(td)
                    src_wav = temp_path / f"slot{src:03d}.wav"
                    self._emit("busy", op=f"Moving {src:03d} -> {dst:03d}")
                    client.get(src, src_wav)

                    if dst_info:
                        dst_wav = temp_path / f"slot{dst:03d}.wav"
                        client.get(dst, dst_wav)
                        client.delete(src)
                        client.delete(dst)
                        client.put(src_wav, dst, name=src_name, progress=False)
                        client.put(dst_wav, src, name=dst_info.name, progress=False)
                        self._emit("success", message=f"Swapped {src:03d} ↔ {dst:03d}")
                    else:
                        client.delete(src)
                        client.put(src_wav, dst, name=src_name, progress=False)
                        self._emit("success", message=f"Moved {src:03d} → {dst:03d}")
                
                self._emit_inventory(client)
            elif req.op == "delete":
                slot = int(req.payload["slot"])
                client.delete(slot)
                self._emit("success", message=f"Deleted slot {slot:03d}")
                self._emit_inventory(client)
            elif req.op == "bulk_delete":
                slots = [int(s) for s in req.payload["slots"]]
                for slot in slots:
                    client.delete(slot)
                n = len(slots)
                self._emit("success", message=f"Deleted {n} slot{'s' if n != 1 else ''}")
                self._emit_inventory(client)
            elif req.op == "squash":
                start = int(req.payload.get("start", 1))
                end = int(req.payload.get("end", 999))
                sounds = client.list_sounds()
                used_slots = [s for s in sorted(sounds.keys()) if start <= s <= end]

                mapping = {}
                target_slot = start
                for slot in used_slots:
                    if slot != target_slot:
                        mapping[slot] = target_slot
                    target_slot += 1

                if not mapping:
                    self._emit("success", message="Already compacted")
                    return

                total = len(mapping)
                done = 0
                for old_slot, new_slot in mapping.items():
                    info = client.info(old_slot, include_size=False)
                    name = info.name

                    with tempfile.TemporaryDirectory() as td:
                        temp_path = Path(td) / f"slot{old_slot:03d}.wav"
                        self._emit("busy", op=f"Squashing ({done}/{total}): {old_slot:03d} -> {new_slot:03d}")
                        client.get(old_slot, temp_path)

                        deleted = False
                        try:
                            client.delete(old_slot)
                            deleted = True
                            client.put(temp_path, new_slot, name=name, progress=False)
                        except Exception:
                            if deleted:
                                try:
                                    client.put(temp_path, old_slot, name=name, progress=False)
                                except Exception:
                                    pass
                            raise
                    done += 1

                self._emit("success", message=f"Squashed {total} slots")
                self._emit_inventory(client)
            elif req.op == "optimize":
                slots = req.payload["slots"]
                rate = req.payload.get("rate")
                speed = req.payload.get("speed")
                pitch = req.payload.get("pitch", 0.0)

                from ko2 import backup_copy, optimize_sample
                
                total = len(slots)
                done = 0
                optimized_count = 0
                for slot in slots:
                    try:
                        info = client.info(slot, include_size=False)
                    except Exception:
                        done += 1
                        continue
                    name = info.name

                    with tempfile.TemporaryDirectory() as td:
                        temp_path = Path(td) / f"slot{slot:03d}.wav"
                        self._emit("busy", op=f"Optimizing ({done+1}/{total}): {slot:03d}")
                        
                        try:
                            client.get(slot, temp_path)
                            
                            opt_path = temp_path.with_suffix(".opt.wav")
                            success, msg, orig_size, opt_size = optimize_sample(temp_path, output_path=opt_path, downsample_rate=rate, speed=speed)
                            
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
                            backup_copy(temp_path, slot=slot, name_hint=name)
                            
                            client.put(upload_path, slot, name=name, progress=False, pitch=pitch)
                            optimized_count += 1
                        except Exception as e:
                            self._emit("error", op=req.op, message=f"Error on slot {slot:03d}: {e}")
                    done += 1

                self._emit("success", message=f"Optimized {optimized_count} of {total} slots")
                self._emit_inventory(client)
            else:
                raise ValueError(f"Unknown operation: {req.op}")
        except Exception as exc:
            self._emit("error", op=req.op, message=str(exc))
            self._close_client()
        finally:
            self._emit("idle", op=req.op)

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

    def _emit_inventory(self, client: EP133Client) -> None:
        sounds = client.list_sounds()
        self._emit("inventory", sounds=sounds)
        self._emit_inventory_name_hydration(client, sounds)

    def _emit_inventory_name_hydration(
        self, client: EP133Client, sounds: dict[int, dict]
    ) -> None:
        updates: dict[int, dict[str, Any]] = {}
        for slot, entry in sorted(sounds.items()):
            patch: dict[str, Any] = {}
            try:
                node_id = int(entry.get("node_id") or slot)
                meta = client.get_node_metadata(node_id)
                if not meta and node_id != slot:
                    meta = client.get_node_metadata(slot)
                if not meta:
                    continue
                display_name = str(meta.get("name") or meta.get("sym") or "").strip()
                if display_name:
                    patch["name"] = display_name
                if "channels" in meta:
                    patch["channels"] = int(meta.get("channels") or 0)
                if "samplerate" in meta:
                    patch["samplerate"] = int(meta.get("samplerate") or 0)
            except Exception:
                continue

            if not patch:
                continue
            updates[int(slot)] = patch
            if len(updates) >= 40:
                self._emit("inventory_enriched", updates=updates)
                updates = {}

        if updates:
            self._emit("inventory_enriched", updates=updates)

    def _trace_hook(self, direction: str, raw: bytes) -> None:
        if not self._debug_logger:
            return
        event = self._debug_logger.record(direction, raw)
        if event is None:
            return
        self._emit("trace", line=event.ui_line(), trace=asdict(event))

    def _emit(self, kind: str, **payload: Any) -> None:
        self._event_queue.put(WorkerEvent(kind=kind, payload=payload))


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
