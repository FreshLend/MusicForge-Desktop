from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, 
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                               QScrollArea, QTabWidget, QVBoxLayout, QWidget)

from core.api import ApiClient, ApiError
from core.i18n import Translator, tr
from src.icons import get_svg_icon
from src.pages.shared import format_count, ApiThread
from src.player import Player
from src.widgets import (CoverImage, ImageCache, PlaylistCard, ResponsiveGrid,
                         TrackCard)


class EditProfileDialog(QDialog):
    updated = Signal()

    def __init__(self, api: ApiClient, user: dict, parent=None):
        super().__init__(parent)
        self.api = api
        self.user = user
        self.setWindowTitle(tr('profile.edit_title'))
        self.setMinimumWidth(450)

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        avatar_row = QHBoxLayout()
        self.avatar_preview = CoverImage(80, 40, border_color="#00d4ff")
        self.avatar_preview.load(self.api.safe_avatar_url(user))
        avatar_row.addWidget(self.avatar_preview)

        self.avatar_path = None
        pick_btn = QPushButton(tr('profile.choose_avatar'))
        pick_btn.setObjectName('GhostBtn')
        pick_btn.clicked.connect(self._pick_avatar)
        avatar_row.addWidget(pick_btn)
        avatar_row.addStretch()
        v.addLayout(avatar_row)

        f = QFormLayout()
        self.name_input = QLineEdit(user.get('display_name', ''))
        self.name_input.setPlaceholderText(tr('profile.name_placeholder'))
        f.addRow(tr('profile.name'), self.name_input)

        self.bio_input = QLineEdit(user.get('bio', ''))
        self.bio_input.setPlaceholderText(tr('profile.bio_placeholder'))
        f.addRow(tr('profile.bio'), self.bio_input)
        v.addLayout(f)

        self.status = QLabel('')
        self.status.setObjectName('StatusText')
        v.addWidget(self.status)

        save_btn = QPushButton(tr('common.save'))
        save_btn.setObjectName('PrimaryBtn')
        save_btn.clicked.connect(self._save)
        v.addWidget(save_btn)

    def _pick_avatar(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('dialog.select_avatar'), '', tr('dialog.images_filter'))
        if path:
            self.avatar_path = path
            self.avatar_preview.load(f'file:///{path}', force=True)

    def _save(self):
        name = self.name_input.text().strip()
        if not name:
            self.status.setText(tr('profile.name_empty'))
            return
        bio = self.bio_input.text().strip()
        self.status.setText(tr('common.saving'))
        try:
            self.api.update_profile(name, bio, self.avatar_path)
            self.updated.emit()
            self.accept()
        except ApiError as e:
            self.status.setText(tr('common.error_prefix', message=e.message))
        except Exception as e:
            self.status.setText(tr('common.error_prefix', message=str(e)))


