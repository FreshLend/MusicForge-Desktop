from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, QSettings
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class Player(QObject):
    track_changed = Signal(dict)
    state_changed = Signal(bool)
    position_changed = Signal(int, int)
    volume_changed = Signal(float)

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

        self.audio.volumeChanged.connect(self._on_volume_changed)

        self.queue: List[Dict] = []
        self.index: int = -1
        self.context_name: Optional[str] = None
        self._listen_reported: set = set()
        self._current_id: Optional[str] = None
        self._listen_timer = QTimer(self)
        self._listen_timer.setInterval(2000)
        self._listen_timer.timeout.connect(self._maybe_report)

    def _on_volume_changed(self):
        self.settings.setValue("volume", self.audio.volume())
        self.volume_changed.emit(self.audio.volume())

    def _on_status(self, status):
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
        if self.player.position() >= 15000:
            tid = self._current_id
            if tid not in self._listen_reported:
                self._listen_reported.add(tid)
                try:
                    self.api.track_listen(tid)
                except Exception as e:
                    print(f"listen report failed: {e}")
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

    def _play_current(self):
        if self.index < 0 or self.index >= len(self.queue):
            return
        track = self.queue[self.index]
        tid = track.get('id')
        url = track.get('audio_url') or self.api.stream_url(tid)
        url = self.api.absolute(url)
        self._current_id = tid
        self.player.setSource(QUrl(url))
        self.player.play()
        self.track_changed.emit(track)

    def toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
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
        self.player.stop()
        self.player.setSource(QUrl())
        self.queue = []
        self.index = -1
        self._current_id = None
        self.context_name = None
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