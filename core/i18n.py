import json
import sys
from pathlib import Path
from typing import List

from PySide6.QtCore import QObject, QSettings, Signal


if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

LANGS_DIR = BASE_DIR / 'langs'

LANGUAGE_NAMES = {
    'en_US': 'English',
    'ru_RU': 'Русский',
}


class Translator(QObject):
    language_changed = Signal()

    _instance = None

    @classmethod
    def instance(cls) -> 'Translator':
        if cls._instance is None:
            cls._instance = Translator()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._settings = QSettings('MusicForge', 'I18n')
        self._lang = 'en_US'
        self._strings = {}
        saved = self._settings.value('language', 'en_US', type=str)
        self.load(saved)

    def available(self) -> List[str]:
        if not LANGS_DIR.exists():
            return []
        return sorted(p.stem for p in LANGS_DIR.glob('*.json'))

    def load(self, lang: str) -> bool:
        path = LANGS_DIR / f'{lang}.json'
        if not path.exists():
            return False
        try:
            self._strings = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return False
        self._lang = lang
        return True

    def current(self) -> str:
        return self._lang

    def t(self, key: str, **kwargs) -> str:
        val = self._strings.get(key)
        if val is None:
            return key
        if kwargs:
            try:
                return val.format(**kwargs)
            except Exception:
                return val
        return val

    def set_language(self, lang: str) -> bool:
        if lang == self._lang and self._strings:
            return True
        if not self.load(lang):
            return False
        self._settings.setValue('language', lang)
        self.language_changed.emit()
        return True


def tr(key: str, **kwargs) -> str:
    return Translator.instance().t(key, **kwargs)