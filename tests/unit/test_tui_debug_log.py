import json

from core.models import FileListRequest
from tui.debug_log import DebugLogger, _build_event


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


def test_download_data_rx_not_misparsed_as_fileop():
    """RX on cmd 0x3D with audio PCM must parse as GET_DATA, not as a
    false PUT_INIT/DELETE/VERIFY from random PCM bytes."""
    # Construct a fake download data response: F0 [TE header] 3D seq 05 status [packed7 audio] F7
    # cmd=0x3D (DOWNLOAD-0x40), body has CMD_FILE byte at [7]
    raw = bytes([
        0xF0,
        0x00, 0x20, 0x76, 0x33, 0x40,  # TE mfr + family
        0x3D,                            # cmd (download response)
        0x10,                            # seq
        0x05,                            # CMD_FILE
        0x00,                            # status=0
        # Packed7 payload: random PCM that could decode as fileop 0x02/0x06/0x0B
        0x00, 0x02, 0x00, 0x05, 0x03, 0x84, 0x03, 0xE8,
        0x00, 0x00, 0x10, 0x00, 0x6B, 0x69, 0x63, 0x6B,
        0xF7,
    ])
    event = _build_event("RX", raw)
    # Must NOT be parsed as PUT_INIT, DELETE, VERIFY, etc.
    assert event.op in ("GET_DATA", "GET_INIT_RSP"), f"got op={event.op}"
    assert event.op == "GET_DATA"  # no .pcm filename → it's a data chunk
