import re
from pathlib import Path

def patch_file(p: Path):
    text = p.read_text()
    
    # In test_optimize.py
    text = text.replace('monkeypatch.setattr(\n        ko2, "optimize_sample"', 'monkeypatch.setattr(\n        cli.cmd_audio, "optimize_sample"')
    text = text.replace('monkeypatch.setattr(ko2, "optimize_sample"', 'monkeypatch.setattr(cli.cmd_audio, "optimize_sample"')
    text = text.replace('monkeypatch.setattr(ko2, "backup_copy"', 'monkeypatch.setattr(cli.cmd_audio, "backup_copy")')

    # In test_squash.py
    if p.name == "test_squash.py":
        text = text.replace('monkeypatch.setattr(ko2, "backup_copy"', 'monkeypatch.setattr(cli.cmd_slots, "backup_copy"')
        text = text.replace('monkeypatch.setattr(ko2, "_squash_process_with_view"', 'monkeypatch.setattr(cli.cmd_slots, "_squash_process_with_view"')
    
    # In test_tui_cli_integration.py
    if p.name == "test_tui_cli_integration.py":
        if "import ko2" not in text:
            # We had renamed it to import cli.cli_main as ko2, but let's make sure it works
            text = text.replace("import cli.cli_main as ko2", "import cli.cli_main as ko2")
            
    # In test_upload_recovery.py
    if p.name == "test_upload_recovery.py":
        text = text.replace('monkeypatch.setattr(ko2, "EP133Client"', 'monkeypatch.setattr(cli.cmd_transfer, "EP133Client"')

    # General fallback for any ko2.
    text = text.replace('ko2.backup_copy', 'core.ops.backup_copy')
    text = text.replace('ko2.optimize_sample', 'core.ops.optimize_sample')
    
    # Just to be safe, any monkeypatch.setattr(ko2, ...) that might be left:
    # We replace based on function name logic.
    
    p.write_text(text)

for f in Path("tests/unit").glob("*.py"):
    patch_file(f)
for f in Path("tests/e2e").glob("*.py"):
    patch_file(f)
