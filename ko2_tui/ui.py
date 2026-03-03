from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Checkbox

from .state import SlotRow
from ko2_utils import format_size, format_duration


import typing
if typing.TYPE_CHECKING:
    from typing import Any

from rich.text import Text

def get_rich_size_color(size_bytes: int) -> str:
    """Return a rich markup color string based on file size."""
    if size_bytes <= 0:
        return ""

    ranges = [
        (0, 50 * 1024, ["#113b11", "#155015"]),            # dark green
        (50 * 1024, 200 * 1024, ["#4a4511", "#665c14"]),   # olive
        (200 * 1024, 500 * 1024, ["#8a601c", "#a86c14"]),  # orange/brown
        (500 * 1024, 1024 * 1024, ["#8c3b17", "#a63a12"]), # dark orange -> rust
        (1024 * 1024, 2 * 1024 * 1024, ["#822515", "#58120c"]),  # rust -> dark red
        (2 * 1024 * 1024, 10 * 1024 * 1024, ["#58120c", "#340b07"]),  # deep red
    ]

    for lo, hi, palette in ranges:
        if size_bytes < hi:
            if len(palette) == 1:
                return f"on {palette[0]}"
            ratio = (size_bytes - lo) / (hi - lo)
            idx = min(len(palette) - 1, int(ratio * len(palette)))
            return f"on {palette[idx]}"

    return "on #340b07"

def table_row_values(row: SlotRow, selected: bool = False) -> tuple[Any, ...]:
    marker = Text("●", style="bold green") if selected else Text(" ")
    
    if not row.loaded:
        return (marker, Text(f"{row.slot:03d}", style="dim"), Text("?", style="dim"), Text("?", style="dim"), Text("?", style="dim"), Text("?", style="dim"), Text("?", style="dim"))

    if not row.exists:
        return (marker, Text(f"{row.slot:03d}", style="dim"), Text("(empty)", style="dim"), Text("-", style="dim", justify="right"), Text("-", style="dim"), Text("-", style="dim"), Text("-", style="dim", justify="right"))

    slot_txt = Text(f"{row.slot:03d}")
    name_txt = Text(row.name)

    # If it exists but channels is 0, we haven't loaded node metadata yet
    if row.channels == 0:
        size_str = format_size(row.size_bytes)
        color_style = get_rich_size_color(row.size_bytes)
        size_txt = Text(size_str, style=color_style, justify="right") if color_style else Text(size_str, justify="right")
        return (marker, slot_txt, name_txt, size_txt, Text("?", style="dim"), Text("?", style="dim"), Text("?", style="dim", justify="right"))

    if row.channels == 2:
        channels_txt = Text("S", style="bold red")
    elif row.channels == 1:
        channels_txt = Text("M", style="dim")
    else:
        channels_txt = Text("-", style="dim")

    rate_txt = Text(str(row.samplerate))
    
    size_str = format_size(row.size_bytes)
    color_style = get_rich_size_color(row.size_bytes)
    size_txt = Text(size_str, style=color_style, justify="right") if color_style else Text(size_str, justify="right")
    
    dur_str = format_duration(row.size_bytes, row.samplerate, row.channels)
    dur_txt = Text(dur_str, justify="right")

    return (marker, slot_txt, name_txt, size_txt, channels_txt, rate_txt, dur_txt)


class TextInputModal(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, placeholder: str = "", initial: str = "", allow_empty: bool = False):
        super().__init__()
        self._title = title
        self._placeholder = placeholder
        self._initial = initial
        self._allow_empty = allow_empty

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
        if value or self._allow_empty:
            self.dismiss(value)
        else:
            self.dismiss(None)

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

    @on(Input.Submitted, "#path")
    def _submit_path(self) -> None:
        self.query_one("#name", Input).focus()

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


class OptimizeModal(ModalScreen[tuple[bool, int | None, float | None, float] | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, message: str):
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="modal"):
            yield Label(self._message, id="modal_title")
            
            # TODO: We can later load defaults from a config file
            yield Checkbox("Downmix to Mono (Stereo -> Mono)", value=True, id="opt_mono")
            yield Checkbox("Downsample to 22.05 kHz", value=False, id="opt_22k")
            yield Checkbox("Downsample to 11.025 kHz", value=False, id="opt_11k")
            yield Checkbox("Time-stretch 2x (with -12.0 pitch correction)", value=False, id="opt_fast")

            with Horizontal(id="modal_actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Optimize", id="ok", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#opt_mono", Checkbox).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#ok")
    def _ok(self) -> None:
        mono = self.query_one("#opt_mono", Checkbox).value
        opt_22k = self.query_one("#opt_22k", Checkbox).value
        opt_11k = self.query_one("#opt_11k", Checkbox).value
        opt_fast = self.query_one("#opt_fast", Checkbox).value
        
        rate = None
        if opt_11k:
            rate = 11025
        elif opt_22k:
            rate = 22050

        speed = 2.0 if opt_fast else None
        pitch = -12.0 if opt_fast else 0.0

        self.dismiss((mono, rate, speed, pitch))
