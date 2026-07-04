"""
Tool Updater - check and update yt-dlp, Deno and FFmpeg to the latest versions.

Updates are atomic: download to a temp file -> verify the new binary runs ->
swap with a backup kept until the swap succeeds, so a failed update never
leaves the app without a working tool.
"""
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import zipfile

from PyQt5.QtCore import QThread, pyqtSignal

import config
from tools.net import urlopen

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0

YTDLP_LATEST_API = 'https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest'
DENO_LATEST_API = 'https://api.github.com/repos/denoland/deno/releases/latest'
FFMPEG_VERSION_URL = 'https://www.gyan.dev/ffmpeg/builds/release-version'
YTDLP_EXE_URL = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe'

_exe_version_cache = {}


def _http_get(url, timeout=20):
    with urlopen(url, timeout=timeout) as resp:
        return resp.read()


def _rmtree_retry(path, attempts=6, delay=0.5):
    """Remove a directory tree, retrying while OneDrive/antivirus hold locks"""
    def _onerr(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    for i in range(attempts):
        if not os.path.exists(path):
            return True
        shutil.rmtree(path, onerror=_onerr)
        if not os.path.exists(path):
            return True
        time.sleep(delay * (i + 1))
    return not os.path.exists(path)


def _run_version(cmd):
    """Run a `tool --version` style command, return its first output line"""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                           encoding='utf-8', errors='replace',
                           creationflags=_CREATE_NO_WINDOW)
        lines = (p.stdout or p.stderr or '').strip().splitlines()
        return lines[0].strip() if lines else None
    except Exception:
        return None


def version_tuple(v):
    """'2026.06.09' / 'v2.9.1' / '8.1.2' -> comparable tuple of ints"""
    return tuple(int(x) for x in re.findall(r'\d+', v or '')) or (0,)


# ---------------------------------------------------------- local versions

def local_ytdlp_exe_version(cached=True):
    path = config.YTDLP_EXE
    if not (path and os.path.exists(path)):
        return None
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return None
    if cached and key in _exe_version_cache:
        return _exe_version_cache[key]
    v = _run_version([path, '--version'])
    _exe_version_cache[key] = v
    return v


def local_ytdlp_module_version():
    try:
        from yt_dlp.version import __version__
        return __version__
    except Exception:
        return None


def local_deno_version():
    if config.DENO_EXE and os.path.exists(config.DENO_EXE):
        line = _run_version([config.DENO_EXE, '--version'])
        if line:
            m = re.search(r'deno (\S+)', line)
            return m.group(1) if m else None
    return None


def local_ffmpeg_version():
    if os.path.exists(config.LOCAL_FFMPEG_EXE):
        line = _run_version([config.LOCAL_FFMPEG_EXE, '-version'])
        if line:
            m = re.search(r'ffmpeg version (\S+)', line)
            if m:
                return m.group(1).split('-')[0]
    return None


# --------------------------------------------------------- latest versions

def latest_ytdlp_version():
    try:
        return json.loads(_http_get(YTDLP_LATEST_API)).get('tag_name', '').lstrip('v') or None
    except Exception:
        return None


def latest_deno_version():
    try:
        return json.loads(_http_get(DENO_LATEST_API)).get('tag_name', '').lstrip('v') or None
    except Exception:
        return None


def latest_ffmpeg_version():
    try:
        return _http_get(FFMPEG_VERSION_URL).decode('utf-8', 'replace').strip() or None
    except Exception:
        return None


