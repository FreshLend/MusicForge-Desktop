from typing import Dict
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget)

from core.api import ApiClient
from core.i18n import Translator, tr
from src.pages.shared import show_error, ApiThread
from src.player import Player
from src.widgets import TrackRow


class HistoryPage(QWidget):
    open_track = Signal(str)

    def __init__(self, api: ApiClient, player: Player, main, parent=None):
        super().__init__(parent)
        self.api = api
        self.player = player
        self.main = main
        self._page = 1
        self._has_more = True
        self._loading = False
        self._items = []

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

        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        Translator.instance().language_changed.connect(self.retranslate)

    def retranslate(self):
        self.title_label.setText(tr('history.title'))

    def refresh(self):
        self._page = 1
        self._has_more = True
        self._items = []
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._load_more()

    def _load_more(self):
        if self._loading or not self._has_more:
            return
        self._loading = True
        self.status.setText(tr('common.loading'))
        
        t = ApiThread(self.api.history, page=self._page, per_page=50)
        t.done.connect(self._on_loaded)
        t.failed.connect(self._on_failed)
        t.start()

    def _on_failed(self, e):
        self._loading = False
        self.status.setText(tr('common.error_prefix', message=e))

    def _on_loaded(self, data):
        self._loading = False
        items = data.get('items', [])
        self._has_more = data.get('page', 1) < data.get('pages', 1)
        self._page += 1
        
        start_idx = len(self._items)
        self._items.extend(items)
        
        for i, it in enumerate(items):
            actual_idx = start_idx + i
            t = it['track']
            row = TrackRow(t, self.api, index=actual_idx + 1, show_fav=False,
                           show_history_delete=True, show_edit_delete=False)
            row.play_requested.connect(lambda tr_, idx=actual_idx: self.player.play_queue([x['track'] for x in self._items], idx))
            row.history_delete_requested.connect(self._delete)
            row.clicked.connect(self.open_track.emit)
            self.list_layout.addWidget(row)
            
        self.inner.updateGeometry()
        self.status.setText(tr('history.count', count=len(self._items)))

    def _on_scroll(self, value):
        if self._loading or not self._has_more:
            return
        sb = self.scroll.verticalScrollBar()
        if value >= sb.maximum() - 150:
            self._load_more()

    def _delete(self, track: Dict):
        t = ApiThread(self.api.history_delete, track['id'])
        t.done.connect(lambda _: self.refresh())
        t.failed.connect(lambda e: show_error(self, e))
        t.start()