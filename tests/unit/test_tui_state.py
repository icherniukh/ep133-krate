from tui.state import FoldedRegion, SlotRow, TuiState, build_visible_rows, find_empty_runs, initial_slots


def test_initial_slots_has_999_entries():
    slots = initial_slots(999)
    assert len(slots) == 999
    assert slots[1].slot == 1
    assert slots[999].slot == 999


def test_apply_inventory_marks_present_slots():
    state = TuiState()
    state.apply_inventory(
        {
            5: {"name": "005 kick", "size": 1234, "node_id": 1005},
            12: {"name": "012 snare", "size": 5678, "node_id": 1012},
        }
    )

    assert state.slots[5].exists is True
    assert state.slots[5].name == "005 kick"
    assert state.slots[5].size_bytes == 1234

    assert state.slots[12].exists is True
    assert state.slots[12].name == "012 snare"

    assert state.slots[1].exists is False
    assert state.slots[1].name == "(empty)"


def test_apply_slot_details_updates_row_fields():
    state = TuiState()
    state.apply_inventory({7: {"name": "007 bass", "size": 2000}})

    state.apply_slot_details(
        7,
        {
            "name": "bassline",
            "channels": 2,
            "samplerate": 44100,
            "size_bytes": 3000,
            "format": "s16",
            "is_empty": False,
        },
    )

    row = state.slots[7]
    assert row.name == "bassline"
    assert row.channels == 2
    assert row.samplerate == 44100
    assert row.size_bytes == 3000
    assert state.details_by_slot[7]["format"] == "s16"


def test_apply_inventory_updates_hydrates_names_and_audio_fields():
    state = TuiState()
    state.apply_inventory(
        {
            1: {"name": "001.pcm", "size": 1200, "node_id": 1},
            2: {"name": "002.pcm", "size": 2200, "node_id": 2},
        }
    )
    state.apply_inventory_updates(
        {
            1: {"name": "afterparty kick", "channels": 1, "samplerate": 46875},
            2: {"name": "nt hh closed b", "channels": 2, "samplerate": 44100},
        }
    )

    assert state.slots[1].name == "afterparty kick"
    assert state.slots[1].channels == 1
    assert state.slots[1].samplerate == 46875

    assert state.slots[2].name == "nt hh closed b"
    assert state.slots[2].channels == 2
    assert state.slots[2].samplerate == 44100


def test_apply_inventory_preserves_prior_hydration_for_untouched_slots():
    state = TuiState()
    sounds = {
        1: {"name": "001.pcm", "size": 1200, "node_id": 1},
        2: {"name": "002.pcm", "size": 2200, "node_id": 2},
    }
    state.apply_inventory(sounds)
    state.apply_inventory_updates(
        {
            1: {"name": "afterparty kick", "channels": 1, "samplerate": 46875},
            2: {"name": "nt hh closed b", "channels": 2, "samplerate": 44100},
        }
    )

    # Simulate post-op refresh: full inventory first, then partial hydration only
    # for touched slots.
    state.apply_inventory(sounds)
    state.apply_inventory_updates(
        {
            1: {"name": "afterparty kick v2", "channels": 1, "samplerate": 46875},
        }
    )

    assert state.slots[1].name == "afterparty kick v2"
    assert state.slots[1].channels == 1

    # Slot 2 should keep previously known enriched metadata and not degrade to
    # file-list fallback state.
    assert state.slots[2].name == "nt hh closed b"
    assert state.slots[2].channels == 2
    assert state.slots[2].samplerate == 44100


def test_clear_slot_marks_slot_empty_and_removes_details():
    state = TuiState()
    state.apply_inventory({5: {"name": "kick", "size": 1000, "node_id": 1005}})
    state.apply_slot_details(5, {"name": "kick", "size_bytes": 1000, "channels": 1, "samplerate": 46875, "is_empty": False})

    assert state.slots[5].exists is True
    assert 5 in state.details_by_slot

    state.clear_slot(5)

    assert state.slots[5].exists is False
    assert state.slots[5].name == "(empty)"
    assert 5 not in state.details_by_slot


# ---------------------------------------------------------------------------
# build_visible_rows / fold logic
# ---------------------------------------------------------------------------

def _make_slots(occupied: list[int], total: int = 10) -> dict[int, SlotRow]:
    """Create a slots dict with *total* entries where *occupied* slots exist."""
    slots = {s: SlotRow(slot=s) for s in range(1, total + 1)}
    for s in occupied:
        slots[s].exists = True
        slots[s].name = f"sample{s:03d}"
    return slots


def test_build_visible_rows_no_folds_returns_all_slots():
    slots = _make_slots([3, 7], total=10)
    rows = build_visible_rows(slots, folded_regions=set())
    assert len(rows) == 10
    assert all(isinstance(r, SlotRow) for r in rows)
    assert [r.slot for r in rows] == list(range(1, 11))  # type: ignore[union-attr]


