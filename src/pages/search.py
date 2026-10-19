from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QTabWidget,
                               QVBoxLayout, QWidget)

from core.api import ApiClient
from core.i18n import Translator, tr
from src.pages.shared import apply_busy_cursor
from src.player import Player
from src.widgets import PlaylistCard, ResponsiveGrid, TrackCard


class SearchPage(QWidget):
    open_playlist = Signal(str)
    edit_track = Signal(dict)
    delete_track = Signal(dict)

    def __init__(self, api: ApiClient, player: Player, main, parent=None):
        super().__init__(parent)
        self.api = api
        self.player = player
        self.main = main

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        self.title_label = QLabel(tr('search.title'))
        self.title_label.setObjectName('PageTitle')
        v.addWidget(self.title_label)

        search_row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText(tr('search.placeholder'))
        self.query.returnPressed.connect(self._do_search)
        self.search_btn = QPushButton(tr('search.button'))
        self.search_btn.setObjectName('PrimaryBtn')
        self.search_btn.clicked.connect(self._do_search)
        search_row.addWidget(self.query, 1)
        search_row.addWidget(self.search_btn)
        v.addLayout(search_row)

        self.tabs = QTabWidget()
        self.tracks_widget = self._make_grid_container()
        self.playlists_widget = self._make_playlist_container()
        self.tabs.addTab(self.tracks_widget, tr('search.tab_tracks'))
        self.tabs.addTab(self.playlists_widget, tr('search.tab_playlists'))
        v.addWidget(self.tabs, 1)

        self.status = QLabel('')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setObjectName('StatusText')
        v.addWidget(self.status)

        Translator.instance().language_changed.connect(self.retranslate)

    def retranslate(self):
        self.title_label.setText(tr('search.title'))
        self.query.setPlaceholderText(tr('search.placeholder'))
        self.search_btn.setText(tr('search.button'))
        self.tabs.setTabText(0, tr('search.tab_tracks'))
        self.tabs.setTabText(1, tr('search.tab_playlists'))

    def _make_grid_container(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 0, 0)
        self.tracks_grid = ResponsiveGrid()
        iv.addWidget(self.tracks_grid)
        scroll.setWidget(inner)
        return scroll

    def _make_playlist_container(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 0, 0)
        self.playlists_grid = ResponsiveGrid()
        iv.addWidget(self.playlists_grid)
        scroll.setWidget(inner)
        return scroll

    def _do_search(self):
        q = self.query.text().strip()
        if not q:
            return
        with apply_busy_cursor():
            try:
                tracks = self.api.search(q, 'tracks', 50)
                playlists = self.api.search(q, 'playlists', 20)
            except Exception as e:
                self.status.setText(tr('search.error', message=str(e)))
                return

        self.tracks_grid.clear()
        for t in tracks:
            card = TrackCard(t, self.api)
            card.play_requested.connect(self.player.play_track)
            card.edit_requested.connect(self.edit_track.emit)
            card.delete_requested.connect(self.delete_track.emit)
            self.tracks_grid.add_widget(card)

        self.playlists_grid.clear()
        for pl in playlists:
            card = PlaylistCard(pl, self.api)
            card.open_requested.connect(self.open_playlist.emit)
            self.playlists_grid.add_widget(card)

        self.status.setText(tr('search.results', tracks=len(tracks), playlists=len(playlists)))

    def refresh(self):
        pass