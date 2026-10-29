"""Compare two OTIO files: `python tools/otio_compare.py LEFT RIGHT`."""
import sys
import types
from pathlib import Path

CLIENT_DIR = Path(__file__).resolve().parent.parent / "client"
PACKAGE_DIR = CLIENT_DIR / "ayon_editorial"

# The real `ayon_editorial/__init__` imports ayon_core; a bare package
# object with the right `__path__` is enough (see tests/conftest.py).
if "ayon_editorial" not in sys.modules:
    package = types.ModuleType("ayon_editorial")
    package.__path__ = [str(PACKAGE_DIR)]
    sys.modules["ayon_editorial"] = package

from ayon_editorial.otio.compare import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
