import time
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QByteArray, QPoint, Qt, QUrl, Signal
from PySide6.QtGui import QPixmap, QMouseEvent, QPainter, QPainterPath, QPen, QColor, QAction
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSlider, QStyle, QStyleOptionSlider,
                               QVBoxLayout, QWidget, QGridLayout, QMenu)

from core.i18n import tr
from src.icons import get_svg_icon
from src.pages.shared import format_count


class ImageCache:
    _instance: Optional['ImageCache'] = None

    @classmethod
    def instance(cls) -> 'ImageCache':
        if cls._instance is None:
            cls._instance = ImageCache()
        return cls._instance

    def __init__(self):
        self.nam = QNetworkAccessManager()
        self.nam.finished.connect(self._on_finished)
        self.cache: Dict[str, QPixmap] = {}
        self.pending: Dict[str, List[Callable]] = {}

    def get(self, url: str, cb: Callable[[QPixmap], None]):
        if not url:
            cb(QPixmap())
            return
        if url in self.cache:
            cb(self.cache[url])
            return
        if url in self.pending:
            self.pending[url].append(cb)
            return
        self.pending[url] = [cb]
        self.nam.get(QNetworkRequest(QUrl(url)))

    def invalidate(self, url: str):
        self.cache.pop(url, None)
        self.pending.pop(url, None)

    def clear(self):
        self.cache.clear()
        self.pending.clear()

    def _on_finished(self, reply):
        url = reply.url().toString()
        data: QByteArray = reply.readAll()
        pix = QPixmap()
        if pix.loadFromData(data):
            self.cache[url] = pix
        else:
            pix = QPixmap()
        for cb in self.pending.pop(url, []):
            try:
                cb(pix)
            except RuntimeError:
                pass
        reply.deleteLater()


class ClickableSlider(QSlider):
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            groove = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self)
            handle = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self)
            if groove.contains(event.position().toPoint()):
                sliderLength = handle.width()
                sliderMin = groove.x()
                sliderMax = groove.right() - sliderLength + 1
                pos = event.position().x()
                pos = max(sliderMin, min(sliderMax, pos))
                val = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), int(pos - sliderMin), sliderMax - sliderMin, opt.upsideDown)
                self.setValue(val)
                self.sliderMoved.emit(val)
                event.accept()
                return
        super().mousePressEvent(event)


