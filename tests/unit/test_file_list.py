from ko2_models import parse_file_list_response, slot_from_sound_entry


def test_parse_file_list_response_parses_files_and_dirs():
    # Payload is already 7-bit unpacked/decoded.
    # First two bytes are a header/unknown.
    payload = bytearray(b"\x00\x00")

    # Entry 1: file node 1001, flags=0x00, size=16, name="001 kick"
    payload.extend(bytes([0x03, 0xE9, 0x00, 0x00, 0x00, 0x00, 0x10]))
    payload.extend(b"001 kick\x00")

    # Entry 2: dir node 1000, flags=0x02, size=0, name="sounds"
    payload.extend(bytes([0x03, 0xE8, 0x02, 0x00, 0x00, 0x00, 0x00]))
    payload.extend(b"sounds\x00")

    entries = parse_file_list_response(bytes(payload))
    assert entries == [
        {"node_id": 1001, "flags": 0, "size": 16, "name": "001 kick", "is_dir": False},
        {"node_id": 1000, "flags": 2, "size": 0, "name": "sounds", "is_dir": True},
    ]


def test_slot_from_sound_entry_prefers_node_id_mapping():
    assert slot_from_sound_entry({"node_id": 1850, "name": "whatever"}) == 850


def test_slot_from_sound_entry_falls_back_to_filename_prefix():
    assert slot_from_sound_entry({"node_id": 9999, "name": "852 snare"}) == 852


def test_parse_file_list_response_prefers_14bit_when_prefix_matches():
    # Simulate 14-bit encoded node_id for slot 129 (node_id=1129 -> hi=0x08, lo=0x69)
    payload = bytearray(b"\x00\x00")
    payload.extend(bytes([0x08, 0x69, 0x00, 0x00, 0x00, 0x00, 0x10]))
    payload.extend(b"129 snare\x00")
    entries = parse_file_list_response(bytes(payload))
    assert entries[0]["node_id"] == 1129


def test_slot_from_sound_entry_prefers_filename_when_node_id_conflicts():
    assert slot_from_sound_entry({"node_id": 285, "name": "001.pcm"}) == 1
