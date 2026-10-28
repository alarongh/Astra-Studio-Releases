from __future__ import annotations

_qapplication = None


def pytest_sessionstart(session) -> None:
    """Start one widget-capable Qt application before any core-only Qt tests.

    A QCoreApplication cannot be upgraded to QApplication later in the same
    process.  The full suite used to create QCoreApplication first and
    then terminate natively when the caption regression constructed a widget.
    """
    if session.config.option.collectonly:
        return

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return

    global _qapplication
    _qapplication = QApplication.instance() or QApplication([])
    if not isinstance(_qapplication, QApplication):
        raise RuntimeError("Acceptance requires QApplication before Qt runtime tests")
    _qapplication.setQuitOnLastWindowClosed(False)
