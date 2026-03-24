"""
Upload queue screen for the Krate mobile app.

Allows the user to pick an audio file and queue it for upload to the
EP-133 KO-II via the krate-bridge HTTP service.
"""

from __future__ import annotations

from pathlib import Path

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

_STATUS_QUEUED = "queued"
_STATUS_UPLOADING = "uploading"
_STATUS_DONE = "done"
_STATUS_ERROR = "error"


class UploadQueueScreen(toga.Box):
    """Toga Box for managing the audio file upload queue."""

    def __init__(
        self,
        bridge_url: str = "http://localhost:8765",
        target_slot: int = 1,
    ) -> None:
        super().__init__(style=Pack(direction=COLUMN, padding=8))
        self._bridge_url = bridge_url
        self._queue: list[dict] = []
        title = toga.Label(
            "Upload Queue",
            style=Pack(padding_bottom=8, font_size=18),
        )
        self.add(title)

        slot_row = toga.Box(style=Pack(direction=ROW, padding_bottom=8))
        slot_row.add(toga.Label("Target slot: ", style=Pack(padding_right=4)))
        self._slot_input = toga.NumberInput(
            min=1,
            max=999,
            value=target_slot,
            style=Pack(width=80),
        )
        slot_row.add(self._slot_input)
        self.add(slot_row)

        pick_btn = toga.Button(
            "Pick Audio File…",
            on_press=self._on_pick_file,
            style=Pack(padding_bottom=8),
        )
        self.add(pick_btn)

        self._status_label = toga.Label(
            "No files queued.",
            style=Pack(padding_bottom=8, color="#888888"),
        )
        self.add(self._status_label)

        self._list_view = toga.DetailedList(
            accessors=["title", "subtitle"],
            style=Pack(flex=1),
        )
        self.add(self._list_view)

        submit_btn = toga.Button(
            "Upload All",
            on_press=self._on_upload_all,
            style=Pack(padding_top=8),
        )
        self.add(submit_btn)

    async def _on_pick_file(self, widget: toga.Button) -> None:
        try:
            dialog = toga.OpenFileDialog(
                title="Select audio file",
                file_types=["wav", "aif", "aiff", "mp3", "flac"],
            )
            result = await self.app.dialog(dialog)
            if result:
                path = Path(result)
                slot = int(self._slot_input.value or 1)
                entry = {
                    "path": path,
                    "slot": slot,
                    "status": _STATUS_QUEUED,
                }
                self._queue.append(entry)
                self._refresh_list()
        except Exception as exc:
            self._status_label.text = f"File pick error: {exc}"

    def _refresh_list(self) -> None:
        items = [
            {
                "title": f"[{e['slot']:03d}] {e['path'].name}",
                "subtitle": e["status"].upper(),
            }
            for e in self._queue
        ]
        self._list_view.data = items
        count = len(self._queue)
        self._status_label.text = f"{count} file(s) in queue." if count else "No files queued."

    def _on_upload_all(self, widget: toga.Button) -> None:
        if not self._queue:
            self._status_label.text = "Queue is empty — pick a file first."
            return
        errors = 0
        for entry in self._queue:
            if entry["status"] == _STATUS_DONE:
                continue
            entry["status"] = _STATUS_UPLOADING
            self._refresh_list()
            try:
                self._upload_entry(entry)
                entry["status"] = _STATUS_DONE
            except Exception as exc:
                entry["status"] = _STATUS_ERROR
                errors += 1
            self._refresh_list()
        if errors:
            self._status_label.text = f"Upload complete with {errors} error(s)."
        else:
            self._status_label.text = "All uploads complete."

    def _upload_entry(self, entry: dict) -> None:
        """POST the audio file to the bridge /upload endpoint."""
        path: Path = entry["path"]
        slot: int = entry["slot"]
        with httpx.Client(base_url=self._bridge_url, timeout=120.0) as client:
            with open(path, "rb") as fh:
                resp = client.post(
                    "/upload",
                    files={"file": (path.name, fh, "audio/wav")},
                    params={"slot": slot},
                )
            resp.raise_for_status()
