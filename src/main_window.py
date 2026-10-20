from typing import Dict

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QMainWindow,
                               QPushButton, QSlider, QStackedWidget,
                               QVBoxLayout, QWidget)

from core.api import ApiClient, ApiError, get_app_icon_path
from core.i18n import Translator, tr
from src.discord_rpc import DiscordRPC
from src.icons import get_svg_icon
from src.pages import (EditTrackDialog, FavoritesPage, HistoryPage,
                       HomePage, NewReleasesPage, PlaylistDetailPage,
                       PlaylistsPage, PopularPage, ProfilePage, SearchPage,
                       SettingsPage, UploadDialog)
from src.pages.shared import (apply_busy_cursor, ask_yes_no, fmt_time,
                              show_error, show_info)
from src.player import Player
from src.widgets import CoverImage, ClickableSlider, ImageCache


_ACTIVE_WINDOW = None


class Sidebar(QWidget):
    navigate = Signal(str)
    upload_clicked = Signal()

    BUTTONS = [
        ('home', 'home', 'nav.home'),
        ('new', 'new', 'nav.new'),
        ('popular', 'fire', 'nav.popular'),
        ('search', 'search', 'nav.search'),
        ('favorites', 'heart', 'nav.favorites'),
        ('playlists', 'folder', 'nav.playlists'),
        ('history', 'history', 'nav.history'),
        ('profile', 'user', 'nav.profile'),
        ('settings', 'settings', 'nav.settings'),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(220)
        self.setObjectName('Sidebar')

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 20, 16, 20)
        v.setSpacing(4)

        logo_layout = QHBoxLayout()
        logo_layout.setContentsMargins(10, 0, 0, 0)
        logo_layout.setSpacing(8)

        app_icon = QIcon(get_app_icon_path())
        if not app_icon.isNull():
            icon_label = QLabel()
            icon_label.setPixmap(app_icon.pixmap(24, 24))
            logo_layout.addWidget(icon_label)

        logo_text = QLabel('<span style="color:#00d4ff;">Music</span><span style="color:#ffffff;">Forge</span>')
        logo_text.setObjectName('SidebarLogo')
        logo_text.setTextFormat(Qt.TextFormat.RichText)
        logo_layout.addWidget(logo_text)
        logo_layout.addStretch()
        v.addLayout(logo_layout)
        v.addSpacing(12)

        self.buttons: Dict[str, QPushButton] = {}
        for key, icon_name, label_key in self.BUTTONS:
            b = QPushButton(f'  {tr(label_key)}')
            b.setObjectName('SidebarBtn')
            b.setCheckable(True)
            b.setIcon(get_svg_icon(icon_name, '#a8a8c0', 18))
            b.setProperty('label_key', label_key)
            b.clicked.connect(lambda _=False, k=key: self.navigate.emit(k))
            v.addWidget(b)
            self.buttons[key] = b

        v.addStretch()

        self.upload_btn = QPushButton(f'  {tr("nav.upload_track")}')
        self.upload_btn.setObjectName('SidebarUploadBtn')
        self.upload_btn.setIcon(get_svg_icon('upload', '#0b0b14', 18))
        self.upload_btn.clicked.connect(self.upload_clicked.emit)
        v.addWidget(self.upload_btn)

        Translator.instance().language_changed.connect(self.retranslate)

    def retranslate(self):
        for key, b in self.buttons.items():
            b.setText(f'  {tr(b.property("label_key"))}')
        self.upload_btn.setText(f'  {tr("nav.upload_track")}')

    def set_active(self, key: str):
        for k, b in self.buttons.items():
            b.setChecked(k == key)


