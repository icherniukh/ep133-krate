from pathlib import Path
from queue import Queue
from types import SimpleNamespace

from ko2_tui import actions
from ko2_tui.worker import DeviceWorker


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
    assert "inventory" in kinds
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
