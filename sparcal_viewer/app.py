"""Application entry point."""
from __future__ import annotations

import os
import shutil
import sys

from PySide6 import QtCore, QtWidgets

from .main_window import MainWindow

# Name of the study folder shipped with the app (folder + "<name>.config" inside).
DEFAULT_STUDY = "DCIS_2_SPARCAL"


def _bundled_study_dir() -> str | None:
    """Locate the default study folder shipped alongside the app.

    Search order: the PyInstaller bundle (``sys._MEIPASS``), next to the
    executable / .app, then the repo checkout (running from source). Returns the
    folder path that actually contains ``<DEFAULT_STUDY>.config``, or None."""
    candidates = []
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        candidates.append(os.path.join(base, DEFAULT_STUDY))
        candidates.append(os.path.join(os.path.dirname(sys.executable), DEFAULT_STUDY))
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(repo, DEFAULT_STUDY))
    for c in candidates:
        if os.path.isfile(os.path.join(c, f"{DEFAULT_STUDY}.config")):
            return c
    return None


def default_config_path() -> str | None:
    """Resolve the .config to open on launch when none is given on the command line.

    ``SPARCAL_DEFAULT_CONFIG`` overrides everything. Otherwise the bundled study is
    used; for a frozen (read-only) app it is copied once into a writable per-user
    data directory so edits — regions, groups, centers — persist across runs."""
    env = os.environ.get("SPARCAL_DEFAULT_CONFIG")
    if env and os.path.isfile(env):
        return env

    src = _bundled_study_dir()
    if not src:
        return None
    cfg_name = f"{DEFAULT_STUDY}.config"

    # Running from a writable source checkout: open it in place.
    if not getattr(sys, "frozen", False) and os.access(src, os.W_OK):
        return os.path.join(src, cfg_name)

    # Frozen app: copy the bundled study to a writable location on first launch.
    dest_root = QtCore.QStandardPaths.writableLocation(
        QtCore.QStandardPaths.AppDataLocation) or os.path.expanduser("~")
    dest = os.path.join(dest_root, DEFAULT_STUDY)
    dest_cfg = os.path.join(dest, cfg_name)
    if not os.path.isfile(dest_cfg):
        os.makedirs(dest_root, exist_ok=True)
        shutil.copytree(src, dest, dirs_exist_ok=True)
    return dest_cfg


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QtWidgets.QApplication(argv)
    app.setApplicationName("SPARCAL Spatial-SNV Viewer")
    win = MainWindow()
    win.show()

    # A .config path on the command line wins; otherwise open the bundled default.
    opened = False
    for arg in argv[1:]:
        if arg.lower().endswith((".config", ".yaml", ".yml")):
            win.open_config(arg)
            opened = True
            break
    if not opened:
        dc = default_config_path()
        if dc:
            win.open_config(dc)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