class ResponsiveGrid(QWidget):
    def __init__(self, parent=None, max_cols: int = 0):
        super().__init__(parent)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(16)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._items = []
        self._cols = 0
        self._max_cols = max_cols

    def add_widget(self, w):
        self._items.append(w)
        self._relayout()

    def clear(self):
        for w in self._items:
            w.setParent(None)
            w.deleteLater()
        self._items.clear()
        while self.grid.count():
            self.grid.takeAt(0)
        self._cols = 0

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    def _relayout(self):
        if not self._items:
            return
        item_width = 180
        if self._items:
            item_width = self._items[0].width() or 180
        w = self.width()
        if w <= 0:
            return
        new_cols = max(1, (w + 16) // (item_width + 16))
        if self._max_cols > 0:
            new_cols = min(new_cols, self._max_cols)
        if new_cols != self._cols or self.grid.count() != len(self._items):
            self._cols = new_cols
            while self.grid.count():
                self.grid.takeAt(0)
            for i, item in enumerate(self._items):
                row = i // self._cols
                col = i % self._cols
                self.grid.addWidget(item, row, col)


class CoverImage(QLabel):
    def __init__(self, size: int = 160, radius: int = 6, border_color: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"background:#1a1a28; border-radius:{radius}px; color:#4a4a6a;")
        self.setText('')
        self._url = ''
        self._radius = radius
        self._border_color = border_color

    def load(self, url: str, force: bool = False):
        if not url:
            return
        if not force and url == self._url:
            return
        self._url = url
        self.setPixmap(QPixmap())
        request_url = url
        if force:
            sep = '&' if '?' in url else '?'
            request_url = f"{url}{sep}_t={int(time.time() * 1000)}"

        def apply(pix: QPixmap):
            if pix.isNull():
                return
            target = self.size()
            scaled = pix.scaled(target, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                Qt.TransformationMode.SmoothTransformation)
            x = max(0, (scaled.width() - target.width()) // 2)
            y = max(0, (scaled.height() - target.height()) // 2)
            cropped = scaled.copy(x, y, target.width(), target.height())
            rounded = QPixmap(target)
            rounded.fill(Qt.GlobalColor.transparent)
            painter = QPainter(rounded)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            path = QPainterPath()
            if self._radius >= target.width() / 2:
                path.addEllipse(0, 0, target.width(), target.height())
            else:
                path.addRoundedRect(0, 0, target.width(), target.height(), self._radius, self._radius)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, cropped)
            if self._border_color:
                painter.setClipping(False)
                pen = QPen(QColor(self._border_color))
                pen.setWidth(2)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                if self._radius >= target.width() / 2:
                    painter.drawEllipse(1, 1, target.width() - 2, target.height() - 2)
                else:
                    painter.drawRoundedRect(1, 1, target.width() - 2, target.height() - 2, self._radius, self._radius)
            painter.end()
            self.setPixmap(rounded)

        ImageCache.instance().get(request_url, apply)


class TrackCard(QFrame):
    play_requested = Signal(dict)
    edit_requested = Signal(dict)
    delete_requested = Signal(dict)
    clicked = Signal(str)

    def __init__(self, track: Dict, api, parent=None):
        super().__init__(parent)
        self.track = track
        self.api = api
        self.setObjectName('TrackCard')
        self.setFixedSize(180, 280)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(6)

        cover = CoverImage(160, 8)
        cover.load(api.cover_url(track))
        v.addWidget(cover)

        title = QLabel(track.get('title', ''))
        title.setObjectName('TrackTitle')
        title.setWordWrap(True)
        title.setFixedHeight(38)
        v.addWidget(title)

        artist_text = track.get('artist', '')
        if track.get('is_ai'):
            artist_text = f"{artist_text}{tr('track.ai_suffix')}"
        artist = QLabel(artist_text)
        artist.setObjectName('TrackArtist')
        v.addWidget(artist)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addStretch()
        play = QPushButton()
        play.setIcon(get_svg_icon('play', '#0b0b14', 18))
        play.setObjectName('CardPlayBtn')
        play.setFixedSize(34, 34)
        play.clicked.connect(lambda: self.play_requested.emit(self.track))
        btn_row.addWidget(play)
        v.addLayout(btn_row)

    def _show_context_menu(self, pos: QPoint):
        can_edit = False
        if self.api.user:
            is_owner = self.track.get('artist_id') == self.api.user.get('id')
            is_admin = self.api.user.get('is_admin', False)
            can_edit = is_owner or is_admin
        if not can_edit:
            return
        menu = QMenu(self)
        act_edit = QAction(tr('track.edit_menu'), self)
        act_edit.triggered.connect(lambda: self.edit_requested.emit(self.track))
        menu.addAction(act_edit)
        act_del = QAction(tr('track.delete_menu'), self)
        act_del.triggered.connect(lambda: self.delete_requested.emit(self.track))
        menu.addAction(act_del)
        menu.exec(self.mapToGlobal(pos))

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.track.get('id', ''))

    def mouseDoubleClickEvent(self, e):
        self.play_requested.emit(self.track)


class TrackRow(QFrame):
    play_requested = Signal(dict)
    remove_requested = Signal(dict)
    add_requested = Signal(dict)
    favorite_toggle_requested = Signal(dict)
    history_delete_requested = Signal(dict)
    edit_requested = Signal(dict)
    delete_requested = Signal(dict)
    clicked = Signal(str)

    def __init__(self, track: Dict, api, index: Optional[int] = None,
                 show_add: bool = False, show_remove: bool = False, show_fav: bool = True,
                 show_history_delete: bool = False, show_edit_delete: bool = True,
                 parent=None):
        super().__init__(parent)
        self.track = track
        self.api = api
        self.setObjectName('TrackRow')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(64)

        h = QHBoxLayout(self)
        h.setContentsMargins(10, 6, 10, 6)
        h.setSpacing(12)

        if index is not None:
            idx = QLabel(str(index))
            idx.setFixedWidth(24)
            idx.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            idx.setObjectName('TrackIndex')
            h.addWidget(idx)

        cover = CoverImage(40, 4)
        cover.load(api.cover_url(track))
        h.addWidget(cover)

        v = QVBoxLayout()
        v.setSpacing(2)
        v.setContentsMargins(0, 0, 0, 0)
        t = QLabel(track.get('title', ''))
        t.setObjectName('TrackRowTitle')
        v.addWidget(t)
        artist_text = track.get('artist', '')
        if track.get('is_ai'):
            artist_text = f"{artist_text}{tr('track.ai_suffix')}"
        a = QLabel(artist_text)
        a.setObjectName('TrackRowArtist')
        v.addWidget(a)
        h.addLayout(v, 1)

        plays_text = format_count(track.get('play_count', 0))
        plays_label = QLabel(plays_text)
        plays_label.setObjectName('TrackRowArtist')
        plays_label.setStyleSheet("margin-right: 10px;")
        h.addWidget(plays_label)

        can_edit = False
        if self.api.user:
            is_owner = self.track.get('artist_id') == self.api.user.get('id')
            is_admin = self.api.user.get('is_admin', False)
            can_edit = is_owner or is_admin

        play = QPushButton()
        play.setIcon(get_svg_icon('play', '#a8a8c0', 20))
        play.setObjectName('RowBtn')
        play.setFixedSize(36, 36)
        play.clicked.connect(lambda: self.play_requested.emit(self.track))
        h.addWidget(play)

        if show_fav:
            fav = QPushButton()
            fav.setIcon(get_svg_icon('heart', '#a8a8c0', 20))
            fav.setObjectName('RowBtn')
            fav.setFixedSize(36, 36)
            fav.clicked.connect(lambda: self.favorite_toggle_requested.emit(self.track))
            h.addWidget(fav)

        if show_add:
            add = QPushButton()
            add.setIcon(get_svg_icon('add', '#a8a8c0', 20))
            add.setObjectName('RowBtn')
            add.setFixedSize(36, 36)
            add.clicked.connect(lambda: self.add_requested.emit(self.track))
            h.addWidget(add)

        if can_edit and show_edit_delete:
            edit_btn = QPushButton()
            edit_btn.setIcon(get_svg_icon('settings', '#a8a8c0', 20))
            edit_btn.setObjectName('RowBtn')
            edit_btn.setFixedSize(36, 36)
            edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.track))
            h.addWidget(edit_btn)

            del_btn = QPushButton()
            del_btn.setIcon(get_svg_icon('trash', '#ff6b6b', 20))
            del_btn.setObjectName('RowBtnDanger')
            del_btn.setFixedSize(36, 36)
            del_btn.clicked.connect(lambda: self.delete_requested.emit(self.track))
            h.addWidget(del_btn)

        if show_remove:
            rm = QPushButton()
            rm.setIcon(get_svg_icon('close', '#ff6b6b', 20))
            rm.setObjectName('RowBtnDanger')
            rm.setFixedSize(36, 36)
            rm.clicked.connect(lambda: self.remove_requested.emit(self.track))
            h.addWidget(rm)

        if show_history_delete:
            rm = QPushButton()
            rm.setIcon(get_svg_icon('close', '#ff6b6b', 20))
            rm.setObjectName('RowBtnDanger')
            rm.setFixedSize(36, 36)
            rm.clicked.connect(lambda: self.history_delete_requested.emit(self.track))
            h.addWidget(rm)

    def set_active(self, active: bool):
        if active:
            self.setStyleSheet("QFrame { background: #1a1a28; border-left: 4px solid #00d4ff; }")
        else:
            self.setStyleSheet("")

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if not self.childAt(e.position().toPoint()):
                self.clicked.emit(self.track.get('id', ''))

    def mouseDoubleClickEvent(self, e):
        self.play_requested.emit(self.track)


