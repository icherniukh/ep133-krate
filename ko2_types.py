# Compatibility shim — makes `import ko2_types` resolve to `core.types`
import sys
from pathlib import Path

_src = str(Path(__file__).resolve().parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from core import types as _real  # noqa: E402
sys.modules[__name__] = _real
