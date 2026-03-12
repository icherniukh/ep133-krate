#!/usr/bin/env python3
"""
KO2 - EP-133 KO-II Command Line Tool Entrypoint
"""
import sys
from pathlib import Path

# Add src to sys.path if not running from an installed package
_src = str(Path(__file__).resolve().parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from cli.cli_main import main

if __name__ == "__main__":
    sys.exit(main())
