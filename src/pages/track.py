from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QInputDialog, 
                               QLabel, QMenu, QPushButton, QScrollArea, 
                               QVBoxLayout, QWidget)

from core.api import ApiClient
from core.i18n import Translator, tr
from src.icons import get_svg_icon
from src.pages.shared import format_count, show_error, ApiThread
from src.player import Player
from src.widgets import CoverImage, ResponsiveGrid, TrackCard


class TrackPage(QWidget):
    back_requested = Signal()
    edit_track = Signal(dict)
    delete_track = Signal(dict)

    def __init__(self, api: ApiClient, player: Player, main, parent=None):
        super().__init__(parent)
        self.api = api
        self.player = player
        self.main = main
        self.track_id = None
        self.track_data = {}

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        top = QHBoxLayout()
        self.back_btn = QPushButton(tr('common.back'))
        self.back_btn.setObjectName('GhostBtn')
        self.back_btn.clicked.connect(self.back_requested.emit)
        top.addWidget(self.back_btn)
        top.addStretch()
        v.addLayout(top)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.content = QWidget()
        self.layout = QVBoxLayout(self.content)
        self.layout.setSpacing(24)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.info_layout = QHBoxLayout()
        self.info_layout.setSpacing(24)
        self.info_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.cover = CoverImage(200, 12, border_color="#00d4ff")
        self.info_layout.addWidget(self.cover)

        self.details_layout = QVBoxLayout()
        self.details_layout.setSpacing(8)

        self.title = QLabel()
        self.title.setObjectName('PageTitle')
        self.title.setWordWrap(True)
        self.details_layout.addWidget(self.title)

        self.artist = QLabel()
        self.artist.setObjectName('ProfileLogin')
        self.details_layout.addWidget(self.artist)

        self.meta = QLabel()
        self.meta.setObjectName('StatusText')
        self.details_layout.addWidget(self.meta)

        self.tags = QLabel()
        self.tags.setObjectName('TrackArtist')
        self.details_layout.addWidget(self.tags)

        self.details_layout.addStretch()
        
        actions = QHBoxLayout()
        self.play_btn = QPushButton(tr('track.play'))
        self.play_btn.setObjectName('PrimaryBtn')
        self.play_btn.setIcon(get_svg_icon('play', '#0b0b14', 16))
        self.play_btn.clicked.connect(self._play)
        actions.addWidget(self.play_btn)

        self.like_btn = QPushButton()
        self.like_btn.setObjectName('GhostBtn')
        self.like_btn.setIcon(get_svg_icon('like', '#a8a8c0', 18))
        self.like_btn.clicked.connect(self._like)
        actions.addWidget(self.like_btn)

        self.dislike_btn = QPushButton()
        self.dislike_btn.setObjectName('GhostBtn')
        self.dislike_btn.setIcon(get_svg_icon('dislike', '#a8a8c0', 18))
        self.dislike_btn.clicked.connect(self._dislike)
        actions.addWidget(self.dislike_btn)

        self.fav_btn = QPushButton()
        self.fav_btn.setObjectName('GhostBtn')
        self.fav_btn.setIcon(get_svg_icon('heart', '#a8a8c0', 18))
        self.fav_btn.clicked.connect(self._fav)
        actions.addWidget(self.fav_btn)

        self.add_pl_btn = QPushButton(tr('playlists.add_to'))
        self.add_pl_btn.setObjectName('GhostBtn')
        self.add_pl_btn.clicked.connect(self._show_pl_menu)
        actions.addWidget(self.add_pl_btn)

        actions.addStretch()
        self.details_layout.addLayout(actions)
        self.info_layout.addLayout(self.details_layout, 1)
        self.layout.addLayout(self.info_layout)

        self.rec_title = QLabel(tr('home.recommendations'))
        self.rec_title.setObjectName('SectionTitle')
        self.layout.addWidget(self.rec_title)

        self.rec_grid = ResponsiveGrid()
        self.layout.addWidget(self.rec_grid)

        self.scroll.setWidget(self.content)
        v.addWidget(self.scroll, 1)

        Translator.instance().language_changed.connect(self.retranslate)

    def retranslate(self):
        self.back_btn.setText(tr('common.back'))
        self.play_btn.setText(tr('track.play'))
        self.rec_title.setText(tr('home.recommendations'))
        self.add_pl_btn.setText(tr('playlists.add_to'))
        self._update_ui()

    def load(self, tid: str):
        self.track_id = tid
        self.refresh()

    def refresh(self):
        if not self.track_id:
            return
            
        t1 = ApiThread(self.api.get_track, self.track_id)
        t1.done.connect(self._on_track_loaded)
        t1.failed.connect(lambda e: show_error(self, e))
        t1.start()

    def _on_track_loaded(self, data):
        self.track_data = data
        self._update_ui()
        
        t2 = ApiThread(self.api.track_similar, self.track_id, limit=24)
        t2.done.connect(self._on_similar_loaded)
        t2.start()

    def _on_similar_loaded(self, recs):
        self.rec_grid.clear()
        self._fill_recs(recs)
        if len(recs) < 16:
            t = ApiThread(self.api.list_tracks, 1, 20, 'popular')
            t.done.connect(lambda d: self._fill_fallback(
                {r.get('id') for r in recs}, d.get('items', [])))
            t.start()
        else:
            self.content.updateGeometry()
            QTimer.singleShot(0, self.rec_grid._relayout)

    def _fill_recs(self, recs):
        for t in recs:
            card = TrackCard(t, self.api)
            card.play_requested.connect(self.player.play_track)
            card.clicked.connect(self.main.open_track)
            self.rec_grid.add_widget(card)

    def _fill_fallback(self, existing_ids, items):
        for t in items:
            if len(existing_ids) >= 24:
                break
            if t.get('id') in existing_ids:
                continue
            card = TrackCard(t, self.api)
            card.play_requested.connect(self.player.play_track)
            card.clicked.connect(self.main.open_track)
            self.rec_grid.add_widget(card)
            existing_ids.add(t.get('id'))
        self.content.updateGeometry()
        QTimer.singleShot(0, self.rec_grid._relayout)

    def _update_ui(self):
        if not self.track_data:
            return
        t = self.track_data
        self.title.setText(t.get('title', ''))
        self.artist.setText(t.get('artist', ''))
        self.cover.load(self.api.cover_url(t))
        
        plays = format_count(t.get('play_count', 0))
        self.meta.setText(tr('track.plays', count=plays))

        tags = ', '.join(t.get('tags', []))
        self.tags.setText(tr('track.tags', tags=tags) if tags else "")
        
        r = t.get('user_rating', 0)
        is_fav = t.get('is_favorite', False)

        self.like_btn.setText(f" {format_count(t.get('likes', 0))}")
        self.dislike_btn.setText(f" {format_count(t.get('dislikes', 0))}")

        self.like_btn.setIcon(get_svg_icon('like', '#00d4ff' if r == 1 else '#a8a8c0', 18))
        self.dislike_btn.setIcon(get_svg_icon('dislike', '#ff6b6b' if r == -1 else '#a8a8c0', 18))
        self.fav_btn.setIcon(get_svg_icon('heart', '#00d4ff' if is_fav else '#a8a8c0', 18))

    def _play(self):
        if self.track_data:
            self.player.play_track(self.track_data)

    def _like(self):
        self._rate(1)

    def _dislike(self):
        self._rate(-1)

    def _rate(self, val):
        t = ApiThread(self.api.track_rate, self.track_id, val)
        t.done.connect(self._on_rated)
        t.failed.connect(lambda e: show_error(self, e))
        t.start()

    def _on_rated(self, res):
        if not isinstance(res, dict):
            return
        self.track_data['likes'] = res.get('likes', 0)
        self.track_data['dislikes'] = res.get('dislikes', 0)
        self.track_data['user_rating'] = res.get('user_rating', 0)
        self._update_ui()

    def _fav(self):
        if self.track_data.get('is_favorite'):
            t = ApiThread(self.api.track_favorite_remove, self.track_id)
            t.done.connect(lambda _: self._on_fav_toggled(False))
        else:
            t = ApiThread(self.api.track_favorite_add, self.track_id)
            t.done.connect(lambda _: self._on_fav_toggled(True))
        t.failed.connect(lambda e: show_error(self, e))
        t.start()
        
    def _on_fav_toggled(self, is_fav):
        self.track_data['is_favorite'] = is_fav
        self._update_ui()

    def _show_pl_menu(self):
        t = ApiThread(self.api.playlists_list)
        t.done.connect(self._build_pl_menu)
        t.start()
        
    def _build_pl_menu(self, playlists):
        menu = QMenu(self)
        create_act = menu.addAction(tr('playlists.new_title'))
        create_act.triggered.connect(self._create_playlist)
        
        if playlists:
            menu.addSeparator()
            
        in_pl = self.track_data.get('in_playlists', [])
        
        for pl in playlists:
            action = menu.addAction(pl['name'])
            action.setCheckable(True)
            action.setChecked(pl['id'] in in_pl)
            action.triggered.connect(lambda checked, p=pl: self._toggle_playlist(p['id']))
            
        menu.exec(self.add_pl_btn.mapToGlobal(self.add_pl_btn.rect().bottomLeft()))

    def _create_playlist(self):
        name, ok = QInputDialog.getText(self, tr('playlists.new_title'), tr('playlists.name_prompt'))
        if not ok or not name.strip():
            return
        t = ApiThread(self.api.playlist_create, name.strip())
        t.done.connect(self._on_pl_created)
        t.start()
        
    def _on_pl_created(self, pl):
        t = ApiThread(self.api.playlist_add_track, pl['id'], self.track_id)
        t.done.connect(lambda _: self.refresh())
        t.start()

    def _toggle_playlist(self, pid):
        in_pl = self.track_data.get('in_playlists', [])
        if pid in in_pl:
            t = ApiThread(self.api.playlist_remove_track, pid, self.track_id)
            t.done.connect(lambda _: self._on_pl_toggled(pid, False))
        else:
            t = ApiThread(self.api.playlist_add_track, pid, self.track_id)
            t.done.connect(lambda _: self._on_pl_toggled(pid, True))
        t.start()
        
    def _on_pl_toggled(self, pid, added):
        in_pl = self.track_data.get('in_playlists', [])
        if added and pid not in in_pl:
            in_pl.append(pid)
        elif not added and pid in in_pl:
            in_pl.remove(pid)
        self.track_data['in_playlists'] = in_pl