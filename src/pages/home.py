from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget)

from core.api import ApiClient
from core.i18n import Translator, tr
from src.pages.shared import ApiThread
from src.player import Player
from src.widgets import ResponsiveGrid, SectionWidget, TrackCard


class HomePage(QWidget):
    edit_track = Signal(dict)
    delete_track = Signal(dict)
    open_track = Signal(str)

    def __init__(self, api: ApiClient, player: Player, main, parent=None):
        super().__init__(parent)
        self.api = api
        self.player = player
        self.main = main
        self._loading = False
        self._thread = None

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(24, 24, 24, 24)
        iv.setSpacing(32)
        iv.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.rec_section = SectionWidget(tr('home.recommendations'))
        self.new_section = SectionWidget(tr('home.new_releases'))
        self.pop_section = SectionWidget(tr('home.popular_month'))

        iv.addWidget(self.rec_section)
        iv.addWidget(self.new_section)
        iv.addWidget(self.pop_section)

        self.scroll.setWidget(inner)
        v.addWidget(self.scroll)

        Translator.instance().language_changed.connect(self.retranslate)

    def retranslate(self):
        self.rec_section.set_title(tr('home.recommendations'))
        self.new_section.set_title(tr('home.new_releases'))
        self.pop_section.set_title(tr('home.popular_month'))

    def refresh(self):
        if self._loading:
            return
        self._loading = True
        self._thread = ApiThread(self._fetch_all)
        self._thread.done.connect(self._on_loaded)
        self._thread.failed.connect(self._on_failed)
        self._thread.start()

    def _fetch_all(self):
        with ThreadPoolExecutor(max_workers=3) as ex:
            f_recs = ex.submit(self.api.recommendations, 32)
            f_new = ex.submit(self.api.list_tracks, page=1, per_page=16, sort='new')
            f_pop = ex.submit(self.api.list_tracks, page=1, per_page=16, sort='popular')
            return (f_recs.result(), f_new.result(), f_pop.result())

    def _on_loaded(self, data):
        self._loading = False
        recs, new_data, pop_data = data
        self.rec_section.set_tracks(recs, self.api, self.player.play_track,
                                    self.edit_track.emit, self.delete_track.emit, self.open_track.emit)
        self.new_section.set_tracks(new_data.get('items', []), self.api, self.player.play_track,
                                    self.edit_track.emit, self.delete_track.emit, self.open_track.emit)
        self.pop_section.set_tracks(pop_data.get('items', []), self.api, self.player.play_track,
                                    self.edit_track.emit, self.delete_track.emit, self.open_track.emit)

    def _on_failed(self, err):
        self._loading = False


class GridPage(QWidget):
    edit_track = Signal(dict)
    delete_track = Signal(dict)
    open_track = Signal(str)

    def __init__(self, api: ApiClient, player: Player, main, title_key: str, fetch_func, parent=None):
        super().__init__(parent)
        self.api = api
        self.player = player
        self.main = main
        self.fetch_func = fetch_func
        self.title_key = title_key
        self.page = 1
        self.total_pages = 1
        self.loading = False
        self.thread = None

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        self.title_label = QLabel(tr(title_key))
        self.title_label.setObjectName('PageTitle')
        v.addWidget(self.title_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.inner = QWidget()
        iv = QVBoxLayout(self.inner)
        iv.setContentsMargins(0, 0, 0, 0)

        self.grid = ResponsiveGrid()
        iv.addWidget(self.grid)

        self.scroll.setWidget(self.inner)
        v.addWidget(self.scroll)

        self.status = QLabel('')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setObjectName('StatusText')
        v.addWidget(self.status)

        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)

        Translator.instance().language_changed.connect(self.retranslate)

    def retranslate(self):
        self.title_label.setText(tr(self.title_key))

    def clear(self):
        self.grid.clear()
        self.inner.updateGeometry()

    def refresh(self):
        self.page = 1
        self.total_pages = 1
        self.loading = False
        self.clear()
        self.load_page()

    def _on_scroll(self, value):
        if self.loading or self.page > self.total_pages:
            return
        sb = self.scroll.verticalScrollBar()
        if value >= sb.maximum() - 150:
            self.load_page()

    def load_page(self):
        if self.loading:
            return
        self.loading = True
        self.status.setText(tr('common.loading'))
        
        t = ApiThread(self.fetch_func, self.page, 20)
        t.done.connect(self._on_loaded)
        t.failed.connect(self._on_error)
        t.start()

    def _on_loaded(self, data):
        self.loading = False
        items = data.get('items', [])
        self.total_pages = data.get('pages', 1)
        self.page = data.get('page', 1) + 1
        for t in items:
            card = TrackCard(t, self.api)
            card.play_requested.connect(self.player.play_track)
            card.clicked.connect(self.open_track.emit)
            card.edit_requested.connect(self.edit_track.emit)
            card.delete_requested.connect(self.delete_track.emit)
            self.grid.add_widget(card)
        self.inner.updateGeometry()
        self.status.setText(tr('grid.loaded_count', count=self.grid.grid.count()))

    def _on_error(self, err):
        self.loading = False
        self.status.setText(tr('common.error_prefix', message=err))


class NewReleasesPage(GridPage):
    def __init__(self, api, player, main, parent=None):
        super().__init__(api, player, main, 'grid.new_releases_title',
                         lambda p, pp: api.list_tracks(p, pp, sort='new'), parent)


class PopularPage(GridPage):
    def __init__(self, api, player, main, parent=None):
        super().__init__(api, player, main, 'grid.popular_title',
                         lambda p, pp: api.list_tracks(p, pp, sort='popular'), parent)