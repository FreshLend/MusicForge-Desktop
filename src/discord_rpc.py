import time
from typing import Dict, Optional

from PySide6.QtCore import QObject, QSettings, Signal
from pypresence import Presence
from pypresence.exceptions import DiscordNotFound, InvalidPipe
from pypresence.types import ActivityType

from core.i18n import Translator, tr


DISCORD_CLIENT_ID = "1561704242593538129"

_LOCAL_PREFIXES = (
    'http://127.0.0.1',
    'http://localhost',
    'http://[::1]',
    'https://127.0.0.1',
    'https://localhost',
    'https://[::1]',
)


class DiscordRPC(QObject):
    availability_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rpc = None
        self._connected = False
        self._enabled = True
        self._current_track: Optional[Dict] = None
        self._context_name: Optional[str] = None
        self._paused = False
        self._track_started_at: Optional[int] = None
        self._track_duration_ms: int = 0
        self._current_position_ms: int = 0
        self._server_base_url: str = ''
        self._settings = QSettings('MusicForge', 'DiscordRPC')
        self._enabled = self._settings.value('enabled', True, type=bool)
        Translator.instance().language_changed.connect(self._refresh_presence)

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool):
        if self._enabled == enabled:
            return
        self._enabled = enabled
        self._settings.setValue('enabled', enabled)
        if enabled:
            self.start()
        else:
            self.stop()

    def set_server(self, base_url: str):
        self._server_base_url = base_url or ''
        if self._connected and self._current_track:
            self._refresh_presence()

    def start(self):
        if not self._enabled:
            return
        if self._connected:
            return
        try:
            self._rpc = Presence(DISCORD_CLIENT_ID)
            self._rpc.connect()
            self._connected = True
            self.availability_changed.emit(True)
            self._refresh_presence()
        except (DiscordNotFound, InvalidPipe):
            self._connected = False
            self._rpc = None
            self.availability_changed.emit(False)
        except Exception:
            self._connected = False
            self._rpc = None
            self.availability_changed.emit(False)

    def stop(self):
        if self._rpc is not None and self._connected:
            try:
                self._rpc.clear()
                self._rpc.close()
            except Exception:
                pass
        self._rpc = None
        self._connected = False
        self.availability_changed.emit(False)

    def update_track(self, track: Optional[Dict], context_name: Optional[str] = None):
        self._current_track = track if track else None
        self._context_name = context_name
        self._paused = False
        self._track_duration_ms = 0
        self._current_position_ms = 0
        self._track_started_at = int(time.time() * 1000) if self._current_track else None
        self._refresh_presence()

    def sync_position(self, position_ms: int, duration_ms: int):
        if duration_ms <= 0:
            return
        self._current_position_ms = position_ms
        if self._track_duration_ms != duration_ms:
            self._track_duration_ms = duration_ms
            if not self._paused and self._track_started_at is not None:
                now = int(time.time() * 1000)
                self._track_started_at = now - position_ms
            self._refresh_presence()

    def update_paused(self, paused: bool):
        if self._paused == paused:
            return
        self._paused = paused
        if not self._current_track:
            return
        now = int(time.time() * 1000)
        if paused:
            self._track_started_at = None
        else:
            if self._track_duration_ms > 0:
                self._track_started_at = now - self._current_position_ms
            else:
                self._track_started_at = now
        self._refresh_presence()

    def _is_local_url(self, url: str) -> bool:
        lower = url.lower()
        return any(lower.startswith(p) for p in _LOCAL_PREFIXES)

    def _refresh_presence(self):
        if not self._connected or self._rpc is None:
            return
        try:
            large_image = 'logo'
            buttons = []
            if self._server_base_url and not self._is_local_url(self._server_base_url):
                buttons.append({
                    'label': tr('discord_rpc.open_in_app'),
                    'url': self._server_base_url,
                })

            if not self._current_track:
                kwargs = {
                    'activity_type': ActivityType.LISTENING,
                    'details': 'MusicForge',
                    'state': tr('discord_rpc.browsing'),
                    'large_image': large_image,
                }
                if buttons:
                    kwargs['buttons'] = buttons[:2]
                self._rpc.update(**kwargs)
                return

            track = self._current_track
            title = track.get('title') or 'Unknown'
            artist = track.get('artist') or 'Unknown'

            details = 'MusicForge'
            
            if self._context_name:
                state = f"{title} • {self._context_name}"
            else:
                state = title
                
            large_text = artist

            if self._paused:
                paused_text = tr('discord_rpc.paused')
                state = f"{state} · {paused_text}"

            small_text = tr('discord_rpc.paused') if self._paused else tr('discord_rpc.playing')
            small_image = 'pause' if self._paused else 'play'

            cover = track.get('cover_url') or ''
            if cover.startswith('https://'):
                large_image = cover

            kwargs = {
                'activity_type': ActivityType.LISTENING,
                'details': details,
                'state': state,
                'large_image': large_image,
                'large_text': large_text,
                'small_image': small_image,
                'small_text': small_text,
            }

            if not self._paused and self._track_started_at and self._track_duration_ms > 0:
                kwargs['start'] = self._track_started_at
                kwargs['end'] = self._track_started_at + self._track_duration_ms

            if buttons:
                kwargs['buttons'] = buttons[:2]

            self._rpc.update(**kwargs)
        except Exception:
            self._connected = False
            self._rpc = None
            self.availability_changed.emit(False)