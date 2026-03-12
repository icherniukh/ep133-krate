from pathlib import Path

def patch_file(p: Path):
    text = p.read_text()
    
    # We must replace instances of `ko2.cmd_XY` with `cli.cmd_Z.cmd_XY`.
    text = text.replace("ko2.cmd_move", "cli.cmd_slots.cmd_move")
    text = text.replace("ko2.cmd_copy", "cli.cmd_slots.cmd_copy")
    text = text.replace("ko2.cmd_delete", "cli.cmd_slots.cmd_delete")
    text = text.replace("ko2.cmd_rename", "cli.cmd_slots.cmd_rename")
    text = text.replace("ko2.cmd_squash", "cli.cmd_slots.cmd_squash")
    
    text = text.replace("ko2.cmd_get", "cli.cmd_transfer.cmd_get")
    text = text.replace("ko2.cmd_put", "cli.cmd_transfer.cmd_put")
    
    text = text.replace("ko2.cmd_optimize", "cli.cmd_audio.cmd_optimize")
    text = text.replace("ko2.cmd_fingerprint", "cli.cmd_audio.cmd_fingerprint")
    text = text.replace("ko2.cmd_audition", "cli.cmd_audio.cmd_audition")
    
    text = text.replace("ko2.SlotEmptyError", "SlotEmptyError")
    text = text.replace("ko2.EP133Client", "EP133Client")
    text = text.replace("ko2.optimize_sample", "optimize_sample")
    text = text.replace("ko2.backup_copy", "backup_copy")
    
    # monkeypatches:
    # monkeypatch.setattr(ko2, "EP133Client", ...)
    # Actually, if we just look at what the test patches, we can replace the module it patches.
    # For cmd_move, cmd_copy, cmd_delete, cmd_rename, cmd_squash: cli.cmd_slots
    # For cmd_get, cmd_put: cli.cmd_transfer
    # Since tests are usually focused, we replace monkeypatch.setattr(ko2, ...) with the specific module.
    
    # Let's handle imports:
    if "import ko2" in text or "from ko2 import" in text:
        text = text.replace("import ko2\n", "import cli.cmd_transfer\nimport cli.cmd_slots\nimport cli.cmd_audio\nimport cli.cmd_system\nimport core.ops\nimport cli.helpers\nfrom ko2_client import EP133Client, SlotEmptyError\nfrom core.ops import backup_copy, optimize_sample\n")
        text = text.replace("import ko2.py", "import cli.cli_main as ko2_py") # for test_tui_cli_integration
    
    if p.name == "test_cli_output.py":
        text = text.replace('monkeypatch.setattr(ko2, "EP133Client"', 'monkeypatch.setattr("ko2_client.EP133Client"')
        text = text.replace('monkeypatch.setattr(ko2, "backup_copy"', 'monkeypatch.setattr(cli.cmd_slots, "backup_copy"')
        text = text.replace('monkeypatch.setattr(\n        ko2, "optimize_sample"', 'monkeypatch.setattr(\n        cli.cmd_audio, "optimize_sample"')
    elif p.name == "test_move_copy.py":
        text = text.replace('monkeypatch.setattr(ko2, "EP133Client"', 'monkeypatch.setattr(cli.cmd_slots, "EP133Client"')
        text = text.replace('monkeypatch.setattr(ko2, "backup_copy"', 'monkeypatch.setattr(cli.cmd_slots, "backup_copy"')
    elif p.name == "test_optimize.py":
        text = text.replace('monkeypatch.setattr(ko2, "EP133Client"', 'monkeypatch.setattr(cli.cmd_audio, "EP133Client"')
        text = text.replace('monkeypatch.setattr(ko2, "backup_copy"', 'monkeypatch.setattr(cli.cmd_audio, "backup_copy"')
    elif p.name == "test_upload_recovery.py":
        text = text.replace('monkeypatch.setattr(ko2, "EP133Client"', 'monkeypatch.setattr(cli.cmd_transfer, "EP133Client"')
    elif p.name == "test_fingerprint_cli.py":
        text = text.replace('monkeypatch.setattr(ko2, "EP133Client"', 'monkeypatch.setattr(cli.cmd_audio, "EP133Client"')
    elif p.name == "test_squash.py":
        text = text.replace('monkeypatch.setattr(ko2, "EP133Client"', 'monkeypatch.setattr(cli.cmd_slots, "EP133Client"')
        text = text.replace('monkeypatch.setattr(ko2, "_squash_process_with_view"', 'monkeypatch.setattr(cli.cmd_slots, "_squash_process_with_view"')
    elif p.name == "test_tui_cli_integration.py":
        text = text.replace('import ko2', 'import cli.cli_main as ko2')

    p.write_text(text)

for f in Path("tests/unit").glob("*.py"):
    patch_file(f)
for f in Path("tests/e2e").glob("*.py"):
    patch_file(f)
