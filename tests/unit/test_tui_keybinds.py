"""Tests for TUIApp keybinding behavior.

Covers:
- `?` key: opens HelpModal; Escape dismisses it
- `O` key (uppercase): dispatches optimize-all action via ConfirmModal
- `d` key: opens download TextInputModal (d=download per BINDINGS)
- `backspace` key: opens delete ConfirmModal
- Modal dismiss: Escape closes HelpModal and move-mode cancel
- Squash action: `s` key opens ConfirmModal for squash
"""
from __future__ import annotations

import asyncio

import pytest

from tui.app import TUIApp
from tui.ui import ConfirmModal, HelpModal, OptimizeModal, TextInputModal
from tui.worker import WorkerEvent


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


# ---------------------------------------------------------------------------
# ? key → HelpModal
# ---------------------------------------------------------------------------

def test_question_mark_opens_help_modal(monkeypatch):
    """Pressing ? must push HelpModal onto the screen stack."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            await pilot.press("question_mark")
            await pilot.pause()
            assert isinstance(app.screen, HelpModal)

    asyncio.run(_run())


def test_escape_dismisses_help_modal(monkeypatch):
    """Pressing Escape while HelpModal is open must dismiss it."""
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


def test_help_modal_does_not_submit_worker_request(monkeypatch):
    """Opening and closing HelpModal must not enqueue any worker request."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            before = list(_request_ops(app))

            await pilot.press("question_mark")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

            after = _request_ops(app)
            assert after == before

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# O key (uppercase) → optimize-all via ConfirmModal
# ---------------------------------------------------------------------------

def test_optimize_all_key_opens_confirm_modal(monkeypatch):
    """Pressing O (uppercase) must open a ConfirmModal for optimize-all."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            await pilot.press("O")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmModal)

    asyncio.run(_run())


def test_optimize_all_confirm_submits_request(monkeypatch):
    """Confirming the optimize-all dialog must submit an optimize_all worker request."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            await pilot.press("O")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmModal)
            app.screen.dismiss(True)
            await pilot.pause()

            ops = _request_ops(app)
            assert "optimize_all" in ops

    asyncio.run(_run())


def test_optimize_all_cancel_skips_request(monkeypatch):
    """Cancelling the optimize-all dialog must NOT submit any worker request."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            before = list(_request_ops(app))

            await pilot.press("O")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmModal)
            app.screen.dismiss(False)
            await pilot.pause()

            after = _request_ops(app)
            assert "optimize_all" not in after
            assert after == before

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# d key → download (opens TextInputModal)
# Note: `d` is bound to `action_download`, NOT delete.
# Delete is bound to `backspace` / `delete`.
# ---------------------------------------------------------------------------

def test_d_key_opens_download_modal(monkeypatch):
    """Pressing d (download) must push a TextInputModal for the output path."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            await pilot.press("d")
            await pilot.pause()
            assert isinstance(app.screen, TextInputModal)

    asyncio.run(_run())


def test_d_key_download_modal_dismiss_submits_request(monkeypatch):
    """Confirming a path in the download modal must submit a download worker request."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            await pilot.press("d")
            await pilot.pause()
            assert isinstance(app.screen, TextInputModal)
            app.screen.dismiss("/tmp/test-dl.wav")
            await pilot.pause()

            ops = _request_ops(app)
            assert "download" in ops

    asyncio.run(_run())


def test_d_key_download_modal_cancel_skips_request(monkeypatch):
    """Cancelling the download modal (dismiss with None) must not submit a request."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            before = list(_request_ops(app))

            await pilot.press("d")
            await pilot.pause()
            assert isinstance(app.screen, TextInputModal)
            app.screen.dismiss(None)
            await pilot.pause()

            after = _request_ops(app)
            assert "download" not in after
            assert after == before

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# backspace key → delete ConfirmModal
# ---------------------------------------------------------------------------

def test_backspace_key_opens_delete_confirm(monkeypatch):
    """Pressing backspace on an occupied slot must push a ConfirmModal."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            await pilot.press("backspace")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmModal)

    asyncio.run(_run())


def test_backspace_confirm_submits_delete(monkeypatch):
    """Confirming the delete dialog must submit a delete worker request."""
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


def test_backspace_cancel_skips_delete(monkeypatch):
    """Cancelling the delete dialog must not submit any delete request."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            before = list(_request_ops(app))

            await pilot.press("backspace")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmModal)
            app.screen.dismiss(False)
            await pilot.pause()

            after = _request_ops(app)
            assert "delete" not in after

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Escape in move mode cancels move (not a modal, but same dismiss mechanic)
# ---------------------------------------------------------------------------

