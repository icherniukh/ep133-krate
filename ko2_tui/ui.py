from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label

from .state import SlotRow


def format_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "-"
    if size_bytes < 1024:
        return f"{size_bytes}B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}K"
    return f"{size_bytes / (1024 * 1024):.1f}M"


def format_duration(size_bytes: int, samplerate: int, channels: int) -> str:
    if size_bytes <= 0 or samplerate <= 0 or channels <= 0:
        return "-"
    bytes_per_frame = 2 * channels
    frames = size_bytes // bytes_per_frame
    seconds = frames / samplerate
    return f"{seconds:.2f}"


def table_row_values(row: SlotRow) -> tuple[str, str, str, str, str, str]:
    channels = "S" if row.channels == 2 else "M" if row.channels == 1 else "-"
    rate = str(row.samplerate) if row.exists else "-"
    return (
        f"{row.slot:03d}",
        row.name,
        format_size(row.size_bytes),
        channels,
        rate,
        format_duration(row.size_bytes, row.samplerate, row.channels),
    )


class TextInputModal(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, placeholder: str = "", initial: str = ""):
        super().__init__()
        self._title = title
        self._placeholder = placeholder
        self._initial = initial

    def compose(self) -> ComposeResult:
        with Vertical(id="modal"):
            yield Label(self._title, id="modal_title")
            yield Input(value=self._initial, placeholder=self._placeholder, id="value")
            with Horizontal(id="modal_actions"):
                yield Button("Cancel", id="cancel")
                yield Button("OK", id="ok", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#value", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#ok")
    def _ok(self) -> None:
        value = self.query_one("#value", Input).value.strip()
        self.dismiss(value if value else None)

    @on(Input.Submitted, "#value")
    def _submit(self) -> None:
        self._ok()


class UploadModal(ModalScreen[tuple[str, str | None] | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, slot: int):
        super().__init__()
        self._slot = slot

    def compose(self) -> ComposeResult:
        with Vertical(id="modal"):
            yield Label(f"Upload to slot {self._slot:03d}", id="modal_title")
            yield Input(placeholder="Path to WAV file", id="path")
            yield Input(placeholder="Optional sample name", id="name")
            with Horizontal(id="modal_actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Upload", id="ok", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#path", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#ok")
    def _ok(self) -> None:
        path = self.query_one("#path", Input).value.strip()
        name = self.query_one("#name", Input).value.strip()
        if not path:
            self.dismiss(None)
            return
        self.dismiss((path, name or None))

    @on(Input.Submitted, "#name")
    def _submit_name(self) -> None:
        self._ok()


class ConfirmModal(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, message: str):
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="modal"):
            yield Label(self._message, id="modal_title")
            with Horizontal(id="modal_actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Yes", id="ok", variant="error")

    def on_mount(self) -> None:
        self.query_one("#cancel", Button).focus()

    def action_cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#ok")
    def _ok(self) -> None:
        self.dismiss(True)
