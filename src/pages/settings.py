from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout,
                               QWidget)

from core.api import ApiClient, is_secure_url, normalize_base_url
from core.i18n import LANGUAGE_NAMES, Translator, tr
from src.pages.shared import apply_busy_cursor, ask_yes_no, show_error, show_info
from src.player import Player


class SettingsPage(QWidget):
    logout_requested = Signal()

    def __init__(self, api: ApiClient, player: Player, main, parent=None):
        super().__init__(parent)
        self.api = api
        self.player = player
        self.main = main

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        title_row = QHBoxLayout()
        self.title_label = QLabel(tr('settings.title'))
        self.title_label.setObjectName('PageTitle')
        title_row.addWidget(self.title_label)

        self.http_badge = QLabel(tr('settings.insecure_badge'))
        self.http_badge.setObjectName('InsecureBadge')
        self.http_badge.setToolTip(tr('settings.insecure_tooltip'))
        self.http_badge.hide()
        title_row.addWidget(self.http_badge)
        title_row.addStretch()
        v.addLayout(title_row)

        self.account_label = QLabel('')
        self.account_label.setObjectName('ProfileInfo')
        self.account_label.setWordWrap(True)
        self.account_label.setTextFormat(Qt.TextFormat.PlainText)
        v.addWidget(self.account_label)

        form = QFormLayout()
        self.server_label = QLabel(tr('settings.server'))
        self.server_edit = QLineEdit(self.api.base_url)
        form.addRow(self.server_label, self.server_edit)

        self.language_label = QLabel(tr('common.language'))
        self.lang_combo = QComboBox()
        for code in Translator.instance().available():
            self.lang_combo.addItem(LANGUAGE_NAMES.get(code, code), code)
        idx = self.lang_combo.findData(Translator.instance().current())
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        form.addRow(self.language_label, self.lang_combo)

        self.rpc_checkbox = QCheckBox(tr('settings.discord_rpc'))
        self.rpc_checkbox.setChecked(self.main.discord_rpc.is_enabled())
        self.rpc_checkbox.toggled.connect(self.main.discord_rpc.set_enabled)
        form.addRow(self.rpc_checkbox)

        v.addLayout(form)

        self.change_server_btn = QPushButton(tr('settings.change_server'))
        self.change_server_btn.setObjectName('PrimaryBtn')
        self.change_server_btn.clicked.connect(self._save_server)
        v.addWidget(self.change_server_btn)

        v.addSpacing(20)

        self.logout_btn = QPushButton(tr('settings.logout'))
        self.logout_btn.setObjectName('DangerBtn')
        self.logout_btn.clicked.connect(self._logout)
        v.addWidget(self.logout_btn)

        v.addStretch()

        Translator.instance().language_changed.connect(self.retranslate)

    def retranslate(self):
        self.title_label.setText(tr('settings.title'))
        self.server_label.setText(tr('settings.server'))
        self.language_label.setText(tr('common.language'))
        self.change_server_btn.setText(tr('settings.change_server'))
        self.logout_btn.setText(tr('settings.logout'))
        self.http_badge.setText(tr('settings.insecure_badge'))
        self.http_badge.setToolTip(tr('settings.insecure_tooltip'))
        self.rpc_checkbox.setText(tr('settings.discord_rpc'))
        self.refresh()

    def _on_language_changed(self, idx):
        code = self.lang_combo.itemData(idx)
        if code:
            Translator.instance().set_language(code)

    def _save_server(self):
        url = self.server_edit.text().strip()
        if not url:
            return
        try:
            normalized = normalize_base_url(url)
        except ValueError:
            show_error(self, tr('settings.invalid_server'))
            return
        if normalized == self.api.base_url:
            show_info(self, tr('settings.server_unchanged'))
            return
        if not is_secure_url(normalized):
            if not ask_yes_no(self, tr('settings.security_title'),
                              tr('settings.insecure_warning')):
                return
        with apply_busy_cursor():
            reachable = self.api.health_check(normalized)
        if not reachable:
            if not ask_yes_no(self, tr('settings.server_unreachable_title'),
                              tr('settings.server_unreachable_confirm')):
                return
        self.api.set_base_url(normalized)
        self.logout_requested.emit()

    def _logout(self):
        self.api.logout_and_forget()
        self.logout_requested.emit()

    def refresh(self):
        self.server_edit.setText(self.api.base_url)
        if self.api.base_url.startswith('https://'):
            self.http_badge.hide()
        else:
            self.http_badge.show()
        me = self.api.user or {}
        login = me.get('login')
        if login:
            self.account_label.setText(tr('settings.current_account', login=login, url=self.api.base_url))
        else:
            self.account_label.setText(tr('settings.current_server', url=self.api.base_url))