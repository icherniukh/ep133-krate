"""File picker for upload.

Primary: yazi --chooser-file (suspend TUI, launch yazi, read results).
Fallback: DirectoryTreePickerModal (built-in Textual DirectoryTree, Space to
          toggle WAV file selection, Enter to confirm).
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Label


def _is_yazi_available() -> bool:
    return shutil.which("yazi") is not None


class _WavTree(DirectoryTree):
    """DirectoryTree that shows only directories and .wav files."""

    def __init__(self, *args, selected: set[Path] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._selected: set[Path] = selected or set()

    def filter_paths(self, paths):
        return [p for p in paths if p.is_dir() or p.suffix.lower() == ".wav"]

    def render_label(self, node, base_style, style):
        label = super().render_label(node, base_style, style)
        if node.data and not node.data.path.is_dir():
            path = Path(str(node.data.path))
            if path in self._selected:
                return Text.assemble("● ", label)
        return label


class DirectoryTreePickerModal(ModalScreen[list[Path] | None]):
    """Multi-select WAV file picker using Textual's DirectoryTree.

    Space toggles selection on the highlighted file.
    Enter confirms the current selection.
    Escape cancels.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("space", "toggle_select", "Select/Deselect"),
        Binding("enter", "confirm", "Confirm", priority=True),
    ]

    DEFAULT_CSS = """
    DirectoryTreePickerModal {
        align: center middle;
    }
    DirectoryTreePickerModal > Vertical {
        width: 90%;
        max-width: 120;
        height: 85%;
        max-height: 50;
        padding: 1 2;
        border: round $accent;
        background: $panel;
    }
    DirectoryTreePickerModal #modal_title {
        height: 1;
        text-style: bold;
        color: $text;
    }
    DirectoryTreePickerModal #tree {
        height: 1fr;
        border: tall $background;
    }
    DirectoryTreePickerModal #selection_count {
        height: 1;
        color: $accent;
    }
    DirectoryTreePickerModal #modal_actions {
        height: auto;
        margin-top: 1;
        align: right middle;
    }
    """

    def __init__(self, start_dir: Path | None = None):
        super().__init__()
        self._start_dir = start_dir or Path.home()
        self._selected: set[Path] = set()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(
                "Select WAV files  (Space = select · Enter = confirm · Esc = cancel)",
                id="modal_title",
            )
            yield Label("0 files selected", id="selection_count")
            yield _WavTree(str(self._start_dir), id="tree", selected=self._selected)
            with Horizontal(id="modal_actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Upload Selected", id="ok", variant="primary")

    def on_mount(self) -> None:
        container = self.query_one("Vertical")
        container.styles.opacity = 0
        container.animate("opacity", 1.0, duration=0.15, easing="out_cubic")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_toggle_select(self) -> None:
        tree = self.query_one("#tree", _WavTree)
        node = tree.cursor_node
        if node is None or node.data is None:
            return
        path = Path(str(node.data.path))
        if path.is_dir():
            return
        if path in self._selected:
            self._selected.discard(path)
        else:
            self._selected.add(path)
        self._update_count()
        tree.refresh()

    def _update_count(self) -> None:
        n = len(self._selected)
        label = self.query_one("#selection_count", Label)
        label.update(f"{n} file{'s' if n != 1 else ''} selected")

    def action_confirm(self) -> None:
        self.dismiss(sorted(self._selected) if self._selected else None)

    @on(Button.Pressed, "#cancel")
    def _on_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#ok")
    def _on_ok(self) -> None:
        self.action_confirm()


async def _pick_with_yazi(app, start_dir: Path | None) -> list[Path]:
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        chooser_path = Path(f.name)
    try:
        cmd = ["yazi", "--chooser-file", str(chooser_path)]
        if start_dir:
            cmd.append(str(start_dir))
        app._log(f"[yazi] launching: {' '.join(cmd)}")
        with app.suspend():
            result = subprocess.run(cmd)
        app._log(f"[yazi] exited with code {result.returncode}")
        if not chooser_path.exists():
            app._log("[yazi] chooser file missing after exit")
            return []
        text = chooser_path.read_text().strip()
        app._log(f"[yazi] chooser file contents: {text!r}")
        paths = [Path(p) for p in text.splitlines() if p.strip()]
        app._log(f"[yazi] parsed {len(paths)} path(s)")
        return paths
    except Exception as exc:
        app._log(f"[yazi] error: {exc!r}")
        return []
    finally:
        chooser_path.unlink(missing_ok=True)


async def pick_files(
    app, start_dir: Path | None = None, force_modal: bool = False
) -> list[Path]:
    """Return a list of WAV files chosen by the user.

    Uses yazi if available (and force_modal is False); falls back to
    DirectoryTreePickerModal otherwise.  Returns [] if the user cancels.
    """
    if not force_modal and _is_yazi_available():
        return await _pick_with_yazi(app, start_dir)
    result = await app.push_screen_wait(DirectoryTreePickerModal(start_dir))
    return result or []
