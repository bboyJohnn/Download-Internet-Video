# -*- coding: utf-8 -*-
"""
Build script: creates two ready-to-use distributions of Download Internet Video.

1. dist/Download Internet Video 1.0 Portable/   - folder version (fast startup).
   Copy the folder to any PC and run DownloadInternetVideo.exe inside it.
2. dist/DownloadInternetVideo.exe               - single-file version.
   One exe with everything inside (slower startup: unpacks to temp each run).

Both include ffmpeg, yt-dlp, Deno and all locales - nothing needs to be
installed on the target PC.

Usage:  python build_release.py [onedir|onefile|all]
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, 'dist')
PORTABLE_NAME = 'Download Internet Video 1.0 Portable'

RUNTIME = os.path.join(ROOT, 'runtime')
FFMPEG_BIN = os.path.join(RUNTIME, 'ffmpeg', 'bin')
DENO_EXE = os.path.join(RUNTIME, 'deno', 'deno.exe')
YTDLP_EXE = os.path.join(RUNTIME, 'yt-dlp.exe')
ICON = os.path.join(ROOT, 'app.ico')

COMMON_ARGS = [
    '--noconfirm', '--clean', '--windowed',
    '--icon', ICON,
    '--add-data', f'{os.path.join(ROOT, "locales")};locales',
    '--add-data', f'{ICON};.',
]


def run_pyinstaller(args, workdir):
    cmd = [sys.executable, '-m', 'PyInstaller', *args,
           '--workpath', os.path.join(workdir, 'build'),
           '--specpath', workdir,
           '--distpath', DIST,
           os.path.join(ROOT, 'main.py')]
    print('>>', ' '.join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def check_tools():
    missing = [p for p in (os.path.join(FFMPEG_BIN, 'ffmpeg.exe'),
                           os.path.join(FFMPEG_BIN, 'ffprobe.exe'),
                           DENO_EXE, YTDLP_EXE, ICON) if not os.path.exists(p)]
    if missing:
        print('Missing required files:')
        for p in missing:
            print('  -', p)
        sys.exit(1)


def build_onedir(workdir):
    print('\n=== Building portable folder version ===')
    run_pyinstaller([*COMMON_ARGS, '--name', 'DownloadInternetVideo'], workdir)

    src = os.path.join(DIST, 'DownloadInternetVideo')
    dst = os.path.join(DIST, PORTABLE_NAME)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    os.rename(src, dst)

    # All tools live in runtime/ next to the exe (persistent, updatable)
    target_ffmpeg = os.path.join(dst, 'runtime', 'ffmpeg', 'bin')
    os.makedirs(target_ffmpeg, exist_ok=True)
    for exe in ('ffmpeg.exe', 'ffprobe.exe'):
        shutil.copy2(os.path.join(FFMPEG_BIN, exe), os.path.join(target_ffmpeg, exe))
    os.makedirs(os.path.join(dst, 'runtime', 'deno'), exist_ok=True)
    shutil.copy2(DENO_EXE, os.path.join(dst, 'runtime', 'deno', 'deno.exe'))
    shutil.copy2(YTDLP_EXE, os.path.join(dst, 'runtime', 'yt-dlp.exe'))

    print('Portable folder ready:', dst)
    return dst


def build_onefile(workdir):
    print('\n=== Building single-file exe version ===')
    run_pyinstaller([
        *COMMON_ARGS, '--onefile', '--name', 'DownloadInternetVideo',
        '--add-data', f'{os.path.join(FFMPEG_BIN, "ffmpeg.exe")};runtime/ffmpeg/bin',
        '--add-data', f'{os.path.join(FFMPEG_BIN, "ffprobe.exe")};runtime/ffmpeg/bin',
        '--add-data', f'{DENO_EXE};runtime/deno',
        '--add-data', f'{YTDLP_EXE};runtime',
    ], workdir)
    exe = os.path.join(DIST, 'DownloadInternetVideo.exe')
    print('Single-file exe ready:', exe)
    return exe


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else 'all'
    check_tools()
    workdir = tempfile.mkdtemp(prefix='div_build_')
    try:
        if what in ('onedir', 'all'):
            build_onedir(workdir)
        if what in ('onefile', 'all'):
            build_onefile(workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    print('\nDone.')


if __name__ == '__main__':
    main()
