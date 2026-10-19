from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QStackedWidget, QTabWidget,
                               QVBoxLayout, QWidget)

from core.api import (ApiClient, ApiError, DEFAULT_BASE_URL, is_secure_url,
                      normalize_base_url)
from core.i18n import LANGUAGE_NAMES, Translator, tr
from src.pages.shared import apply_busy_cursor, ask_yes_no, show_error


class AuthDialog(QDialog):
    authenticated = Signal()

    def __init__(self, api: ApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self.setWindowTitle(tr('auth.window_title'))
        self.setMinimumWidth(520)

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(12)

        self.title_label = QLabel(tr('auth.title'))
        self.title_label.setObjectName('AuthTitle')
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.title_label)

        self.stack = QStackedWidget()
        self.choose_page = self._build_choose_page()
        self.add_page = self._build_add_page()
        self.stack.addWidget(self.choose_page)
        self.stack.addWidget(self.add_page)
        v.addWidget(self.stack)

        self.status = QLabel('')
        self.status.setObjectName('AuthStatus')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        v.addWidget(self.status)

        lang_row = QHBoxLayout()
        lang_row.addStretch()
        self.lang_label = QLabel(tr('common.language'))
        lang_row.addWidget(self.lang_label)
        self.lang_combo = QComboBox()
        for code in Translator.instance().available():
            self.lang_combo.addItem(LANGUAGE_NAMES.get(code, code), code)
        idx = self.lang_combo.findData(Translator.instance().current())
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        lang_row.addWidget(self.lang_combo)
        v.addLayout(lang_row)

        Translator.instance().language_changed.connect(self.retranslate)

        self._refresh_after_change()

    def _on_language_changed(self, idx):
        code = self.lang_combo.itemData(idx)
        if code:
            Translator.instance().set_language(code)

    def _build_choose_page(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        server_row = QHBoxLayout()
        self.server_label = QLabel(tr('settings.server'))
        server_row.addWidget(self.server_label)
        self.server_combo = QComboBox()
        self.server_combo.setEditable(False)
        self.server_combo.currentTextChanged.connect(self._refresh_accounts)
        server_row.addWidget(self.server_combo, 1)
        v.addLayout(server_row)

        self.accounts_list = QListWidget()
        self.accounts_list.setMinimumHeight(160)
        self.accounts_list.itemDoubleClicked.connect(lambda _: self._login_saved())
        v.addWidget(self.accounts_list)

        self.empty_hint = QLabel(tr('auth.no_accounts'))
        self.empty_hint.setObjectName('StatusText')
        self.empty_hint.setWordWrap(True)
        v.addWidget(self.empty_hint)

        row = QHBoxLayout()
        self.use_btn = QPushButton(tr('auth.login'))
        self.use_btn.setObjectName('PrimaryBtn')
        self.use_btn.clicked.connect(self._login_saved)
        self.add_btn = QPushButton(tr('auth.add_account'))
        self.add_btn.setObjectName('GhostBtn')
        self.add_btn.clicked.connect(self._show_add_page_current)
        self.forget_btn = QPushButton(tr('auth.forget_account'))
        self.forget_btn.setObjectName('GhostBtn')
        self.forget_btn.clicked.connect(self._forget_account)
        self.del_server_btn = QPushButton(tr('auth.delete_server'))
        self.del_server_btn.setObjectName('DangerBtn')
        self.del_server_btn.clicked.connect(self._forget_server)
        row.addWidget(self.use_btn)
        row.addWidget(self.add_btn)
        row.addWidget(self.forget_btn)
        row.addWidget(self.del_server_btn)
        v.addLayout(row)
        return w

    def _build_add_page(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        server_row = QHBoxLayout()
        self.server_edit_label = QLabel(tr('settings.server'))
        self.server_edit = QLineEdit(self.api.base_url or DEFAULT_BASE_URL)
        self.server_edit.setPlaceholderText(DEFAULT_BASE_URL)
        self.server_edit.textChanged.connect(self._update_server_hint)
        self.check_btn = QPushButton(tr('auth.check'))
        self.check_btn.setObjectName('GhostBtn')
        self.check_btn.clicked.connect(self._check_server)
        server_row.addWidget(self.server_edit_label)
        server_row.addWidget(self.server_edit, 1)
        server_row.addWidget(self.check_btn)
        v.addLayout(server_row)

        self.server_hint = QLabel('')
        self.server_hint.setObjectName('StatusText')
        self.server_hint.setWordWrap(True)
        self.server_hint.setTextFormat(Qt.TextFormat.PlainText)
        v.addWidget(self.server_hint)

        self.tabs = QTabWidget()
        self.login_tab = self._build_login_tab()
        self.register_tab = self._build_register_tab()
        self.tabs.addTab(self.login_tab, tr('auth.login_tab'))
        self.tabs.addTab(self.register_tab, tr('auth.register_tab'))
        v.addWidget(self.tabs)

        self.back_btn = QPushButton(tr('auth.back_to_accounts'))
        self.back_btn.setObjectName('GhostBtn')
        self.back_btn.clicked.connect(self._show_choose_page)
        v.addWidget(self.back_btn)
        return w

    def _build_login_tab(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.login_input = QLineEdit()
        self.login_input.setPlaceholderText(tr('auth.login_placeholder'))
        self.login_password = QLineEdit()
        self.login_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.login_password.returnPressed.connect(self._do_login)
        self.login_label = QLabel(tr('auth.login_label'))
        self.password_label = QLabel(tr('auth.password'))
        f.addRow(self.login_label, self.login_input)
        f.addRow(self.password_label, self.login_password)
        self.login_btn = QPushButton(tr('auth.login'))
        self.login_btn.setObjectName('PrimaryBtn')
        self.login_btn.clicked.connect(self._do_login)
        f.addRow('', self.login_btn)
        return w

    def _build_register_tab(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.reg_login = QLineEdit()
        self.reg_email = QLineEdit()
        self.reg_password = QLineEdit()
        self.reg_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_password2 = QLineEdit()
        self.reg_password2.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_name = QLineEdit()
        self.reg_name.setPlaceholderText(tr('auth.display_name_placeholder'))
        self.reg_login_label = QLabel(tr('auth.login_label'))
        self.reg_email_label = QLabel(tr('auth.email'))
        self.reg_password_label = QLabel(tr('auth.password'))
        self.reg_password2_label = QLabel(tr('auth.password_repeat'))
        self.reg_name_label = QLabel(tr('auth.name'))
        f.addRow(self.reg_login_label, self.reg_login)
        f.addRow(self.reg_email_label, self.reg_email)
        f.addRow(self.reg_password_label, self.reg_password)
        f.addRow(self.reg_password2_label, self.reg_password2)
        f.addRow(self.reg_name_label, self.reg_name)
        self.reg_btn = QPushButton(tr('auth.register'))
        self.reg_btn.setObjectName('PrimaryBtn')
        self.reg_btn.clicked.connect(self._do_register)
        f.addRow('', self.reg_btn)
        return w

    def retranslate(self):
        self.setWindowTitle(tr('auth.window_title'))
        self.title_label.setText(tr('auth.title'))
        self.lang_label.setText(tr('common.language'))
        self.server_label.setText(tr('settings.server'))
        self.empty_hint.setText(tr('auth.no_accounts'))
        self.use_btn.setText(tr('auth.login'))
        self.add_btn.setText(tr('auth.add_account'))
        self.forget_btn.setText(tr('auth.forget_account'))
        self.del_server_btn.setText(tr('auth.delete_server'))
        self.server_edit_label.setText(tr('settings.server'))
        self.check_btn.setText(tr('auth.check'))
        self.tabs.setTabText(0, tr('auth.login_tab'))
        self.tabs.setTabText(1, tr('auth.register_tab'))
        self.back_btn.setText(tr('auth.back_to_accounts'))
        self.login_input.setPlaceholderText(tr('auth.login_placeholder'))
        self.login_label.setText(tr('auth.login_label'))
        self.password_label.setText(tr('auth.password'))
        self.login_btn.setText(tr('auth.login'))
        self.reg_login_label.setText(tr('auth.login_label'))
        self.reg_email_label.setText(tr('auth.email'))
        self.reg_password_label.setText(tr('auth.password'))
        self.reg_password2_label.setText(tr('auth.password_repeat'))
        self.reg_name_label.setText(tr('auth.name'))
        self.reg_name.setPlaceholderText(tr('auth.display_name_placeholder'))
        self.reg_btn.setText(tr('auth.register'))
        self._refresh_accounts(self.server_combo.currentText() if self.server_combo.count() > 0 else '')

    def _refresh_after_change(self):
        self._refresh_servers()
        servers = self.api.list_servers()
        pending_new = self.api.base_url not in servers
        if pending_new:
            self.back_btn.setVisible(self.api.has_any_account())
            self.server_edit.setText(self.api.base_url)
            self._update_server_hint()
            self.stack.setCurrentWidget(self.add_page)
        elif self.api.has_any_account():
            self.back_btn.setVisible(True)
            self.stack.setCurrentWidget(self.choose_page)
        else:
            self.back_btn.setVisible(False)
            self.server_edit.setText(self.api.base_url or DEFAULT_BASE_URL)
            self._update_server_hint()
            self.stack.setCurrentWidget(self.add_page)

    def _refresh_servers(self):
        servers = self.api.list_servers()
        self.server_combo.blockSignals(True)
        self.server_combo.clear()
        for s in servers:
            self.server_combo.addItem(s)
        if servers:
            idx = self.server_combo.findText(self.api.base_url)
            if idx < 0:
                idx = 0
            self.server_combo.setCurrentIndex(idx)
        self.server_combo.blockSignals(False)
        current = self.server_combo.currentText() if self.server_combo.count() > 0 else ''
        self._refresh_accounts(current)

    def _refresh_accounts(self, server_url: str):
        self.accounts_list.clear()
        if not server_url:
            self.empty_hint.setVisible(True)
            return
        accounts = self.api.list_accounts(server_url)
        is_current_server = server_url == self.api.base_url
        current_uid = self.api.current_user_id() if is_current_server else None
        for acc in accounts:
            login = acc.get('login') or '(без логина)'
            display = acc.get('display_name') or ''
            uid = acc.get('user_id')
            text = f"@{login}"
            if display and display != login:
                text += f" — {display}"
            if current_uid is not None and uid == current_uid:
                text += tr('auth.current_marker')
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, (server_url, uid))
            self.accounts_list.addItem(item)
        self.empty_hint.setVisible(self.accounts_list.count() == 0)

    def _update_server_hint(self):
        known = set(self.api.list_servers())
        url = self.server_edit.text().strip()
        if not url:
            self.server_hint.setText('')
            return
        try:
            normalized = normalize_base_url(url)
        except ValueError:
            self.server_hint.setText(tr('auth.invalid_address'))
            return
        if normalized not in known:
            self.server_hint.setText(tr('auth.new_server', url=normalized))
        else:
            self.server_hint.setText('')

    def _show_choose_page(self):
        if not self.api.has_any_account():
            return
        self._refresh_servers()
        self.stack.setCurrentWidget(self.choose_page)

    def _show_add_page_current(self):
        known = set(self.api.list_servers())
        current = self.server_combo.currentText() if self.server_combo.count() > 0 else ''
        if self.api.base_url and self.api.base_url not in known:
            target = self.api.base_url
        else:
            target = current or self.api.base_url or DEFAULT_BASE_URL
        self.login_input.clear()
        self.login_password.clear()
        self.server_edit.setText(target)
        self._update_server_hint()
        self.back_btn.setVisible(self.api.has_any_account())
        self.stack.setCurrentWidget(self.add_page)

    def _login_saved(self):
        item = self.accounts_list.currentItem()
        if not item:
            self.status.setText(tr('auth.choose_account'))
            return
        server_url, user_id = item.data(Qt.ItemDataRole.UserRole)
        with apply_busy_cursor():
            if not self.api.switch_account(server_url, user_id):
                self.status.setText(tr('auth.account_select_failed'))
                return
            try:
                self.api.me()
            except ApiError as e:
                if e.status == 401:
                    self.status.setText(tr('auth.token_invalid', message=e.message))
                    self.api.remove_account(server_url, user_id)
                    self._refresh_after_change()
                else:
                    self.status.setText(tr('common.error_prefix', message=e.message))
                return
            except Exception as e:
                self.status.setText(tr('common.error_prefix', message=str(e)))
                return
        self.authenticated.emit()
        self.accept()

    def _forget_account(self):
        item = self.accounts_list.currentItem()
        if not item:
            self.status.setText(tr('auth.choose_account'))
            return
        server_url, user_id = item.data(Qt.ItemDataRole.UserRole)
        is_current = (server_url == self.api.base_url
                      and user_id is not None
                      and self.api.current_user_id() == user_id)
        marker = tr('auth.current_marker') if is_current else ''
        if not ask_yes_no(self, tr('auth.forget_account_title'),
                          tr('auth.forget_account_confirm', marker=marker)):
            return
        self.api.remove_account(server_url, user_id)
        self._refresh_after_change()

    def _forget_server(self):
        url = self.server_combo.currentText() if self.server_combo.count() > 0 else ''
        if not url:
            return
        accounts = self.api.list_accounts(url)
        is_current = url == self.api.base_url
        marker = tr('auth.current_marker') if is_current else ''
        if not ask_yes_no(self, tr('auth.delete_server_title'),
                          tr('auth.delete_server_confirm', url=url, marker=marker, count=len(accounts))):
            return
        self.api.remove_server(url)
        self._refresh_after_change()

    def _check_server(self):
        url = self.server_edit.text().strip()
        if not url:
            return
        try:
            normalized = normalize_base_url(url)
        except ValueError:
            self.status.setText(tr('auth.invalid_address'))
            return
        with apply_busy_cursor():
            ok = self.api.health_check(normalized)
        self.status.setText(tr('auth.server_ok') if ok else tr('auth.server_unreachable'))

    def _sync_server(self) -> bool:
        url = self.server_edit.text().strip() or DEFAULT_BASE_URL
        try:
            normalized = normalize_base_url(url)
        except ValueError:
            self.status.setText(tr('auth.invalid_address'))
            return False
        if not is_secure_url(normalized):
            if not ask_yes_no(self, tr('auth.security_title'),
                              tr('auth.insecure_warning')):
                return False
        if self.api.base_url != normalized:
            self.api.set_base_url(normalized)
        return True

    def _do_login(self):
        if not self._sync_server():
            return
        login = self.login_input.text().strip()
        password = self.login_password.text()
        if not login or not password:
            self.status.setText(tr('auth.enter_login_password'))
            return
        with apply_busy_cursor():
            try:
                self.api.login(login, password)
            except ApiError as e:
                self.login_password.clear()
                self.status.setText(tr('common.error_prefix', message=e.message))
                return
            except Exception as e:
                self.login_password.clear()
                self.status.setText(tr('common.network_error', message=str(e)))
                return
        self.login_password.clear()
        self.authenticated.emit()
        self.accept()

    def _do_register(self):
        if not self._sync_server():
            return
        login = self.reg_login.text().strip()
        email = self.reg_email.text().strip()
        pwd = self.reg_password.text()
        pwd2 = self.reg_password2.text()
        name = self.reg_name.text().strip()
        if not login or not email or not pwd:
            self.status.setText(tr('auth.fill_required'))
            return
        if len(pwd) < 8:
            self.status.setText(tr('auth.password_too_short'))
            return
        if pwd != pwd2:
            self.status.setText(tr('auth.passwords_dont_match'))
            return
        with apply_busy_cursor():
            try:
                self.api.register(login, email, pwd, name)
            except ApiError as e:
                self.reg_password.clear()
                self.reg_password2.clear()
                self.status.setText(tr('common.error_prefix', message=e.message))
                return
            except Exception as e:
                self.reg_password.clear()
                self.reg_password2.clear()
                self.status.setText(tr('common.network_error', message=str(e)))
                return
        self.reg_password.clear()
        self.reg_password2.clear()
        self.authenticated.emit()
        self.accept()