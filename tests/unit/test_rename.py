from core.client import EP133Client


def _make_client_for_rename(status: int | None):
    c = EP133Client.__new__(EP133Client)
    c.list_sounds = lambda: {201: {"node_id": 201}}
    if status is None:
        c._send_file_request = lambda *a, **k: None
    else:
        c._send_file_request = lambda *a, **k: (status, b"")
    return c


def test_rename_uses_file_response_status_success():
    c = _make_client_for_rename(status=0)
    c.rename(201, "afterparty kick")


def test_rename_raises_on_missing_response():
    c = _make_client_for_rename(status=None)
    try:
        c.rename(201, "x")
        raise AssertionError("Expected rename to fail")
    except Exception as e:
        assert "no response" in str(e)


def test_rename_raises_on_nonzero_status():
    c = _make_client_for_rename(status=5)
    try:
        c.rename(201, "x")
        raise AssertionError("Expected rename to fail")
    except Exception as e:
        assert "status=0x05" in str(e)
