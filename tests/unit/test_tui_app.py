from __future__ import annotations

import asyncio

from ko2_tui.app import KO2TUIApp
from ko2_tui.ui import TextInputModal, UploadModal
from ko2_tui.worker import WorkerEvent


class StubWorker:
    def __init__(self, device_name, request_queue, event_queue, client_factory=None, debug_logger=None):
        self.device_name = device_name
        self.request_queue = request_queue
        self.event_queue = event_queue
        self.submitted = []

    def start(self):
        return None

    def submit(self, request):
        self.submitted.append(request)

    def join(self, timeout=0):
        return None


def _request_ops(app: KO2TUIApp) -> list[str]:
    worker = app._worker
    assert worker is not None
    return [r.op for r in worker.submitted]


def _make_ready(app: KO2TUIApp) -> None:
    app._handle_event(WorkerEvent(kind="idle", payload={"op": "refresh_inventory"}))
    app._handle_event(
        WorkerEvent(
            kind="inventory",
            payload={"sounds": {1: {"name": "001.pcm", "size": 1200, "node_id": 1}}},
        )
    )


def test_tui_mount_submits_initial_refresh(monkeypatch):
    monkeypatch.setattr("ko2_tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = KO2TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as _pilot:
            ops = _request_ops(app)
            assert ops and ops[0] == "refresh_inventory"

    asyncio.run(_run())


def test_download_key_opens_modal_and_submits_request(monkeypatch):
    monkeypatch.setattr("ko2_tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = KO2TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            app.action_download()
            await pilot.pause()
            assert isinstance(app.screen, TextInputModal)
            app.screen.dismiss("/tmp/test-download.wav")
            await pilot.pause()

            ops = _request_ops(app)
            assert "download" in ops

    asyncio.run(_run())


def test_upload_key_opens_modal_and_submits_request(monkeypatch):
    monkeypatch.setattr("ko2_tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = KO2TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            app.action_upload()
            await pilot.pause()
            assert isinstance(app.screen, UploadModal)
            app.screen.dismiss(("/tmp/input.wav", "afterparty kick"))
            await pilot.pause()

            ops = _request_ops(app)
            assert "upload" in ops

    asyncio.run(_run())


def test_rename_key_opens_modal_and_submits_request(monkeypatch):
    monkeypatch.setattr("ko2_tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = KO2TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            app._handle_event(
                WorkerEvent(kind="inventory_enriched", payload={"updates": {1: {"name": "afterparty kick"}}})
            )

            app.action_rename()
            await pilot.pause()
            assert isinstance(app.screen, TextInputModal)
            app.screen.dismiss("afterparty kick v2")
            await pilot.pause()

            ops = _request_ops(app)
            assert "rename" in ops

    asyncio.run(_run())


def test_delete_key_submits_request(monkeypatch):
    monkeypatch.setattr("ko2_tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = KO2TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            await pilot.press("x")
            await pilot.pause()

            ops = _request_ops(app)
            assert "delete" in ops

    asyncio.run(_run())


def test_requests_are_queued_while_busy(monkeypatch):
    monkeypatch.setattr("ko2_tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = KO2TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as _pilot:
            _make_ready(app)
            app.state.set_busy(True, "Running refresh_inventory...")
            await _pilot.press("x")
            await _pilot.pause()
            ops = _request_ops(app)
            assert "delete" in ops

    asyncio.run(_run())


def test_inventory_enriched_event_updates_name(monkeypatch):
    monkeypatch.setattr("ko2_tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = KO2TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as _pilot:
            _make_ready(app)

            assert app.state.slots[1].name == "001.pcm"
            app._handle_event(
                WorkerEvent(
                    kind="inventory_enriched",
                    payload={"updates": {1: {"name": "afterparty kick", "channels": 1}}},
                )
            )
            assert app.state.slots[1].name == "afterparty kick"
            assert app.state.slots[1].channels == 1

    asyncio.run(_run())


def test_trace_friendly_label_uses_hydrated_name():
    app = KO2TUIApp(device_name="EP-133", debug=True)
    app.state.apply_inventory({201: {"name": "201.pcm", "size": 9000, "node_id": 201}})
    app.state.apply_inventory_updates({201: {"name": "nt hh closed b"}})

    line = 'MIDI RX cmd=0x3D GET_INIT_RSP st=0x00 name="201.pcm"'
    trace = {"name": "201.pcm"}
    rendered = app._with_friendly_trace_name(line, trace)

    assert 'label="nt hh closed b"' in rendered