class PlayerBar(QWidget):
    def __init__(self, player: Player, api: ApiClient, parent=None):
        super().__init__(parent)
        self.player = player
        self.api = api
        self.setFixedHeight(84)
        self.setObjectName('PlayerBar')

        h = QHBoxLayout(self)
        h.setContentsMargins(16, 8, 16, 8)
        h.setSpacing(16)

        self.cover = CoverImage(56, 6)
        h.addWidget(self.cover)

        info = QVBoxLayout()
        info.setSpacing(2)
        self.title = QLabel('—')
        self.title.setObjectName('PlayerTitle')
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.artist = QLabel('')
        self.artist.setObjectName('PlayerArtist')
        self.artist.setTextFormat(Qt.TextFormat.PlainText)
        info.addWidget(self.title)
        info.addWidget(self.artist)
        h.addLayout(info)
        h.addSpacing(20)

        self.prev_btn = QPushButton()
        self.prev_btn.setIcon(get_svg_icon('prev', '#a8a8c0', 20))
        self.prev_btn.setObjectName('PlayerBtn')
        self.prev_btn.setFixedSize(40, 40)

        self.play_btn = QPushButton()
        self.play_btn.setIcon(get_svg_icon('play', '#0b0b14', 24))
        self.play_btn.setObjectName('PlayerBtnPlay')
        self.play_btn.setFixedSize(50, 50)

        self.next_btn = QPushButton()
        self.next_btn.setIcon(get_svg_icon('next', '#a8a8c0', 20))
        self.next_btn.setObjectName('PlayerBtn')
        self.next_btn.setFixedSize(40, 40)

        self.loop_btn = QPushButton()
        self.loop_btn.setIcon(get_svg_icon('repeat', '#a8a8c0', 20))
        self.loop_btn.setObjectName('PlayerBtn')
        self.loop_btn.setFixedSize(40, 40)
        self.loop_btn.setCheckable(True)
        self.loop_btn.clicked.connect(self._toggle_loop)

        h.addWidget(self.prev_btn)
        h.addWidget(self.play_btn)
        h.addWidget(self.next_btn)
        h.addWidget(self.loop_btn)

        self.pos_label = QLabel('0:00')
        self.pos_label.setObjectName('PlayerTime')
        self.pos_label.setFixedWidth(48)
        self.pos_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(self.pos_label)

        self.slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName('ProgressSlider')
        self.slider.setRange(0, 1000)
        self.slider.sliderMoved.connect(self._seek)
        h.addWidget(self.slider, 1)

        self.dur_label = QLabel('0:00')
        self.dur_label.setObjectName('PlayerTime')
        self.dur_label.setFixedWidth(48)
        self.dur_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(self.dur_label)

        self.vol = QSlider(Qt.Orientation.Horizontal)
        self.vol.setObjectName('VolumeSlider')
        self.vol.setRange(0, 100)
        self.vol.setValue(int(self.player.volume() * 100))
        self.vol.setFixedWidth(110)
        self.vol.valueChanged.connect(lambda v: self.player.set_volume(v / 100.0))
        h.addWidget(self.vol)

        self.prev_btn.clicked.connect(self.player.prev)
        self.play_btn.clicked.connect(self.player.toggle)
        self.next_btn.clicked.connect(self.player.next)

        self.player.track_changed.connect(self._on_track)
        self.player.state_changed.connect(self._on_state)
        self.player.position_changed.connect(self._on_pos)

        self._update_nav_visibility()

    def _toggle_loop(self):
        active = self.loop_btn.isChecked()
        self.player.loop = active
        color = '#00d4ff' if active else '#a8a8c0'
        self.loop_btn.setIcon(get_svg_icon('repeat', color, 20))

    def _on_track(self, t: Dict):
        if not t:
            self.title.setText('—')
            self.artist.setText('')
            self.cover.clear()
            self._update_nav_visibility()
            return
        self.title.setText(t.get('title', ''))
        self.artist.setText(t.get('artist', ''))
        self.cover.load(self.api.cover_url(t))
        self._update_nav_visibility()

    def _update_nav_visibility(self):
        multi = len(self.player.queue) > 1
        self.prev_btn.setVisible(multi)
        self.next_btn.setVisible(multi)

    def _on_state(self, playing: bool):
        icon_name = 'pause' if playing else 'play'
        self.play_btn.setIcon(get_svg_icon(icon_name, '#0b0b14', 24))

    def _on_pos(self, pos: int, dur: int):
        if not self.slider.isSliderDown():
            if dur > 0:
                self.slider.setValue(int(pos * 1000 / dur))
            else:
                self.slider.setValue(0)
        self.pos_label.setText(fmt_time(pos))
        self.dur_label.setText(fmt_time(dur))

    def _seek(self, value: int):
        dur = self.player.player.duration()
        if dur > 0:
            self.player.seek(int(value * dur / 1000))


