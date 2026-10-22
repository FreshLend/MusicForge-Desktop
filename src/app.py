import os
import sys

os.environ["QT_LOGGING_RULES"] = "qt.multimedia.*=false;*.debug=false;*.info=false"
os.environ["QT_FFMPEG_DEBUG"] = "0"

from PySide6.QtCore import QSettings, qInstallMessageHandler, QtMsgType, Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (QApplication, QDialog, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QProgressBar, QFrame)

from core.api import ApiClient, load_saved_base_url, get_app_icon_path
from core.i18n import Translator, tr
from src.auth import AuthDialog
from src.main_window import MainWindow


class FilteredStderr:
    def __init__(self, original):
        self.original = original
        self.ignore_patterns = [
            "Input #0", "Metadata:", "Stream #0", "[mp3float",
            "[aac", "[h264", "qt.multimedia", "Could not update timestamps"
        ]

    def write(self, text):
        if not any(p in text for p in self.ignore_patterns):
            self.original.write(text)

    def flush(self):
        self.original.flush()


sys.stderr = FilteredStderr(sys.stderr)


def qt_message_handler(mode, context, message):
    if "Could not update timestamps" in message:
        return
    if "FFmpeg log:" in message:
        return
    if mode == QtMsgType.QtInfoMsg:
        pass
    elif mode == QtMsgType.QtWarningMsg:
        print(f"Qt Warning: {message}", file=sys.stderr)
    elif mode == QtMsgType.QtCriticalMsg:
        print(f"Qt Critical: {message}", file=sys.stderr)
    elif mode == QtMsgType.QtFatalMsg:
        print(f"Qt Fatal: {message}", file=sys.stderr)
    else:
        print(f"Qt Debug: {message}", file=sys.stderr)


qInstallMessageHandler(qt_message_handler)


class SplashScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.SplashScreen)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(400, 220)
        
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.center() - self.rect().center())
        
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        
        container = QFrame()
        container.setObjectName("SplashContainer")
        outer.addWidget(container)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 40, 32, 40)
        layout.setSpacing(16)
        
        title_row = QHBoxLayout()
        title_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        app_icon = QIcon(get_app_icon_path())
        if not app_icon.isNull():
            icon_label = QLabel()
            icon_label.setPixmap(app_icon.pixmap(40, 40))
            title_row.addWidget(icon_label)
            
        title = QLabel("MusicForge")
        title.setStyleSheet("color: #ffffff; font-size: 28px; font-weight: 800; font-family: 'Inter', 'Segoe UI'; background: transparent; border: none;")
        title_row.addWidget(title)
        
        layout.addLayout(title_row)
        layout.addSpacing(10)
        
        self.status = QLabel(tr('splash.starting'))
        self.status.setStyleSheet("color: #00d4ff; font-size: 14px; font-family: 'Inter', 'Segoe UI'; background: transparent; border: none;")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)
        
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setStyleSheet("""
            QProgressBar { border: none; background: #1a1a28; border-radius: 2px; }
            QProgressBar::chunk { background: #00d4ff; border-radius: 2px; }
        """)
        layout.addWidget(self.progress)
        layout.addStretch()
        
        self.setStyleSheet("""
            QFrame#SplashContainer {
                background-color: #0d0d16;
                border: 1px solid #1a1a28;
                border-radius: 12px;
            }
        """)

    def set_status(self, text: str):
        self.status.setText(text)
        QApplication.processEvents()


