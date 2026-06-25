from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from image_translator.gui.main_window import MainWindow


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        if isinstance(existing, QApplication):
            return existing
        raise RuntimeError("An incompatible Qt application instance already exists.")
    return QApplication(list(argv) if argv is not None else sys.argv)


def main(argv: Sequence[str] | None = None) -> int:
    application = create_application(argv)
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
