from core.client import EP133Client


def _client():
    return EP133Client.__new__(EP133Client)


def test_info_uses_node_metadata_without_legacy_fallback(monkeypatch):
    c = _client()
    monkeypatch.setattr(
        c,
        "list_sounds",
        lambda: {200: {"node_id": 200, "name": "200.pcm", "size": 123}},
    )
    monkeypatch.setattr(
        c,
        "get_node_metadata",
        lambda node_id: {"name": "node", "channels": 2, "samplerate": 48000},
    )
    monkeypatch.setattr(c, "_get_file_size", lambda slot: 123)

    called = {"legacy": False}

    def _legacy(slot):
        called["legacy"] = True
        return {"name": "legacy"}

    monkeypatch.setattr(c, "get_meta_legacy", _legacy)

    info = c.info(200, include_size=True)
    assert info.name == "node"
    assert info.channels == 2
    assert info.samplerate == 48000
    assert called["legacy"] is False


def test_info_uses_filesystem_name_when_node_metadata_missing(monkeypatch):
    c = _client()
    monkeypatch.setattr(
        c,
        "list_sounds",
        lambda: {150: {"node_id": 150, "name": "150 clap", "size": 456}},
    )
    monkeypatch.setattr(c, "get_node_metadata", lambda node_id: None)
    monkeypatch.setattr(c, "_get_file_size", lambda slot: 456)

    info = c.info(150, include_size=True)
    assert info.name == "150 clap"
    assert info.channels == 1
    assert info.samplerate == 46875