class ToolUpdateThread(QThread):
    """Background thread that checks versions and updates outdated tools"""
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    log = pyqtSignal(str)
    finished_update = pyqtSignal(bool, str)

    def __init__(self, base_dir, force=False, parent=None, tr=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.force = force
        self._tr = tr
        self._is_running = True

    def stop(self):
        self._is_running = False

    def _t(self, text, **kw):
        """Translate a template and substitute placeholders"""
        s = self._tr(text) if self._tr else text
        try:
            return s.format(**kw) if kw else s
        except Exception:
            return text.format(**kw) if kw else text

    # ------------------------------------------------------------- helpers

    def _download(self, url, dst):
        """Download url to dst via a .part file; raises on failure/cancel"""
        tmp = dst + '.part'
        try:
            with urlopen(url, timeout=30) as resp, open(tmp, 'wb') as out_f:
                total = resp.getheader('Content-Length')
                total = int(total) if total and total.isdigit() else None
                downloaded = 0
                while True:
                    if not self._is_running:
                        raise RuntimeError('Cancelled by user')
                    data = resp.read(65536)
                    if not data:
                        break
                    out_f.write(data)
                    downloaded += len(data)
                    if total:
                        self.progress.emit(int(downloaded * 100 / total))
            if total is not None and downloaded < total:
                raise RuntimeError(f'Incomplete download: {downloaded}/{total} bytes')
            os.replace(tmp, dst)
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass

    def _swap_dir(self, new_dir, target_dir):
        """Atomically replace target_dir with new_dir, rolling back on failure"""
        backup = target_dir + '.old'
        if not _rmtree_retry(backup):
            raise RuntimeError(f'cannot remove old backup {backup} (files locked?)')
        had_old = os.path.exists(target_dir)
        if had_old:
            os.rename(target_dir, backup)
        try:
            os.rename(new_dir, target_dir)
        except OSError:
            if had_old and os.path.exists(backup):
                os.rename(backup, target_dir)
            raise
        if not _rmtree_retry(backup):
            self.log.emit(f'Note: could not remove {os.path.basename(backup)} '
                          '(locked by another program, e.g. OneDrive sync). '
                          'It is harmless and will be cleaned up on the next update.')

    def _cleanup_leftovers(self):
        """Remove temp dirs/files a previous (interrupted) update left behind"""
        for name in ('ffmpeg.old', 'ffmpeg.new', 'ffmpeg.extract',
                     'deno.old', 'deno.new'):
            path = os.path.join(self.base_dir, name)
            if os.path.isdir(path) and _rmtree_retry(path, attempts=3):
                self.log.emit(f'Removed leftover {name}')
        for name in ('ffmpeg.zip', 'ffmpeg.zip.part', 'deno.zip',
                     'deno.zip.part', 'yt-dlp.exe.new', 'yt-dlp.exe.new.part'):
            path = os.path.join(self.base_dir, name)
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass

    # -------------------------------------------------------------- checks

    def _log_versions(self, tool, installed, latest):
        self.log.emit(self._t('{tool}: installed {installed}, latest {latest}',
                              tool=tool,
                              installed=installed or '-',
                              latest=latest or self._t('unknown')))

    def _make_plan(self):
        """Compare local vs latest versions, return [(name, action), ...]"""
        plan = []

        self.status.emit(self._t('Checking versions...'))

        latest_yt = latest_ytdlp_version()
        cur_exe = local_ytdlp_exe_version(cached=False)
        self._log_versions('yt-dlp.exe', cur_exe, latest_yt)
        if self.force or (latest_yt and (not cur_exe or version_tuple(cur_exe) < version_tuple(latest_yt))):
            plan.append(('yt-dlp.exe', self._update_ytdlp_exe))

        if not getattr(sys, 'frozen', False) and config.YTDLP_MODULE:
            cur_mod = local_ytdlp_module_version()
            self._log_versions('yt-dlp module', cur_mod, latest_yt)
            if self.force or (latest_yt and (not cur_mod or version_tuple(cur_mod) < version_tuple(latest_yt))):
                plan.append(('yt-dlp module', self._update_ytdlp_module))

        latest_deno = latest_deno_version()
        cur_deno = local_deno_version()
        self._log_versions('Deno', cur_deno, latest_deno)
        if self.force or (latest_deno and (not cur_deno or version_tuple(cur_deno) < version_tuple(latest_deno))):
            plan.append(('Deno', self._update_deno))

        latest_ff = latest_ffmpeg_version()
        cur_ff = local_ffmpeg_version()
        self._log_versions('FFmpeg', cur_ff, latest_ff)
        if self.force or (latest_ff and (not cur_ff or version_tuple(cur_ff) < version_tuple(latest_ff))):
            plan.append(('FFmpeg', self._update_ffmpeg))

        return plan

    # ------------------------------------------------------------- updates

    def _update_ytdlp_exe(self):
        dst = os.path.join(self.base_dir, 'yt-dlp.exe')
        tmp = dst + '.new'
        self._download(YTDLP_EXE_URL, tmp)
        ver = _run_version([tmp, '--version'])
        if not ver:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise RuntimeError('new yt-dlp.exe failed verification')
        os.replace(tmp, dst)
        _exe_version_cache.clear()
        self.log.emit(self._t('{tool} updated to {version}',
                              tool='yt-dlp.exe', version=ver))

    def _update_ytdlp_module(self):
        p = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp[default]'],
            capture_output=True, text=True, timeout=600,
            encoding='utf-8', errors='replace', creationflags=_CREATE_NO_WINDOW)
        if p.returncode != 0:
            raise RuntimeError(f'pip failed: {(p.stderr or p.stdout or "")[-400:]}')
        self.log.emit(self._t('yt-dlp module updated (restart the app to use the new version)'))

    def _update_deno(self):
        zip_path = os.path.join(self.base_dir, 'deno.zip')
        new_dir = os.path.join(self.base_dir, 'deno.new')
        try:
            self._download(config.DENO_DOWNLOAD_URL, zip_path)
            _rmtree_retry(new_dir)
            os.makedirs(new_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(new_dir)

            new_exe = os.path.join(new_dir, 'deno.exe' if sys.platform == 'win32' else 'deno')
            ver_line = _run_version([new_exe, '--version'])
            if not ver_line:
                raise RuntimeError('new deno failed verification')

            self._swap_dir(new_dir, os.path.join(self.base_dir, 'deno'))
            self.log.emit(self._t('{tool} updated to {version}',
                                  tool='Deno', version=ver_line))
        finally:
            _rmtree_retry(new_dir, attempts=3)
            try:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
            except OSError:
                pass

    def _update_ffmpeg(self):
        zip_path = os.path.join(self.base_dir, 'ffmpeg.zip')
        extract_dir = os.path.join(self.base_dir, 'ffmpeg.extract')
        new_dir = os.path.join(self.base_dir, 'ffmpeg.new')
        try:
            self._download(config.FFMPEG_DOWNLOAD_URL, zip_path)
            self.status.emit(self._t('Extracting {name}...', name='FFmpeg'))
            _rmtree_retry(extract_dir)
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(extract_dir)

            inner_bin = None
            for root, dirs, files in os.walk(extract_dir):
                if os.path.basename(root) == 'bin' and any(
                        f.lower().startswith('ffmpeg') for f in files):
                    inner_bin = root
                    break
            if not inner_bin:
                raise RuntimeError('bin folder not found in the FFmpeg archive')

            _rmtree_retry(new_dir)
            new_bin = os.path.join(new_dir, 'bin')
            os.makedirs(new_bin, exist_ok=True)
            for fname in os.listdir(inner_bin):
                shutil.copy2(os.path.join(inner_bin, fname), os.path.join(new_bin, fname))

            new_exe = os.path.join(new_bin, 'ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg')
            ver_line = _run_version([new_exe, '-version'])
            if not ver_line:
                raise RuntimeError('new ffmpeg failed verification')

            self._swap_dir(new_dir, os.path.join(self.base_dir, 'ffmpeg'))
            self.log.emit(self._t('{tool} updated to {version}', tool='FFmpeg',
                                  version=ver_line.split('Copyright')[0].strip()))
        finally:
            _rmtree_retry(extract_dir, attempts=3)
            _rmtree_retry(new_dir, attempts=3)
            try:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
            except OSError:
                pass

    # ----------------------------------------------------------------- run

    def run(self):
        try:
            self._cleanup_leftovers()
            plan = self._make_plan()
            if not plan:
                self.finished_update.emit(True, self._t('Everything is up to date'))
                return

            updated, failed = [], []
            for name, action in plan:
                if not self._is_running:
                    self.finished_update.emit(False, self._t('Cancelled by user'))
                    return
                self.status.emit(self._t('Updating {name}...', name=name))
                self.progress.emit(0)
                try:
                    action()
                    updated.append(name)
                except Exception as e:
                    self.log.emit(self._t('{name}: update failed: {error}',
                                          name=name, error=e))
                    failed.append(name)
                self.progress.emit(100)

            config.refresh_tools()

            if failed:
                self.finished_update.emit(
                    False, self._t('Updated: {updated}. Failed: {failed}',
                                   updated=', '.join(updated) or '-',
                                   failed=', '.join(failed)))
            else:
                self.finished_update.emit(
                    True, self._t('Updated: {names}', names=', '.join(updated)))
        except Exception as e:
            self.finished_update.emit(False, str(e))


__all__ = ['ToolUpdateThread', 'version_tuple', 'local_ytdlp_exe_version',
           'local_ytdlp_module_version', 'local_deno_version', 'local_ffmpeg_version',
           'latest_ytdlp_version', 'latest_deno_version', 'latest_ffmpeg_version']
