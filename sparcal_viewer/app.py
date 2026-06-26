"""Application entry point."""
from __future__ import annotations

import sys

from PySide6 import QtWidgets

from .main_window import MainWindow


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QtWidgets.QApplication(argv)
    app.setApplicationName("SPARCAL Spatial-SNV Viewer")
    win = MainWindow()
    win.show()
    # optional: pass a .config path on the command line to auto-open
    for arg in argv[1:]:
        if arg.lower().endswith((".config", ".yaml", ".yml")):
            win.open_config(arg)
            break
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
