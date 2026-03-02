from __future__ import annotations

import re
from queue import Empty, Queue
from typing import Iterable, cast

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, RichLog, Static

from . import actions
from .debug_log import DebugLogger
from .selectors import parse_selector
from .state import TuiState
from .ui import ConfirmModal, TextInputModal, UploadModal, table_row_values
from .worker import DeviceWorker, WorkerEvent


class KO2TUIApp(App[None]):
    CSS = """
    #status {
        height: 1;
        padding: 0 1;
    }
    #main {
        height: 1fr;
    }
    #slots {
        width: 2fr;
    }
    #details {
        width: 1fr;
        padding: 1;
        border: round $boost;
    }
    #logs {
        height: 12;
        border: round $boost;
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
        Binding("r", "refresh", "Refresh"),
        Binding("enter", "view_details", "Details"),
        Binding("g", "download", "Download"),
        Binding("u", "upload", "Upload"),
        Binding("n", "rename", "Rename"),
        Binding("s", "select", "Select"),
        Binding("x", "delete", "Delete"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, device_name: str, debug: bool = False, debug_log: str | None = None):
        super().__init__()
        self.device_name = device_name
        self.debug_enabled = bool(debug)
        self.debug_log = debug_log

        self.state = TuiState()
        self._request_queue: Queue[actions.WorkerRequest] = Queue()
        self._event_queue: Queue[WorkerEvent] = Queue()
        self._worker: DeviceWorker | None = None
        self._debug_logger: DebugLogger | None = None
        self._col_keys: list = []

    def compose(self) -> ComposeResult:
        yield Static(id="status")
        with Horizontal(id="main"):
            yield DataTable(id="slots")
            yield Static("No slot selected", id="details")
        yield RichLog(id="logs", wrap=True, markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self._init_table()
        self._debug_logger = DebugLogger(
            enabled=self.debug_enabled,
            output_path=self.debug_log,
        )

        self._worker = DeviceWorker(
            device_name=self.device_name,
            request_queue=self._request_queue,
            event_queue=self._event_queue,
            debug_logger=self._debug_logger,
        )
        self._worker.start()

        self.set_interval(0.05, self._drain_worker_events)

        self._update_status("Ready")
        if self._debug_logger and self._debug_logger.path:
            self._log(f"Debug capture: {self._debug_logger.path}")
        self._queue_request(actions.refresh_inventory())

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

    def _init_table(self) -> None:
        table = self.query_one("#slots", DataTable)
        table.cursor_type = "row"
        self._col_keys = table.add_columns(" ", "Slot", "Name", "Size", "CH", "Rate", "Sec")
        self._refresh_table()

    def _refresh_table(self) -> None:
        table = self.query_one("#slots", DataTable)
        table.clear(columns=False)
        for slot in range(1, len(self.state.slots) + 1):
            row = self.state.slots[slot]
            selected = slot in self.state.selected_slots
            table.add_row(*table_row_values(row, selected), key=str(slot))

        cursor_row = max(0, min(len(self.state.slots) - 1, self.state.selected_slot - 1))
        try:
            table.move_cursor(row=cursor_row, column=0, animate=False)
        except Exception:
            pass

    def _update_table_rows(self, slot_nums: Iterable[int]) -> None:
        table = self.query_one("#slots", DataTable)
        for slot in slot_nums:
            row = self.state.slots[slot]
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
        self.state.selected_slot = event.cursor_row + 1
        self._render_details(self.state.selected_slot)

    def _current_slot(self) -> int:
        table = self.query_one("#slots", DataTable)
        try:
            row = int(table.cursor_row)
        except Exception:
            row = self.state.selected_slot - 1
        return max(1, row + 1)

    def _queue_request(self, request: actions.WorkerRequest) -> None:
        if self.state.busy:
            self._log(f"Queued: {request.op} (waiting for current operation)")
        else:
            self.state.set_busy(True, f"Running {request.op}...")
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
            self.state.set_busy(True, f"Running {payload.get('op', 'operation')}...")
            self._update_status(self.state.status)
            return

        if kind == "idle":
            self.state.set_busy(False, "Ready")
            self._update_status("Ready")
            return

        if kind == "inventory":
            sounds = cast(dict[int, dict], payload.get("sounds", {}))
            self.state.apply_inventory(sounds)
            self._refresh_table()
            used = len(sounds)
            self._log(f"Inventory refreshed: {used} used slots")
            self._render_details(self.state.selected_slot)
            return

        if kind == "inventory_enriched":
            updates = cast(dict[int, dict], payload.get("updates", {}))
            if updates:
                self.state.apply_inventory_updates(updates)
                self._update_table_rows(updates.keys())
                self._render_details(self.state.selected_slot)
            return

        if kind == "details":
            slot = int(payload.get("slot") or self.state.selected_slot)
            details = cast(dict, payload.get("details", {}))
            self.state.apply_slot_details(slot, details)
            self._refresh_table()
            self._render_details(slot)
            self._log(f"Loaded details for slot {slot:03d}")
            return

        if kind == "success":
            self._log(f"OK: {payload.get('message', '')}")
            return

        if kind == "error":
            msg = str(payload.get("message", "Unknown error"))
            self.state.last_error = msg
            self._update_status(f"Error: {msg}")
            self._log(f"ERROR: {msg}")
            return

        if kind == "trace" and self.debug_enabled:
            line = str(payload.get("line", ""))
            trace = cast(dict, payload.get("trace", {}))
            line = self._with_friendly_trace_name(line, trace)
            if line:
                self._log(line)

    def _render_details(self, slot: int) -> None:
        slot = max(1, min(slot, len(self.state.slots)))
        self.state.selected_slot = slot
        row = self.state.slots[slot]
        details = self.state.details_by_slot.get(slot)
        if not row.exists:
            text = f"Slot {slot:03d}\n\n(empty)"
        else:
            channels = row.channels if row.channels else "-"
            rate = row.samplerate if row.samplerate else "-"
            size = row.size_bytes
            lines = [
                f"Slot: {slot:03d}",
                f"Name: {row.name}",
                f"Size: {size} bytes",
                f"Channels: {channels}",
                f"Rate: {rate}",
            ]
            if details:
                sym = details.get("sym")
                fmt = details.get("format")
                if sym:
                    lines.append(f"Symbol: {sym}")
                if fmt:
                    lines.append(f"Format: {fmt}")
            text = "\n".join(lines)
        self.query_one("#details", Static).update(text)

    def _update_status(self, state_text: str) -> None:
        debug_suffix = ""
        if self._debug_logger and self._debug_logger.path:
            debug_suffix = f" | debug={self._debug_logger.path.name}"
        n_sel = len(self.state.selected_slots)
        sel_suffix = f" | {n_sel} selected" if n_sel else ""
        status = f"Device: {self.device_name} | {state_text}{sel_suffix}{debug_suffix}"
        self.query_one("#status", Static).update(status)

    def _log(self, line: str) -> None:
        self.query_one("#logs", RichLog).write(line)

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
        slot = self._current_slot()
        if slot in self.state.details_by_slot:
            self._render_details(slot)
        else:
            self._queue_request(actions.fetch_details(slot))

    def action_select(self) -> None:
        n = len(self.state.selected_slots)
        title = f"Select slots  ({n} currently selected)" if n else "Select slots"
        self.push_screen(
            TextInputModal(
                title=title,
                placeholder="200, 201-210, 500-599   (empty to clear)",
                allow_empty=True,
            ),
            callback=self._on_select_modal,
        )

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

    def action_upload(self) -> None:
        slot = self._current_slot()
        self.push_screen(
            UploadModal(slot=slot),
            callback=lambda result: self._on_upload_modal(slot, result),
        )

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

    def _on_upload_modal(self, slot: int, result: tuple[str, str | None] | None) -> None:
        if result is None:
            return
        path, name = result
        self._queue_request(actions.upload(slot, path, name=name))

    def _on_rename_modal(self, slot: int, new_name: str | None) -> None:
        if new_name:
            self._queue_request(actions.rename(slot, new_name))

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

    def action_quit(self) -> None:
        self._shutdown_worker()
        self.exit()
