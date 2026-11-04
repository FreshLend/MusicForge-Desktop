from urllib.parse import urlparse

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QPainter, QPainterPath
from PySide6.QtWidgets import (QDialog, QFormLayout, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from core.api import ApiClient
from core.i18n import Translator, tr
from src.icons import get_svg_icon
from src.pages.shared import ask_yes_no
from src.player import Player
from src.radio import RadioStations
from src.widgets import ImageCache


def _normalize_stream_url(url: str) -> str:
    if not url:
        return ''
    url = url.strip()
    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'https://' + url
    return url


def _origin(url: str) -> str:
    try:
        parsed = urlparse(_normalize_stream_url(url))
        if not parsed.hostname:
            return ''
        scheme = parsed.scheme or 'https'
        host = parsed.hostname
        port = parsed.port
        if port and not ((scheme == 'https' and port == 443) or
                         (scheme == 'http' and port == 80)):
            return f'{scheme}://{host}:{port}'
        return f'{scheme}://{host}'
    except Exception:
        return ''


def _favicon_url(stream_url: str) -> str:
    origin = _origin(stream_url)
    if not origin:
        return ''
    return f'{origin}/favicon.ico'


def _rounded_icon(pix: QPixmap, size: int, radius: int) -> QPixmap:
    target = pix.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation)
    x = max(0, (target.width() - size) // 2)
    y = max(0, (target.height() - size) // 2)
    cropped = target.copy(x, y, size, size)
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, cropped)
    painter.end()
    return result


class AddStationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('radio.add_title'))
        self.setMinimumWidth(480)

        self._name = ''
        self._url = ''

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        form = QFormLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(tr('radio.name_placeholder'))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(tr('radio.url_placeholder'))
        form.addRow(tr('radio.name_label'), self.name_input)
        form.addRow(tr('radio.url_label'), self.url_input)
        v.addLayout(form)

        self.status = QLabel('')
        self.status.setObjectName('StatusText')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        v.addWidget(self.status)

        row = QHBoxLayout()
        row.addStretch()
        cancel_btn = QPushButton(tr('common.cancel'))
        cancel_btn.setObjectName('GhostBtn')
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(cancel_btn)
        ok_btn = QPushButton(tr('common.save'))
        ok_btn.setObjectName('PrimaryBtn')
        ok_btn.clicked.connect(self._validate)
        row.addWidget(ok_btn)
        v.addLayout(row)

    def _validate(self):
        name = self.name_input.text().strip()
        url = self.url_input.text().strip()
        if not name or not url:
            self.status.setText(tr('radio.fill_required'))
            return
        url = _normalize_stream_url(url)
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.hostname:
                raise ValueError()
        except Exception:
            self.status.setText(tr('radio.invalid_url'))
            return
        self._name = name
        self._url = url
        self.accept()

    def get_name(self) -> str:
        return self._name

    def get_url(self) -> str:
        return self._url


