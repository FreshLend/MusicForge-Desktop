from typing import Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QInputDialog, QLabel,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from core.api import ApiClient
from core.i18n import Translator, tr
from src.icons import get_svg_icon
from src.pages.shared import ask_yes_no, show_error, ApiThread
from src.player import Player
from src.widgets import PlaylistCard, ResponsiveGrid, TrackRow


class PlaylistsPage(QWidget):
    open_playlist = Signal(str)

    def __init__(self, api: ApiClient, player: Player, main, parent=None):
        super().__init__(parent)
        self.api = api
        self.player = player
        self.main = main

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        header = QHBoxLayout()
        self.title_label = QLabel(tr('playlists.title'))
        self.title_label.setObjectName('PageTitle')
        header.addWidget(self.title_label)
        header.addStretch()

        self.create_btn = QPushButton(tr('playlists.create'))
        self.create_btn.setObjectName('PrimaryBtn')
        self.create_btn.clicked.connect(self._create_playlist)
        header.addWidget(self.create_btn)
        v.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.inner = QWidget()
        iv = QVBoxLayout(self.inner)
        iv.setContentsMargins(0, 0, 0, 0)
        self.grid = ResponsiveGrid()
        iv.addWidget(self.grid)
        self.scroll.setWidget(self.inner)
        v.addWidget(self.scroll, 1)

        self.status = QLabel('')
        self.status.setObjectName('StatusText')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        v.addWidget(self.status)

        Translator.instance().language_changed.connect(self.retranslate)

    def retranslate(self):
        self.title_label.setText(tr('playlists.title'))
        self.create_btn.setText(tr('playlists.create'))

    def _create_playlist(self):
        name, ok = QInputDialog.getText(self, tr('playlists.new_title'), tr('playlists.name_prompt'))
        if not ok or not name.strip():
            return
        t = ApiThread(self.api.playlist_create, name.strip())
        t.done.connect(lambda _: self.refresh())
        t.failed.connect(lambda e: show_error(self, e))
        t.start()

    def refresh(self):
        t = ApiThread(self.api.playlists_list)
        t.done.connect(self._on_loaded)
        t.failed.connect(lambda e: self.status.setText(tr('common.error_prefix', message=e)))
        t.start()
        
    def _on_loaded(self, items):
        self.grid.clear()
        for pl in items:
            card = PlaylistCard(pl, self.api)
            card.open_requested.connect(self.open_playlist.emit)
            self.grid.add_widget(card)
        self.inner.updateGeometry()
        self.status.setText(tr('playlists.count', count=len(items)))