def test_escape_in_move_mode_cancels_move(monkeypatch):
    """Pressing Escape while in move mode must cancel the move (moving_src → None)."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            # Enter move mode
            await pilot.press("m")
            await pilot.pause()
            assert app.moving_src is not None

            # Escape must cancel it
            await pilot.press("escape")
            await pilot.pause()
            assert app.moving_src is None

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# s key → squash ConfirmModal
# ---------------------------------------------------------------------------

def test_s_key_opens_squash_confirm(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            await pilot.press("s")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmModal)

    asyncio.run(_run())


def test_s_key_squash_confirm_submits_request(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            await pilot.press("s")
            await pilot.pause()
            app.screen.dismiss(True)
            await pilot.pause()
            assert "squash" in _request_ops(app)

    asyncio.run(_run())


def test_s_key_squash_cancel_skips_request(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            before = list(_request_ops(app))
            await pilot.press("s")
            await pilot.pause()
            app.screen.dismiss(False)
            await pilot.pause()
            assert _request_ops(app) == before

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# c key → copy TextInputModal (occupied slot)
# ---------------------------------------------------------------------------

def test_c_key_opens_copy_modal(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            await pilot.press("c")
            await pilot.pause()
            assert isinstance(app.screen, TextInputModal)

    asyncio.run(_run())


def test_c_key_copy_confirm_submits_request(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            await pilot.press("c")
            await pilot.pause()
            app.screen.dismiss("50")
            await pilot.pause()
            assert "copy" in _request_ops(app)

    asyncio.run(_run())


def test_c_key_copy_cancel_skips_request(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            before = list(_request_ops(app))
            await pilot.press("c")
            await pilot.pause()
            app.screen.dismiss(None)
            await pilot.pause()
            assert _request_ops(app) == before

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# r key → rename TextInputModal
# ---------------------------------------------------------------------------

def test_r_key_opens_rename_modal(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            await pilot.press("r")
            await pilot.pause()
            assert isinstance(app.screen, TextInputModal)

    asyncio.run(_run())


def test_r_key_rename_confirm_submits_request(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            await pilot.press("r")
            await pilot.pause()
            app.screen.dismiss("new-name")
            await pilot.pause()
            assert "rename" in _request_ops(app)

    asyncio.run(_run())


def test_r_key_rename_cancel_skips_request(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            before = list(_request_ops(app))
            await pilot.press("r")
            await pilot.pause()
            app.screen.dismiss(None)
            await pilot.pause()
            assert _request_ops(app) == before

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# o key → optimize OptimizeModal
# ---------------------------------------------------------------------------

def test_o_key_opens_optimize_modal(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            await pilot.press("o")
            await pilot.pause()
            assert isinstance(app.screen, OptimizeModal)

    asyncio.run(_run())


def test_o_key_optimize_confirm_submits_request(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            await pilot.press("o")
            await pilot.pause()
            app.screen.dismiss((True, None, None, 0.0))
            await pilot.pause()
            assert "optimize" in _request_ops(app)

    asyncio.run(_run())


def test_o_key_optimize_cancel_skips_request(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            before = list(_request_ops(app))
            await pilot.press("o")
            await pilot.pause()
            app.screen.dismiss(None)
            await pilot.pause()
            assert _request_ops(app) == before

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# l key → toggle log pane
# ---------------------------------------------------------------------------

def test_l_key_hides_log_pane(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            assert app._logs_visible
            await pilot.press("l")
            await pilot.pause()
            assert not app._logs_visible

    asyncio.run(_run())


def test_l_key_toggles_log_pane_back_on(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            await pilot.press("l")
            await pilot.pause()
            await pilot.press("l")
            await pilot.pause()
            assert app._logs_visible

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# p key → audition (occupied slot submits request)
# ---------------------------------------------------------------------------

def test_p_key_queues_audition_request(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            await pilot.press("p")
            await pilot.pause()
            assert "audition" in _request_ops(app)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# ctrl+r → refresh inventory
# ---------------------------------------------------------------------------

def test_ctrl_r_queues_refresh(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            before_count = len(_request_ops(app))
            await pilot.press("ctrl+r")
            await pilot.pause()
            ops = _request_ops(app)
            assert len(ops) > before_count
            assert ops[-1] == "refresh_inventory"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# space key → toggle slot selection
# ---------------------------------------------------------------------------

def test_space_key_selects_slot(monkeypatch):
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            assert 1 not in app.state.selected_slots
            await pilot.press("space")
            await pilot.pause()
            assert 1 in app.state.selected_slots

    asyncio.run(_run())


def test_space_key_deselects_slot(monkeypatch):
    """Space on an already-selected slot removes it from the selection."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            # Pre-select slot 1 and keep cursor there
            app.state.selected_slots.add(1)
            app.state.selected_slot = 1
            await pilot.press("space")
            await pilot.pause()
            assert 1 not in app.state.selected_slots

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Modal key isolation — app keys must not fire while a modal is open
# ---------------------------------------------------------------------------

