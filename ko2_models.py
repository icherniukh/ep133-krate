# Compatibility shim — makes `import ko2_models` resolve to `core.models`
import sys
from pathlib import Path

_src = str(Path(__file__).resolve().parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from core import models as _real  # noqa: E402
sys.modules[__name__] = _real