class PlaylistDetailPage(QWidget):
    back_requested = Signal()
    edit_track = Signal(dict)
    delete_track = Signal(dict)
    open_track = Signal(str)

    def __init__(self, api: ApiClient, player: Player, main, parent=None):
        super().__init__(parent)
        self.api = api
        self.player = player
        self.main = main
        self.playlist_id: Optional[str] = None
        self.tracks: List[Dict] = []
        self.playlist_info: Dict = {}
        self.rows: List[TrackRow] = []

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        top = QHBoxLayout()
        self.back_btn = QPushButton(tr('common.back'))
        self.back_btn.setObjectName('GhostBtn')
        self.back_btn.clicked.connect(self.back_requested.emit)
        top.addWidget(self.back_btn)
        top.addStretch()

        self.rename_btn = QPushButton(tr('common.rename'))
        self.rename_btn.setObjectName('GhostBtn')
        self.rename_btn.clicked.connect(self._rename)
        top.addWidget(self.rename_btn)

        self.visibility_btn = QPushButton(tr('playlists.make_public'))
        self.visibility_btn.setObjectName('GhostBtn')
        self.visibility_btn.clicked.connect(self._toggle_visibility)
        top.addWidget(self.visibility_btn)

        self.play_all_btn = QPushButton(tr('playlists.play_all'))
        self.play_all_btn.setIcon(get_svg_icon('play', '#0b0b14', 16))
        self.play_all_btn.setObjectName('PrimaryBtn')
        self.play_all_btn.clicked.connect(self._play_all)
        top.addWidget(self.play_all_btn)

        self.delete_btn = QPushButton(tr('common.delete'))
        self.delete_btn.setObjectName('DangerBtn')
        self.delete_btn.clicked.connect(self._delete)
        top.addWidget(self.delete_btn)
        v.addLayout(top)

        self.title_label = QLabel('')
        self.title_label.setObjectName('PageTitle')
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        v.addWidget(self.title_label)

        self.meta = QLabel('')
        self.meta.setObjectName('StatusText')
        self.meta.setTextFormat(Qt.TextFormat.PlainText)
        v.addWidget(self.meta)

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

        self.player.track_changed.connect(self._on_track_change)
        Translator.instance().language_changed.connect(self.retranslate)

    def retranslate(self):
        self.back_btn.setText(tr('common.back'))
        self.rename_btn.setText(tr('common.rename'))
        self.play_all_btn.setText(tr('playlists.play_all'))
        self.delete_btn.setText(tr('common.delete'))
        if self.playlist_info:
            self._update_meta()
            self._update_visibility_btn()

    def _on_track_change(self, t: Dict):
        if not t:
            for row in self.rows:
                row.set_active(False)
            return
        tid = t.get('id')
        for row in self.rows:
            row.set_active(row.track.get('id') == tid)

    def _update_visibility_btn(self):
        is_pub = bool(self.playlist_info.get('is_public'))
        self.visibility_btn.setText(tr('playlists.make_private') if is_pub else tr('playlists.make_public'))

    def _update_meta(self):
        pub = tr('playlists.public') if self.playlist_info.get('is_public') else tr('playlists.private')
        owner = self.playlist_info.get('owner', '')
        self.meta.setText(tr('playlists.meta', owner=owner, visibility=pub, count=len(self.tracks)))

    def load(self, pid: str):
        self.playlist_id = pid
        self.refresh()

    def refresh(self):
        if not self.playlist_id:
            return
        
        t = ApiThread(self.api.playlist_get, self.playlist_id)
        t.done.connect(self._on_loaded)
        t.failed.connect(lambda e: show_error(self, e))
        t.start()
        
    def _on_loaded(self, info):
        self.playlist_info = info
        self.tracks = info.get('tracks', [])
        self.title_label.setText(info.get('name', tr('playlists.detail_title')))
        self._update_meta()
        self._update_visibility_btn()

        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self.rows.clear()

        current = self.player.current_track()
        curr_id = current.get('id') if current else None

        for i, t in enumerate(self.tracks):
            row = TrackRow(t, self.api, index=i + 1, show_fav=False,
                           show_remove=True, show_edit_delete=False)
            row.play_requested.connect(lambda tr_, idx=i: self.player.play_queue(
                self.tracks, idx, context_name=self.playlist_info.get('name')
            ))
            row.remove_requested.connect(self._remove_track)
            row.clicked.connect(self.open_track.emit)
            if t.get('id') == curr_id:
                row.set_active(True)
            self.list_layout.addWidget(row)
            self.rows.append(row)

    def _play_all(self):
        if self.tracks:
            self.player.play_queue(self.tracks, 0, context_name=self.playlist_info.get('name'))

    def _rename(self):
        name, ok = QInputDialog.getText(self, tr('playlists.rename_title'), tr('playlists.rename_prompt'),
                                        text=self.playlist_info.get('name', ''))
        if not ok or not name.strip():
            return
        t = ApiThread(self.api.playlist_update, self.playlist_id, name=name.strip())
        t.done.connect(lambda _: self.refresh())
        t.failed.connect(lambda e: show_error(self, e))
        t.start()

    def _toggle_visibility(self):
        new_vis = not self.playlist_info.get('is_public', False)
        t = ApiThread(self.api.playlist_update, self.playlist_id, is_public=new_vis)
        t.done.connect(lambda _: self.refresh())
        t.failed.connect(lambda e: show_error(self, e))
        t.start()

    def _delete(self):
        if not ask_yes_no(self, tr('playlists.delete_title'), tr('playlists.delete_confirm')):
            return
        t = ApiThread(self.api.playlist_delete, self.playlist_id)
        t.done.connect(lambda _: self.back_requested.emit())
        t.failed.connect(lambda e: show_error(self, e))
        t.start()

    def _remove_track(self, track: Dict):
        t = ApiThread(self.api.playlist_remove_track, self.playlist_id, track['id'])
        t.done.connect(lambda _: self.refresh())
        t.failed.connect(lambda e: show_error(self, e))
        t.start()