class MainWindow(QMainWindow):
    def __init__(self, api: ApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self.player = Player(api, self)

        self.discord_rpc = DiscordRPC(self)
        self.discord_rpc.set_server(self.api.base_url)
        self.player.track_changed.connect(self._on_discord_track)
        self.player.state_changed.connect(
            lambda playing: self.discord_rpc.update_paused(not playing)
        )
        self.player.position_changed.connect(self.discord_rpc.sync_position)
        self.discord_rpc.start()

        self.setWindowTitle('MusicForge')
        self.resize(1280, 800)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.navigate.connect(self.navigate)
        self.sidebar.upload_clicked.connect(self.open_upload)
        body.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)

        root.addLayout(body, 1)

        self.player_bar = PlayerBar(self.player, api)
        root.addWidget(self.player_bar)

        self.setCentralWidget(central)

        self._pages: Dict[str, QWidget] = {}

        self.home = HomePage(api, self.player, self)
        self.new_page = NewReleasesPage(api, self.player, self)
        self.popular_page = PopularPage(api, self.player, self)
        self.search_page = SearchPage(api, self.player, self)
        self.favorites_page = FavoritesPage(api, self.player, self)
        self.playlists_page = PlaylistsPage(api, self.player, self)
        self.playlist_detail = PlaylistDetailPage(api, self.player, self)
        self.history_page = HistoryPage(api, self.player, self)
        self.profile_page = ProfilePage(api, self.player, self)
        self.settings_page = SettingsPage(api, self.player, self)

        self._add('home', self.home)
        self._add('new', self.new_page)
        self._add('popular', self.popular_page)
        self._add('search', self.search_page)
        self._add('favorites', self.favorites_page)
        self._add('playlists', self.playlists_page)
        self._add('playlist_detail', self.playlist_detail)
        self._add('history', self.history_page)
        self._add('profile', self.profile_page)
        self._add('settings', self.settings_page)

        self.search_page.open_playlist.connect(self.open_playlist)
        self.playlists_page.open_playlist.connect(self.open_playlist)
        self.profile_page.open_playlist.connect(self.open_playlist)
        self.playlist_detail.back_requested.connect(lambda: self.navigate('playlists'))
        self.settings_page.logout_requested.connect(self._on_logout)

        for page in [self.home, self.new_page, self.popular_page,
                     self.search_page, self.profile_page]:
            page.edit_track.connect(self.on_edit_track)
            page.delete_track.connect(self.on_delete_track)

        self.navigate('home')
        self._apply_startup()

    def _add(self, key: str, widget: QWidget):
        self._pages[key] = widget
        self.stack.addWidget(widget)

    def _apply_startup(self):
        try:
            self.api.me()
        except Exception:
            pass

    def _on_discord_track(self, track: Dict):
        if not track:
            self.discord_rpc.update_track(None)
            return
        
        rpc_track = dict(track)
        
        absolute_cover = self.api.cover_url(track)
        if absolute_cover:
            import time
            rpc_track['cover_url'] = f"{absolute_cover}?v={int(time.time())}"
        else:
            rpc_track['cover_url'] = ''
        
        context = getattr(self.player, 'context_name', None)
        self.discord_rpc.update_track(rpc_track, context_name=context)

    def navigate(self, key: str):
        if key not in self._pages:
            return
        page = self._pages[key]
        try:
            with apply_busy_cursor():
                if hasattr(page, 'refresh'):
                    page.refresh()
        except Exception as e:
            show_error(self, str(e))
        self.stack.setCurrentWidget(page)
        self.sidebar.set_active(key)

    def open_playlist(self, pid: str):
        self.playlist_detail.load(pid)
        self.stack.setCurrentWidget(self.playlist_detail)
        for k, b in self.sidebar.buttons.items():
            b.setChecked(False)

    def open_upload(self):
        dlg = UploadDialog(self.api, self)
        dlg.uploaded.connect(self._on_uploaded)
        dlg.exec()

    def _on_uploaded(self, track: Dict):
        show_info(self, tr('main.uploaded_message', title=track.get('title', '')),
                  tr('common.done'))
        try:
            self.home.refresh()
            self.new_page.refresh()
        except Exception:
            pass

    def on_edit_track(self, track: Dict):
        dlg = EditTrackDialog(self.api, track, self)
        dlg.updated.connect(lambda: self._on_track_edited(track))
        dlg.exec()

    def _on_track_edited(self, track: Dict):
        self._refresh_current_page()
        current = self.player.current_track()
        if current and current.get('id') == track.get('id'):
            self.player_bar.cover.load(self.api.cover_url(current), force=True)

    def on_delete_track(self, track: Dict):
        if not ask_yes_no(self, tr('main.delete_title'),
                          tr('main.delete_confirm', title=track.get('title', ''))):
            return
        try:
            self.api.track_delete(track['id'])
            self._refresh_current_page()
        except ApiError as e:
            show_error(self, e.message)

    def _refresh_current_page(self):
        ImageCache.instance().clear()
        current = self.stack.currentWidget()
        try:
            with apply_busy_cursor():
                if hasattr(current, 'refresh'):
                    current.refresh()
        except Exception as e:
            show_error(self, str(e))

    def _on_logout(self):
        global _ACTIVE_WINDOW
        self.player.stop()
        self.discord_rpc.stop()
        self.close()
        from src.auth import AuthDialog
        dlg = AuthDialog(self.api, None)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new = MainWindow(self.api)
            new.show()
            _ACTIVE_WINDOW = new
        else:
            import sys
            sys.exit(0)

    def closeEvent(self, event):
        self.discord_rpc.stop()
        super().closeEvent(event)