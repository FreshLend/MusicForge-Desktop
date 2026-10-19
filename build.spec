# -*- mode: python ; coding: utf-8 -*-

import sys
import platform
import os
import re

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

spec_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

def get_version_from_file():
    updater_file = os.path.join(spec_dir, 'core', 'updater.py')
    try:
        with open(updater_file, 'r', encoding='utf-8') as f:
            content = f.read()
            match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)
    except Exception as e:
        print(f"Не удалось прочитать версию из {updater_file}: {e}")
    return "v0.0.0"

VERSION = get_version_from_file()

system = platform.system().lower()
is_macos = system == 'darwin'
print(f"Сборка MusicForge {VERSION} для {platform.system()}")

params = {
    'windows': {
        'separator': ';',
        'icon': os.path.join('src', 'assets', 'icons', 'icon.ico'),
        'name': f'MusicForge-{VERSION}.exe',
        'console': False
    },
    'linux': {
        'separator': ':',
        'icon': os.path.join('src', 'assets', 'icons', 'icon.png'),
        'name': f'MusicForge-{VERSION}',
        'console': False
    },
    'darwin': {
        'separator': ':',
        'icon': os.path.join('src', 'assets', 'icons', 'icon.icns'),
        'name': f'MusicForge-{VERSION}',
        'console': False
    }
}

p = params.get(system, params['linux'])

if is_macos:
    app_name = f'MusicForge-{VERSION}.app'
else:
    app_name = None

a = Analysis(
    ['main.py'],
    pathex=['.', 'src', 'core'],
    binaries=[],
    datas=[
        ('src/langs', 'src/langs'),
        ('src/assets', 'src/assets'),
    ],
    hiddenimports=[
        'core.api',
        'core.i18n',
        'core.updater',
        'src.app',
        'src.auth',
        'src.main_window',
        'src.player',
        'src.widgets',
        'src.icons',
        'src.discord_rpc',
        'src.pages',
        'pypresence',
        'keyring',
        'PySide6.QtMultimedia',
        'PySide6.QtNetwork',
        'PySide6.QtSvg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=p['name'],
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=p['console'],
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=p['icon']
)

if is_macos:
    app = BUNDLE(
        exe,
        name=app_name,
        icon=p['icon'],
        bundle_identifier='com.musicforge.desktop',
        info_plist={
            'NSPrincipalClass': 'NSApplication',
            'NSHighResolutionCapable': 'True',
            'CFBundleShortVersionString': VERSION.replace('v', ''),
            'CFBundleVersion': VERSION.replace('v', ''),
            'CFBundleName': f'MusicForge {VERSION}',
            'CFBundleDisplayName': f'MusicForge {VERSION}',
        }
    )