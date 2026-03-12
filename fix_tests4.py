from pathlib import Path
import re

def fix():
    # 1. test_cli_output.py
    p = Path("tests/unit/test_cli_output.py")
    if p.exists():
        text = p.read_text()
        text = text.replace('monkeypatch.setattr("ko2_client.EP133Client"', r'''
        monkeypatch.setattr(cli.cmd_slots, "EP133Client", lambda *a, **k: client)
        monkeypatch.setattr(cli.cmd_transfer, "EP133Client", lambda *a, **k: client)
        monkeypatch.setattr(cli.cmd_audio, "EP133Client", lambda *a, **k: client)
        # '''.strip())
        text = text.replace('monkeypatch.setattr("core.client.EP133Client"', r'''
        monkeypatch.setattr(cli.cmd_slots, "EP133Client", lambda *a, **k: client)
        monkeypatch.setattr(cli.cmd_transfer, "EP133Client", lambda *a, **k: client)
        monkeypatch.setattr(cli.cmd_audio, "EP133Client", lambda *a, **k: client)
        # '''.strip())
        text = text.replace('monkeypatch.setattr(ko2_client, "EP133Client"', r'''
        monkeypatch.setattr(cli.cmd_slots, "EP133Client", lambda *a, **k: client)
        monkeypatch.setattr(cli.cmd_transfer, "EP133Client", lambda *a, **k: client)
        monkeypatch.setattr(cli.cmd_audio, "EP133Client", lambda *a, **k: client)
        # '''.strip())
        p.write_text(text)

    # 2. test_upload_recovery.py
    p = Path("tests/unit/test_upload_recovery.py")
    if p.exists():
        text = p.read_text()
        text = text.replace('import ko2', 'import cli.cmd_transfer as ko2')
        text = text.replace('ko2.', 'cli.cmd_transfer.')
        p.write_text(text)

    # 3. test_tui_cli_integration.py
    p = Path("tests/unit/test_tui_cli_integration.py")
    if p.exists():
        text = p.read_text()
        text = text.replace('import ko2\n', 'import cli.cli_main as ko2\n')
        # If there are still 'ko2.main()' calls, they will now refer to cli.cli_main.main!
        p.write_text(text)

    # 4. test_move_copy.py
    p = Path("tests/unit/test_move_copy.py")
    if p.exists():
        text = p.read_text()
        # FakeClient missing info() method?
        if "def info(" not in text:
            # Add a fake info method
            info_method = """
    def info(self, slot, include_size=False):
        if slot not in self._sounds:
            raise SlotEmptyError(f"slot {slot} empty")
        e = self._sounds[slot]
        return SimpleNamespace(name=e.get("name"), size_bytes=e.get("size"))
"""
            text = text.replace('def get(self, slot, path: Path):', info_method + '\n    def get(self, slot, path: Path):')
            text = text.replace('from ko2_display import SilentView', 'from ko2_display import SilentView\nfrom ko2_client import SlotEmptyError')
        p.write_text(text)
        
if __name__ == "__main__":
    fix()