class PlaylistCard(QFrame):
    open_requested = Signal(str)

    def __init__(self, playlist: Dict, api, parent=None):
        super().__init__(parent)
        self.playlist = playlist
        self.api = api
        self.setObjectName('PlaylistCard')
        self.setFixedSize(220, 140)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(4)

        name = QLabel(playlist.get('name', ''))
        name.setObjectName('PlaylistName')
        name.setWordWrap(True)
        v.addWidget(name)

        owner = QLabel(playlist.get('owner', ''))
        owner.setObjectName('PlaylistMeta')
        v.addWidget(owner)

        count = QLabel(tr('playlist.tracks_count', count=playlist.get('track_count', 0)))
        count.setObjectName('PlaylistMeta')
        v.addWidget(count)

        v.addStretch()

        vis = QLabel(tr('playlist.public_badge') if playlist.get('is_public') else tr('playlist.private_badge'))
        vis.setObjectName('PlaylistVisibility')
        v.addWidget(vis)

    def mouseDoubleClickEvent(self, e):
        self.open_requested.emit(self.playlist.get('id', ''))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.open_requested.emit(self.playlist.get('id', ''))


class SectionWidget(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        self.title_label = QLabel(title)
        self.title_label.setObjectName('SectionTitle')
        v.addWidget(self.title_label)

        self.grid = ResponsiveGrid()
        v.addWidget(self.grid)

    def set_title(self, title: str):
        self.title_label.setText(title)

    def set_tracks(self, tracks: List[Dict], api, on_play, on_edit=None, on_delete=None, on_click=None):
        self.grid.clear()
        for t in tracks:
            card = TrackCard(t, api)
            card.play_requested.connect(on_play)
            if on_edit:
                card.edit_requested.connect(on_edit)
            if on_delete:
                card.delete_requested.connect(on_delete)
            if on_click:
                card.clicked.connect(on_click)
            self.grid.add_widget(card)