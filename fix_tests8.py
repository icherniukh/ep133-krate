from pathlib import Path
import re

def fix():
    # 1. test_audition.py
    p = Path("tests/unit/test_audition.py")
    if p.exists():
        text = p.read_text()
        text = text.replace('patch("EP133Client"', 'patch("cli.cmd_audio.EP133Client"')
        p.write_text(text)
        
if __name__ == "__main__":
    fix()