def test_build_visible_rows_fold_collapses_matching_region():
    # slots 1-5 empty, slot 6 occupied, slots 7-10 empty
    slots = _make_slots([6], total=10)
    rows = build_visible_rows(slots, folded_regions={(1, 5), (7, 10)})

    # Expect: FoldedRegion(1-5), SlotRow(6), FoldedRegion(7-10)
    assert len(rows) == 3
    first, middle, last = rows
    assert isinstance(first, FoldedRegion)
    assert first.start_slot == 1
    assert first.end_slot == 5
    assert first.count == 5

    assert isinstance(middle, SlotRow)
    assert middle.slot == 6

    assert isinstance(last, FoldedRegion)
    assert last.start_slot == 7
    assert last.end_slot == 10
    assert last.count == 4


def test_build_visible_rows_partial_fold_only_folds_specified():
    # Only fold the first region, leave the second expanded
    slots = _make_slots([6], total=10)
    rows = build_visible_rows(slots, folded_regions={(1, 5)})

    # Expect: FoldedRegion(1-5), SlotRow(6), SlotRow(7)..SlotRow(10)
    assert len(rows) == 6
    assert isinstance(rows[0], FoldedRegion)
    assert isinstance(rows[1], SlotRow)
    assert rows[1].slot == 6  # type: ignore[union-attr]
    # Slots 7-10 remain expanded
    for i, slot in enumerate(range(7, 11)):
        assert isinstance(rows[2 + i], SlotRow)
        assert rows[2 + i].slot == slot  # type: ignore[union-attr]


def test_build_visible_rows_single_empty_stays_visible():
    # Isolated empty slots (run < 2) are shown individually even if in folded_regions.
    slots = _make_slots([1, 3, 5], total=5)
    rows = build_visible_rows(slots, folded_regions={(2, 2), (4, 4)})
    # Runs of length 1 are below min_run=2, so all rows are SlotRows.
    assert len(rows) == 5
    assert all(isinstance(r, SlotRow) for r in rows)


def test_build_visible_rows_run_of_exactly_two_collapses():
    # Slots 2-3 empty — exactly at the min_run threshold.
    slots = _make_slots([1, 4, 5], total=5)
    rows = build_visible_rows(slots, folded_regions={(2, 3)})
    # Expect: SlotRow(1), FoldedRegion(2-3), SlotRow(4), SlotRow(5)
    assert len(rows) == 4
    assert isinstance(rows[0], SlotRow)
    assert isinstance(rows[1], FoldedRegion)
    assert rows[1].count == 2  # type: ignore[union-attr]
    assert isinstance(rows[2], SlotRow)
    assert isinstance(rows[3], SlotRow)


def test_build_visible_rows_all_empty_folds_into_one_region():
    slots = _make_slots([], total=8)
    rows = build_visible_rows(slots, folded_regions={(1, 8)})
    assert len(rows) == 1
    region = rows[0]
    assert isinstance(region, FoldedRegion)
    assert region.start_slot == 1
    assert region.end_slot == 8
    assert region.count == 8


def test_build_visible_rows_all_occupied_no_folding():
    slots = _make_slots(list(range(1, 6)), total=5)
    rows = build_visible_rows(slots, folded_regions={(1, 5)})
    # All occupied — nothing to fold
    assert len(rows) == 5
    assert all(isinstance(r, SlotRow) for r in rows)


def test_build_visible_rows_fold_preserves_slot_order():
    slots = _make_slots([2, 7], total=10)
    rows = build_visible_rows(slots, folded_regions={(3, 6), (8, 10)})
    slot_nums = []
    for r in rows:
        if isinstance(r, SlotRow):
            slot_nums.append(r.slot)
        else:
            slot_nums.append(r.start_slot)
    assert slot_nums == sorted(slot_nums)


# ---------------------------------------------------------------------------
# find_empty_runs
# ---------------------------------------------------------------------------

def test_find_empty_runs_basic():
    slots = _make_slots([6], total=10)
    runs = find_empty_runs(slots)
    assert runs == [(1, 5), (7, 10)]


def test_find_empty_runs_no_empties():
    slots = _make_slots(list(range(1, 6)), total=5)
    runs = find_empty_runs(slots)
    assert runs == []


def test_find_empty_runs_all_empty():
    slots = _make_slots([], total=8)
    runs = find_empty_runs(slots)
    assert runs == [(1, 8)]


def test_find_empty_runs_single_empties_below_min_run():
    slots = _make_slots([1, 3, 5], total=5)
    runs = find_empty_runs(slots)
    assert runs == []  # each empty run is length 1, below min_run=2
