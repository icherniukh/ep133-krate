from tui.dialog_log import DialogLogger


def test_dialog_logger_writes_lines(tmp_path):
    out = tmp_path / "dialog.log"
    logger = DialogLogger(enabled=True, output_path=out)
    try:
        logger.record("line one")
        logger.record("line two")
    finally:
        logger.close()

    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0].endswith("line one")
    assert lines[1].endswith("line two")


def test_dialog_logger_default_capture_path(tmp_path):
    logger = DialogLogger(enabled=True, capture_dir=tmp_path / "captures")
    try:
        assert logger.path is not None
        assert logger.path.parent == tmp_path / "captures"
        assert logger.path.name.startswith("tui-dialog-")
    finally:
        logger.close()