class RadioRow(QFrame):
    play_requested = Signal(dict)
    delete_requested = Signal(dict)

    ICON_SIZE = 48
    ICON_RADIUS = 6

    def __init__(self, station: dict, parent=None):
        super().__init__(parent)
        self.station = station
        self.setObjectName('TrackRow')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(64)

        h = QHBoxLayout(self)
        h.setContentsMargins(10, 6, 10, 6)
        h.setSpacing(12)

        self.icon = QLabel()
        self.icon.setFixedSize(self.ICON_SIZE, self.ICON_SIZE)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setStyleSheet(
            f"background:#1a1a28; border-radius:{self.ICON_RADIUS}px;")
        self._set_placeholder()
        h.addWidget(self.icon)

        fav = _favicon_url(station['url'])
        if fav:
            def apply(pix: QPixmap):
                if pix.isNull():
                    return
                self.icon.setPixmap(
                    _rounded_icon(pix, self.ICON_SIZE, self.ICON_RADIUS))
            ImageCache.instance().get(fav, apply)

        v = QVBoxLayout()
        v.setSpacing(2)
        v.setContentsMargins(0, 0, 0, 0)

        name = QLabel(station['name'])
        name.setObjectName('TrackRowTitle')
        v.addWidget(name)

        url_label = QLabel(station['url'])
        url_label.setObjectName('TrackRowArtist')
        v.addWidget(url_label)
        h.addLayout(v, 1)

        play_btn = QPushButton()
        play_btn.setIcon(get_svg_icon('play', '#a8a8c0', 20))
        play_btn.setObjectName('RowBtn')
        play_btn.setFixedSize(36, 36)
        play_btn.clicked.connect(self._emit_play)
        h.addWidget(play_btn)

        del_btn = QPushButton()
        del_btn.setIcon(get_svg_icon('trash', '#ff6b6b', 20))
        del_btn.setObjectName('RowBtnDanger')
        del_btn.setFixedSize(36, 36)
        del_btn.clicked.connect(
            lambda: self.delete_requested.emit(self.station))
        h.addWidget(del_btn)

    def _emit_play(self):
        self.play_requested.emit(self.station)

    def _set_placeholder(self):
        self.icon.setPixmap(
            get_svg_icon('radio', '#4a4a6a', 28).pixmap(28, 28))

    def set_active(self, active: bool):
        if active:
            self.setStyleSheet(
                "QFrame { background: #1a1a28; "
                "border-left: 4px solid #00d4ff; }")
        else:
            self.setStyleSheet("")

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if not self.childAt(e.position().toPoint()):
                self._emit_play()


class RadioPage(QWidget):
    def __init__(self, api: ApiClient, player: Player, main, parent=None):
        super().__init__(parent)
        self.api = api
        self.player = player
        self.main = main
        self.stations = RadioStations.instance()
        self._rows = []

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        header = QHBoxLayout()
        self.title_label = QLabel(tr('radio.title'))
        self.title_label.setObjectName('PageTitle')
        header.addWidget(self.title_label)
        header.addStretch()

        self.add_btn = QPushButton(tr('radio.add'))
        self.add_btn.setObjectName('PrimaryBtn')
        self.add_btn.clicked.connect(self._on_add)
        header.addWidget(self.add_btn)
        v.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.inner = QWidget()
        self.list_layout = QVBoxLayout(self.inner)
        self.list_layout.setSpacing(8)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.inner)
        v.addWidget(self.scroll, 1)

        self.player.track_changed.connect(self._on_track_changed)
        Translator.instance().language_changed.connect(self.retranslate)

        self._reload()

    def retranslate(self):
        self.title_label.setText(tr('radio.title'))
        self.add_btn.setText(tr('radio.add'))
        self._reload()

    def refresh(self):
        self._update_active_states()

    def _reload(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._rows.clear()

        stations = self.stations.list()
        if not stations:
            empty = QLabel(tr('radio.empty'))
            empty.setObjectName('StatusText')
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("padding: 40px; color: #6e6e8a;")
            empty.setWordWrap(True)
            self.list_layout.addWidget(empty)
        else:
            for station in stations:
                row = RadioRow(station)
                row.play_requested.connect(self._on_play)
                row.delete_requested.connect(self._on_delete)
                self.list_layout.addWidget(row)
                self._rows.append(row)

        self._update_active_states()

    def _update_active_states(self, track=None):
        if track is None:
            track = self.player.current_track()
        current_url = None
        if track and track.get('is_radio'):
            current_url = track.get('audio_url')
        for row in self._rows:
            row.set_active(row.station['url'] == current_url)

    def _on_track_changed(self, track):
        self._update_active_states(track)

    def _on_add(self):
        dlg = AddStationDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.stations.add(dlg.get_name(), dlg.get_url())
            self._reload()

    def _on_play(self, station: dict):
        self.player.play_stream(station['name'], station['url'],
                                _favicon_url(station['url']))
        self._update_active_states()

    def _on_delete(self, station: dict):
        if not ask_yes_no(
                self, tr('radio.delete_title'),
                tr('radio.delete_confirm', name=station['name'])):
            return
        self.stations.remove(station['url'])
        self._reload()