"""Slot browser screen — lists occupied sample slots with audition."""

from __future__ import annotations

import asyncio
from typing import Optional

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW


class SlotListScreen(toga.Box):

    def __init__(self, transport=None) -> None:
        super().__init__(style=Pack(direction=COLUMN, margin=8))
        self._transport = transport
        self._client = None
        self._slots: dict = {}

        header = toga.Box(style=Pack(direction=ROW, margin_bottom=8))
        title = toga.Label(
            "Sample Slots",
            style=Pack(flex=1, font_size=18),
        )
        refresh_btn = toga.Button(
            "Refresh",
            on_press=self._on_refresh,
            style=Pack(margin_left=8),
        )
        header.add(title)
        header.add(refresh_btn)
        self.add(header)

        self._status_label = toga.Label(
            "Connect to device to load slots.",
            style=Pack(margin_bottom=8, color="#888888"),
        )
        self.add(self._status_label)

        self._list_view = toga.DetailedList(
            accessors=["title", "subtitle", "icon"],
            on_select=self._on_slot_select,
            style=Pack(flex=1),
        )
        self.add(self._list_view)

        self._play_btn = toga.Button(
            "Play Selected",
            on_press=self._on_play,
            style=Pack(margin_top=8),
            enabled=False,
        )
        self.add(self._play_btn)

    def set_client(self, client) -> None:
        self._client = client

    def on_connected(self) -> None:
        self._status_label.text = "Connected. Tap Refresh to load slots."

    async def _on_refresh(self, widget: toga.Button) -> None:
        if not self._client:
            self._status_label.text = "Not connected to device."
            return

        self._status_label.text = "Loading…"
        self._list_view.data = []
        self._slots = {}
        try:
            slots = await asyncio.to_thread(self._fetch_slots)
            if not slots:
                self._status_label.text = "No samples found on device."
                return
            self._slots = slots
            items = [
                {
                    "title": f"[{num:03d}] {entry.get('name', '(unnamed)')}",
                    "subtitle": _fmt_size(entry.get("size", 0)),
                }
                for num, entry in sorted(slots.items())
            ]
            self._list_view.data = items
            self._status_label.text = f"{len(slots)} sample(s) loaded."
        except Exception as exc:
            self._status_label.text = f"Error: {exc}"

    def _fetch_slots(self) -> dict:
        return self._client.list_sounds()

    def _on_slot_select(self, widget: toga.DetailedList, row=None, **kwargs) -> None:
        self._play_btn.enabled = row is not None

    async def _on_play(self, widget: toga.Button) -> None:
        if not self._client:
            self._status_label.text = "Not connected."
            return

        selection = self._list_view.selection
        if selection is None:
            return

        title = selection.title if hasattr(selection, "title") else str(selection)
        try:
            slot_str = title.split("]")[0].lstrip("[")
            slot = int(slot_str)
        except (ValueError, IndexError):
            self._status_label.text = "Could not determine slot number."
            return

        self._status_label.text = f"Playing slot {slot}…"
        try:
            await asyncio.to_thread(self._client.audition, slot)
            self._status_label.text = f"Playing slot {slot}."
        except Exception as exc:
            self._status_label.text = f"Audition error: {exc}"


def _fmt_size(size_bytes: int) -> str:
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"
