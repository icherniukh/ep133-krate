import asyncio
import tempfile
from pathlib import Path

import pytest

from tests.helpers import create_test_wav
from tui.app import TUIApp
from tui import actions


pytestmark = pytest.mark.e2e

UPLOAD_SLOT = 50  # Use a high slot unlikely to conflict with existing samples


async def _wait_until(predicate, *, timeout_s: float = 12.0, step_s: float = 0.05) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(step_s)
    raise AssertionError("Timed out waiting for condition")


def test_tui_upload_populates_slot(device_name, emulator_device):
    """Upload a WAV via TUI worker, verify slot appears in inventory."""
    with tempfile.TemporaryDirectory() as td:
        wav_path = Path(td) / "e2e-upload.wav"
        create_test_wav(wav_path, duration_sec=0.1)

        async def _run():
            app = TUIApp(device_name=device_name, debug=False)
            async with app.run_test() as pilot:
                await _wait_until(lambda: not app.state.busy, timeout_s=12.0)

                # Ensure slot is empty before upload
                if app.state.slots[UPLOAD_SLOT].exists:
                    app._queue_request(actions.delete(UPLOAD_SLOT))
                    await _wait_until(lambda: not app.state.busy, timeout_s=12.0)

                app._queue_request(actions.upload(UPLOAD_SLOT, str(wav_path)))
                await _wait_until(lambda: not app.state.busy, timeout_s=15.0)

                # Verify slot is populated
                assert app.state.slots[UPLOAD_SLOT].exists, \
                    f"Slot {UPLOAD_SLOT} should exist after upload"
                assert app.state.slots[UPLOAD_SLOT].size_bytes > 0

                # Cleanup
                app._queue_request(actions.delete(UPLOAD_SLOT))
                await _wait_until(lambda: not app.state.busy, timeout_s=12.0)

                app.action_quit()

        asyncio.run(_run())


def test_tui_move_transfers_sample(device_name, emulator_device):
    """Move a sample via TUI worker, verify source empty and destination occupied."""
    src_slot = UPLOAD_SLOT
    dst_slot = UPLOAD_SLOT + 1

    with tempfile.TemporaryDirectory() as td:
        wav_path = Path(td) / "e2e-move.wav"
        create_test_wav(wav_path, duration_sec=0.1)

        async def _run():
            app = TUIApp(device_name=device_name, debug=False)
            async with app.run_test() as pilot:
                await _wait_until(lambda: not app.state.busy, timeout_s=12.0)

                # Clean both slots
                for slot in (src_slot, dst_slot):
                    if app.state.slots[slot].exists:
                        app._queue_request(actions.delete(slot))
                        await _wait_until(lambda: not app.state.busy, timeout_s=12.0)

                # Upload to source slot
                app._queue_request(actions.upload(src_slot, str(wav_path)))
                await _wait_until(lambda: not app.state.busy, timeout_s=15.0)
                assert app.state.slots[src_slot].exists

                src_name = app.state.slots[src_slot].name

                # Move src → dst
                app._queue_request(actions.move(src_slot, dst_slot))
                await _wait_until(lambda: not app.state.busy, timeout_s=15.0)

                # Verify: source empty, destination has the sample
                assert not app.state.slots[src_slot].exists, \
                    f"Slot {src_slot} should be empty after move"
                assert app.state.slots[dst_slot].exists, \
                    f"Slot {dst_slot} should exist after move"

                # Cleanup
                app._queue_request(actions.delete(dst_slot))
                await _wait_until(lambda: not app.state.busy, timeout_s=12.0)

                app.action_quit()

        asyncio.run(_run())


def test_tui_inventory_not_empty_after_upload(device_name, emulator_device):
    """After upload, at least some slots must show as occupied (catches all-empty bug)."""
    with tempfile.TemporaryDirectory() as td:
        wav_path = Path(td) / "e2e-notempty.wav"
        create_test_wav(wav_path, duration_sec=0.1)

        async def _run():
            app = TUIApp(device_name=device_name, debug=False)
            async with app.run_test() as pilot:
                await _wait_until(lambda: not app.state.busy, timeout_s=12.0)

                # Ensure slot is empty
                if app.state.slots[UPLOAD_SLOT].exists:
                    app._queue_request(actions.delete(UPLOAD_SLOT))
                    await _wait_until(lambda: not app.state.busy, timeout_s=12.0)

                app._queue_request(actions.upload(UPLOAD_SLOT, str(wav_path)))
                await _wait_until(lambda: not app.state.busy, timeout_s=15.0)

                # The all-empty bug: after upload, inventory shows zero occupied slots.
                occupied = [s for s in range(1, 1000) if app.state.slots[s].exists]
                assert len(occupied) > 0, "Inventory must not be empty after upload"

                # Cleanup
                app._queue_request(actions.delete(UPLOAD_SLOT))
                await _wait_until(lambda: not app.state.busy, timeout_s=12.0)

                app.action_quit()

        asyncio.run(_run())
