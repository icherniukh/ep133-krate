"""Krate mobile app — Toga UI for the EP-133 KO-II."""

from __future__ import annotations

import asyncio
import logging

try:
    import std_nslog  # noqa: F401  # iOS logging bridge; import for side effects.
except ImportError:
    std_nslog = None  # type: ignore[assignment]

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from .transport import create_transport, MIDITransport
from .screens.slot_list import SlotListScreen
from .screens.upload_queue import UploadQueueScreen

_log = logging.getLogger(__name__)


class KrateApp(toga.App):

    def startup(self) -> None:
        self._transport: MIDITransport = create_transport()
        self._client = None

        root = toga.Box(style=Pack(direction=COLUMN))

        conn_bar = toga.Box(style=Pack(direction=ROW, margin=8, align_items="center"))
        self._status_dot = toga.Box(
            style=Pack(width=12, height=12, background_color="#cc0000", margin_right=8),
        )
        conn_bar.add(self._status_dot)
        self._device_picker = toga.Selection(
            items=[],
            style=Pack(flex=1),
        )
        conn_bar.add(self._device_picker)
        self._connect_btn = toga.Button(
            "Connect",
            on_press=self._on_connect,
            style=Pack(margin_left=8),
        )
        conn_bar.add(self._connect_btn)
        scan_btn = toga.Button(
            "Scan",
            on_press=self._on_scan,
            style=Pack(margin_left=4),
        )
        conn_bar.add(scan_btn)
        root.add(conn_bar)

        self._status_label = toga.Label(
            "Tap Scan to find devices.",
            style=Pack(margin_left=8, margin_bottom=4, color="#888888", font_size=12),
        )
        root.add(self._status_label)

        nav = toga.Box(style=Pack(direction=ROW, margin=4))
        btn_slots = toga.Button(
            "Slots",
            on_press=lambda _: self._show_screen("slots"),
            style=Pack(flex=1, margin=4),
        )
        btn_upload = toga.Button(
            "Upload",
            on_press=lambda _: self._show_screen("upload"),
            style=Pack(flex=1, margin=4),
        )
        nav.add(btn_slots)
        nav.add(btn_upload)
        root.add(nav)

        self._slot_screen = SlotListScreen(transport=self._transport)
        self._upload_screen = UploadQueueScreen(transport=self._transport)

        self._content_box = toga.Box(style=Pack(flex=1, direction=COLUMN))
        self._content_box.add(self._slot_screen)
        root.add(self._content_box)

        self._active_screen: str = "slots"
        self._devices = []

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = root
        self.main_window.show()

        self.on_running = self._on_running

    async def _on_running(self, app) -> None:
        devices = await asyncio.to_thread(self._do_scan)
        self._apply_scan_results(devices)

    def _do_scan(self) -> list:
        """Blocking: run on thread pool. Returns device list, touches no UI."""
        return self._transport.discover_devices()

    def _apply_scan_results(self, devices: list) -> None:
        """Main-thread only: update UI with discovered devices."""
        self._devices = devices
        names = [d.name for d in devices]
        self._device_picker.items = names
        if devices:
            for d in devices:
                if "EP-133" in d.name or "KO II" in d.name:
                    self._device_picker.value = d.name
                    break
            self._status_label.text = f"{len(devices)} device(s) found."
        else:
            self._status_label.text = "No MIDI devices found."

    async def _on_scan(self, widget: toga.Button) -> None:
        self._status_label.text = "Scanning…"
        devices = await asyncio.to_thread(self._do_scan)
        self._apply_scan_results(devices)

    async def _on_connect(self, widget: toga.Button) -> None:
        if self._transport.is_connected:
            await asyncio.to_thread(self._do_disconnect)
            # Back on main thread — safe to update UI
            self._slot_screen.set_client(None)
            self._upload_screen.set_client(None)
            self._status_dot.style.background_color = "#cc0000"
            self._connect_btn.text = "Connect"
            self._status_label.text = "Disconnected."
            return

        selected = self._device_picker.value
        if not selected:
            self._status_label.text = "Select a device first."
            return

        device = None
        for d in self._devices:
            if d.name == selected:
                device = d
                break
        if not device:
            self._status_label.text = "Device not found — try scanning again."
            return

        self._status_label.text = f"Connecting to {device.name}…"
        try:
            client = await asyncio.to_thread(self._connect_device, device)
            # Back on main thread — safe to update UI
            self._client = client
            self._slot_screen.set_client(client)
            self._upload_screen.set_client(client)
            self._status_dot.style.background_color = "#00cc00"
            self._connect_btn.text = "Disconnect"
            self._status_label.text = f"Connected: {device.name}"
            self._slot_screen.on_connected()
            self._upload_screen.on_connected()
        except Exception as exc:
            self._status_label.text = f"Connect failed: {exc}"

    def _connect_device(self, device) -> "EP133Client":
        """Blocking: run on thread pool. Returns connected client, touches no UI."""
        self._transport.connect(device)
        from core.client import EP133Client
        client = EP133Client(
            device_name=device.name,
            transport=self._transport,
        )
        client.connect()
        return client

    def _do_disconnect(self) -> None:
        """Blocking: run on thread pool. Closes MIDI, touches no UI."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def _show_screen(self, name: str) -> None:
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
    return KrateApp("Krate", "com.ep133.krate")
