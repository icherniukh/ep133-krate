import struct
import wave
from pathlib import Path
from queue import Queue
from types import SimpleNamespace

from tui import actions
from tui.worker import DeviceWorker


class FakeClient:
    def __init__(self):
        self.calls = []
        self.meta = {1001: {"name": "afterparty kick", "channels": 1, "samplerate": 46875}}

    def connect(self):
        self.calls.append("connect")

    def close(self):
        self.calls.append("close")

    def list_sounds(self):
        self.calls.append("list_sounds")
        return {1: {"name": "001 kick", "size": 1234, "node_id": 1001}}

    def get_node_metadata(self, node_id: int):
        self.calls.append(("get_node_metadata", node_id))
        return self.meta.get(node_id)

    def info(self, slot, include_size=True):
        self.calls.append(("info", slot, include_size))
        return SimpleNamespace(
            slot=slot,
            name="kick",
            sym="",
            samplerate=46875,
            format="s16",
            channels=1,
            size_bytes=1234,
            duration=0.1,
            is_empty=False,
        )

    def get(self, slot, output_path: Path):
        self.calls.append(("get", slot, str(output_path)))
        Path(output_path).write_bytes(b"RIFF....")
        return Path(output_path)

    def put(self, input_path: Path, slot: int, name=None, progress=False):
        self.calls.append(("put", str(input_path), slot, name, progress))

    def rename(self, slot: int, new_name: str):
        self.calls.append(("rename", slot, new_name))

    def delete(self, slot: int):
        self.calls.append(("delete", slot))


def _drain(event_queue: Queue):
    items = []
    while not event_queue.empty():
        items.append(event_queue.get_nowait())
    return items


def test_worker_refresh_emits_inventory():
    req_q: Queue = Queue()
    evt_q: Queue = Queue()
    fake = FakeClient()

    worker = DeviceWorker(
        device_name="EP-133",
        request_queue=req_q,
        event_queue=evt_q,
        client_factory=lambda *args, **kwargs: fake,
    )

    worker._process_request(actions.refresh_inventory())
    events = _drain(evt_q)
    kinds = [e.kind for e in events]

    assert kinds[0] == "busy"
    assert "inventory" in kinds
    assert "inventory_enriched" in kinds
    assert kinds[-1] == "idle"


def test_worker_rename_emits_success_and_refresh():
    req_q: Queue = Queue()
    evt_q: Queue = Queue()
    fake = FakeClient()

    worker = DeviceWorker(
        device_name="EP-133",
        request_queue=req_q,
        event_queue=evt_q,
        client_factory=lambda *args, **kwargs: fake,
    )

    worker._process_request(actions.rename(7, "new-name"))
    events = _drain(evt_q)

    assert ("rename", 7, "new-name") in fake.calls
    kinds = [e.kind for e in events]
    assert "success" in kinds
    # Rename skips list_sounds — emits inventory_enriched directly with the new name.
    assert "inventory_enriched" in kinds
    assert "inventory" not in kinds
    enriched = next(e for e in events if e.kind == "inventory_enriched")
    assert enriched.payload.get("updates") == {7: {"name": "new-name"}}
    assert kinds[-1] == "idle"


def test_worker_delete_emits_slot_removed():
    req_q: Queue = Queue()
    evt_q: Queue = Queue()
    fake = FakeClient()

    worker = DeviceWorker(
        device_name="EP-133",
        request_queue=req_q,
        event_queue=evt_q,
        client_factory=lambda *args, **kwargs: fake,
    )

    worker._process_request(actions.delete(5))
    events = _drain(evt_q)

    assert ("delete", 5) in fake.calls
    kinds = [e.kind for e in events]
    assert "success" in kinds
    # Delete skips list_sounds — emits slot_removed instead.
    assert "slot_removed" in kinds
    assert "inventory" not in kinds
    removed = next(e for e in events if e.kind == "slot_removed")
    assert removed.payload.get("slot") == 5
    assert kinds[-1] == "idle"


