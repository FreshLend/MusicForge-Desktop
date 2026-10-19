from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout)

from core.api import ApiClient, ApiError
from core.i18n import tr


class EditTrackDialog(QDialog):
    updated = Signal()

    def __init__(self, api: ApiClient, track: dict, parent=None):
        super().__init__(parent)
        self.api = api
        self.track = track
        self.setWindowTitle(tr('edit_track.title'))
        self.setMinimumWidth(500)

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        f = QFormLayout()
        self.title_input = QLineEdit(track.get('title', ''))

        artist_value = track.get('artist', '') or ''
        my_name = (self.api.user or {}).get('display_name') or ''
        if artist_value and my_name and artist_value == my_name:
            artist_value = ''
        self.artist_input = QLineEdit(artist_value)

        tags_str = ', '.join(track.get('tags', []))
        self.tags_input = QLineEdit(tags_str)

        self.is_ai = QCheckBox(tr('edit_track.is_ai'))
        self.is_ai.setChecked(track.get('is_ai', False))

        self.cover_input = QLineEdit()
        self.cover_input.setReadOnly(True)
        b_cover = QPushButton(tr('common.choose'))
        b_cover.clicked.connect(self._pick_cover)
        row_cover = QHBoxLayout()
        row_cover.addWidget(self.cover_input, 1)
        row_cover.addWidget(b_cover)

        self.lyrics_input = QLineEdit()
        self.lyrics_input.setReadOnly(True)
        b_lyrics = QPushButton(tr('common.choose'))
        b_lyrics.clicked.connect(self._pick_lyrics)
        row_lyrics = QHBoxLayout()
        row_lyrics.addWidget(self.lyrics_input, 1)
        row_lyrics.addWidget(b_lyrics)

        f.addRow(tr('edit_track.title_label'), self.title_input)
        f.addRow(tr('edit_track.artist_label'), self.artist_input)
        f.addRow(tr('edit_track.tags'), self.tags_input)
        f.addRow('', self.is_ai)
        f.addRow(tr('edit_track.new_cover'), row_cover)
        f.addRow(tr('edit_track.new_lyrics'), row_lyrics)

        v.addLayout(f)

        self.status = QLabel('')
        self.status.setObjectName('StatusText')
        v.addWidget(self.status)

        btn_save = QPushButton(tr('common.save'))
        btn_save.setObjectName('PrimaryBtn')
        btn_save.clicked.connect(self._save)
        v.addWidget(btn_save)

    def _pick_cover(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('dialog.select_cover'), '', tr('dialog.images_filter'))
        if path:
            self.cover_input.setText(path)

    def _pick_lyrics(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('dialog.select_lyrics'), '', tr('dialog.srt_filter'))
        if path:
            self.lyrics_input.setText(path)

    def _save(self):
        data = {
            'title': self.title_input.text().strip(),
            'artist_name': self.artist_input.text().strip(),
            'tags': self.tags_input.text().strip(),
            'is_ai': 'true' if self.is_ai.isChecked() else 'false'
        }
        cover_path = self.cover_input.text().strip() or None
        lyrics_path = self.lyrics_input.text().strip() or None
        self.status.setText(tr('common.saving'))
        try:
            self.api.update_track(self.track['id'], data, cover_path, lyrics_path)
            self.updated.emit()
            self.accept()
        except ApiError as e:
            self.status.setText(tr('common.error_prefix', message=e.message))
        except Exception as e:
            self.status.setText(tr('common.error_prefix', message=str(e)))