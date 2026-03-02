import asyncio

import pytest

from ko2_tui.app import KO2TUIApp
from ko2_tui.ui import TextInputModal


pytestmark = pytest.mark.e2e


async def _wait_until(predicate, *, timeout_s: float = 5.0, step_s: float = 0.05) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(step_s)
    raise AssertionError("Timed out waiting for condition")


def test_tui_rename_roundtrip_with_emulator(device_name, emulator_device):
    async def _run():
        app = KO2TUIApp(device_name=device_name, debug=False)
        async with app.run_test() as pilot:
            await _wait_until(lambda: app.state.slots[1].exists, timeout_s=5.0)
            await _wait_until(
                lambda: app.state.slots[1].name != "001.pcm",
                timeout_s=5.0,
            )
            await _wait_until(lambda: not app.state.busy, timeout_s=12.0)

            original_name = app.state.slots[1].name
            new_name = "tui rename e2e"

            app.action_rename()
            await pilot.pause()
            assert isinstance(app.screen, TextInputModal)
            app.screen.dismiss(new_name)
            await pilot.pause()

            await _wait_until(lambda: app.state.slots[1].name == new_name, timeout_s=12.0)

            # Restore baseline for future runs.
            app.action_rename()
            await pilot.pause()
            assert isinstance(app.screen, TextInputModal)
            app.screen.dismiss(original_name)
            await pilot.pause()
            await _wait_until(lambda: app.state.slots[1].name == original_name, timeout_s=12.0)

            app.action_quit()

    asyncio.run(_run())
