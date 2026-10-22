from contextlib import contextmanager
from PySide6.QtCore import Qt, QThread, Signal
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


def format_count(n: int) -> str:
    if n is None:
        return "0"
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


class ApiThread(QThread):
    done = Signal(object)
    failed = Signal(str)
    _active_threads = set()

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self._cancelled = False

    def start(self, *args, **kwargs):
        ApiThread._active_threads.add(self)
        self.finished.connect(self._cleanup)
        super().start(*args, **kwargs)

    def cancel(self):
        self._cancelled = True

    def _cleanup(self):
        self.wait(1000)
        ApiThread._active_threads.discard(self)
        self.deleteLater()

    def run(self):
        if self._cancelled:
            return
        try:
            res = self.func(*self.args, **self.kwargs)
            if not self._cancelled:
                self.done.emit(res)
        except Exception as e:
            if not self._cancelled:
                self.failed.emit(str(e))


def cancel_all_threads():
    for t in list(ApiThread._active_threads):
        t.cancel()


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