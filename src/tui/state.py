from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.models import MAX_SLOTS, MAX_SAMPLE_RATE


@dataclass
class SlotRow:
    slot: int
    name: str = "(empty)"
    size_bytes: int = 0
    channels: int = 0
    samplerate: int = MAX_SAMPLE_RATE
    exists: bool = False
    loaded: bool = False


@dataclass
class FoldedRegion:
    """Represents a collapsed run of consecutive empty slots in the table."""
    start_slot: int
    end_slot: int
    count: int


# A visible table item is either a real slot row or a folded summary.
VisibleRow = SlotRow | FoldedRegion


def find_empty_runs(
    slots: dict[int, SlotRow],
    min_run: int = 2,
) -> list[tuple[int, int]]:
    """Return all contiguous empty runs of at least *min_run* slots.

    Each entry is ``(start_slot, end_slot)`` inclusive.
    """
    ordered = sorted(slots)
    runs: list[tuple[int, int]] = []
    run_start: int | None = None
    run_end: int | None = None

    for s in ordered:
        if not slots[s].exists:
            if run_start is None:
                run_start = s
            run_end = s
        else:
            if run_start is not None and run_end is not None:
                if run_end - run_start + 1 >= min_run:
                    runs.append((run_start, run_end))
                run_start = None
                run_end = None

    if run_start is not None and run_end is not None:
        if run_end - run_start + 1 >= min_run:
            runs.append((run_start, run_end))

    return runs


def build_visible_rows(
    slots: dict[int, SlotRow],
    folded_regions: set[tuple[int, int]],
    min_run: int = 2,
) -> list[VisibleRow]:
    """Return the ordered list of rows to display in the slots table.

    *folded_regions* is a set of ``(start_slot, end_slot)`` tuples.  Runs
    that appear in this set are collapsed into :class:`FoldedRegion` summary
    rows.  All other slots are returned as individual :class:`SlotRow` items.

    When *folded_regions* is empty, every slot is visible (999 rows).
    """
    if not folded_regions:
        return [slots[s] for s in sorted(slots)]

    ordered = sorted(slots)
    result: list[VisibleRow] = []
    run_start: int | None = None
    run_end: int | None = None

    def _flush_run(start: int, end: int) -> None:
        length = end - start + 1
        if length >= min_run and (start, end) in folded_regions:
            result.append(FoldedRegion(start_slot=start, end_slot=end, count=length))
        else:
            for s in range(start, end + 1):
                result.append(slots[s])

    for s in ordered:
        row = slots[s]
        if not row.exists:
            if run_start is None:
                run_start = s
            run_end = s
        else:
            if run_start is not None:
                _flush_run(run_start, run_end)  # type: ignore[arg-type]
                run_start = None
                run_end = None
            result.append(row)

    if run_start is not None:
        _flush_run(run_start, run_end)  # type: ignore[arg-type]

    return result


# TODO: add a samples database — central local storage for samples to enable
# quick upload/download/backup, deduplication, and unlimited library space on
# the computer independent of the 999-slot device limit.


@dataclass
class TuiState:
    slots: dict[int, SlotRow] = field(default_factory=lambda: initial_slots(MAX_SLOTS))
    details_by_slot: dict[int, dict[str, Any]] = field(default_factory=dict)
    selected_slot: int = 1
    selected_slots: set[int] = field(default_factory=set)
    busy: bool = False
    status: str = "idle"
    last_error: str | None = None

    def set_busy(self, busy: bool, status: str = "") -> None:
        self.busy = busy
        self.status = status or ("busy" if busy else "idle")

    def apply_inventory(self, sounds: Mapping[int, Mapping[str, Any]]) -> None:
        previous = self.slots
        fresh = initial_slots(MAX_SLOTS)

        # When inventory is applied, it means we have listed all slots.
        # Mark all of them as loaded.
        for r in fresh.values():
            r.loaded = True

        for slot, entry in sounds.items():
            if not (1 <= int(slot) <= MAX_SLOTS):
                continue
            slot_num = int(slot)
            row = fresh[slot_num]
            row.exists = True
            row.loaded = True
            fallback_name = f"Slot {slot_num:03d}"
            row.name = str(entry.get("name") or fallback_name)
            row.size_bytes = int(entry.get("size") or 0)

            # Preserve previously hydrated metadata (friendly name/channels/rate)
            # for unchanged slots when post-op refresh hydrates only touched slots.
            prev = previous.get(slot_num)
            if not prev or not prev.exists:
                continue

            if prev.channels > 0:
                row.channels = int(prev.channels)
                row.samplerate = int(prev.samplerate or MAX_SAMPLE_RATE)

            prev_name = str(prev.name or "")
            if prev_name and prev_name not in {"(empty)", fallback_name}:
                row.name = prev_name

        for slot, details in self.details_by_slot.items():
            if slot in fresh:
                self._apply_details_to_row(fresh[slot], details)

        self.slots = fresh

    def apply_slot_details(self, slot: int, details: Mapping[str, Any]) -> None:
        if slot not in self.slots:
            self.slots[slot] = SlotRow(slot=slot)
        row = self.slots[slot]
        if details.get("name"):
            row.name = str(details.get("name"))
        # is_empty=True → exists=False; is_empty=False → exists=True; absent → keep current
        row.exists = not bool(details.get("is_empty", not row.exists))
        row.loaded = True
        self._apply_details_to_row(row, details)
        self.details_by_slot[slot] = dict(details)

    def apply_inventory_updates(self, updates: Mapping[int, Mapping[str, Any]]) -> None:
        for slot, patch in updates.items():
            if slot not in self.slots:
                continue
            row = self.slots[slot]
            if not row.exists:
                continue
            name = patch.get("name")
            if name:
                row.name = str(name)
            if patch.get("channels") is not None:
                row.channels = int(patch.get("channels") or 0)
            if patch.get("samplerate") is not None:
                row.samplerate = int(patch.get("samplerate") or MAX_SAMPLE_RATE)

    def clear_slot(self, slot: int) -> None:
        if slot in self.slots:
            self.slots[slot] = SlotRow(slot=slot, loaded=True)
        self.details_by_slot.pop(slot, None)

    @staticmethod
    def _apply_details_to_row(row: SlotRow, details: Mapping[str, Any]) -> None:
        if details.get("size_bytes") is not None:
            row.size_bytes = int(details.get("size_bytes") or row.size_bytes)
        if details.get("channels") is not None:
            row.channels = int(details.get("channels") or 0)
        if details.get("samplerate") is not None:
            row.samplerate = int(details.get("samplerate") or MAX_SAMPLE_RATE)


def initial_slots(max_slots: int) -> dict[int, SlotRow]:
    return {slot: SlotRow(slot=slot) for slot in range(1, max_slots + 1)}
