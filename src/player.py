from typing import Dict, List, Optional
from PySide6.QtCore import QObject, QTimer, QUrl, Signal, QSettings
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QMediaDevices


class Player(QObject):
    track_changed = Signal(dict)
    state_changed = Signal(bool)
    position_changed = Signal(int, int)
    volume_changed = Signal(float)
    buffering_changed = Signal(bool)

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)

        self.settings = QSettings("MusicForge", "DesktopPlayer")
        saved_vol = self.settings.value("volume", 0.7, type=float)
        self.audio.setVolume(saved_vol)

        self.loop = False

        self.player.positionChanged.connect(self._on_pos)
        self.player.durationChanged.connect(lambda _: self._on_pos(self.player.position()))
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.errorOccurred.connect(self._on_error)

        self.audio.volumeChanged.connect(self._on_volume_changed)

        self.queue: List[Dict] = []
        self.index: int = -1
        self.context_name: Optional[str] = None
        self._listen_reported: set = set()
        self._current_id: Optional[str] = None

        self._listen_timer = QTimer(self)
        self._listen_timer.setInterval(2000)
        self._listen_timer.timeout.connect(self._maybe_report)

        self._device_timer = QTimer(self)
        self._device_timer.setInterval(2000)
        self._device_timer.timeout.connect(self._check_audio_device)
        self._device_timer.start()

        self._buffering = False
        self._user_paused = False
        self._stream_error_count = 0

        self._stream_watchdog = QTimer(self)
        self._stream_watchdog.setSingleShot(True)
        self._stream_watchdog.setInterval(90000)
        self._stream_watchdog.timeout.connect(self._on_stream_timeout)

        self._stream_retry_timer = QTimer(self)
        self._stream_retry_timer.setSingleShot(True)
        self._stream_retry_timer.timeout.connect(self._restart_stream)

    def _set_buffering(self, b: bool):
        if self._buffering == b:
            return
        self._buffering = b
        if not b:
            self._stream_watchdog.stop()
        self.buffering_changed.emit(b)

    def is_buffering(self) -> bool:
        return self._buffering

    def _on_stream_timeout(self):
        if not self._buffering:
            return
        if self._user_paused:
            self._stream_watchdog.stop()
            return
        track = self.current_track()
        if not track or not track.get('is_radio'):
            return
        self._stream_error_count += 1
        if self._stream_error_count <= 3:
            self._restart_stream()
        else:
            self._set_buffering(False)

    def _restart_stream(self):
        track = self.current_track()
        if not track or not track.get('is_radio'):
            return
        url = track.get('audio_url', '')
        if not url:
            return
        self.play_stream(track.get('title', ''), url)

    def _on_volume_changed(self):
        self.settings.setValue("volume", self.audio.volume())
        self.volume_changed.emit(self.audio.volume())

    def _check_audio_device(self):
        default_device = QMediaDevices.defaultAudioOutput()
        if default_device and self.audio.device().id() != default_device.id():
            self.audio.setDevice(default_device)

    def _on_error(self, error, error_string):
        if error == QMediaPlayer.Error.NoError:
            return
        track = self.current_track()
        is_radio = bool(track and track.get('is_radio'))
        if is_radio:
            self._stream_watchdog.stop()
            self._stream_retry_timer.stop()
            self._stream_error_count += 1
            if self._stream_error_count > 3:
                self._set_buffering(False)
                return
            delay = 5000 if not self._buffering else 30000
            self._stream_retry_timer.start(delay)
            return
        QTimer.singleShot(3000, self._retry_play)

    def _retry_play(self):
        if self.player.error() != QMediaPlayer.Error.NoError and self.queue:
            self._play_current()

    def _on_status(self, status):
        track = self.current_track()
        is_radio = bool(track and track.get('is_radio'))

        if is_radio:
            if status in (QMediaPlayer.MediaStatus.LoadedMedia,
                          QMediaPlayer.MediaStatus.BufferedMedia):
                self._set_buffering(False)
                self._stream_error_count = 0
                if not self._user_paused:
                    if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                        self.player.play()
            elif status == QMediaPlayer.MediaStatus.InvalidMedia:
                self._set_buffering(False)
            elif status == QMediaPlayer.MediaStatus.EndOfMedia:
                self._set_buffering(False)
                if self._stream_error_count <= 3:
                    self._stream_retry_timer.start(3000)
            return

        self._set_buffering(False)
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.loop:
                self.player.setPosition(0)
                self.player.play()
                return
            if len(self.queue) > 1:
                self.next()
            else:
                self.stop()

    def _on_state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.state_changed.emit(playing)
        if playing:
            self._listen_timer.start()
        else:
            self._listen_timer.stop()

    def _on_pos(self, pos):
        self.position_changed.emit(int(pos), int(self.player.duration()))

    def _maybe_report(self):
        if not self._current_id:
            return
        if self._current_id.startswith('radio:'):
            self._listen_timer.stop()
            return
        if self.player.position() >= 15000:
            tid = self._current_id
            if tid not in self._listen_reported:
                self._listen_reported.add(tid)
                try:
                    self.api.track_listen(tid)
                except Exception:
                    pass
            self._listen_timer.stop()

    def play_track(self, track: Dict):
        tid = track.get('id')
        if tid:
            self._listen_reported.discard(tid)
        self.context_name = None
        self.queue = [track]
        self.index = 0
        self._play_current()

    def play_queue(self, tracks: List[Dict], start_index: int = 0, context_name: Optional[str] = None):
        if not tracks:
            return
        idx = max(0, min(start_index, len(tracks) - 1))
        tid = tracks[idx].get('id')
        if tid:
            self._listen_reported.discard(tid)
        self.queue = list(tracks)
        self.index = idx
        self.context_name = context_name
        self._play_current()

    def play_stream(self, name: str, url: str, cover_url: str = ''):
        current = self.current_track()
        if current and current.get('is_radio') and current.get('audio_url') == url:
            self.toggle()
            return

        track = {
            'id': f'radio:{url}',
            'title': name,
            'artist': 'Radio',
            'audio_url': url,
            'cover_url': cover_url,
            'is_radio': True,
        }
        self.queue = [track]
        self.index = 0
        self.context_name = name
        self._current_id = track['id']
        self._listen_reported.clear()
        self._user_paused = False
        self._stream_error_count = 0
        self._stream_retry_timer.stop()

        self.player.stop()
        self._set_buffering(True)
        self._stream_watchdog.start()
        self.player.setSource(QUrl(url))
        self.player.play()
        self.track_changed.emit(track)

    def _play_current(self):
        if self.index < 0 or self.index >= len(self.queue):
            return
        track = self.queue[self.index]
        if track.get('is_radio'):
            self.play_stream(track.get('title', ''), track.get('audio_url', ''),
                             track.get('cover_url', ''))
            return
        tid = track.get('id')
        url = track.get('audio_url') or self.api.stream_url(tid)
        url = self.api.absolute(url)
        self._current_id = tid
        self._user_paused = False
        self.player.setSource(QUrl(url))
        self.player.play()
        self.track_changed.emit(track)

    def toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._user_paused = True
            self.player.pause()
        else:
            self._user_paused = False
            if self.player.source().isEmpty() and self.queue:
                self._play_current()
            else:
                self.player.play()

    def next(self):
        if not self.queue:
            return
        self.index = (self.index + 1) % len(self.queue)
        self._play_current()

    def prev(self):
        if not self.queue:
            return
        self.index = (self.index - 1) % len(self.queue)
        self._play_current()

    def stop(self):
        self._stream_watchdog.stop()
        self._stream_retry_timer.stop()
        self._set_buffering(False)
        self.player.stop()
        self.player.setSource(QUrl())
        self.queue = []
        self.index = -1
        self._current_id = None
        self.context_name = None
        self._user_paused = False
        self._stream_error_count = 0
        self.track_changed.emit({})

    def set_volume(self, v: float):
        self.audio.setVolume(max(0.0, min(1.0, v)))

    def volume(self) -> float:
        return self.audio.volume()

    def seek(self, pos_ms: int):
        self.player.setPosition(pos_ms)

    def current_track(self) -> Optional[Dict]:
        if 0 <= self.index < len(self.queue):
            return self.queue[self.index]
        return None