import importlib
import types

import ko2


class _FakeApp:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        _FakeApp.last_kwargs = kwargs

    def run(self):
        _FakeApp.ran = True


def test_tui_command_dispatch(monkeypatch):
    _FakeApp.last_kwargs = None
    _FakeApp.ran = False

    fake_module = types.SimpleNamespace(TUIApp=_FakeApp)
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_module)
    monkeypatch.setattr(ko2, "find_device", lambda: "EP-133")
    monkeypatch.setattr("sys.argv", ["ko2.py", "tui"])

    rc = ko2.main()

    assert rc == 0
    assert _FakeApp.ran is True
    assert _FakeApp.last_kwargs["device_name"] == "EP-133"
    assert _FakeApp.last_kwargs["debug"] is False


def test_tui_command_passes_debug_flags(monkeypatch):
    _FakeApp.last_kwargs = None
    _FakeApp.ran = False

    fake_module = types.SimpleNamespace(TUIApp=_FakeApp)
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_module)
    monkeypatch.setattr(ko2, "find_device", lambda: "EP-133")
    monkeypatch.setattr("sys.argv", [
        "ko2.py",
        "tui",
        "--debug",
        "captures/test.jsonl",
    ])

    rc = ko2.main()

    assert rc == 0
    assert _FakeApp.ran is True
    assert _FakeApp.last_kwargs["device_name"] == "EP-133"
    assert _FakeApp.last_kwargs["debug"] is True
    assert _FakeApp.last_kwargs["debug_log"] == "captures/test.jsonl"


def test_tui_command_passes_dialog_log_flag(monkeypatch):
    _FakeApp.last_kwargs = None
    _FakeApp.ran = False

    fake_module = types.SimpleNamespace(TUIApp=_FakeApp)
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_module)
    monkeypatch.setattr(ko2, "find_device", lambda: "EP-133")
    monkeypatch.setattr("sys.argv", [
        "ko2.py",
        "tui",
        "--debug",
        "captures/test.jsonl",
        "--dialog-log",
        "captures/dialog.log",
    ])

    rc = ko2.main()

    assert rc == 0
    assert _FakeApp.ran is True
    assert _FakeApp.last_kwargs["dialog_log"] == "captures/dialog.log"


def test_tui_import_error_is_user_friendly(monkeypatch, capsys):
    def _raise(_name):
        raise ImportError("missing textual")

    monkeypatch.setattr(importlib, "import_module", _raise)
    monkeypatch.setattr(ko2, "find_device", lambda: "EP-133")
    monkeypatch.setattr("sys.argv", ["ko2.py", "tui"])

    rc = ko2.main()
    out = capsys.readouterr().out

    assert rc == 1
    assert "textual" in out.lower()
