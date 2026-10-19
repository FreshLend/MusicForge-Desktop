from typing import Dict, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget)

from core.api import ApiClient, ApiError
from core.i18n import Translator, tr
from src.pages.shared import show_error
from src.player import Player
from src.widgets import TrackRow


class HistoryPage(QWidget):
    def __init__(self, api: ApiClient, player: Player, main, parent=None):
        super().__init__(parent)
        self.api = api
        self.player = player
        self.main = main
        self.items: List[Dict] = []

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        self.title_label = QLabel(tr('history.title'))
        self.title_label.setObjectName('PageTitle')
        v.addWidget(self.title_label)

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

        self.status = QLabel('')
        self.status.setObjectName('StatusText')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        v.addWidget(self.status)

        Translator.instance().language_changed.connect(self.retranslate)

    def retranslate(self):
        self.title_label.setText(tr('history.title'))

    def refresh(self):
        try:
            items = self.api.history()
        except Exception as e:
            self.status.setText(tr('common.error_prefix', message=str(e)))
            return
        self.items = items
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        tracks_flat = [it['track'] for it in items]
        for i, it in enumerate(items):
            t = it['track']
            row = TrackRow(t, self.api, index=i + 1, show_fav=False,
                           show_history_delete=True, show_edit_delete=False)
            row.play_requested.connect(lambda tr_, idx=i: self.player.play_queue(tracks_flat, idx))
            row.history_delete_requested.connect(self._delete)
            self.list_layout.addWidget(row)
        self.status.setText(tr('history.count', count=len(items)))

    def _delete(self, track: Dict):
        try:
            self.api.history_delete(track['id'])
        except ApiError as e:
            show_error(self, e.message)
            return
        self.refresh()