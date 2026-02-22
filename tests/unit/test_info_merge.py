from ko2_client import EP133Client


def _client():
    return EP133Client.__new__(EP133Client)


def test_info_prefers_node_name_over_get_meta_for_slot_over_127(monkeypatch):
    c = _client()
    monkeypatch.setattr(
        c,
        "list_sounds",
        lambda: {200: {"node_id": 200, "name": "200.pcm", "size": 123}},
    )
    monkeypatch.setattr(c, "get_node_metadata", lambda node_id: {"name": "node"})
    monkeypatch.setattr(
        c,
        "_meta_from_get_meta",
        lambda slot: {"name": "meta", "channels": 2, "samplerate": 46875},
    )
    monkeypatch.setattr(c, "_get_file_size", lambda slot: 123)

    info = c.info(200, include_size=True, allow_get_meta=True)
    assert info.name == "node"
    assert info.channels == 2
    assert info.samplerate == 46875


def test_info_uses_get_meta_for_missing_fields_slot_over_127(monkeypatch):
    c = _client()
    monkeypatch.setattr(
        c,
        "list_sounds",
        lambda: {150: {"node_id": 150, "name": "150.pcm", "size": 456}},
    )
    monkeypatch.setattr(c, "get_node_metadata", lambda node_id: {"name": "node"})
    monkeypatch.setattr(
        c,
        "_meta_from_get_meta",
        lambda slot: {"name": "meta", "channels": 1, "samplerate": 46875, "format": "s16"},
    )
    monkeypatch.setattr(c, "_get_file_size", lambda slot: 456)

    info = c.info(150, include_size=True, allow_get_meta=True)
    assert info.name == "node"
    assert info.channels == 1
    assert info.samplerate == 46875
    assert info.format == "s16"
