from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ko2_models import MAX_SLOTS, SAMPLE_RATE


@dataclass
class SlotRow:
    slot: int
    name: str = "(empty)"
    size_bytes: int = 0
    channels: int = 0
    samplerate: int = SAMPLE_RATE
    exists: bool = False


# TODO(database): TuiState holds all sample metadata in memory and re-fetches
# it from the device on every refresh.  This makes the app stateless across
# sessions — names, tags, notes, and organisational metadata are lost on exit.
#
# Future work: implement a persistent local database (SQLite) that:
#   - caches device metadata (sample name, rate, channels, size, node_id)
#   - stores user annotations (tags, colour labels, notes, aliases)
#   - tracks provenance (source file path, upload date, checksum)
#   - enables offline browsing and search without a connected device
#   - syncs on connect: compare cached state against live device, flag drift
#
# The database should live in XDG_DATA_HOME / .ko2/samples.db.
# TuiState would then be initialised from the DB and flushed back after ops.


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
        fresh = initial_slots(MAX_SLOTS)
        for slot, entry in sounds.items():
            if not (1 <= int(slot) <= MAX_SLOTS):
                continue
            row = fresh[int(slot)]
            row.exists = True
            row.name = str(entry.get("name") or f"Slot {int(slot):03d}")
            row.size_bytes = int(entry.get("size") or 0)

        for slot, details in self.details_by_slot.items():
            if slot in fresh and fresh[slot].exists:
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
                row.samplerate = int(patch.get("samplerate") or SAMPLE_RATE)

    @staticmethod
    def _apply_details_to_row(row: SlotRow, details: Mapping[str, Any]) -> None:
        if details.get("size_bytes") is not None:
            row.size_bytes = int(details.get("size_bytes") or row.size_bytes)
        if details.get("channels") is not None:
            row.channels = int(details.get("channels") or 0)
        if details.get("samplerate") is not None:
            row.samplerate = int(details.get("samplerate") or SAMPLE_RATE)


def initial_slots(max_slots: int) -> dict[int, SlotRow]:
    return {slot: SlotRow(slot=slot) for slot in range(1, max_slots + 1)}
