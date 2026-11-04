import json
from typing import List, Dict, Optional

from PySide6.QtCore import QSettings


class RadioStations:
    _instance: Optional['RadioStations'] = None

    @classmethod
    def instance(cls) -> 'RadioStations':
        if cls._instance is None:
            cls._instance = RadioStations()
        return cls._instance

    def __init__(self):
        self._settings = QSettings('MusicForge', 'RadioStations')
        self._stations: List[Dict] = []
        self._load()

    def _load(self):
        raw = self._settings.value('stations', '[]', type=str)
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                self._stations = [
                    {'name': str(x.get('name', '')),
                     'url': str(x.get('url', ''))}
                    for x in data
                    if x.get('url')
                ]
        except Exception:
            self._stations = []

    def _save(self):
        self._settings.setValue('stations', json.dumps(self._stations))

    def list(self) -> List[Dict]:
        return list(self._stations)

    def add(self, name: str, url: str) -> bool:
        if not name or not url:
            return False
        for s in self._stations:
            if s['url'] == url:
                s['name'] = name
                self._save()
                return False
        self._stations.append({'name': name, 'url': url})
        self._save()
        return True

    def update(self, old_url: str, name: str, url: str) -> bool:
        if not name or not url:
            return False
        for s in self._stations:
            if s['url'] == old_url:
                s['name'] = name
                s['url'] = url
                self._save()
                return True
        return False

    def remove(self, url: str) -> bool:
        before = len(self._stations)
        self._stations = [s for s in self._stations if s['url'] != url]
        if len(self._stations) != before:
            self._save()
            return True
        return False

    def find(self, url: str) -> Optional[Dict]:
        for s in self._stations:
            if s['url'] == url:
                return s
        return None