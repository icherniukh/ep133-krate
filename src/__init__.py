# Re-export src/ packages so that `import core` works from the repo root.
import sys
from pathlib import Path

_src = str(Path(__file__).resolve().parent / "src")  # pylint: disable=invalid-name
if _src not in sys.path:
    sys.path.insert(0, _src)
