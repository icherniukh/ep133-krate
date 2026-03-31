"""Krate mobile app — Toga UI for the EP-133 KO-II."""

from __future__ import annotations

import asyncio
import logging

try:
    import std_nslog  # noqa: F401  # pylint: disable=unused-import
except ImportError:
    std_nslog = None  # type: ignore[assignment]

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from core.client import EP133Client
from .transport import create_transport

# Import new screens
from .screens.device_tab import DeviceTab
from .screens.local_tab import LocalTab


class KrateApp(toga.App):
    """Main Application Entry Point."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._transport = None
        self._client = None
        
        # UI Elements that need tracking
        self.device_tab = None
        self.local_tab = None

    def startup(self) -> None:
        """Called when the app starts."""
        self.main_window = toga.MainWindow(title=self.formal_name)
        
        # Setup Tabs
        self.tabs = toga.OptionContainer()
        self.device_tab = DeviceTab(self)
        self.local_tab = LocalTab(self)
        
        self.tabs.add("Device", self.device_tab)
        self.tabs.add("Local", self.local_tab)

        # Tools Menu
        tools_cmd = toga.Command(
            self.action_open_tools,
            text="Tools",
            tooltip="Bulk operations and settings"
        )
        self.commands.add(tools_cmd)

        self.main_window.content = self.tabs
        
        # In a real app we'd trigger scanning here or on a separate "Connect" screen,
        # but for this foundational UI we'll just show the main tabs immediately.
        
        self.main_window.show()

    def action_open_tools(self, _widget):
        """Open the tools menu for bulk ops."""
        self.main_window.info_dialog("Tools", "Bulk operations (Squash, Optimize All) will go here.")

    def _log(self, msg: str) -> None:
        print(f"[UI] {msg}")

    # --- Transport & Client Management (Stubs for now) ---
    
    def connect_device(self, device):
        pass


def main() -> KrateApp:
    logging.basicConfig(level=logging.INFO)
    return KrateApp("Krate", "com.ep133")