def test_worker_upload_missing_file_emits_error(tmp_path):
    req_q: Queue = Queue()
    evt_q: Queue = Queue()
    fake = FakeClient()

    worker = DeviceWorker(
        device_name="EP-133",
        request_queue=req_q,
        event_queue=evt_q,
        client_factory=lambda *args, **kwargs: fake,
    )

    missing = tmp_path / "missing.wav"
    worker._process_request(actions.upload(3, str(missing), name="x"))
    events = _drain(evt_q)
    kinds = [e.kind for e in events]

    assert "error" in kinds
    assert kinds[-1] == "idle"


def test_worker_bulk_delete_emits_progress_and_timed_success():
    req_q: Queue = Queue()
    evt_q: Queue = Queue()
    fake = FakeClient()

    worker = DeviceWorker(
        device_name="EP-133",
        request_queue=req_q,
        event_queue=evt_q,
        client_factory=lambda *args, **kwargs: fake,
    )

    worker._process_request(actions.bulk_delete([1, 2, 3]))
    events = _drain(evt_q)

    progress = [e for e in events if e.kind == "progress"]
    assert len(progress) == 3
    assert progress[-1].payload["current"] == 3
    assert progress[-1].payload["total"] == 3

    success = [e for e in events if e.kind == "success"]
    assert success
    msg = str(success[-1].payload.get("message", ""))
    assert "Deleted 3 slots" in msg
    assert msg.endswith("s)")


def test_worker_refresh_enrichment_chunks_updates():
    class ManyMetaClient(FakeClient):
        def list_sounds(self):
            self.calls.append("list_sounds")
            return {
                slot: {"name": f"{slot:03d}.pcm", "size": 1000 + slot, "node_id": slot}
                for slot in range(1, 86)
            }

        def get_node_metadata(self, node_id: int):
            self.calls.append(("get_node_metadata", node_id))
            return {"name": f"name-{node_id}", "channels": 1, "samplerate": 46875}

    req_q: Queue = Queue()
    evt_q: Queue = Queue()
    fake = ManyMetaClient()

    worker = DeviceWorker(
        device_name="EP-133",
        request_queue=req_q,
        event_queue=evt_q,
        client_factory=lambda *args, **kwargs: fake,
    )

    worker._process_request(actions.refresh_inventory())
    events = _drain(evt_q)
    enriched = [e for e in events if e.kind == "inventory_enriched"]

    # 85 entries, emitted in chunks of up to 40.
    assert len(enriched) == 3
    assert sum(len(e.payload["updates"]) for e in enriched) == 85


def test_worker_optimize_emits_slot_refresh(monkeypatch, tmp_path):
    class OptimizeClient(FakeClient):
        def put(self, input_path: Path, slot: int, name=None, progress=False, pitch=0.0):
            self.calls.append(("put", str(input_path), slot, name, progress, pitch))

    def _fake_optimize_sample(input_path, output_path, downsample_rate=None, speed=None):
        Path(output_path).write_bytes(Path(input_path).read_bytes())
        return True, "ok", 16000, 8000

    def _fake_backup_copy(path, slot=None, name_hint=None):
        return tmp_path / "noop.wav"

    monkeypatch.setattr("tui.worker.optimize_sample", _fake_optimize_sample)
    monkeypatch.setattr("tui.worker.backup_copy", _fake_backup_copy)

    req_q: Queue = Queue()
    evt_q: Queue = Queue()
    fake = OptimizeClient()

    worker = DeviceWorker(
        device_name="EP-133",
        request_queue=req_q,
        event_queue=evt_q,
        client_factory=lambda *args, **kwargs: fake,
    )

    worker._process_request(actions.optimize([1], mono=True, rate=None, speed=None, pitch=0.0))
    events = _drain(evt_q)
    kinds = [e.kind for e in events]

    assert "slot_refresh" in kinds
    assert "success" in kinds


