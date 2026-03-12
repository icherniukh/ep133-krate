import json

from core.models import FileListRequest
from tui.debug_log import DebugLogger


def test_debug_logger_writes_jsonl(tmp_path):
    out = tmp_path / "trace.jsonl"
    logger = DebugLogger(enabled=True, output_path=out)

    raw = FileListRequest(node_id=1000, page=0).build(seq=1)
    event = logger.record("TX", raw)
    logger.close()

    assert event is not None
    assert event.ui_line().startswith("MIDI TX")
    assert out.exists()

    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["dir"] == "TX"
    assert payload["cmd"] == 0x6A


def test_debug_logger_default_capture_path(tmp_path):
    logger = DebugLogger(enabled=True, capture_dir=tmp_path / "captures")
    try:
        assert logger.path is not None
        assert logger.path.parent == tmp_path / "captures"
        assert logger.path.name.startswith("tui-")
    finally:
        logger.close()
