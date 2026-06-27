import os
import sys

# Ensure the parent directory is on sys.path so absolute imports work
# both when run as `python -m sparcal_viewer` and when frozen by PyInstaller.
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from sparcal_viewer.app import main

if __name__ == "__main__":
    raise SystemExit(main())
