from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

from tui.app import TUIApp, _waveform_signature, _render_progress_bar
from tui.ui import ConfirmModal, HelpModal, OptimizeModal, TextInputModal
from tui.worker import WorkerEvent
from textual.widgets import Checkbox, DataTable, Static, TextArea
from tui.app import _LogView


class StubWorker:
    def __init__(self, device_name, request_queue, event_queue, client_factory=None, debug_logger=None, waveform_cache_checker=None):
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


def _request_ops(app: TUIApp) -> list[str]:
    worker = app._worker
    assert worker is not None
    return [r.op for r in worker.submitted]


def _make_ready(app: TUIApp) -> None:
    app._handle_event(WorkerEvent(kind="idle", payload={"op": "refresh_inventory"}))
    app._handle_event(
        WorkerEvent(
            kind="inventory",
            payload={"sounds": {1: {"name": "001.pcm", "size": 1200, "node_id": 1}}},
        )
    )


def test_tui_mount_submits_initial_refresh(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as _pilot:
            ops = _request_ops(app)
            assert ops and ops[0] == "refresh_inventory"

    asyncio.run(_run())


def test_download_key_opens_modal_and_submits_request(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
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


def test_upload_single_file_to_occupied_slot_submits_request(monkeypatch):
    """u key with one file selected on an occupied slot: confirm → upload queued."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)
    monkeypatch.setattr("tui.app.pick_files", AsyncMock(return_value=[Path("/tmp/input.wav")]))

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            assert app.state.slots[1].exists  # slot 1 is occupied

            await pilot.press("u")
            await pilot.pause()

            assert isinstance(app.screen, ConfirmModal)
            app.screen.dismiss(True)
            await pilot.pause()

            ops = _request_ops(app)
            assert "upload" in ops

    asyncio.run(_run())


def test_rename_key_opens_modal_and_submits_request(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
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


def test_delete_key_shows_confirm_then_submits(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            await pilot.press("backspace")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmModal)
            app.screen.dismiss(True)
            await pilot.pause()

            ops = _request_ops(app)
            assert "delete" in ops

    asyncio.run(_run())


def test_delete_confirm_cancel_skips_request(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            await pilot.press("backspace")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmModal)
            app.screen.dismiss(False)
            await pilot.pause()

            ops = _request_ops(app)
            assert "delete" not in ops

    asyncio.run(_run())


def test_device_actions_blocked_while_busy(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            before = list(_request_ops(app))
            app.state.set_busy(True, "Running refresh_inventory...")
            await pilot.press("backspace")
            await pilot.pause()
            # Delete should be blocked — no modal, no new request
            assert not isinstance(app.screen, ConfirmModal)
            assert _request_ops(app) == before

    asyncio.run(_run())


def test_inventory_enriched_event_updates_name(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
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


def test_inventory_refresh_preserves_viewport_scroll(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            table = app.query_one("#slots", DataTable)

            table.move_cursor(row=500, animate=False)
            table.scroll_to(y=300, animate=False, immediate=True, force=True)
            await pilot.pause()
            before = float(table.scroll_y)

            app._handle_event(
                WorkerEvent(
                    kind="inventory",
                    payload={"sounds": {1: {"name": "001.pcm", "size": 1200, "node_id": 1}}},
                )
            )
            await pilot.pause()
            after = float(table.scroll_y)

            assert abs(after - before) < 1.0

    asyncio.run(_run())


def test_inventory_event_does_not_full_rebuild(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as _pilot:
            _make_ready(app)

            called = False

            def _mark_rebuild() -> None:
                nonlocal called
                called = True

            app._refresh_table = _mark_rebuild  # type: ignore[method-assign]
            app._handle_event(
                WorkerEvent(
                    kind="inventory",
                    payload={"sounds": {1: {"name": "001.pcm", "size": 1234, "node_id": 1}}},
                )
            )

            assert called is False
            assert app.state.slots[1].size_bytes == 1234

    asyncio.run(_run())


def test_details_event_does_not_full_rebuild(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as _pilot:
            _make_ready(app)

            called = False

            def _mark_rebuild() -> None:
                nonlocal called
                called = True

            app._refresh_table = _mark_rebuild  # type: ignore[method-assign]
            app._handle_event(
                WorkerEvent(
                    kind="details",
                    payload={
                        "slot": 1,
                        "details": {
                            "name": "afterparty kick",
                            "channels": 1,
                            "samplerate": 46875,
                            "size_bytes": 2345,
                            "is_empty": False,
                        },
                    },
                )
            )

            assert called is False
            assert app.state.slots[1].name == "afterparty kick"
            assert app.state.slots[1].size_bytes == 2345

    asyncio.run(_run())


def test_select_key_opens_modal_and_sets_selection(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            await pilot.press("v")
            await pilot.pause()
            assert isinstance(app.screen, TextInputModal)
            app.screen.dismiss("1")
            await pilot.pause()

            assert app.state.selected_slots == {1}

    asyncio.run(_run())


def test_select_empty_expression_clears_selection(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            app.state.selected_slots = {1}

            await pilot.press("v")
            await pilot.pause()
            assert isinstance(app.screen, TextInputModal)
            app.screen.dismiss("")  # empty = clear
            await pilot.pause()

            assert app.state.selected_slots == set()

    asyncio.run(_run())


def test_select_cancel_leaves_selection_unchanged(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            app.state.selected_slots = {1}

            await pilot.press("s")
            await pilot.pause()
            app.screen.dismiss(None)  # cancelled
            await pilot.pause()

            assert app.state.selected_slots == {1}

    asyncio.run(_run())


def test_delete_on_selection_queues_bulk_delete(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            app.state.selected_slots = {1}

            await pilot.press("backspace")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmModal)
            app.screen.dismiss(True)
            await pilot.pause()

            ops = _request_ops(app)
            assert "bulk_delete" in ops
            assert "delete" not in ops
            assert app.state.selected_slots == set()

    asyncio.run(_run())


def test_delete_with_no_selection_uses_single_delete(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            assert app.state.selected_slots == set()

            await pilot.press("backspace")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmModal)
            app.screen.dismiss(True)
            await pilot.pause()

            ops = _request_ops(app)
            assert "delete" in ops
            assert "bulk_delete" not in ops

    asyncio.run(_run())


def test_trace_friendly_label_uses_hydrated_name():
    app = TUIApp(device_name="EP-133", debug=True)
    app.state.apply_inventory({201: {"name": "201.pcm", "size": 9000, "node_id": 201}})
    app.state.apply_inventory_updates({201: {"name": "nt hh closed b"}})

    line = 'MIDI RX cmd=0x3D GET_INIT_RSP st=0x00 name="201.pcm"'
    trace = {"name": "201.pcm"}
    rendered = app._with_friendly_trace_name(line, trace)

    assert 'label="nt hh closed b"' in rendered


def test_trace_event_renders_user_friendly_debug_message():
    app = TUIApp(device_name="EP-133", debug=True)
    app.state.apply_inventory({201: {"name": "201.pcm", "size": 9000, "node_id": 201}})
    app.state.apply_inventory_updates({201: {"name": "nt hh closed b"}})
    lines: list[str] = []
    app._log = lines.append  # type: ignore[method-assign]

    app._handle_event(
        WorkerEvent(
            kind="trace",
            payload={"trace": {"dir": "TX", "op": "GET_INIT", "slot": 201, "name": "201.pcm"}},
        )
    )

    assert lines == ['Debug: download requested for slot 201 "nt hh closed b"']


def test_trace_event_suppresses_chunk_chatter():
    app = TUIApp(device_name="EP-133", debug=True)
    lines: list[str] = []
    app._log = lines.append  # type: ignore[method-assign]

    app._handle_event(
        WorkerEvent(
            kind="trace",
            payload={"trace": {"dir": "TX", "op": "GET_DATA", "slot": 43}},
        )
    )

    assert lines == []


def test_slot_refresh_does_not_change_selected_slot(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as _pilot:
            _make_ready(app)
            app.state.selected_slot = 1

            app._handle_event(
                WorkerEvent(
                    kind="slot_refresh",
                    payload={
                        "slot": 2,
                        "details": {
                            "name": "fresh snare",
                            "channels": 1,
                            "samplerate": 46875,
                            "size_bytes": 2222,
                            "is_empty": False,
                        },
                    },
                )
            )

            assert app.state.selected_slot == 1
            assert app.state.slots[2].name == "fresh snare"
            assert app.state.slots[2].size_bytes == 2222

    asyncio.run(_run())


def test_details_event_queues_waveform_request(monkeypatch):
    class _EmptyWaveformStore:
        def __init__(self, *args, **kwargs):
            pass

        @staticmethod
        def is_valid_bins(bins):
            return isinstance(bins, dict) and isinstance(bins.get("mins"), list) and isinstance(bins.get("maxs"), list)

        def get_for_slot(self, slot, sig):
            return None

        def set_for_slot(self, slot, sig, bins, fingerprint=None):
            return None

    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)
    monkeypatch.setattr("tui.app.WaveformStore", _EmptyWaveformStore)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as _pilot:
            _make_ready(app)

            before = list(_request_ops(app))
            app._handle_event(
                WorkerEvent(
                    kind="details",
                    payload={
                        "slot": 1,
                        "details": {
                            "name": "afterparty kick",
                            "channels": 1,
                            "samplerate": 46875,
                            "size_bytes": 2345,
                            "is_empty": False,
                        },
                    },
                )
            )

            after = _request_ops(app)
            assert len(after) == len(before) + 1
            assert after[-1] == "waveform"
            assert 1 in app._waveform_pending

            app._handle_event(
                WorkerEvent(
                    kind="waveform",
                    payload={
                        "slot": 1,
                        "bins": {"mins": [-64, -12, -40], "maxs": [64, 45, 20], "width": 3},
                    },
                )
            )
            assert 1 not in app._waveform_pending
            assert app._waveform_by_slot.get(1) == {"mins": [-64, -12, -40], "maxs": [64, 45, 20], "width": 3}

    asyncio.run(_run())


def test_cursor_up_wraps_from_first_to_last_slot(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            table = app.query_one("#slots", DataTable)
            table.move_cursor(row=0, animate=False)
            await pilot.pause()

            await pilot.press("up")
            await pilot.pause()

            assert table.cursor_row == table.row_count - 1
            assert app.state.selected_slot == 999

    asyncio.run(_run())


def test_cursor_down_wraps_from_last_to_first_slot(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            table = app.query_one("#slots", DataTable)
            table.move_cursor(row=table.row_count - 1, animate=False)
            await pilot.pause()

            await pilot.press("down")
            await pilot.pause()

            assert table.cursor_row == 0
            assert app.state.selected_slot == 1

    asyncio.run(_run())


def test_cursor_keys_move_one_row_in_middle(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            table = app.query_one("#slots", DataTable)
            table.move_cursor(row=500, animate=False)
            await pilot.pause()

            await pilot.press("up")
            await pilot.pause()
            assert table.cursor_row == 499

            await pilot.press("down")
            await pilot.pause()
            assert table.cursor_row == 500

    asyncio.run(_run())


def test_log_view_toggle_hides_and_preserves_lines(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            logs = app.query_one("#logs", _LogView)

            app._log("line-a")
            await pilot.pause()
            before = len(logs.text.splitlines())
            assert before >= 1
            assert not logs.has_class("hidden")

            await pilot.press("l")
            await pilot.pause()
            assert logs.has_class("hidden")
            assert len(logs.text.splitlines()) == before

            app._log("line-b")
            await pilot.pause()
            mid = len(logs.text.splitlines())
            assert mid == before + 1

            await pilot.press("l")
            await pilot.pause()
            assert not logs.has_class("hidden")
            assert len(logs.text.splitlines()) == mid

    asyncio.run(_run())


def test_log_toggle_does_not_break_table_navigation(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            table = app.query_one("#slots", DataTable)
            table.move_cursor(row=12, animate=False)
            await pilot.pause()

            await pilot.press("l")
            await pilot.pause()
            await pilot.press("j")
            await pilot.pause()

            assert table.cursor_row == 13
            assert app.state.selected_slot == 14

    asyncio.run(_run())


def test_enter_key_triggers_details_request(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            before = list(_request_ops(app))

            await pilot.press("enter")
            await pilot.pause()

            after = _request_ops(app)
            assert len(after) == len(before) + 1
            assert after[-1] == "fetch_details"

    asyncio.run(_run())


def test_enter_drops_in_move_mode(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            before = list(_request_ops(app))

            await pilot.press("m")
            await pilot.pause()
            await pilot.press("j")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            after = _request_ops(app)
            assert len(after) == len(before) + 1
            assert after[-1] == "move"

    asyncio.run(_run())


def test_space_select_moves_down_only_on_toggle_on(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            table = app.query_one("#slots", DataTable)
            table.move_cursor(row=10, animate=False)
            await pilot.pause()

            await pilot.press("space")
            await pilot.pause()
            assert 11 in app.state.selected_slots
            assert table.cursor_row == 11

            await pilot.press("space")
            await pilot.pause()
            assert 12 in app.state.selected_slots
            assert table.cursor_row == 12

            table.move_cursor(row=10, animate=False)
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            assert 11 not in app.state.selected_slots
            assert table.cursor_row == 10

    asyncio.run(_run())


def test_escape_cancels_move_mode(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            await pilot.press("m")
            await pilot.pause()
            assert app.moving_src is not None

            await pilot.press("escape")
            await pilot.pause()
            assert app.moving_src is None

    asyncio.run(_run())


def test_status_shows_busy_and_idle_marker(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as _pilot:
            # Before any device contact: unknown state, no active class.
            app._handle_event(WorkerEvent(kind="idle", payload={"op": "refresh_inventory"}))
            status_bar = app.query_one("#status")
            left = app.query_one("#status_left", Static)
            right = app.query_one("#status_right", Static)
            assert not status_bar.has_class("active")
            assert "⚪" in str(right.render())

            # After inventory: device_online=True → green circle, no active class.
            app._handle_event(WorkerEvent(kind="inventory", payload={"sounds": {}}))
            assert not status_bar.has_class("active")
            assert "🟢" in str(right.render())

            # Busy op: yellow circle and active class.
            app._handle_event(WorkerEvent(kind="busy", payload={"op": "download"}))
            assert status_bar.has_class("active")
            assert "🟡" in str(right.render())

            # Error: red circle and error class.
            app._handle_event(WorkerEvent(kind="error", payload={"message": "fail"}))
            assert not status_bar.has_class("active")
            assert status_bar.has_class("error")
            assert "🔴" in str(right.render())

    asyncio.run(_run())


def test_progress_event_updates_status(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as _pilot:
            _make_ready(app)
            app._handle_event(
                WorkerEvent(
                    kind="progress",
                    payload={"op": "optimize", "message": "Optimizing slot 003", "current": 2, "total": 5},
                )
            )
            left = app.query_one("#status_left", Static)
            rendered = str(left.render())
            assert "Optimizing slot 003" in rendered
            assert "40%" in rendered  # 2/5 = 40% progress bar
            status_bar = app.query_one("#status")
            assert status_bar.has_class("active")

    asyncio.run(_run())


def test_dialog_log_file_receives_ui_messages(monkeypatch, tmp_path):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        dialog_path = tmp_path / "dialog.log"
        debug_path = tmp_path / "debug.jsonl"
        app = TUIApp(
            device_name="EP-133",
            debug=True,
            debug_log=str(debug_path),
            dialog_log=str(dialog_path),
        )
        async with app.run_test() as pilot:
            _make_ready(app)
            app._log("custom line")
            await pilot.pause()

        content = dialog_path.read_text(encoding="utf-8")
        assert "custom line" in content

    asyncio.run(_run())


def test_optimize_modal_uses_unstereo_label(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            await pilot.press("o")
            await pilot.pause()
            assert isinstance(app.screen, OptimizeModal)
            mono_box = app.screen.query_one("#opt_mono", Checkbox)
            assert "Unstereo" in str(mono_box.label)

    asyncio.run(_run())


def test_waveform_cache_hit_skips_worker_request(monkeypatch):
    class _FakeWaveformStore:
        def __init__(self, *args, **kwargs):
            self._d = {}
            self._f = {}

        @staticmethod
        def is_valid_bins(bins):
            return isinstance(bins, dict) and isinstance(bins.get("mins"), list) and isinstance(bins.get("maxs"), list)

        def get_for_slot(self, slot, sig):
            row = self._d.get(int(slot))
            if not row:
                return None
            if row["sig"] != sig:
                return None
            return row["bins"]

        def set_for_slot(self, slot, sig, bins, fingerprint=None):
            self._d[int(slot)] = {"sig": sig, "bins": bins, "fp": fingerprint}

        def set_fingerprint(self, hash_hex, payload):
            self._f[str(hash_hex)] = dict(payload)

    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)
    monkeypatch.setattr("tui.app.WaveformStore", _FakeWaveformStore)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as _pilot:
            _make_ready(app)
            app._handle_event(
                WorkerEvent(
                    kind="details",
                    payload={
                        "slot": 1,
                        "details": {
                            "name": "afterparty kick",
                            "channels": 1,
                            "samplerate": 46875,
                            "size_bytes": 2345,
                            "is_empty": False,
                        },
                    },
                )
            )
            app._waveform_by_slot.clear()
            app._waveform_pending.clear()

            sig = _waveform_signature(1, app.state.slots)
            assert sig is not None
            bins = {"mins": [-5, -3, 0], "maxs": [4, 7, 2], "width": 3}
            app._waveform_store.set_for_slot(1, sig, bins)  # type: ignore[attr-defined]

            before = list(_request_ops(app))
            app._ensure_waveform(1)
            after = _request_ops(app)

            assert after == before
            assert app._waveform_by_slot.get(1) == bins
            assert 1 not in app._waveform_pending

    asyncio.run(_run())


def test_question_mark_key_opens_help_modal(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            await pilot.press("question_mark")
            await pilot.pause()
            assert isinstance(app.screen, HelpModal)

            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, HelpModal)

    asyncio.run(_run())


def test_upload_occupied_slot_aborts_on_cancel(monkeypatch):
    """Cancelling the overwrite confirm must not queue any upload."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)
    monkeypatch.setattr("tui.app.pick_files", AsyncMock(return_value=[Path("/tmp/new.wav")]))

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            assert app.state.slots[1].exists

            await pilot.press("u")
            await pilot.pause()

            assert isinstance(app.screen, ConfirmModal)
            app.screen.dismiss(False)
            await pilot.pause()

            ops = _request_ops(app)
            assert "upload" not in ops

    asyncio.run(_run())


def test_upload_empty_slot_skips_confirm(monkeypatch):
    """Uploading to an empty slot must queue upload directly without a confirm dialog."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)
    monkeypatch.setattr("tui.app.pick_files", AsyncMock(return_value=[Path("/tmp/new.wav")]))

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            assert not app.state.slots[2].exists

            table = app.query_one("#slots", DataTable)
            table.move_cursor(row=1, animate=False)  # row index 1 = slot 2
            await pilot.pause()

            await pilot.press("u")
            await pilot.pause()

            assert not isinstance(app.screen, ConfirmModal)
            ops = _request_ops(app)
            assert "upload" in ops

    asyncio.run(_run())


def test_upload_multiple_files_queues_batch_upload(monkeypatch):
    """Selecting multiple files must queue a batch_upload starting from the cursor slot."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)
    monkeypatch.setattr(
        "tui.app.pick_files",
        AsyncMock(return_value=[Path("/tmp/a.wav"), Path("/tmp/b.wav")]),
    )

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            # Slots 2+ are empty

            table = app.query_one("#slots", DataTable)
            table.move_cursor(row=1, animate=False)  # slot 2
            await pilot.pause()

            await pilot.press("u")
            await pilot.pause()

            ops = _request_ops(app)
            assert "batch_upload" in ops

    asyncio.run(_run())


def test_precalc_cache_hit_skips_midi_download():
    """When _has_cached_waveform returns True, _maybe_run_waveform_precalc_step
    must not call _download_slot_wav_bytes (zero MIDI traffic)."""
    from queue import Queue as _Queue
    from tui.worker import DeviceWorker

    download_calls: list[int] = []

    class _FakeClient:
        pass

    class _Worker(DeviceWorker):
        def _ensure_client(self):
            return _FakeClient()

        def _download_slot_wav_bytes(self, client, *, slot, phases, cancel_check=None):
            download_calls.append(slot)
            return None

    event_q: _Queue = _Queue()
    req_q: _Queue = _Queue()

    # cache_checker returns True for slot 5 (cache hit) and False for slot 7 (cache miss).
    def _checker(slot: int) -> bool:
        return slot == 5

    worker = _Worker(
        device_name=None,
        request_queue=req_q,
        event_queue=event_q,
        waveform_cache_checker=_checker,
    )
    # Manually populate the precalc queue with two slots.
    worker._waveform_precalc_slots = [5, 7]

    # Step 1: slot 5 — cache hit, no download.
    worker._maybe_run_waveform_precalc_step()
    assert download_calls == [], "slot 5 is cached: _download_slot_wav_bytes must NOT be called"

    # Step 2: slot 7 — cache miss, download proceeds.
    worker._maybe_run_waveform_precalc_step()
    assert download_calls == [7], "slot 7 is not cached: _download_slot_wav_bytes MUST be called"


def test_waveform_event_persists_fingerprint_index(monkeypatch):
    class _FakeWaveformStore:
        def __init__(self, *args, **kwargs):
            self._d = {}
            self._f = {}

        @staticmethod
        def is_valid_bins(bins):
            return isinstance(bins, dict) and isinstance(bins.get("mins"), list) and isinstance(bins.get("maxs"), list)

        def get_for_slot(self, slot, sig):
            row = self._d.get(int(slot))
            if not row:
                return None
            if row["sig"] != sig:
                return None
            return row["bins"]

        def set_for_slot(self, slot, sig, bins, fingerprint=None):
            self._d[int(slot)] = {"sig": sig, "bins": bins, "fp": fingerprint}

        def set_fingerprint(self, hash_hex, payload):
            self._f[str(hash_hex)] = dict(payload)

    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)
    monkeypatch.setattr("tui.app.WaveformStore", _FakeWaveformStore)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as _pilot:
            _make_ready(app)
            app._handle_event(
                WorkerEvent(
                    kind="details",
                    payload={
                        "slot": 1,
                        "details": {
                            "name": "afterparty kick",
                            "channels": 1,
                            "samplerate": 46875,
                            "size_bytes": 2345,
                            "is_empty": False,
                        },
                    },
                )
            )

            bins = {"mins": [-64, -12, -40], "maxs": [64, 45, 20], "width": 3}
            fp = {
                "sha256": "c" * 64,
                "frames": 100,
                "channels": 1,
                "samplerate": 46875,
                "sample_width": 2,
                "duration_s": 0.1,
            }
            app._handle_event(WorkerEvent(kind="waveform", payload={"slot": 1, "bins": bins, "fp": fp}))
            store = app._waveform_store  # type: ignore[attr-defined]
            assert store._f.get("c" * 64) is not None

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Progress bar rendering
# ---------------------------------------------------------------------------

def test_render_progress_bar():
    assert _render_progress_bar(0, 10) == "[░░░░░░░░░░░░░░░░] 0%"
    assert _render_progress_bar(5, 10) == "[████████░░░░░░░░] 50%"
    assert _render_progress_bar(10, 10) == "[████████████████] 100%"
    assert _render_progress_bar(1, 3) == "[█████░░░░░░░░░░░] 33%"


def test_progress_bar_shown_for_multi_step_ops(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as _pilot:
            _make_ready(app)
            # Multi-step: total > 2 → bar shown
            app._handle_event(WorkerEvent(
                kind="progress",
                payload={"op": "bulk_delete", "message": "Deleting slot 005", "current": 3, "total": 8},
            ))
            rendered = str(app.query_one("#status_left", Static).render())
            assert "█" in rendered
            assert "37%" in rendered  # 3/8

            # Single op: total=2 → no bar
            app._handle_event(WorkerEvent(
                kind="progress",
                payload={"op": "upload", "message": "Uploading to slot 050", "current": 1, "total": 2},
            ))
            rendered = str(app.query_one("#status_left", Static).render())
            assert "█" not in rendered

    asyncio.run(_run())


def test_progress_bar_resets_on_idle(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as _pilot:
            _make_ready(app)
            app._handle_event(WorkerEvent(
                kind="progress",
                payload={"op": "optimize", "message": "Optimizing", "current": 5, "total": 10},
            ))
            assert app._progress_total == 10
            app._handle_event(WorkerEvent(kind="idle", payload={"op": "optimize"}))
            assert app._progress_current == 0
            assert app._progress_total == 0
            rendered = str(app.query_one("#status_left", Static).render())
            assert "█" not in rendered

    asyncio.run(_run())