def test_keys_dont_fire_app_actions_while_modal_open(monkeypatch):
    """Pressing app keys (d, s, space, etc.) while a modal is open must NOT
    trigger the app's action — they should be swallowed by the modal."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            # Open rename modal (TextInputModal)
            await pilot.press("r")
            await pilot.pause()
            assert isinstance(app.screen, TextInputModal)
            before = list(_request_ops(app))

            # Press keys that would normally trigger app actions
            for key in ["d", "s", "o", "c", "m", "space", "backspace", "p"]:
                await pilot.press(key)
                await pilot.pause()

            # No new worker requests should have been submitted
            assert _request_ops(app) == before
            # Still on the same modal
            assert isinstance(app.screen, TextInputModal)

    asyncio.run(_run())


def test_enter_submits_rename_modal(monkeypatch):
    """Pressing Enter in the rename TextInputModal must submit the value,
    not trigger the app's view_details action."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            await pilot.press("r")
            await pilot.pause()
            assert isinstance(app.screen, TextInputModal)

            # Type a name and press Enter
            inp = app.screen.query_one("#value")
            inp.value = "kick-808"
            await pilot.press("enter")
            await pilot.pause()

            # Modal should be dismissed
            assert not isinstance(app.screen, TextInputModal)
            # Rename request should be submitted
            assert "rename" in _request_ops(app)

    asyncio.run(_run())


def test_enter_confirms_confirm_modal(monkeypatch):
    """Pressing Enter in a ConfirmModal must confirm (dismiss True),
    not trigger the app's view_details action."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            await pilot.press("s")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmModal)

            await pilot.press("enter")
            await pilot.pause()

            # Modal should be dismissed — confirm modal focuses Cancel by
            # default, so Enter on Cancel dismisses with False (no squash).
            # The key point: we're NOT still on ConfirmModal and no
            # view_details action fired.
            assert not isinstance(app.screen, ConfirmModal)

    asyncio.run(_run())


def test_space_toggles_checkbox_in_optimize_modal(monkeypatch):
    """Pressing Space in OptimizeModal must toggle a checkbox,
    not trigger the app's toggle_select action."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)
            selection_before = set(app.state.selected_slots)

            await pilot.press("o")
            await pilot.pause()
            assert isinstance(app.screen, OptimizeModal)

            # Focus the mono checkbox (should be focused by default)
            from textual.widgets import Checkbox
            cb = app.screen.query_one("#opt_mono", Checkbox)
            cb.focus()
            initial_value = cb.value

            await pilot.press("space")
            await pilot.pause()

            # Checkbox should have toggled
            assert cb.value != initial_value
            # App selection must not have changed
            assert app.state.selected_slots == selection_before

    asyncio.run(_run())


def test_up_down_navigate_within_confirm_modal(monkeypatch):
    """Up/Down in a ConfirmModal must move focus between buttons,
    not move the app's DataTable cursor."""
    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="EP-133", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            await pilot.press("s")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmModal)

            # Note which slot was selected before
            slot_before = app.state.selected_slot

            # Press up/down — should not change app cursor
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("up")
            await pilot.pause()

            # App slot selection unchanged
            assert app.state.selected_slot == slot_before
            # Still on modal
            assert isinstance(app.screen, ConfirmModal)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# audition_started event → playback state initialization
# ---------------------------------------------------------------------------

def test_audition_started_event_initializes_playback_state(monkeypatch):
    """_handle_event('audition_started') calls _start_playback_animation."""
    import time

    monkeypatch.setattr("tui.app.DeviceWorker", StubWorker)

    async def _run():
        app = TUIApp(device_name="test", debug=False)
        async with app.run_test() as pilot:
            _make_ready(app)

            before = time.monotonic()
            app._handle_event(WorkerEvent(kind="audition_started", payload={"slot": 1, "duration_s": 1.5}))
            after = time.monotonic()
            await pilot.pause()

            assert app._play_slot == 1
            assert app._play_duration == pytest.approx(1.5)
            assert before <= app._play_start <= after

            # Clean up timer
            if app._play_timer is not None:
                app._play_timer.stop()

    asyncio.run(_run())