STYLE = """
QWidget {
    background: #0b0b14;
    color: #f0f0f5;
    font-family: 'Inter', 'Segoe UI', sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog { background: #0b0b14; }

QPushButton {
    background: #12121f;
    border: 1px solid #222236;
    border-radius: 8px;
    padding: 6px 14px;
    color: #f0f0f5;
}
QPushButton:hover { border-color: #00d4ff; color: #00d4ff; }
QPushButton:pressed { background: #1a1a28; }

QPushButton#PrimaryBtn {
    background: #00d4ff; color: #0b0b14; border: none; font-weight: 600;
}
QPushButton#PrimaryBtn:hover { background: #66e0ff; }
QPushButton#DangerBtn {
    background: transparent; color: #ff6b6b; border: 1px solid #55222e;
}
QPushButton#DangerBtn:hover { background: #2a0f14; }
QPushButton#GhostBtn {
    background: transparent; border: 1px solid #222236;
}
QPushButton#GhostBtn:hover { border-color: #00d4ff; color: #00d4ff; }

QLineEdit, QComboBox, QSpinBox {
    background: #12121f; border: 1px solid #222236; border-radius: 8px;
    padding: 6px 10px; color: #f0f0f5;
}
QLineEdit:focus { border-color: #00d4ff; }
QCheckBox { color: #f0f0f5; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid #222236; background: #12121f; }
QCheckBox::indicator:checked { background: #00d4ff; border-color: #00d4ff; }

QTabWidget::pane { border: none; }
QTabBar::tab {
    background: transparent; color: #a8a8c0; padding: 6px 14px;
    border-radius: 8px; margin-right: 4px;
}
QTabBar::tab:selected { background: #1a1a28; color: #00d4ff; }
QTabBar::tab:hover:!selected { color: #f0f0f5; }

QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #12121f; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #2a2a3e; border-radius: 4px; min-height: 20px; }
QScrollBar::handle:vertical:hover { background: #00d4ff; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #12121f; height: 8px; margin: 0; }
QScrollBar::handle:horizontal { background: #2a2a3e; border-radius: 4px; min-width: 20px; }
QScrollBar::handle:horizontal:hover { background: #00d4ff; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QFrame#TrackCard {
    background: #12121f;
    border: 1px solid transparent;
    border-radius: 12px;
}
QFrame#TrackCard:hover {
    background: #1a1a2e;
    border-color: #00d4ff;
}
QLabel#TrackTitle { color: #f0f0f5; font-weight: 600; background: transparent; border: none; }
QLabel#TrackArtist { color: #a8a8c0; background: transparent; border: none; }
QPushButton#CardPlayBtn {
    background: #00d4ff; color: #0b0b14; border: none;
    border-radius: 17px; font-weight: bold;
}
QPushButton#CardPlayBtn:hover { background: #66e0ff; }

QFrame#TrackRow {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
}
QFrame#TrackRow:hover {
    background: #12121f;
    border-color: #222236;
}
QLabel#TrackRowTitle { color: #f0f0f5; font-weight: 600; background: transparent; border: none; }
QLabel#TrackRowArtist { color: #a8a8c0; font-size: 12px; background: transparent; border: none; }
QLabel#TrackIndex { color: #6e6e8a; background: transparent; border: none; }

QPushButton#RowBtn {
    background: transparent; border: none; border-radius: 8px;
}
QPushButton#RowBtn:hover { background: #2a2a3e; }
QPushButton#RowBtnDanger {
    background: transparent; border: none; border-radius: 8px;
}
QPushButton#RowBtnDanger:hover { background: #2a0f14; }

QFrame#PlaylistCard {
    background: #12121f;
    border: 1px solid transparent;
    border-radius: 12px;
}
QFrame#PlaylistCard:hover {
    background: #1a1a2e;
    border-color: #00d4ff;
}
QLabel#PlaylistName { color: #00d4ff; font-size: 16px; font-weight: 700; background: transparent; border: none; }
QLabel#PlaylistMeta { color: #a8a8c0; font-size: 12px; background: transparent; border: none; }
QLabel#PlaylistVisibility { color: #6e6e8a; font-size: 11px; background: transparent; border: none; }

QLabel#PageTitle {
    color: #00d4ff; font-size: 24px; font-weight: 800;
    padding-bottom: 4px;
}
QLabel#SectionTitle {
    color: #f0f0f5; font-size: 20px; font-weight: 700;
}
QLabel#StatusText { color: #a8a8c0; font-size: 12px; }

QLabel#AuthTitle { color: #00d4ff; font-size: 26px; font-weight: 700; }
QLabel#AuthStatus { color: #ff9a9a; }

QWidget#Sidebar { background: #0d0d16; border-right: 1px solid #1a1a28; }
QLabel#SidebarLogo { background: transparent; padding: 0px; font-size: 20px; font-weight: 800; }
QPushButton#SidebarBtn {
    text-align: left; padding: 10px 14px;
    background: transparent; border: none; border-radius: 8px;
    color: #a8a8c0;
}
QPushButton#SidebarBtn:hover { background: #12121f; color: #f0f0f5; }
QPushButton#SidebarBtn:checked { background: #00d4ff; color: #0b0b14; font-weight: 700; }
QPushButton#SidebarUploadBtn {
    background: #00d4ff; color: #0b0b14; border: none;
    border-radius: 8px; padding: 10px; font-weight: 700;
}
QPushButton#SidebarUploadBtn:hover { background: #66e0ff; }

QWidget#PlayerBar { background: #0d0d16; border-top: 1px solid #1a1a28; }
QLabel#PlayerTitle { color: #f0f0f5; font-weight: 600; }
QLabel#PlayerArtist { color: #a8a8c0; font-size: 12px; }
QLabel#PlayerTime { color: #6e6e8a; font-size: 11px; }
QPushButton#PlayerBtn {
    background: transparent; border: none; border-radius: 20px;
}
QPushButton#PlayerBtn:hover { background: #12121f; }
QPushButton#PlayerBtnPlay {
    background: #00d4ff; color: #0b0b14; border: none;
    border-radius: 25px; font-weight: bold;
}
QPushButton#PlayerBtnPlay:hover { background: #66e0ff; }

QSlider#ProgressSlider::groove:horizontal, QSlider#VolumeSlider::groove:horizontal {
    background: #1a1a28; height: 4px; border-radius: 2px;
}
QSlider#ProgressSlider::handle:horizontal, QSlider#VolumeSlider::handle:horizontal {
    background: #00d4ff; width: 12px; height: 12px; border-radius: 6px;
    margin: -4px 0;
}
QSlider#ProgressSlider::sub-page:horizontal, QSlider#VolumeSlider::sub-page:horizontal {
    background: #00d4ff; border-radius: 2px;
}

QLabel#ProfileInfo { color: #f0f0f5; font-size: 14px; }

QLabel#ProfileName {
    color: #ffffff;
    font-size: 28px;
    font-weight: 800;
}
QLabel#ProfileLogin {
    color: #00d4ff;
    font-size: 16px;
    font-weight: 600;
}
QLabel#ProfileBio {
    color: #a8a8c0;
    font-size: 14px;
    padding: 4px 0 12px 0;
}
QLabel#ProfileStats {
    color: #6e6e8a;
    font-size: 13px;
    font-weight: 500;
    padding-top: 8px;
    border-top: 1px solid #1a1a28;
}
QLabel#AdminBadge {
    background: rgba(0, 212, 255, 0.1);
    color: #00d4ff;
    border: 1px solid #00d4ff;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 800;
}
QLabel#InsecureBadge {
    background: rgba(255, 107, 107, 0.1);
    color: #ff6b6b;
    border: 1px solid #ff6b6b;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 800;
}
"""


def main():
    app = QApplication(sys.argv)
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    app.setStyleSheet(STYLE)
    app.setFont(QFont('Inter', 10))
    app.setWindowIcon(QIcon(get_app_icon_path()))

    Translator.instance()

    try:
        import keyring
        keyring.get_keyring()
    except Exception as e:
        print(f'Warning: keyring backend unavailable: {e}', file=sys.stderr)

    splash = SplashScreen()
    splash.show()
    QApplication.processEvents()

    api = ApiClient(load_saved_base_url())

    authenticated = False
    if api.is_authenticated():
        splash.set_status(tr('splash.connecting'))
        try:
            api.me()
            authenticated = True
        except Exception:
            authenticated = False

    if not authenticated:
        splash.close()
        dlg = AuthDialog(api)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return 0
            
        splash.show()
        QApplication.processEvents()

    splash.set_status(tr('splash.loading_ui'))
    window = MainWindow(api)
    
    app._main_window = window
    
    splash.close()
    window.show()
    
    return app.exec()