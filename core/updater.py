import requests
import webbrowser
from PySide6.QtCore import QThread, Signal

APP_VERSION = "v1.1.0"
GITHUB_REPO = "FreshLend/MusicForge-Desktop"


def _parse_version(v: str) -> tuple:
    parts = []
    for x in v.lstrip('v').split('.'):
        num = ''.join(filter(str.isdigit, x))
        if num:
            parts.append(int(num))
    return tuple(parts)


class UpdateCheckThread(QThread):
    update_available = Signal(str, str)

    def __init__(self, repo: str, current_version: str):
        super().__init__()
        self.repo = repo
        self.current_version = current_version

    def run(self):
        try:
            url = f"https://api.github.com/repos/{self.repo}/releases/latest"
            res = requests.get(url, headers={"User-Agent": "MusicForge-Desktop"}, timeout=5)
            
            if res.status_code == 200:
                data = res.json()
                latest_tag = data.get("tag_name", "")
                release_url = data.get("html_url", "")
                
                if latest_tag and release_url:
                    if _parse_version(latest_tag) > _parse_version(self.current_version):
                        self.update_available.emit(latest_tag, release_url)
        except Exception:
            pass