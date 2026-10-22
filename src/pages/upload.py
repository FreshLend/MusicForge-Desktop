from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)

from core.api import ApiClient, ApiError
from core.i18n import tr


class UploadThread(QThread):
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, api: ApiClient, mode: str, kwargs: dict):
        super().__init__()
        self.api = api
        self.mode = mode
        self.kwargs = kwargs

    def run(self):
        try:
            if self.mode == 'file':
                r = self.api.upload_track_file(**self.kwargs)
            else:
                r = self.api.upload_track_youtube(**self.kwargs)
            self.done.emit(r)
        except ApiError as e:
            self.failed.emit(e.message)
        except Exception as e:
            self.failed.emit(str(e))


class UploadDialog(QDialog):
    uploaded = Signal(dict)

    def __init__(self, api: ApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self.setWindowTitle(tr('upload.title'))
        self.setMinimumWidth(520)
        self._thread: Optional[UploadThread] = None

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_file_tab(), tr('upload.tab_file'))
        self.tabs.addTab(self._build_youtube_tab(), tr('upload.tab_youtube'))
        v.addWidget(self.tabs)

        self.status = QLabel('')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setObjectName('StatusText')
        self.status.setWordWrap(True)
        v.addWidget(self.status)

    def _build_file_tab(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.f_title = QLineEdit()
        self.f_artist = QLineEdit()
        self.f_tags = QLineEdit()
        self.f_is_ai = QCheckBox(tr('upload.is_ai'))

        self.f_audio = QLineEdit()
        self.f_audio.setReadOnly(True)
        b_audio = QPushButton(tr('common.choose'))
        b_audio.clicked.connect(lambda: self._pick(self.f_audio, tr('upload.filter_audio')))
        row_audio = QHBoxLayout()
        row_audio.addWidget(self.f_audio, 1)
        row_audio.addWidget(b_audio)

        self.f_cover = QLineEdit()
        self.f_cover.setReadOnly(True)
        b_cover = QPushButton(tr('common.choose'))
        b_cover.clicked.connect(lambda: self._pick(self.f_cover, tr('upload.filter_image')))
        row_cover = QHBoxLayout()
        row_cover.addWidget(self.f_cover, 1)
        row_cover.addWidget(b_cover)

        self.f_video = QLineEdit()
        self.f_video.setReadOnly(True)
        b_video = QPushButton(tr('common.choose'))
        b_video.clicked.connect(lambda: self._pick(self.f_video, tr('upload.filter_video')))
        row_video = QHBoxLayout()
        row_video.addWidget(self.f_video, 1)
        row_video.addWidget(b_video)

        self.f_lyrics = QLineEdit()
        self.f_lyrics.setReadOnly(True)
        b_lyrics = QPushButton(tr('common.choose'))
        b_lyrics.clicked.connect(lambda: self._pick(self.f_lyrics, tr('upload.filter_srt')))
        row_lyrics = QHBoxLayout()
        row_lyrics.addWidget(self.f_lyrics, 1)
        row_lyrics.addWidget(b_lyrics)

        f.addRow(tr('upload.title_label'), self.f_title)
        f.addRow(tr('upload.artist_label'), self.f_artist)
        f.addRow(tr('upload.tags'), self.f_tags)
        f.addRow('', self.f_is_ai)
        f.addRow(tr('upload.audio_required'), row_audio)
        f.addRow(tr('upload.cover'), row_cover)
        f.addRow(tr('upload.video'), row_video)
        f.addRow(tr('upload.lyrics'), row_lyrics)

        btn = QPushButton(tr('upload.upload'))
        btn.setObjectName('PrimaryBtn')
        btn.clicked.connect(self._upload_file)
        f.addRow('', btn)
        return w

    def _build_youtube_tab(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.y_url = QLineEdit()
        self.y_url.setPlaceholderText(tr('upload.youtube_placeholder'))
        self.y_title = QLineEdit()
        self.y_artist = QLineEdit()
        self.y_tags = QLineEdit()
        self.y_is_ai = QCheckBox(tr('upload.is_ai'))

        self.y_lyrics = QLineEdit()
        self.y_lyrics.setReadOnly(True)
        b_lyrics = QPushButton(tr('common.choose'))
        b_lyrics.clicked.connect(lambda: self._pick(self.y_lyrics, tr('upload.filter_srt')))
        row_lyrics = QHBoxLayout()
        row_lyrics.addWidget(self.y_lyrics, 1)
        row_lyrics.addWidget(b_lyrics)

        f.addRow(tr('upload.youtube_url'), self.y_url)
        f.addRow(tr('upload.title_label'), self.y_title)
        f.addRow(tr('upload.artist_label'), self.y_artist)
        f.addRow(tr('upload.tags'), self.y_tags)
        f.addRow('', self.y_is_ai)
        f.addRow(tr('upload.lyrics'), row_lyrics)

        btn = QPushButton(tr('upload.upload_youtube'))
        btn.setObjectName('PrimaryBtn')
        btn.clicked.connect(self._upload_youtube)
        f.addRow('', btn)
        return w

    def _pick(self, field: QLineEdit, filter_str: str):
        path, _ = QFileDialog.getOpenFileName(self, tr('upload.choose_file'), '', filter_str)
        if path:
            field.setText(path)

    def _upload_file(self):
        audio = self.f_audio.text().strip()
        if not audio:
            self.status.setText(tr('upload.choose_audio'))
            return
        title = self.f_title.text().strip()
        if not title:
            import os
            title = os.path.splitext(os.path.basename(audio))[0]
        kwargs = {
            'title': title,
            'artist_name': self.f_artist.text().strip(),
            'tags': self.f_tags.text().strip(),
            'is_ai': self.f_is_ai.isChecked(),
            'audio_path': audio,
            'cover_path': self.f_cover.text().strip() or None,
            'cover_video_path': self.f_video.text().strip() or None,
            'lyrics_path': self.f_lyrics.text().strip() or None,
        }
        self._start('file', kwargs)

    def _upload_youtube(self):
        url = self.y_url.text().strip()
        if not url:
            self.status.setText(tr('upload.enter_url'))
            return
        kwargs = {
            'youtube_url': url,
            'title': self.y_title.text().strip(),
            'artist_name': self.y_artist.text().strip(),
            'tags': self.y_tags.text().strip(),
            'is_ai': self.y_is_ai.isChecked(),
            'lyrics_path': self.y_lyrics.text().strip() or None,
        }
        self._start('youtube', kwargs)

    def _start(self, mode: str, kwargs: dict):
        self.status.setText(tr('upload.uploading'))
        self._thread = UploadThread(self.api, mode, kwargs)
        self._thread.done.connect(self._on_done)
        self._thread.failed.connect(self._on_fail)
        self._thread.start()

    def _on_done(self, track: dict):
        self.status.setText(tr('upload.done', title=track.get('title', '')))
        self.uploaded.emit(track)
        self.accept()

    def _on_fail(self, err: str):
        self.status.setText(tr('common.error_prefix', message=err))