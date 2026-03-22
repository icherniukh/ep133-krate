from __future__ import annotations

import re
import time
from queue import Empty, Queue
from typing import Any, Iterable, cast

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Static, TextArea


class _LogView(TextArea, can_focus=False):
    """Read-only log pane that allows mouse text selection without stealing keyboard focus."""

from . import actions
from .debug_log import DebugLogger
from .file_picker import pick_files
from .dialog_log import DialogLogger
from core.waveform_store import WaveformStore
from .waveform_widget import WaveformWidget
from core.models import Sample, MAX_SAMPLE_RATE
from .selectors import parse_selector
from .state import SlotRow, TuiState
from .ui import ConfirmModal, DetailsWidget, HelpModal, OptimizeModal, TextInputModal, table_row_values
from .worker import DeviceWorker, WorkerEvent


class TUIApp(App[None]):
    CSS = """
    #main {
        height: 1fr;
    }
    #slots_pane {
        width: 2fr;
    }
    #slots_pane DataTable {
        height: 1fr;
    }
    #status {
        height: 1;
        background: #16202e;
    }
    #status.active {
        background: #0d3251;
    }
    #status.error {
        background: #3d1515;
    }
    #status_left {
        width: 1fr;
        height: 1;
        padding: 0 1;
        background: transparent;
    }
    #status_right {
        width: auto;
        height: 1;
        padding: 0 1;
        background: transparent;
    }
    #inspector {
        width: 1fr;
    }
    #details {
        padding: 1;
        border: round $boost;
        height: auto;
        min-height: 9;
    }
    #waveform {
        border: round $accent;
        padding: 0 1;
        height: 1fr;
    }
    #logs {
        height: 12;
        border: round $boost;
    }
    #logs.hidden {
        display: none;
    }
    #modal {
        width: 70;
        height: auto;
        padding: 1 2;
        border: round $accent;
        background: $panel;
    }
    #modal_actions {
        height: auto;
        margin-top: 1;
        align: right middle;
    }
    Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+r", "refresh", "Reload"),
        Binding("enter", "view_details", "Details"),
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("d", "download", "Download"),
        Binding("u", "upload", "Upload"),
        Binding("c", "copy", "Copy"),
        Binding("m", "start_move", "Move"),
        Binding("r", "rename", "Rename"),
        Binding("space", "toggle_select", "Select"),
        Binding("v", "select_expr", "Select Expr"),
        Binding("l", "toggle_logs", "Logs"),
        Binding("s", "squash", "Squash"),
        Binding("o", "optimize", "Optimize"),
        Binding("O", "optimize_all", "Optimize All"),
        Binding("backspace", "delete", "Delete"),
        Binding("delete", "delete", "Delete", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("ctrl+d", "page_down", "Page Down", show=False),
        Binding("ctrl+u", "page_up", "Page Up", show=False),
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "help", "Help", show=False),
        Binding("p", "audition", "Play", show=False),
    ]

    def __init__(
        self,
        device_name: str | None = None,
        debug: bool = False,
        debug_log: str | None = None,
        dialog_log: str | None = None,
        alt_file_picker: bool = False,
    ):
        super().__init__()
        self.device_name = device_name
        self.debug_enabled = bool(debug)
        self.debug_log = debug_log
        self.dialog_log = dialog_log
        self.alt_file_picker = bool(alt_file_picker)

        self.state = TuiState()
        self._request_queue: Queue[actions.WorkerRequest] = Queue()
        self._event_queue: Queue[WorkerEvent] = Queue()
        self._worker: DeviceWorker | None = None
        self._debug_logger: DebugLogger | None = None
        self._dialog_logger: DialogLogger | None = None
        self._col_keys: list = []
        self.moving_src: int | None = None
        self.copying_src: int | None = None
        self._device_online: bool | None = None  # None=unknown, True=online, False=error
        self._waveform_by_slot: dict[int, dict[str, Any]] = {}
        self._waveform_pending: set[int] = set()
        self._waveform_store = WaveformStore()
        self._waveform_precalc_active: bool = False
        self._logs_visible: bool = True
        self._log_lines: list[str] = []
        self._progress_current: int = 0
        self._progress_total: int = 0

        # Playback cursor animation
        self._play_slot: int | None = None
        self._play_start: float = 0.0
        self._play_duration: float = 0.0
        self._play_timer: Any | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            with Vertical(id="slots_pane"):
                yield DataTable(id="slots")
                with Horizontal(id="status"):
                    yield Static("", id="status_left")
                    yield Static("", id="status_right")
            with Vertical(id="inspector"):
                yield DetailsWidget(id="details")
                yield WaveformWidget(id="waveform")
        yield _LogView("", read_only=True, id="logs", show_line_numbers=False)
        yield Footer()

    def on_mount(self) -> None:
        self._init_table()
        self._debug_logger = DebugLogger(
            enabled=self.debug_enabled,
            output_path=self.debug_log,
        )
        self._dialog_logger = DialogLogger(
            enabled=self.debug_enabled,
            output_path=self.dialog_log,
        )

        self._worker = DeviceWorker(
            device_name=self.device_name,
            request_queue=self._request_queue,
            event_queue=self._event_queue,
            debug_logger=self._debug_logger,
            waveform_cache_checker=self._has_cached_waveform,
        )
        self._worker.start()

        self.set_interval(0.05, self._drain_worker_events)

        self._update_status("IDLE")
        if self._debug_logger and self._debug_logger.path:
            self._log(f"Debug capture: {self._debug_logger.path}")
        if self._dialog_logger and self._dialog_logger.path:
            self._log(f"Dialog log: {self._dialog_logger.path}")
        self._queue_request(actions.refresh_inventory())
        self.query_one("#slots", DataTable).focus()

    def on_unmount(self) -> None:
        self._shutdown_worker()

    def _shutdown_worker(self) -> None:
        if self._worker:
            self._worker.submit(actions.stop())
            self._worker.join(timeout=1.0)
            self._worker = None
        if self._debug_logger:
            self._debug_logger.close()
            self._debug_logger = None
        if self._dialog_logger:
            self._dialog_logger.close()
            self._dialog_logger = None

    def _init_table(self) -> None:
        from rich.text import Text
        table = self.query_one("#slots", DataTable)
        table.cursor_type = "row"
        self._col_keys = [
            table.add_column(" ", width=2),
            table.add_column("Slot", width=4),
            table.add_column("Name", width=45),
            table.add_column(Text("Size", justify="right"), width=9),
            table.add_column("CH", width=2),
            table.add_column("Rate", width=6),
            table.add_column(Text("Sec", justify="right"), width=10),
        ]
        self._refresh_table()

    def _get_visual_row(self, slot: int) -> 'SlotRow':
        from copy import copy
        row = self.state.slots[slot]
        if self.moving_src is not None:
            dst = self.state.selected_slot
            if slot == self.moving_src and dst != self.moving_src:
                v = copy(self.state.slots[dst])
                v.slot = self.moving_src
                return v
            elif slot == dst and dst != self.moving_src:
                v = copy(self.state.slots[self.moving_src])
                v.slot = dst
                return v
        if self.copying_src is not None:
            dst = self.state.selected_slot
            if slot == dst and dst != self.copying_src:
                v = copy(self.state.slots[self.copying_src])
                v.slot = dst
                return v
        return row

    def _refresh_table(self) -> None:
        table = self.query_one("#slots", DataTable)
        prev_scroll_x = float(table.scroll_x)
        prev_scroll_y = float(table.scroll_y)
        table.clear(columns=False)
        for slot in range(1, len(self.state.slots) + 1):
            row = self._get_visual_row(slot)
            selected = slot in self.state.selected_slots
            table.add_row(*table_row_values(row, selected), key=str(slot))

        cursor_row = max(0, min(len(self.state.slots) - 1, self.state.selected_slot - 1))
        try:
            # Keep cursor on selected slot without forcing viewport jump.
            table.move_cursor(row=cursor_row, column=0, animate=False, scroll=False)
            table.scroll_to(
                x=prev_scroll_x,
                y=prev_scroll_y,
                animate=False,
                immediate=True,
                force=True,
            )
        except Exception:
            pass

    def _update_table_rows(self, slot_nums: Iterable[int]) -> None:
        table = self.query_one("#slots", DataTable)
        for slot in slot_nums:
            if slot not in self.state.slots:
                continue
            row = self._get_visual_row(slot)
            selected = slot in self.state.selected_slots
            values = table_row_values(row, selected)
            for col_idx, val in enumerate(values):
                table.update_cell(str(slot), self._col_keys[col_idx], val)

    def _update_selection_display(self, prev_selected: set[int]) -> None:
        """Update the selection marker column only for rows whose state changed."""
        table = self.query_one("#slots", DataTable)
        for slot in prev_selected.symmetric_difference(self.state.selected_slots):
            marker = "●" if slot in self.state.selected_slots else " "
            table.update_cell(str(slot), self._col_keys[0], marker)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        old_slot = self.state.selected_slot
        self.state.selected_slot = event.cursor_row + 1

        if self.moving_src is not None:
            # Re-render old and new position to reflect visual swap
            self._update_table_rows([self.moving_src, old_slot, self.state.selected_slot])
            self._update_status("Move mode (Esc to cancel, Enter to drop)")

        if self.copying_src is not None:
            self._update_table_rows([self.copying_src, old_slot, self.state.selected_slot])
            self._update_status("Copy mode (Esc to cancel, Enter to paste)")

        self._update_details(self.state.selected_slot)
        self._update_waveform(self.state.selected_slot)

    def on_resize(self) -> None:
        self.query_one("#waveform", WaveformWidget).refresh()

    def on_key(self, event: events.Key) -> None:
        if event.key not in {"up", "down", "enter"}:
            return
        # Don't intercept keys when a modal is active
        if len(self.screen_stack) > 1:
            return
        if event.key == "enter" and self.moving_src is not None:
            self.action_view_details()
            event.stop()
            event.prevent_default()
            return
        try:
            table = self.query_one("#slots", DataTable)
        except Exception:
            return
        if self.focused is not table:
            return
        if event.key == "enter":
            self.action_view_details()
        elif event.key == "up":
            self.action_cursor_up()
        else:
            self.action_cursor_down()
        event.stop()
        event.prevent_default()

    def _current_slot(self) -> int:
        table = self.query_one("#slots", DataTable)
        try:
            row = int(table.cursor_row)
        except Exception:
            row = self.state.selected_slot - 1
        return max(1, row + 1)

    def _queue_request(self, request: actions.WorkerRequest) -> None:
        op_label = self._human_op_label(request.op)
        if self.state.busy:
            self._log(f"Queued: {op_label} (waiting for current operation)")
        else:
            self.state.set_busy(True, f"Running {op_label}...")
            self._update_status(self.state.status)
        if self._worker:
            self._worker.submit(request)

    def _drain_worker_events(self) -> None:
        while True:
            try:
                event = self._event_queue.get_nowait()
            except Empty:
                break
            self._handle_event(event)

    def _handle_event(self, event: WorkerEvent) -> None:
        kind = event.kind
        payload = event.payload

        if kind == "busy":
            if str(payload.get("op", "")) == "waveform":
                self._waveform_precalc_active = True
                self._update_status(self.state.status)
                return
            op = self._human_op_label(str(payload.get("op", "operation")))
            self.state.set_busy(True, f"Running {op}...")
            self._update_status(self.state.status)
            return

        if kind == "idle":
            if str(payload.get("op", "")) == "waveform":
                self._waveform_precalc_active = False
                self._update_status(self.state.status)
                return
            self.state.set_busy(False, "IDLE")
            self._progress_current = 0
            self._progress_total = 0
            self._update_status("IDLE")
            return

        if kind == "inventory":
            self._device_online = True
            sounds = cast(dict[int, dict], payload.get("sounds", {}))
            self._waveform_by_slot.clear()
            self._waveform_pending.clear()
            self.state.apply_inventory(sounds)
            self._update_table_rows(self.state.slots.keys())
            used = len(sounds)
            self._log(f"Inventory refreshed: {used} used slots")
            self._update_details(self.state.selected_slot)
            self._update_waveform(self.state.selected_slot)
            self._update_status(self.state.status)
            return

        if kind == "inventory_enriched":
            updates = cast(dict[int, dict], payload.get("updates", {}))
            if updates:
                self.state.apply_inventory_updates(updates)
                self._update_table_rows(updates.keys())
                self._update_details(self.state.selected_slot)
                self._update_waveform(self.state.selected_slot)
            return

        if kind == "slot_removed":
            slot = int(payload.get("slot") or 0)
            if slot:
                self._invalidate_waveform(slot)
                self.state.clear_slot(slot)
                self._update_table_rows([slot])
                if slot == self.state.selected_slot:
                    self._update_details(slot)
                    self._update_waveform(slot)
            return

        if kind == "details":
            slot = int(payload.get("slot") or self.state.selected_slot)
            details = cast(dict, payload.get("details", {}))
            preload = bool(payload.get("preload", False))
            self.state.apply_slot_details(slot, details)
            if preload:
                self._load_cached_waveform(slot)
                if slot == self.state.selected_slot:
                    self._update_details(slot)
                    self._update_waveform(slot)
                return
            self._invalidate_waveform(slot)
            self._update_table_rows([slot])
            self._update_details(slot)
            self._ensure_waveform(slot)
            self._log(f"Loaded details for slot {slot:03d}")
            return

        if kind == "slot_refresh":
            self._device_online = True
            slot = int(payload.get("slot") or self.state.selected_slot)
            details = cast(dict, payload.get("details", {}))
            self.state.apply_slot_details(slot, details)
            self._invalidate_waveform(slot)
            self._update_table_rows([slot])
            if slot == self.state.selected_slot:
                self._update_details(slot)
                self._update_waveform(slot)
            return

        if kind == "waveform":
            self._device_online = True
            slot = int(payload.get("slot") or self.state.selected_slot)
            self._waveform_pending.discard(slot)
            bins = payload.get("bins")
            fp = payload.get("fp") if isinstance(payload.get("fp"), dict) else None
            if isinstance(bins, dict) and WaveformStore.is_valid_bins(bins):
                self._waveform_by_slot[slot] = bins
                sig = _waveform_signature(slot, self.state.slots)
                if sig is not None:
                    self._waveform_store.set_for_slot(slot, sig, bins, fingerprint=fp)
                    if fp and isinstance(fp.get("sha256"), str):
                        self._waveform_store.set_fingerprint(
                            str(fp.get("sha256")),
                            {
                                **fp,
                                "slot": int(slot),
                                "name": str(self.state.slots.get(slot).name if self.state.slots.get(slot) else ""),
                                "size_bytes": int(self.state.slots.get(slot).size_bytes if self.state.slots.get(slot) else 0),
                                "bins": bins,
                            },
                        )
            else:
                self._waveform_by_slot.pop(slot, None)
            if slot == self.state.selected_slot:
                self._update_waveform(slot)
            return

        if kind == "audition_started":
            slot = int(payload.get("slot") or 0)
            duration_s = float(payload.get("duration_s") or 0.0)
            if slot and duration_s > 0:
                self._start_playback_animation(slot, duration_s)
            return

        if kind == "success":
            self._device_online = True
            self._log(f"OK: {payload.get('message', '')}")
            return

        if kind == "error":
            self._device_online = False
            self.state.set_busy(False, "Error")
            msg = str(payload.get("message", "Unknown error"))
            self.state.last_error = msg
            self._update_status(f"Error: {msg}")
            self._log(f"ERROR: {msg}")
            return

        if kind == "progress":
            msg = str(payload.get("message", "")).strip()
            current = payload.get("current")
            total = payload.get("total")
            if isinstance(current, int) and isinstance(total, int) and total > 0:
                self._progress_current = current
                self._progress_total = total
            if msg:
                self.state.set_busy(True, msg)
                self._update_status(msg)
            return

        if kind == "op_timing":
            if str(payload.get("op", "")) == "waveform":
                return
            op = self._human_op_label(str(payload.get("op", "operation")))
            total_s = float(payload.get("total_s") or 0.0)
            p50_s = float(payload.get("p50_s") or 0.0)
            p95_s = float(payload.get("p95_s") or 0.0)
            count = int(payload.get("count") or 0)
            self._log(
                f"Timing: {op} took {total_s:.2f}s (p50 {p50_s:.2f}s, p95 {p95_s:.2f}s, n={count})"
            )
            phases = cast(dict, payload.get("phases") or {})
            if phases:
                phase_str = ", ".join(
                    f"{k}={v:.3f}s"
                    for k, v in sorted(phases.items(), key=lambda kv: -kv[1])
                )
                self._log(f"  phases: {phase_str}")
            return

        if kind == "log":
            message = str(payload.get("message", ""))
            if message:
                self._log(message)
            return

        if kind == "trace" and self.debug_enabled:
            trace = cast(dict, payload.get("trace", {}))
            message = self._format_trace_message(trace)
            if message:
                self._log(message)

    _DEVICE_ACTIONS = frozenset({
        "download", "upload", "copy", "start_move", "rename",
        "squash", "optimize", "optimize_all", "delete", "audition", "refresh",
    })

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if len(self.screen_stack) > 1:
            return False
        if self.state.busy and action in self._DEVICE_ACTIONS:
            self._log("Busy — wait for current operation to finish")
            return False
        return True

    def get_bindings(self) -> list[Binding]:
        if self.moving_src is not None:
            return [
                Binding("enter", "view_details", "Drop / Swap"),
                Binding("escape", "cancel_move", "Cancel Move"),
            ]
        if self.copying_src is not None:
            return [
                Binding("enter", "view_details", "Paste"),
                Binding("escape", "cancel_copy", "Cancel Copy"),
            ]
        return super().get_bindings()

    def action_cancel(self) -> None:
        if self.copying_src is not None:
            self.action_cancel_copy()
        else:
            self.action_cancel_move()

    def _update_details(self, slot: int) -> None:
        slot = max(1, min(slot, len(self.state.slots)))
        self.state.selected_slot = slot
        row = self.state.slots[slot]
        details = self.state.details_by_slot.get(slot)
        self.query_one("#details", DetailsWidget).set_slot(slot, row, details)

    def _update_status(self, state_text: str) -> None:
        is_active = self.state.busy or self.moving_src is not None or self.copying_src is not None

        if self.state.busy:
            circle = "🟡"
        elif self._device_online is True:
            circle = "🟢"
        elif self._device_online is False:
            circle = "🔴"
        else:
            circle = "⚪"

        n_sel = len(self.state.selected_slots)
        sel_suffix = f"  {n_sel} selected" if n_sel else ""
        logs_suffix = "" if self._logs_visible else "  logs:hidden"
        total_bytes = sum(row.size_bytes for row in self.state.slots.values() if row.exists)
        max_bytes = 64 * 1024 * 1024
        used_pct = int(100 * total_bytes / max_bytes) if max_bytes else 0
        mem_suffix = f"  {Sample.format_size(total_bytes)}/64.00M ({used_pct}%)"
        wf_suffix = "  ⟳ waveforms" if self._waveform_precalc_active and not is_active else ""
        debug_suffix = ""
        if self._debug_logger and self._debug_logger.path:
            debug_suffix = f"  debug={self._debug_logger.path.name}"

        progress_bar = ""
        if self.state.busy and self._progress_total > 2:
            progress_bar = f"  {_render_progress_bar(self._progress_current, self._progress_total)}"

        left = f"{state_text}{progress_bar}{sel_suffix}{mem_suffix}{logs_suffix}{debug_suffix}{wf_suffix}"
        right = f"{self.device_name or 'EP-133'} {circle}"

        self.query_one("#status_left", Static).update(left)
        self.query_one("#status_right", Static).update(right)

        status_bar = self.query_one("#status")
        status_bar.remove_class("active", "error")
        if is_active:
            status_bar.add_class("active")
        elif self._device_online is False:
            status_bar.add_class("error")

    def _log(self, line: str) -> None:
        self._log_lines.append(line)
        ta = self.query_one("#logs", _LogView)
        ta.load_text("\n".join(self._log_lines))
        ta.move_cursor(ta.document.end, select=False)
        if self._dialog_logger:
            self._dialog_logger.record(line)

    def _human_op_label(self, op: str) -> str:
        key = op.strip().lower().replace(" ", "_")
        labels = {
            "refresh_inventory": "refresh inventory",
            "fetch_details": "load details",
            "download": "download",
            "upload": "upload",
            "copy": "copy",
            "move": "move",
            "rename": "rename",
            "delete": "delete",
            "bulk_delete": "bulk delete",
            "squash": "squash",
            "optimize": "optimize",
            "optimize_all": "optimize all",
            "stop": "stop",
        }
        return labels.get(key, op)

    def _format_trace_message(self, trace: dict) -> str | None:
        op = str(trace.get("op") or "").upper()
        if not op:
            return None

        # Chunk-level protocol chatter is noisy and not useful in the dialog pane.
        if op in {"GET_DATA", "PUT_DATA"}:
            return None

        direction = str(trace.get("dir") or "").upper()
        slot = self._trace_slot(trace)
        status = trace.get("status")
        status_suffix = ""
        if isinstance(status, int) and status != 0:
            status_suffix = f" (status 0x{status:02X})"

        slot_text = ""
        if slot is not None:
            slot_text = f" for slot {slot:03d}"
            friendly = self._friendly_slot_name(slot)
            if friendly:
                slot_text += f' "{friendly}"'

        node = trace.get("node")
        node_text = f" (node {int(node)})" if isinstance(node, int) else ""

        if op == "LIST":
            return "Debug: requesting sample list"
        if op == "LIST_RSP":
            return f"Debug: sample list received{status_suffix}"
        if op == "GET_INIT":
            return f"Debug: download requested{slot_text}"
        if op == "GET_INIT_RSP":
            return f"Debug: download ready{slot_text}{status_suffix}"
        if op == "PUT_INIT":
            return f"Debug: upload start{slot_text}"
        if op == "VERIFY":
            return f"Debug: verify upload{slot_text}{status_suffix}"
        if op == "META_GET":
            return f"Debug: metadata read{slot_text}{node_text}"
        if op == "META_SET":
            return f"Debug: metadata update{slot_text}{node_text}{status_suffix}"
        if op == "DELETE":
            return f"Debug: delete requested{slot_text}"

        # Keep unknown protocol events available in debug mode, but concise.
        dir_prefix = "sent" if direction == "TX" else "received" if direction == "RX" else "event"
        return f"Debug: {dir_prefix} {op}{slot_text}{status_suffix}"

    def _trace_slot(self, trace: dict) -> int | None:
        slot = trace.get("slot")
        if isinstance(slot, int):
            return slot
        name = str(trace.get("name") or "")
        m = re.match(r"^(\d{1,3})\.pcm$", name, flags=re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None
        return None

    def _friendly_slot_name(self, slot: int) -> str:
        row = self.state.slots.get(slot)
        if not row or not row.exists:
            return ""
        friendly = row.name.strip()
        if not friendly:
            return ""
        if friendly.lower() == f"{slot:03d}.pcm":
            return ""
        return friendly

    def _invalidate_waveform(self, slot: int) -> None:
        self._waveform_by_slot.pop(int(slot), None)
        self._waveform_pending.discard(int(slot))

    def _load_cached_waveform(self, slot: int) -> bool:
        slot = int(slot)
        if slot in self._waveform_by_slot:
            return True
        sig = _waveform_signature(slot, self.state.slots)
        if sig is None:
            return False
        cached = self._waveform_store.get_for_slot(slot, sig)
        if isinstance(cached, dict) and WaveformStore.is_valid_bins(cached):
            self._waveform_by_slot[slot] = cached
            return True
        return False

    def _has_cached_waveform(self, slot: int) -> bool:
        """Return True if valid waveform bins are already available for *slot*.

        Used as a cache-checker callback by DeviceWorker to skip MIDI traffic
        during precalc when the cache already holds valid data.
        """
        slot = int(slot)
        if slot in self._waveform_by_slot:
            bins = self._waveform_by_slot[slot]
            if WaveformStore.is_valid_bins(bins):
                return True
        sig = _waveform_signature(slot, self.state.slots)
        if sig is None:
            return False
        cached = self._waveform_store.get_for_slot(slot, sig)
        return isinstance(cached, dict) and WaveformStore.is_valid_bins(cached)

    def _ensure_waveform(self, slot: int) -> None:
        slot = int(slot)
        row = self.state.slots.get(slot)
        if not row or not row.exists:
            return
        if slot in self._waveform_by_slot or slot in self._waveform_pending:
            if slot == self.state.selected_slot:
                self._update_waveform(slot)
            return

        if self._load_cached_waveform(slot):
            if slot == self.state.selected_slot:
                self._update_waveform(slot)
            return

        self._waveform_pending.add(slot)
        if self._worker:
            self._worker.submit(actions.waveform(slot, width=320, height=24))
        if slot == self.state.selected_slot:
            self._update_waveform(slot)

    def _update_waveform(self, slot: int) -> None:
        widget = self.query_one("#waveform", WaveformWidget)
        row = self.state.slots.get(slot)
        if not row or not row.exists:
            widget.set_empty()
        elif slot in self._waveform_pending:
            widget.set_pending(slot)
        elif slot in self._waveform_by_slot:
            widget.set_bins(slot, self._waveform_by_slot[slot])
        else:
            widget.set_not_loaded(slot)

    def _start_playback_animation(self, slot: int, duration_s: float) -> None:
        self._stop_playback_animation()
        self._play_slot = slot
        self._play_start = time.monotonic()
        self._play_duration = duration_s
        self._play_timer = self.set_interval(1 / 24, self._on_playback_tick)

    def _stop_playback_animation(self) -> None:
        if self._play_timer is not None:
            self._play_timer.stop()
            self._play_timer = None
        try:
            widget = self.query_one("#waveform", WaveformWidget)
            widget.clear_cursor()
        except Exception:
            pass
        self._play_slot = None

    def _on_playback_tick(self) -> None:
        if self._play_slot is None or self._play_duration <= 0:
            self._stop_playback_animation()
            return
        elapsed = time.monotonic() - self._play_start
        fraction = elapsed / self._play_duration
        if fraction >= 1.0:
            self._stop_playback_animation()
            return
        if self._play_slot == self.state.selected_slot:
            try:
                widget = self.query_one("#waveform", WaveformWidget)
                widget.set_cursor(fraction)
            except Exception:
                pass

    def _with_friendly_trace_name(self, line: str, trace: dict) -> str:
        slot = trace.get("slot")
        raw_name = str(trace.get("name") or "")
        if slot is None and raw_name:
            m = re.match(r"^(\d{1,3})\.pcm$", raw_name, flags=re.IGNORECASE)
            if m:
                slot = int(m.group(1))
        if slot is None:
            return line
        row = self.state.slots.get(int(slot))
        if not row or not row.exists:
            return line
        friendly = row.name.strip()
        if not friendly:
            return line
        if raw_name and friendly.lower() == raw_name.lower():
            return line
        if raw_name and raw_name.lower().endswith(".pcm"):
            return f'{line} label="{friendly}"'
        return line

    def action_refresh(self) -> None:
        self._queue_request(actions.refresh_inventory())

    def action_view_details(self) -> None:
        if self.moving_src is not None:
            src = self.moving_src
            dst = self.state.selected_slot
            self.moving_src = None
            self._refresh_table()
            self.refresh_bindings()
            if src != dst:
                self._queue_request(actions.move(src, dst))
            else:
                self._update_status(self.state.status)
            return

        if self.copying_src is not None:
            src = self.copying_src
            dst = self.state.selected_slot
            self.copying_src = None
            self._refresh_table()
            self.refresh_bindings()
            if src != dst and not self.state.slots[dst].exists:
                self._queue_request(actions.copy(src, dst))
            else:
                self._update_status(self.state.status)
            return

        slot = self._current_slot()
        if slot in self.state.details_by_slot:
            self._update_details(slot)
            self._ensure_waveform(slot)
        else:
            self._queue_request(actions.fetch_details(slot))

    def action_select_expr(self) -> None:
        n = len(self.state.selected_slots)
        if n:
            expr_list = self._format_selection_expr()
            title = f"Select slots  ({n} currently selected: {expr_list})"
        else:
            title = "Select slots"
        self.push_screen(
            TextInputModal(
                title=title,
                placeholder="200, 201-210, 500-599   (empty to clear)",
                allow_empty=True,
            ),
            callback=self._on_select_modal,
        )

    def action_toggle_logs(self) -> None:
        logs = self.query_one("#logs", _LogView)
        self._logs_visible = not self._logs_visible
        if self._logs_visible:
            logs.remove_class("hidden")
        else:
            logs.add_class("hidden")
        self._update_status(self.state.status)

    def action_toggle_select(self) -> None:
        slot = self._current_slot()
        prev = set(self.state.selected_slots)
        was_selected = slot in self.state.selected_slots
        if slot in self.state.selected_slots:
            self.state.selected_slots.remove(slot)
        else:
            self.state.selected_slots.add(slot)
        
        self._update_selection_display(prev)
        self._update_status(self.state.status)

        # Move down only when toggled on.
        if not was_selected:
            table = self.query_one("#slots", DataTable)
            table.action_cursor_down()

    def action_cursor_down(self) -> None:
        table = self.query_one("#slots", DataTable)
        if table.row_count <= 0:
            return
        if self.copying_src is not None:
            self._copy_cursor_move(1)
            return
        if table.cursor_row >= table.row_count - 1:
            table.move_cursor(row=0, animate=False)
            return
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        table = self.query_one("#slots", DataTable)
        if table.row_count <= 0:
            return
        if self.copying_src is not None:
            self._copy_cursor_move(-1)
            return
        if table.cursor_row <= 0:
            table.move_cursor(row=table.row_count - 1, animate=False)
            return
        table.action_cursor_up()

    def _copy_cursor_move(self, direction: int) -> None:
        """Move cursor to next empty slot in the given direction (1=down, -1=up)."""
        table = self.query_one("#slots", DataTable)
        max_slot = len(self.state.slots)
        current = table.cursor_row + 1  # 1-based slot
        s = current + direction
        while 1 <= s <= max_slot:
            if not self.state.slots[s].exists:
                table.move_cursor(row=s - 1, animate=False)
                return
            s += direction

    def action_page_down(self) -> None:
        table = self.query_one("#slots", DataTable)
        step = max(1, table.size.height // 2)
        new_row = min(table.row_count - 1, table.cursor_row + step)
        table.move_cursor(row=new_row, animate=False)

    def action_page_up(self) -> None:
        table = self.query_one("#slots", DataTable)
        step = max(1, table.size.height // 2)
        new_row = max(0, table.cursor_row - step)
        table.move_cursor(row=new_row, animate=False)

    def _format_selection_expr(self) -> str:
        if not self.state.selected_slots:
            return ""
        slots = sorted(self.state.selected_slots)
        parts = []
        start = slots[0]
        prev = slots[0]
        for s in slots[1:]:
            if s == prev + 1:
                prev = s
            else:
                if start == prev:
                    parts.append(str(start))
                else:
                    parts.append(f"{start}-{prev}")
                start = s
                prev = s
        if start == prev:
            parts.append(str(start))
        else:
            parts.append(f"{start}-{prev}")
        
        full = ",".join(parts)
        if len(full) > 30:
            return full[:27] + "..."
        return full

    def _on_select_modal(self, expr: str | None) -> None:
        if expr is None:
            return  # modal was cancelled — leave selection unchanged
        prev = set(self.state.selected_slots)
        expr = expr.strip()
        if not expr:
            self.state.selected_slots = set()
            if prev:
                self._log("Selection cleared")
        else:
            try:
                selector = parse_selector(expr)
                self.state.selected_slots = selector.resolve(self.state.slots)
            except ValueError as exc:
                self._log(f"Invalid selection: {exc}")
                return
            n = len(self.state.selected_slots)
            self._log(f"Selected {n} slot{'s' if n != 1 else ''}")
        self._update_selection_display(prev)
        self._update_status(self.state.status)

    def action_start_move(self) -> None:
        slot = self._current_slot()
        if not self.state.slots[slot].exists:
            self._log(f"Slot {slot:03d} is empty")
            return
        self.moving_src = slot
        self._refresh_table()
        self.refresh_bindings()
        self._update_status("Move mode (Esc to cancel, Enter to drop)")

    def action_cancel_move(self) -> None:
        if self.moving_src is not None:
            self.moving_src = None
            self._refresh_table()
            self.refresh_bindings()
            self._update_status(self.state.status)

    def action_download(self) -> None:
        if self.state.selected_slots:
            slots = sorted(self.state.selected_slots)
            for slot in slots:
                self._queue_request(actions.download(slot, f"slot{slot:03d}.wav"))
            self._log(f"Queued download of {len(slots)} slots → slot###.wav")
        else:
            slot = self._current_slot()
            default_name = f"slot{slot:03d}.wav"
            self.push_screen(
                TextInputModal(
                    title=f"Download slot {slot:03d}",
                    placeholder="Output path",
                    initial=default_name,
                ),
                callback=lambda path: self._on_download_modal(slot, path),
            )

    async def action_upload(self) -> None:
        cursor_slot = self._current_slot()
        files = await pick_files(self, force_modal=self.alt_file_picker)
        if not files:
            return
        if len(files) == 1:
            input_path = files[0]
            row = self.state.slots.get(cursor_slot)
            if row and row.exists:
                sample_name = row.name.strip() or f"Slot {cursor_slot:03d}"
                self.push_screen(
                    ConfirmModal(f"Slot {cursor_slot:03d} already has a sample ({sample_name}) — overwrite?"),
                    callback=lambda ok: ok and self._queue_request(actions.upload(cursor_slot, str(input_path))),
                )
            else:
                self._queue_request(actions.upload(cursor_slot, str(input_path)))
        else:
            free = [s for s in range(cursor_slot, 1000) if not self.state.slots.get(s, SlotRow(s)).exists]
            if not free:
                self._log(f"No free slots from slot {cursor_slot:03d}")
                return
            if len(free) < len(files):
                self._log(f"Not enough free slots: need {len(files)}, found {len(free)} from slot {cursor_slot:03d}")
                files = files[: len(free)]
            self._queue_request(actions.batch_upload(list(zip(files, free))))

    def action_copy(self) -> None:
        slot = self._current_slot()
        if not self.state.slots[slot].exists:
            self._log(f"Slot {slot:03d} is empty")
            return
        self.copying_src = slot
        # Jump to nearest empty slot
        self._jump_to_empty_slot(slot)
        self._refresh_table()
        self.refresh_bindings()
        self._update_status("Copy mode (Esc to cancel, Enter to paste)")

    def action_cancel_copy(self) -> None:
        if self.copying_src is not None:
            self.copying_src = None
            self._refresh_table()
            self.refresh_bindings()
            self._update_status(self.state.status)

    def _jump_to_empty_slot(self, from_slot: int) -> None:
        """Move cursor to the nearest empty slot, searching forward then backward."""
        table = self.query_one("#slots", DataTable)
        max_slot = len(self.state.slots)
        # Search forward first
        for s in range(from_slot + 1, max_slot + 1):
            if not self.state.slots[s].exists:
                table.move_cursor(row=s - 1, animate=False)
                return
        # Then backward
        for s in range(from_slot - 1, 0, -1):
            if not self.state.slots[s].exists:
                table.move_cursor(row=s - 1, animate=False)
                return
        self._log("No empty slots available")

    def action_rename(self) -> None:
        slot = self._current_slot()
        initial = self.state.slots[slot].name if self.state.slots[slot].exists else ""
        self.push_screen(
            TextInputModal(
                title=f"Rename slot {slot:03d}",
                placeholder="New sample name",
                initial=initial,
            ),
            callback=lambda new_name: self._on_rename_modal(slot, new_name),
        )

    def _on_download_modal(self, slot: int, path: str | None) -> None:
        if path:
            self._queue_request(actions.download(slot, path))

    def _on_rename_modal(self, slot: int, new_name: str | None) -> None:
        if new_name:
            self._queue_request(actions.rename(slot, new_name))

    def action_audition(self) -> None:
        slot = self._current_slot()
        row = self.state.slots.get(slot)
        if not row or not row.exists:
            return
        sr = row.samplerate or MAX_SAMPLE_RATE
        ch = max(row.channels, 1)
        duration_s = row.size_bytes / (sr * ch * 2) if row.size_bytes > 0 else 0.0
        self._queue_request(actions.audition(slot, duration_s=duration_s))

    def action_delete(self) -> None:
        if self.state.selected_slots:
            slots = sorted(self.state.selected_slots)
            n = len(slots)
            slot_list = ", ".join(f"{s:03d}" for s in slots[:5])
            suffix = f", +{n - 5} more" if n > 5 else ""
            self.push_screen(
                ConfirmModal(f"Delete {n} slots: {slot_list}{suffix}?"),
                callback=lambda ok: self._on_bulk_delete_confirm(slots, ok),
            )
        else:
            slot = self._current_slot()
            name = self.state.slots[slot].name if self.state.slots[slot].exists else f"Slot {slot:03d}"
            self.push_screen(
                ConfirmModal(f"Delete slot {slot:03d} ({name})?"),
                callback=lambda ok: self._on_delete_confirm(slot, ok),
            )

    def _on_delete_confirm(self, slot: int, confirmed: bool) -> None:
        if confirmed:
            self._queue_request(actions.delete(slot))

    def _on_bulk_delete_confirm(self, slots: list[int], confirmed: bool) -> None:
        if confirmed:
            self.state.selected_slots = set()
            self._queue_request(actions.bulk_delete(slots))

    def action_squash(self) -> None:
        selected = sorted(self.state.selected_slots)
        if selected:
            start, end = selected[0], selected[-1]
            msg = f"Squash gaps in slots {start}–{end}?"
        else:
            start, end = 1, 999
            msg = "Squash all gaps? (Move samples to fill empty slots)"
        self._squash_range = (start, end)
        self.push_screen(
            ConfirmModal(msg),
            callback=self._on_squash_confirm,
        )

    def _on_squash_confirm(self, confirmed: bool) -> None:
        if confirmed:
            start, end = getattr(self, "_squash_range", (1, 999))
            self._queue_request(actions.squash(start=start, end=end))

    def action_optimize(self) -> None:
        if self.state.selected_slots:
            slots = sorted(self.state.selected_slots)
            msg = f"Optimize {len(slots)} selected slots"
        else:
            slot = self._current_slot()
            slots = [slot]
            msg = f"Optimize slot {slot:03d}"

        self.push_screen(
            OptimizeModal(msg),
            callback=lambda result: self._on_optimize_modal(slots, result),
        )

    def _on_optimize_modal(self, slots: list[int], result: tuple[bool, int | None, float | None, float] | None) -> None:
        if result is None:
            return
        mono, rate, speed, pitch = result
        self.state.selected_slots = set()
        self._queue_request(actions.optimize(slots, mono=mono, rate=rate, speed=speed, pitch=pitch))

    def action_help(self) -> None:
        self.push_screen(HelpModal())

    def action_optimize_all(self) -> None:
        stereo_slots = [
            slot
            for slot, row in self.state.slots.items()
            if row.exists and row.channels > 1
        ]
        n_known = len(stereo_slots)
        if n_known:
            msg = f"Optimize all stereo samples? ({n_known} known stereo + any undetected stereo)"
        else:
            msg = "Optimize all stereo samples? (will scan all slots for stereo)"
        self.push_screen(
            ConfirmModal(msg),
            callback=self._on_optimize_all_confirm,
        )

    def _on_optimize_all_confirm(self, confirmed: bool) -> None:
        if confirmed:
            self._queue_request(actions.optimize_all())


    def action_quit(self) -> None:
        self._shutdown_worker()
        self.exit()


def _render_progress_bar(current: int, total: int, width: int = 16) -> str:
    """Render a text progress bar like [████████░░░░░░░░] 50%."""
    frac = min(1.0, current / total) if total > 0 else 0.0
    filled = int(width * frac)
    empty = width - filled
    pct = int(frac * 100)
    return f"[{'█' * filled}{'░' * empty}] {pct}%"


def _waveform_signature(slot: int, slots: dict[int, SlotRow]) -> dict[str, Any] | None:
    row = slots.get(int(slot))
    if not row or not row.exists or row.size_bytes <= 0:
        return None
    return {
        "name": str(row.name or ""),
        "size_bytes": int(row.size_bytes),
        "channels": int(row.channels or 0),
        "samplerate": int(row.samplerate or 0),
    }
