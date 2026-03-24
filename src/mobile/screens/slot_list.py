"""
Slot browser screen for the Krate mobile app.

Fetches the sample slot list from the krate-bridge HTTP service and
displays it in a scrollable list. A Refresh button reloads from the bridge.
If the bridge is not reachable the screen shows a friendly error message.
"""

from __future__ import annotations

import asyncio

try:
    import toga
    from toga.style import Pack
    from toga.style.pack import COLUMN, ROW
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "toga is required for the mobile app. Install with: pip install toga"
    ) from exc

try:
    import httpx
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "httpx is required for the mobile app. Install with: pip install httpx"
    ) from exc


class SlotListScreen(toga.Box):
    """Toga Box that shows all occupied EP-133 sample slots."""

    def __init__(self, bridge_url: str = "http://localhost:8765") -> None:
        super().__init__(style=Pack(direction=COLUMN, padding=8))
        self._bridge_url = bridge_url

        header = toga.Box(style=Pack(direction=ROW, padding_bottom=8))
        title = toga.Label(
            "Sample Slots",
            style=Pack(flex=1, font_size=18),
        )
        refresh_btn = toga.Button(
            "Refresh",
            on_press=self._on_refresh,
            style=Pack(padding_left=8),
        )
        header.add(title)
        header.add(refresh_btn)
        self.add(header)

        # Status label — shows errors or loading state
        self._status_label = toga.Label(
            "Press Refresh to load slots.",
            style=Pack(padding_bottom=8, color="#888888"),
        )
        self.add(self._status_label)

        self._list_view = toga.DetailedList(
            accessors=["title", "subtitle"],
            style=Pack(flex=1),
        )
        self.add(self._list_view)

    def _fetch_slots(self) -> list[dict]:
        """Synchronous HTTP call to the bridge /slots endpoint."""
        with httpx.Client(base_url=self._bridge_url, timeout=10.0) as client:
            resp = client.get("/slots")
            resp.raise_for_status()
            return resp.json()

    async def _on_refresh(self, widget: toga.Button) -> None:
        self._status_label.text = "Loading…"
        self._list_view.data = []
        try:
            slots = await asyncio.to_thread(self._fetch_slots)
            if not slots:
                self._status_label.text = "No samples found on device."
                return
            items = [
                {"title": f"[{s['slot']:03d}] {s.get('name', '(unnamed)')}", "subtitle": _fmt_size(s.get("size", 0))}
                for s in slots
            ]
            self._list_view.data = items
            self._status_label.text = f"{len(slots)} sample(s) loaded."
        except httpx.ConnectError:
            self._status_label.text = "Bridge not reachable. Is krate-bridge running?"
        except Exception as exc:
            self._status_label.text = f"Error: {exc}"


def _fmt_size(size_bytes: int) -> str:
    """Human-readable byte size."""
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"
