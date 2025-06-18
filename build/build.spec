# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['Download Internet Video 0.7182.py'],  # Убедитесь что имя вашего скрипта правильное
    pathex=['J:\\program\\Скачиватель видео\\project'],  # Добавьте путь к проекту
    binaries=[],
    datas=[
        ('locales/*.json', 'locales'),
        ('ffmpeg/*', 'ffmpeg')
    ],
    hiddenimports=[
        'browser_cookie3',
        'secretstorage',
        'keyring',
        'Cryptodome',
        'yt_dlp',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'yt_dlp.utils'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['_bz2', '_lzma', '_decimal'],  # Исключите ненужные модули
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DownloadInternetVideo',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Включить UPX сжатие
    console=False,  # Без консоли
    icon='icon.ico',  # Укажите путь к иконке если есть
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DownloadInternetVideo',
)