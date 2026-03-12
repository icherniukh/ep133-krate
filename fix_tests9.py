from pathlib import Path

def fix():
    # test_tui_cli_integration.py
    p = Path("tests/unit/test_tui_cli_integration.py")
    if p.exists():
        text = p.read_text()
        text = text.replace('monkeypatch.setattr(ko2, "find_device"', 'monkeypatch.setattr("cli.cli_main.find_device"')
        text = text.replace('ko2.main()', 'cli.cli_main.main()')
        if 'import cli.cli_main' not in text:
            text = 'import cli.cli_main\n' + text
        p.write_text(text)

    # test_upload_recovery.py
    p = Path("tests/unit/test_upload_recovery.py")
    if p.exists():
        text = p.read_text()
        text = text.replace('monkeypatch.setattr(\n        ko2, "EP133Client"', 'monkeypatch.setattr(\n        "cli.cmd_transfer.EP133Client"')
        text = text.replace('monkeypatch.setattr(ko2, "EP133Client"', 'monkeypatch.setattr("cli.cmd_transfer.EP133Client"')
        text = text.replace('ko2.cmd_put', 'cli.cmd_transfer.cmd_put')
        p.write_text(text)

if __name__ == "__main__":
    fix()
