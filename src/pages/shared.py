from contextlib import contextmanager

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from core.i18n import tr


@contextmanager
def apply_busy_cursor():
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        yield
    finally:
        QApplication.restoreOverrideCursor()


def fmt_time(ms: int) -> str:
    if not ms or ms < 0:
        return '0:00'
    s = ms // 1000
    return f'{s // 60}:{s % 60:02d}'


def show_error(parent, message, title: str = None):
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title if title is not None else tr('common.error'))
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(str(message))
    box.exec()


def show_info(parent, message, title: str = None):
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(title if title is not None else tr('common.info'))
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(str(message))
    box.exec()


def ask_yes_no(parent, title: str, message: str) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(str(message))
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    return box.exec() == QMessageBox.StandardButton.Yes