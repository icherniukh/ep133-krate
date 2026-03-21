from __future__ import annotations

from typing import Any

from rich.console import RenderableType
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Checkbox, Static

from .state import SlotRow
from core.models import Sample

# Rich hex colour palette per size band — parallel to TerminalView._ANSI_PALETTE
_RICH_PALETTE: list[list[str]] = [
    ["#113b11", "#155015"],
    ["#4a4511", "#665c14"],
    ["#8a601c", "#a86c14"],
    ["#8c3b17", "#a63a12"],
    ["#822515", "#58120c"],
    ["#58120c", "#340b07"],
]


def _rich_size_color(size_bytes: int) -> str:
    """Return a Rich markup background colour string based on file size."""
    result = Sample.size_band_for(size_bytes)
    if result is None:
        return ""
    band_idx, ratio = result
    palette = _RICH_PALETTE[band_idx]
    idx = min(len(palette) - 1, int(ratio * len(palette)))
    return f"on {palette[idx]}"

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
        size_str = Sample.format_size(row.size_bytes)
        color_style = _rich_size_color(row.size_bytes)
        size_txt = Text(size_str, style=color_style, justify="right") if color_style else Text(size_str, justify="right")
        return (marker, slot_txt, name_txt, size_txt, Text("?", style="dim"), Text("?", style="dim"), Text("?", style="dim", justify="right"))

    abbr = Sample.channels_label(row.channels)
    channels_txt = Text(abbr, style="bold red" if row.channels == 2 else "dim")

    rate_txt = Text(str(row.samplerate))

    size_str = Sample.format_size(row.size_bytes)
    color_style = _rich_size_color(row.size_bytes)
    size_txt = Text(size_str, style=color_style, justify="right") if color_style else Text(size_str, justify="right")

    dur_str = Sample.format_duration(row.size_bytes, row.samplerate, row.channels)
    dur_txt = Text(dur_str, justify="right")

    return (marker, slot_txt, name_txt, size_txt, channels_txt, rate_txt, dur_txt)


class DetailsWidget(Static):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__("", **kwargs)
        self._slot: int = 1
        self._row: SlotRow | None = None
        self._details: dict[str, Any] | None = None

    def set_slot(self, slot: int, row: SlotRow | None, details: dict[str, Any] | None) -> None:
        self._slot = slot
        self._row = row
        self._details = details
        self.refresh()

    def render(self) -> RenderableType:
        slot = self._slot
        row = self._row
        if row is None or not row.exists:
            return f"Slot {slot:03d}\n\n(empty)"
        channels = row.channels if row.channels else "-"
        rate = row.samplerate if row.samplerate else "-"
        lines = [
            f"Slot: {slot:03d}",
            f"Name: {row.name}",
            f"Size: {row.size_bytes} bytes",
            f"Channels: {channels}",
            f"Rate: {rate}",
        ]
        if self._details:
            sym = self._details.get("sym")
            fmt = self._details.get("format")
            if sym:
                lines.append(f"Symbol: {sym}")
            if fmt:
                lines.append(f"Format: {fmt}")
        return "\n".join(lines)


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


class ConfirmModal(ModalScreen[bool]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "ok", "Confirm")
    ]

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

    def action_ok(self) -> None:
        self._ok()

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#ok")
    def _ok(self) -> None:
        self.dismiss(True)


class OptimizeModal(ModalScreen[tuple[bool, int | None, float | None, float] | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "ok", "Optimize")
    ]

    def __init__(self, message: str):
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="modal"):
            yield Label(self._message, id="modal_title")
            
            # TODO: We can later load defaults from a config file
            yield Checkbox("Unstereo (Stereo -> Mono)", value=True, id="opt_mono")
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

    def action_ok(self) -> None:
        self._ok()

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


# All keybindings shown in the help overlay.  Each entry is (key_display, description).
HELP_KEYBINDINGS: list[tuple[str, str]] = [
    # Navigation
    ("j / ↑", "Cursor up"),
    ("k / ↓", "Cursor down"),
    ("Ctrl+U", "Page up"),
    ("Ctrl+D", "Page down"),
    # Sample operations
    ("Enter", "Load details for current slot"),
    ("d", "Download sample"),
    ("u", "Upload sample(s) via file picker (yazi or built-in)"),
    ("c", "Copy sample to another slot"),
    ("m", "Start move (navigate then Enter to drop)"),
    ("r", "Rename sample"),
    ("Backspace / Del", "Delete sample (or selected slots)"),
    ("o", "Optimize sample (mono/downsample/stretch)"),
    ("s", "Squash: fill all empty slots"),
    # Selection
    ("Space", "Toggle slot selection / move cursor down"),
    ("v", "Select slots by expression (e.g. 1-10, 200)"),
    # View
    ("l", "Toggle log pane"),
    ("Ctrl+R", "Reload inventory from device"),
    ("?", "Show this help overlay"),
    ("q", "Quit"),
    # Move mode (active after pressing m)
    ("Enter  (move mode)", "Drop / swap with current slot"),
    ("Escape (move mode)", "Cancel move"),
]


class HelpModal(ModalScreen[None]):
    """Read-only keybinding reference overlay."""

    DEFAULT_CSS = """
    HelpModal > Vertical {
        width: 72;
        height: auto;
        max-height: 90vh;
        padding: 1 2;
        border: round $accent;
        background: $panel;
    }
    HelpModal #help_title {
        text-style: bold;
        margin-bottom: 1;
    }
    HelpModal ScrollableContainer {
        height: auto;
        max-height: 36;
    }
    HelpModal .help_row {
        height: 1;
    }
    HelpModal .help_key {
        width: 24;
        color: $text;
        text-style: bold;
    }
    HelpModal .help_desc {
        width: 1fr;
        color: $text-muted;
    }
    HelpModal #help_footer {
        margin-top: 1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_help", "Close", show=False),
        Binding("q", "dismiss_help", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Keyboard shortcuts", id="help_title")
            with ScrollableContainer():
                for key, desc in HELP_KEYBINDINGS:
                    with Horizontal(classes="help_row"):
                        yield Static(key, classes="help_key")
                        yield Static(desc, classes="help_desc")
            yield Static("Press Escape or q to close", id="help_footer")

    def action_dismiss_help(self) -> None:
        self.dismiss(None)
