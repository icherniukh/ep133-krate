from tui.state import TuiState, initial_slots


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
