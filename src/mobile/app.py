"""
Krate mobile app — Toga companion for the EP-133 KO-II sample manager.

Entry point for BeeWare packaging. The app connects to the krate-bridge
HTTP service running on the same LAN as the device.
"""

from __future__ import annotations

try:
    import toga
    from toga.style import Pack
    from toga.style.pack import COLUMN, ROW
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "toga is required for the mobile app. Install with: pip install toga"
    ) from exc

from .screens.slot_list import SlotListScreen
from .screens.upload_queue import UploadQueueScreen


class KrateApp(toga.App):
    """Toga application — slot browser and upload queue for EP-133 KO-II."""

    def startup(self) -> None:
        self.bridge_url = "http://localhost:8765"

        # Main container with tab-style navigation via buttons
        root = toga.Box(style=Pack(direction=COLUMN))

        # Navigation row
        nav = toga.Box(style=Pack(direction=ROW, padding=4))
        btn_slots = toga.Button(
            "Slots",
            on_press=lambda _: self._show_screen("slots"),
            style=Pack(flex=1, padding=4),
        )
        btn_upload = toga.Button(
            "Upload",
            on_press=lambda _: self._show_screen("upload"),
            style=Pack(flex=1, padding=4),
        )
        nav.add(btn_slots)
        nav.add(btn_upload)
        root.add(nav)

        # Screens
        self._slot_screen = SlotListScreen(bridge_url=self.bridge_url)
        self._upload_screen = UploadQueueScreen(bridge_url=self.bridge_url)

        self._content_box = toga.Box(style=Pack(flex=1, direction=COLUMN))
        self._content_box.add(self._slot_screen)
        root.add(self._content_box)

        self._active_screen: str = "slots"

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = root
        self.main_window.show()

    def _show_screen(self, name: str) -> None:
        """Switch the visible screen."""
        if name == self._active_screen:
            return
        for child in list(self._content_box.children):
            self._content_box.remove(child)
        if name == "slots":
            self._content_box.add(self._slot_screen)
        elif name == "upload":
            self._content_box.add(self._upload_screen)
        self._active_screen = name


def main() -> KrateApp:
    """BeeWare entry point."""
    return KrateApp("Krate", "com.ep133.krate")
