from pathlib import Path
import re

def fix():
    # 1. test_audition.py
    # Change from ko2 import cmd_audition -> from cli.cmd_audio import cmd_audition
    p = Path("tests/unit/test_audition.py")
    if p.exists():
        text = p.read_text()
        text = text.replace("from ko2 import cmd_audition", "from cli.cmd_audio import cmd_audition")
        p.write_text(text)

    # 2. test_tui_cli_integration.py
    # Replace ko2 with cli_main as ko2
    p = Path("tests/unit/test_tui_cli_integration.py")
    if p.exists():
        text = p.read_text()
        text = text.replace('import ko2.py', 'import cli.cli_main as ko2_py')
        if 'import ko2' in text and 'import cli.cli_main as ko2' not in text:
            text = text.replace('import ko2', 'import cli.cli_main as ko2')
        p.write_text(text)

    # 3. test_upload_recovery.py
    p = Path("tests/unit/test_upload_recovery.py")
    if p.exists():
        text = p.read_text()
        if 'import ko2\n' in text:
            text = text.replace('import ko2\n', 'import cli.cmd_transfer as ko2\n')
        if 'import ko2' in text and 'import cli.cmd_transfer as ko2' not in text:
            text = text.replace('import ko2', 'import cli.cmd_transfer as ko2')
        p.write_text(text)

    # 4. Patching backup_copy globally in all tests
    # If a test patches cli.cmd_XYZ.backup_copy, it should patch core.ops.backup_copy Because move_slot/copy_slot are in core.ops and import backup_copy there.
    for p in Path("tests/unit").glob("*.py"):
        text = p.read_text()
        text = text.replace('monkeypatch.setattr(cli.cmd_slots, "backup_copy"', 'monkeypatch.setattr("core.ops.backup_copy"')
        text = text.replace('monkeypatch.setattr(cli.cmd_audio, "backup_copy"', 'monkeypatch.setattr("core.ops.backup_copy"')
        text = text.replace('monkeypatch.setattr(cli.cmd_transfer, "backup_copy"', 'monkeypatch.setattr("core.ops.backup_copy"')
        p.write_text(text)

        
if __name__ == "__main__":
    fix()