class ProfilePage(QWidget):
    open_playlist = Signal(str)
    edit_track = Signal(dict)
    delete_track = Signal(dict)
    open_track = Signal(str)

    def __init__(self, api: ApiClient, player: Player, main, parent=None):
        super().__init__(parent)
        self.api = api
        self.player = player
        self.main = main
        self._force_avatar = False
        self._last_me = None
        
        self._page = 1
        self._has_more = True
        self._loading = False

        v = QVBoxLayout(self)
        v.setContentsMargins(32, 32, 32, 32)
        v.setSpacing(24)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(24)

        self.avatar = CoverImage(140, 70, border_color="#00d4ff")
        header_layout.addWidget(self.avatar)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(6)

        name_row = QHBoxLayout()
        self.name_label = QLabel('')
        self.name_label.setObjectName('ProfileName')
        name_row.addWidget(self.name_label)

        self.admin_badge = QLabel(tr('profile.admin_badge'))
        self.admin_badge.setObjectName('AdminBadge')
        self.admin_badge.hide()
        name_row.addWidget(self.admin_badge)

        name_row.addStretch()

        self.edit_btn = QPushButton(tr('profile.edit_button'))
        self.edit_btn.setObjectName('GhostBtn')
        self.edit_btn.setIcon(get_svg_icon('settings', '#a8a8c0', 16))
        self.edit_btn.clicked.connect(self._edit_profile)
        name_row.addWidget(self.edit_btn)

        info_layout.addLayout(name_row)

        self.login_label = QLabel('')
        self.login_label.setObjectName('ProfileLogin')
        info_layout.addWidget(self.login_label)

        self.bio_label = QLabel('')
        self.bio_label.setObjectName('ProfileBio')
        self.bio_label.setTextFormat(Qt.TextFormat.PlainText)
        info_layout.addWidget(self.bio_label)

        self.stats = QLabel('')
        self.stats.setObjectName('ProfileStats')
        info_layout.addWidget(self.stats)

        info_layout.addStretch()
        header_layout.addLayout(info_layout, 1)
        v.addLayout(header_layout)

        self.tabs = QTabWidget()
        self.tracks_tab = self._build_tracks_tab()
        self.playlists_tab = self._build_playlists_tab()
        self.tabs.addTab(self.tracks_tab, tr('profile.tab_tracks'))
        self.tabs.addTab(self.playlists_tab, tr('profile.tab_playlists'))
        v.addWidget(self.tabs, 1)

        Translator.instance().language_changed.connect(self.retranslate)

    def retranslate(self):
        self.edit_btn.setText(tr('profile.edit_button'))
        self.admin_badge.setText(tr('profile.admin_badge'))
        self.tabs.setTabText(0, tr('profile.tab_tracks'))
        self.tabs.setTabText(1, tr('profile.tab_playlists'))
        if self._last_me is not None:
            if not self._last_me.get('bio'):
                self.bio_label.setText(tr('profile.bio_empty'))
            self._apply_stats(self._last_me)

    def _apply_stats(self, me):
        self.stats.setText(tr('profile.stats',
                              tracks=me.get('tracks_count', 0),
                              likes=format_count(me.get('total_likes', 0)),
                              plays=format_count(me.get('total_plays', 0))))

    def _build_tracks_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        
        sort_row = QHBoxLayout()
        sort_row.addStretch()
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Новые", "new")
        self.sort_combo.addItem("Популярные", "popular")
        self.sort_combo.addItem("Старые", "old")
        self.sort_combo.currentIndexChanged.connect(self._refresh_tracks)
        sort_row.addWidget(self.sort_combo)
        v.addLayout(sort_row)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.inner = QWidget()
        iv = QVBoxLayout(self.inner)
        iv.setContentsMargins(0, 0, 0, 0)
        self.tracks_grid = ResponsiveGrid()
        iv.addWidget(self.tracks_grid)
        self.scroll.setWidget(self.inner)
        v.addWidget(self.scroll, 1)
        
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        return w

    def _build_playlists_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 0, 0)
        self.playlists_grid = ResponsiveGrid()
        iv.addWidget(self.playlists_grid)
        scroll.setWidget(inner)
        return scroll

    def _edit_profile(self):
        me = self.api.user
        if not me:
            return
        dlg = EditProfileDialog(self.api, me, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            ImageCache.instance().clear()
            self._force_avatar = True
            self.refresh()

    def refresh(self):
        if self._loading:
            return
        self._loading = True
            
        t = ApiThread(self.api.me)
        t.done.connect(self._on_me_loaded)
        t.failed.connect(self._on_me_failed)
        t.start()

    def _on_me_failed(self, e):
        self._loading = False
        self.bio_label.setText(tr('common.error_prefix', message=e))

    def _on_me_loaded(self, me):
        self._loading = False
        self._last_me = me
        self.name_label.setText(me.get('display_name') or me.get('login', ''))
        self.login_label.setText(f"@{me.get('login', '')}")
        self.bio_label.setText(me.get('bio', '') or tr('profile.bio_empty'))
        
        if me.get('is_admin'):
            self.admin_badge.show()
        else:
            self.admin_badge.hide()
        self._apply_stats(me)

        avatar_url = self.api.safe_avatar_url(me)
        force = self._force_avatar
        self._force_avatar = False
        self.avatar.load(avatar_url, force=force)

        self._refresh_tracks()
        
        t2 = ApiThread(self.api.playlists_list)
        t2.done.connect(self._on_playlists_loaded)
        t2.start()
        
    def _on_playlists_loaded(self, playlists):
        self.playlists_grid.clear()
        for pl in playlists:
            card = PlaylistCard(pl, self.api)
            card.open_requested.connect(self.open_playlist.emit)
            self.playlists_grid.add_widget(card)

    def _refresh_tracks(self):
        if not self._last_me:
            return
        self._page = 1
        self._has_more = True
        self.tracks_grid.clear()
        self._load_tracks()

    def _load_tracks(self):
        if not self._last_me or self._loading or not self._has_more:
            return
        self._loading = True
        me = self._last_me
        sort_val = self.sort_combo.currentData()
        
        t = ApiThread(self.api.user_tracks, me['id'], page=self._page, per_page=20, sort=sort_val)
        t.done.connect(self._on_tracks_loaded)
        t.failed.connect(self._on_tracks_failed)
        t.start()

    def _on_tracks_failed(self, e):
        self._loading = False

    def _on_tracks_loaded(self, data):
        self._loading = False
        items = data.get('items', [])
        self._has_more = data.get('page', 1) < data.get('pages', 1)
        self._page += 1
        
        for t in items:
            card = TrackCard(t, self.api)
            card.play_requested.connect(self.player.play_track)
            card.clicked.connect(self.open_track.emit)
            card.edit_requested.connect(self.edit_track.emit)
            card.delete_requested.connect(self.delete_track.emit)
            self.tracks_grid.add_widget(card)
        self.inner.updateGeometry()

    def _on_scroll(self, value):
        if self._loading or not self._has_more:
            return
        sb = self.scroll.verticalScrollBar()
        if value >= sb.maximum() - 150:
            self._load_tracks()