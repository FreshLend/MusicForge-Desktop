import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import keyring
import requests
from keyring.errors import KeyringError, PasswordDeleteError


def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def get_app_icon_path() -> str:
    if sys.platform == 'win32':
        icon_name = 'icon.ico'
    elif sys.platform == 'darwin':
        icon_name = 'icon.icns'
    else:
        icon_name = 'icon.png'
    return resource_path(os.path.join('src', 'assets', 'icons', icon_name))


def _user_config_dir() -> Path:
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA') or str(Path.home() / 'AppData' / 'Roaming')
        return Path(base) / 'MusicForge'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'MusicForge'
    xdg = os.environ.get('XDG_CONFIG_HOME')
    if xdg:
        return Path(xdg) / 'MusicForge'
    return Path.home() / '.config' / 'MusicForge'


CONFIG_DIR = _user_config_dir()
CONFIG_FILE = CONFIG_DIR / 'config.json'
DEFAULT_BASE_URL = 'http://127.0.0.1:5000'


def _keyring_service(base_url: str) -> str:
    return f'MusicForge:{base_url}'


def _save_tokens(base_url: str, user_id: str, access_token: str, refresh_token: str) -> bool:
    try:
        keyring.set_password(_keyring_service(base_url), user_id, access_token)
        keyring.set_password(_keyring_service(base_url) + ':refresh', user_id, refresh_token)
        return True
    except KeyringError:
        return False


def _load_tokens(base_url: str, user_id: str) -> tuple:
    try:
        access = keyring.get_password(_keyring_service(base_url), user_id)
        refresh = keyring.get_password(_keyring_service(base_url) + ':refresh', user_id)
        return access, refresh
    except KeyringError:
        return None, None


def _delete_tokens(base_url: str, user_id: str) -> None:
    for service in (_keyring_service(base_url), _keyring_service(base_url) + ':refresh'):
        try:
            keyring.delete_password(service, user_id)
        except (PasswordDeleteError, KeyringError):
            pass


def normalize_base_url(url: str) -> str:
    url = (url or '').strip()
    if not url:
        return DEFAULT_BASE_URL
    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'http://' + url
    parsed = urlparse(url)
    if not parsed.netloc:
        raise ValueError('Некорректный адрес сервера')
    scheme = parsed.scheme
    path = parsed.path.rstrip('/')
    return f'{scheme}://{parsed.netloc}{path}'


def is_secure_url(url: str) -> bool:
    return url.startswith('https://')


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class AccountStore:
    def __init__(self):
        self.data: Dict[str, Any] = {
            'base_url': DEFAULT_BASE_URL,
            'accounts': {},
            'current_user_id': None,
        }
        self._load()

    def _load(self):
        if not CONFIG_FILE.exists():
            return
        try:
            raw = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
        except Exception:
            return
        self.data['base_url'] = raw.get('base_url', DEFAULT_BASE_URL)
        self.data['accounts'] = raw.get('accounts', {})
        self.data['current_user_id'] = raw.get('current_user_id')
        for accounts in self.data['accounts'].values():
            for acc in accounts:
                acc.pop('access_token', None)
                acc.pop('refresh_token', None)

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            'base_url': self.data['base_url'],
            'current_user_id': self.data.get('current_user_id'),
            'accounts': self.data['accounts'],
        }
        tmp = CONFIG_FILE.with_suffix('.json.tmp')
        tmp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        os.replace(tmp, CONFIG_FILE)

    def servers(self) -> List[str]:
        return list(self.data['accounts'].keys())

    def accounts_for(self, base_url: str) -> List[Dict]:
        return list(self.data['accounts'].get(base_url, []))

    def get_account(self, base_url: str, user_id: Optional[str]) -> Optional[Dict]:
        for acc in self.data['accounts'].get(base_url, []):
            if user_id is None and not acc.get('user_id'):
                return acc
            if user_id is not None and acc.get('user_id') == user_id:
                return acc
        return None

    def upsert_account(self, base_url: str, account: Dict):
        account = dict(account)
        account.pop('access_token', None)
        account.pop('refresh_token', None)
        arr = self.data['accounts'].setdefault(base_url, [])
        for i, acc in enumerate(arr):
            same_id = account.get('user_id') and acc.get('user_id') == account['user_id']
            same_login = account.get('login') and acc.get('login') == account['login']
            if same_id or same_login:
                arr[i] = account
                return
        arr.append(account)

    def remove_account(self, base_url: str, user_id: Optional[str]) -> bool:
        arr = self.data['accounts'].get(base_url)
        if not arr:
            return False
        new_arr = [a for a in arr if a.get('user_id') != user_id]
        if len(new_arr) == len(arr):
            return False
        if new_arr:
            self.data['accounts'][base_url] = new_arr
        else:
            self.data['accounts'].pop(base_url, None)
        return True


class ApiClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL):
        self.store = AccountStore()
        try:
            self.base_url = normalize_base_url(base_url)
        except ValueError:
            self.base_url = DEFAULT_BASE_URL
        self.session = requests.Session()
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.user: Optional[Dict[str, Any]] = None
        self._restore_session()

    def _restore_session(self):
        saved = self.store.data.get('base_url')
        if saved:
            try:
                self.base_url = normalize_base_url(saved)
            except ValueError:
                self.base_url = DEFAULT_BASE_URL
        accounts = self.store.accounts_for(self.base_url)
        if not accounts:
            return
        user_id = self.store.data.get('current_user_id')
        acc = self.store.get_account(self.base_url, user_id) or accounts[0]
        uid = acc.get('user_id')
        if not uid:
            return
        access, refresh = _load_tokens(self.base_url, uid)
        if not access:
            return
        self.access_token = access
        self.refresh_token = refresh
        self.store.data['current_user_id'] = uid

    def list_servers(self) -> List[str]:
        return self.store.servers()

    def list_accounts(self, base_url: Optional[str] = None) -> List[Dict]:
        return self.store.accounts_for(base_url or self.base_url)

    def current_user_id(self) -> Optional[str]:
        return self.store.data.get('current_user_id')

    def switch_account(self, base_url: str, user_id: Optional[str]) -> bool:
        try:
            base_url = normalize_base_url(base_url)
        except ValueError:
            return False
        acc = self.store.get_account(base_url, user_id)
        if not acc:
            return False
        uid = acc.get('user_id')
        if not uid:
            return False
        access, refresh = _load_tokens(base_url, uid)
        if not access:
            return False
        self.base_url = base_url
        self.access_token = access
        self.refresh_token = refresh
        self.user = None
        self.store.data['base_url'] = base_url
        self.store.data['current_user_id'] = uid
        self.store.save()
        return True

    def set_base_url(self, url: str):
        self.base_url = normalize_base_url(url)
        self.access_token = None
        self.refresh_token = None
        self.user = None
        self.store.data['base_url'] = self.base_url
        self.store.data['current_user_id'] = None
        self.store.save()

    def clear_auth(self):
        self.access_token = None
        self.refresh_token = None
        self.user = None
        self.store.data['current_user_id'] = None
        self.store.save()

    def remove_account(self, base_url: str, user_id: Optional[str]) -> bool:
        try:
            base_url = normalize_base_url(base_url)
        except ValueError:
            return False
        if user_id:
            _delete_tokens(base_url, user_id)
        ok = self.store.remove_account(base_url, user_id)
        if not ok:
            return False
        if base_url == self.base_url and self.store.data.get('current_user_id') == user_id:
            self.access_token = None
            self.refresh_token = None
            self.user = None
            self.store.data['current_user_id'] = None
        self._reconcile_base_url()
        self.store.save()
        return True

    def remove_server(self, base_url: str) -> bool:
        try:
            base_url = normalize_base_url(base_url)
        except ValueError:
            return False
        if base_url not in self.store.data['accounts']:
            return False
        for acc in self.store.accounts_for(base_url):
            uid = acc.get('user_id')
            if uid:
                _delete_tokens(base_url, uid)
        del self.store.data['accounts'][base_url]
        if base_url == self.base_url:
            self.access_token = None
            self.refresh_token = None
            self.user = None
        self._reconcile_base_url()
        self.store.save()
        return True

    def _reconcile_base_url(self):
        accounts = self.store.data['accounts']
        if self.store.data['base_url'] in accounts:
            return
        remaining = list(accounts.keys())
        self.store.data['base_url'] = remaining[0] if remaining else DEFAULT_BASE_URL
        self.base_url = self.store.data['base_url']
        self.access_token = None
        self.refresh_token = None
        self.user = None
        self.store.data['current_user_id'] = None

    def is_authenticated(self) -> bool:
        return bool(self.access_token)

    def has_any_account(self) -> bool:
        return bool(self.store.servers())

    def health_check(self, url: Optional[str] = None, timeout: int = 8) -> bool:
        target = url or self.base_url
        try:
            target = normalize_base_url(target)
        except ValueError:
            return False
        try:
            r = requests.get(f'{target}/health', timeout=timeout,
                             allow_redirects=False)
        except requests.exceptions.RequestException:
            return False
        if r.status_code == 404:
            try:
                fallback = requests.get(target, timeout=timeout,
                                        allow_redirects=False)
            except requests.exceptions.RequestException:
                return False
            return fallback.status_code < 500
        if r.status_code >= 400:
            return False
        try:
            data = r.json()
        except ValueError:
            return r.status_code == 200
        if isinstance(data, dict) and data.get('status') == 'ok':
            return True
        return r.status_code == 200

    def _headers(self, auth: bool = True) -> Dict[str, str]:
        h = {'Accept': 'application/json'}
        if auth and self.access_token:
            h['Authorization'] = f'Bearer {self.access_token}'
        return h

    def _handle(self, r: requests.Response):
        if r.status_code == 204:
            return None
        try:
            data = r.json()
        except Exception:
            if r.ok:
                return r.content
            raise ApiError(r.status_code, 'bad_response', r.text[:200])
        if not r.ok or (isinstance(data, dict) and data.get('ok') is False):
            err = data.get('error', {}) if isinstance(data, dict) else {}
            raise ApiError(r.status_code, err.get('code', 'error'),
                           err.get('message', f'HTTP {r.status_code}'))
        return data.get('data') if isinstance(data, dict) else data

    def _request(self, method: str, path: str, *, auth: bool = True,
                 retry: bool = True, timeout: int = 300, **kwargs) -> Any:
        url = f'{self.base_url}/api/v1{path}'
        headers = kwargs.pop('headers', {})
        h = self._headers(auth=auth)
        h.update(headers)
        try:
            r = self.session.request(method, url, headers=h, timeout=timeout,
                                     allow_redirects=False, **kwargs)
        except requests.exceptions.Timeout:
            raise ApiError(0, 'timeout', 'Сервер не отвечает')
        except requests.exceptions.ConnectionError:
            raise ApiError(0, 'connection', 'Не удалось подключиться к серверу')
        except requests.exceptions.RequestException as e:
            raise ApiError(0, 'network', str(e))
        if r.status_code == 401 and auth and retry and self.refresh_token:
            if self._try_refresh():
                h = self._headers(auth=auth)
                h.update(headers)
                try:
                    r = self.session.request(method, url, headers=h,
                                             timeout=timeout,
                                             allow_redirects=False, **kwargs)
                except requests.exceptions.RequestException as e:
                    raise ApiError(0, 'network', str(e))
        return self._handle(r)

    def _try_refresh(self) -> bool:
        try:
            r = self.session.post(
                f'{self.base_url}/api/v1/auth/refresh',
                json={'refresh_token': self.refresh_token},
                timeout=20,
                allow_redirects=False,
            )
            if not r.ok:
                return False
            data = r.json().get('data', {})
            new_access = data.get('access_token')
            new_refresh = data.get('refresh_token') or self.refresh_token
            if not new_access:
                return False
            self.access_token = new_access
            self.refresh_token = new_refresh
            self._persist_current()
            return True
        except Exception:
            return False

    def _persist_current(self):
        if not self.user:
            return
        uid = self.user.get('id')
        if not uid:
            return
        acc = {
            'user_id': uid,
            'login': self.user.get('login', ''),
            'display_name': self.user.get('display_name', ''),
            'avatar_url': self.user.get('avatar_url', ''),
        }
        self.store.upsert_account(self.base_url, acc)
        if self.access_token:
            _save_tokens(self.base_url, uid, self.access_token,
                         self.refresh_token or '')
        self.store.data['base_url'] = self.base_url
        self.store.data['current_user_id'] = uid
        self.store.save()

    def login_with_tokens(self, access_token: str, refresh_token: str):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.me()

    def register(self, login: str, email: str, password: str, display_name: str = '') -> Dict:
        data = self._request(
            'POST', '/auth/register', auth=False,
            json={'login': login, 'email': email,
                  'password': password,
                  'display_name': display_name or login},
        )
        self._apply_auth(data)
        return data

    def login(self, login: str, password: str) -> Dict:
        data = self._request(
            'POST', '/auth/login', auth=False,
            json={'login': login, 'password': password},
        )
        self._apply_auth(data)
        return data

    def _apply_auth(self, data: Dict):
        self.access_token = data.get('access_token')
        self.refresh_token = data.get('refresh_token')
        self.user = data.get('user')
        self._persist_current()

    def logout(self):
        self.access_token = None
        self.refresh_token = None
        self.user = None
        self.store.data['current_user_id'] = None
        self.store.save()

    def me(self) -> Dict:
        data = self._request('GET', '/auth/me')
        self.user = data
        self._persist_current()
        return data

    def update_profile(self, display_name: str, bio: str,
                       avatar_path: Optional[str] = None) -> Dict:
        data = {'display_name': display_name, 'bio': bio}
        files = {}
        if avatar_path:
            with open(avatar_path, 'rb') as f:
                files['avatar_file'] = (os.path.basename(avatar_path), f.read())
        result = self._request('PATCH', '/users/me', data=data,
                               files=files if files else None)
        if isinstance(result, dict):
            self.user = result
            self._persist_current()
        return result

    def list_tracks(self, page=1, per_page=50, sort='new') -> Dict:
        return self._request('GET', '/tracks',
                             params={'page': page, 'per_page': per_page, 'sort': sort})

    def get_track(self, tid: str) -> Dict:
        return self._request('GET', f'/tracks/{tid}')

    def track_similar(self, tid: str, limit=10) -> List[Dict]:
        return self._request('GET', f'/tracks/{tid}/similar',
                             params={'limit': limit}).get('items', [])

    def track_lyrics(self, tid: str) -> Optional[str]:
        return self._request('GET', f'/tracks/{tid}/lyrics').get('lyrics')

    def track_rate(self, tid: str, value: int) -> Dict:
        return self._request('POST', f'/tracks/{tid}/rate', json={'value': value})

    def track_listen(self, tid: str) -> Dict:
        return self._request('POST', f'/tracks/{tid}/listen')

    def track_favorite_add(self, tid: str) -> Dict:
        return self._request('POST', f'/tracks/{tid}/favorite')

    def track_favorite_remove(self, tid: str) -> Dict:
        return self._request('DELETE', f'/tracks/{tid}/favorite')

    def track_delete(self, tid: str):
        self._request('DELETE', f'/tracks/{tid}')

    def update_track(self, tid: str, data: dict,
                     cover_path: Optional[str] = None,
                     lyrics_path: Optional[str] = None):
        files = {}
        if cover_path:
            with open(cover_path, 'rb') as f:
                files['cover_file'] = (os.path.basename(cover_path), f.read())
        if lyrics_path:
            with open(lyrics_path, 'rb') as f:
                files['lyrics_file'] = (os.path.basename(lyrics_path), f.read())
        return self._request('PATCH', f'/tracks/{tid}', data=data,
                             files=files if files else None)

    def stream_url(self, tid: str) -> str:
        return f'{self.base_url}/api/v1/tracks/{tid}/stream'

    def absolute(self, url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        if url.startswith('http://') or url.startswith('https://'):
            return url
        if url.startswith('/'):
            return self.base_url + url
        return url

    def _is_safe_media_url(self, url: str) -> bool:
        if not url:
            return False
        if url.startswith('https://'):
            return True
        if url.startswith(self.base_url):
            return True
        return False

    def cover_url(self, track: Dict) -> str:
        absolute = self.absolute(track.get('cover_url', ''))
        if not absolute:
            return ''
        if not self._is_safe_media_url(absolute):
            return ''
        return absolute

    def safe_avatar_url(self, user: Dict) -> str:
        absolute = self.absolute(user.get('avatar_url', ''))
        if not absolute:
            return ''
        if not self._is_safe_media_url(absolute):
            return ''
        return absolute

    def upload_track_file(self, *, title: str, artist_name: str = '', tags: str = '',
                          is_ai: bool = False, audio_path: str,
                          cover_path: Optional[str] = None,
                          cover_video_path: Optional[str] = None,
                          lyrics_path: Optional[str] = None) -> Dict:
        files = {}
        with open(audio_path, 'rb') as f:
            files['audio_file'] = (os.path.basename(audio_path), f.read())
        if cover_path:
            with open(cover_path, 'rb') as f:
                files['cover_file'] = (os.path.basename(cover_path), f.read())
        if cover_video_path:
            with open(cover_video_path, 'rb') as f:
                files['cover_video_file'] = (os.path.basename(cover_video_path), f.read())
        if lyrics_path:
            with open(lyrics_path, 'rb') as f:
                files['lyrics_file'] = (os.path.basename(lyrics_path), f.read())
        data = {
            'upload_type': 'file',
            'title': title,
            'artist_name': artist_name or '',
            'tags': tags or '',
            'is_ai': 'true' if is_ai else 'false',
        }
        return self._request('POST', '/tracks', data=data, files=files)

    def upload_track_youtube(self, *, youtube_url: str, title: str = '',
                             artist_name: str = '', tags: str = '',
                             is_ai: bool = False,
                             lyrics_path: Optional[str] = None) -> Dict:
        data = {
            'upload_type': 'youtube',
            'youtube_url': youtube_url,
            'title': title or 'YouTube Import',
            'artist_name': artist_name or '',
            'tags': tags or '',
            'is_ai': 'true' if is_ai else 'false',
        }
        files = None
        if lyrics_path:
            with open(lyrics_path, 'rb') as f:
                files = {'lyrics_file': (os.path.basename(lyrics_path), f.read())}
        return self._request('POST', '/tracks', data=data, files=files)

    def recommendations(self, limit=20) -> List[Dict]:
        return self._request('GET', '/recommendations',
                             params={'limit': limit}).get('items', [])

    def charts(self, days=30, limit=50) -> List[Dict]:
        return self._request('GET', '/charts',
                             params={'period': days, 'limit': limit}).get('items', [])

    def new_releases(self, days=30, limit=30) -> List[Dict]:
        return self._request('GET', '/new-releases',
                             params={'days': days, 'limit': limit}).get('items', [])

    def search(self, q: str, kind: str = 'tracks', limit=30) -> List[Dict]:
        return self._request('GET', '/search',
                             params={'q': q, 'type': kind, 'limit': limit}).get('items', [])

    def favorites(self) -> List[Dict]:
        return self._request('GET', '/favorites').get('items', [])

    def history(self) -> List[Dict]:
        return self._request('GET', '/history').get('items', [])

    def history_delete(self, tid: str):
        self._request('DELETE', f'/history/{tid}')

    def playlists_list(self) -> List[Dict]:
        return self._request('GET', '/playlists').get('items', [])

    def playlist_create(self, name: str, is_public: bool = False) -> Dict:
        return self._request('POST', '/playlists',
                             json={'name': name, 'is_public': is_public})

    def playlist_get(self, pid: str) -> Dict:
        return self._request('GET', f'/playlists/{pid}')

    def playlist_update(self, pid: str, name: Optional[str] = None,
                        is_public: Optional[bool] = None) -> Dict:
        body = {}
        if name is not None:
            body['name'] = name
        if is_public is not None:
            body['is_public'] = is_public
        return self._request('PATCH', f'/playlists/{pid}', json=body)

    def playlist_delete(self, pid: str):
        self._request('DELETE', f'/playlists/{pid}')

    def playlist_add_track(self, pid: str, tid: str) -> Dict:
        return self._request('POST', f'/playlists/{pid}/tracks',
                             json={'track_id': tid})

    def playlist_remove_track(self, pid: str, tid: str) -> Dict:
        return self._request('DELETE', f'/playlists/{pid}/tracks/{tid}')

    def playlist_reorder(self, pid: str, order: List[str]) -> Dict:
        return self._request('POST', f'/playlists/{pid}/reorder',
                             json={'order': order})

    def user_get(self, uid: str) -> Dict:
        return self._request('GET', f'/users/{uid}')

    def user_tracks(self, uid: str, page=1, per_page=50, own=False) -> Dict:
        params = {'page': page, 'per_page': per_page}
        if own:
            params['own'] = '1'
        return self._request('GET', f'/users/{uid}/tracks', params=params)

    def user_playlists(self, uid: str) -> List[Dict]:
        return self._request('GET', f'/users/{uid}/playlists').get('items', [])


def load_saved_base_url() -> str:
    store = AccountStore()
    return store.data.get('base_url', DEFAULT_BASE_URL)