def test_worker_move_swap_is_destination_first():
    req_q: Queue = Queue()
    evt_q: Queue = Queue()
    
    class SwapClient(FakeClient):
        def list_sounds(self):
            self.calls.append("list_sounds")
            return {
                1: {"name": "001 kick", "size": 1234, "node_id": 1001},
                2: {"name": "002 snare", "size": 1000},
            }

    fake = SwapClient()

    worker = DeviceWorker(
        device_name="EP-133",
        request_queue=req_q,
        event_queue=evt_q,
        client_factory=lambda *args, **kwargs: fake,
    )

    worker._process_request(actions.move(1, 2))

    ops = [c for c in fake.calls if isinstance(c, tuple) and c and c[0] in {"get", "delete", "put"}]
    normalized = []
    for op in ops:
        if op[0] == "get":
            normalized.append(("get", op[1]))
        elif op[0] == "delete":
            normalized.append(("delete", op[1]))
        else:
            normalized.append(("put", op[2], op[3], op[4]))

    assert normalized == [
        ("get", 1),
        ("get", 2),
        ("put", 2, "afterparty kick", False),
        ("put", 1, "002 snare", False),
    ]


def test_worker_waveform_emits_preview(tmp_path):
    class WaveClient(FakeClient):
        def get(self, slot, output_path: Path):
            self.calls.append(("get", slot, str(output_path)))
            with wave.open(str(output_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(46875)
                frames = b"".join(struct.pack("<h", s) for s in [0, 12000, -12000, 18000, -18000] * 100)
                wf.writeframes(frames)
            return Path(output_path)

    req_q: Queue = Queue()
    evt_q: Queue = Queue()
    fake = WaveClient()

    worker = DeviceWorker(
        device_name="EP-133",
        request_queue=req_q,
        event_queue=evt_q,
        client_factory=lambda *args, **kwargs: fake,
    )

    worker._process_request(actions.waveform(1, width=40, height=9))
    events = _drain(evt_q)
    wave_events = [e for e in events if e.kind == "waveform"]

    assert wave_events
    payload = wave_events[-1].payload
    assert payload["slot"] == 1
    bins = payload["bins"]
    assert isinstance(bins, dict)
    assert len(bins["mins"]) == 96
    assert len(bins["mins"]) == len(bins["maxs"])
    fp = payload.get("fp")
    assert isinstance(fp, dict)
    assert isinstance(fp.get("sha256"), str)
    assert len(str(fp.get("sha256") or "")) == 64


def test_waveform_precalc_background_single_mode(monkeypatch):
    monkeypatch.setenv("KO2_TUI_WAVEFORM_PRECALC_MODE", "single")

    class BgClient(FakeClient):
        def get(self, slot, output_path: Path):
            self.calls.append(("get", slot, str(output_path)))
            with wave.open(str(output_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(46875)
                frames = b"".join(struct.pack("<h", s) for s in [0, 12000, -12000, 18000, -18000] * 50)
                wf.writeframes(frames)
            return Path(output_path)

    req_q: Queue = Queue()
    evt_q: Queue = Queue()
    fake = BgClient()
    worker = DeviceWorker(
        device_name="EP-133",
        request_queue=req_q,
        event_queue=evt_q,
        client_factory=lambda *args, **kwargs: fake,
    )
    worker._waveform_precalc_slots = [1]
    monkeypatch.setattr(worker, "_load_ratio", lambda: 0.0)

    worker._maybe_run_waveform_precalc_step()
    events = _drain(evt_q)
    wave_events = [e for e in events if e.kind == "waveform"]
    assert wave_events
    assert wave_events[-1].payload["slot"] == 1
    assert "bins" in wave_events[-1].payload


def test_waveform_precalc_background_threaded_mode(monkeypatch):
    monkeypatch.setenv("KO2_TUI_WAVEFORM_PRECALC_MODE", "threaded")

    class BgClient(FakeClient):
        def get(self, slot, output_path: Path):
            self.calls.append(("get", slot, str(output_path)))
            with wave.open(str(output_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(46875)
                frames = b"".join(struct.pack("<h", s) for s in [0, 10000, -10000, 16000, -16000] * 60)
                wf.writeframes(frames)
            return Path(output_path)

    req_q: Queue = Queue()
    evt_q: Queue = Queue()
    fake = BgClient()
    worker = DeviceWorker(
        device_name="EP-133",
        request_queue=req_q,
        event_queue=evt_q,
        client_factory=lambda *args, **kwargs: fake,
    )
    worker._waveform_precalc_slots = [1]
    monkeypatch.setattr(worker, "_load_ratio", lambda: 0.0)

    worker._maybe_run_waveform_precalc_step()
    worker._drain_waveform_render_futures()
    if worker._waveform_render_pool is not None:
        worker._waveform_render_pool.shutdown(wait=True, cancel_futures=False)
        worker._waveform_render_pool = None
    worker._drain_waveform_render_futures()

    events = _drain(evt_q)
    wave_events = [e for e in events if e.kind == "waveform"]
    assert wave_events
    assert wave_events[-1].payload["slot"] == 1
    assert "bins" in wave_events[-1].payload


def test_worker_optimize_all_skips_mono_slots(monkeypatch, tmp_path):
    """optimize_all scans inventory, skips mono slots, optimizes stereo ones."""

    class OptimizeAllClient(FakeClient):
        def list_sounds(self):
            self.calls.append("list_sounds")
            return {
                1: {"name": "001 mono", "size": 50000, "node_id": 1001},
                2: {"name": "002 stereo", "size": 50000, "node_id": 1002},
            }

        def info(self, slot, include_size=True):
            self.calls.append(("info", slot, include_size))
            channels = 2 if slot == 2 else 1
            return SimpleNamespace(
                slot=slot,
                name=f"slot{slot}",
                sym="",
                samplerate=46875,
                format="s16",
                channels=channels,
                channels_known=True,
                size_bytes=50000,
                duration=0.5,
                is_empty=False,
            )

        def put(self, input_path, slot: int, name=None, progress=False, pitch=0.0):
            self.calls.append(("put", str(input_path), slot, name, progress))

        def get_node_metadata(self, node_id: int):
            self.calls.append(("get_node_metadata", node_id))
            return {"name": f"name-{node_id}", "channels": 1, "samplerate": 46875}

    def _fake_optimize_sample(input_path, output_path, downsample_rate=None, speed=None):
        Path(output_path).write_bytes(b"\x00" * 20000)
        return True, "ok", 50000, 25000

    def _fake_backup_copy(path, slot=None, name_hint=None):
        return tmp_path / "backup.wav"

    monkeypatch.setattr("tui.worker.optimize_sample", _fake_optimize_sample)
    monkeypatch.setattr("tui.worker.backup_copy", _fake_backup_copy)

    req_q: Queue = Queue()
    evt_q: Queue = Queue()
    fake = OptimizeAllClient()

    worker = DeviceWorker(
        device_name="EP-133",
        request_queue=req_q,
        event_queue=evt_q,
        client_factory=lambda *args, **kwargs: fake,
    )

    worker._process_request(actions.optimize_all())
    events = _drain(evt_q)
    kinds = [e.kind for e in events]

    # Only slot 2 (stereo) should have been uploaded
    put_calls = [c for c in fake.calls if isinstance(c, tuple) and c[0] == "put"]
    assert len(put_calls) == 1
    assert put_calls[0][2] == 2  # slot 2

    assert "success" in kinds
    success_msg = next(e.payload.get("message", "") for e in events if e.kind == "success")
    assert "1 of 1" in success_msg
    assert kinds[-1] == "idle"
