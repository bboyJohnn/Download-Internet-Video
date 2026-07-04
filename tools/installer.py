"""
Tool Installation Thread - Downloads and installs ffmpeg, yt-dlp and Deno
"""
import os
import sys
import shutil
import zipfile
from PyQt5.QtCore import QThread, pyqtSignal

from config import FFMPEG_DOWNLOAD_URL, DENO_DOWNLOAD_URL
from tools.net import urlopen


class ToolInstallThread(QThread):
    """Background thread for downloading and installing ffmpeg, yt-dlp and Deno"""
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, base_dir, install_ffmpeg=True, install_ytdlp=True,
                 install_deno=False, parent=None, tr=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.install_ffmpeg = install_ffmpeg
        self.install_ytdlp = install_ytdlp
        self.install_deno = install_deno
        self._tr = tr
        self._is_running = True

    def stop(self):
        """Stop the installation thread"""
        self._is_running = False

    def _t(self, text, **kw):
        """Translate a template and substitute placeholders"""
        s = self._tr(text) if self._tr else text
        try:
            return s.format(**kw) if kw else s
        except Exception:
            return text.format(**kw) if kw else text

    def run(self):
        """Main installation thread execution"""
        try:
            steps = []
            if self.install_ffmpeg:
                steps.append(self._install_ffmpeg)
            if self.install_ytdlp:
                steps.append(self._install_ytdlp)
            if self.install_deno:
                steps.append(self._install_deno)

            for step in steps:
                if not self._is_running:
                    break
                step()  # raises RuntimeError on failure

            if self._is_running:
                self.finished.emit(True, self._t('Installation completed'))
            else:
                self.finished.emit(False, self._t('Cancelled by user'))
        except Exception as e:
            self.finished.emit(False, str(e))

    def _fetch(self, url, dst):
        """Download url to dst atomically (via .part). Returns False if cancelled."""
        tmp = dst + '.part'
        try:
            with urlopen(url, timeout=30) as resp, open(tmp, 'wb') as out_f:
                total = resp.getheader('Content-Length')
                total = int(total) if total and total.isdigit() else None
                downloaded = 0
                while self._is_running:
                    data = resp.read(65536)
                    if not data:
                        break
                    out_f.write(data)
                    downloaded += len(data)
                    if total:
                        self.progress.emit(int(downloaded * 100 / total))

            if not self._is_running:
                return False
            if total is not None and downloaded < total:
                raise RuntimeError(f'Incomplete download of {os.path.basename(dst)}: '
                                   f'{downloaded}/{total} bytes')
            os.replace(tmp, dst)
            return True
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass

    def _install_ffmpeg(self):
        """Download and extract FFmpeg"""
        self.status.emit(self._t('Downloading {name}...', name='FFmpeg'))
        zip_path = os.path.join(self.base_dir, 'ffmpeg.zip')
        try:
            if not self._fetch(FFMPEG_DOWNLOAD_URL, zip_path):
                return  # cancelled

            self.status.emit(self._t('Extracting {name}...', name='FFmpeg'))
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(self.base_dir)

            target_bin = os.path.join(self.base_dir, 'ffmpeg', 'bin')
            os.makedirs(target_bin, exist_ok=True)

            extracted_dir = None
            for item in os.listdir(self.base_dir):
                if item.startswith('ffmpeg-') and os.path.isdir(os.path.join(self.base_dir, item)):
                    extracted_dir = os.path.join(self.base_dir, item)
                    break

            if extracted_dir:
                inner_bin = os.path.join(extracted_dir, 'bin')
                if os.path.exists(inner_bin):
                    for fname in os.listdir(inner_bin):
                        try:
                            shutil.move(os.path.join(inner_bin, fname), os.path.join(target_bin, fname))
                        except Exception:
                            try:
                                shutil.copy2(os.path.join(inner_bin, fname), os.path.join(target_bin, fname))
                            except Exception:
                                pass
                else:
                    for root, dirs, files in os.walk(extracted_dir):
                        for fname in files:
                            if fname.lower() in ('ffmpeg.exe', 'ffmpeg', 'ffprobe.exe', 'ffprobe'):
                                try:
                                    shutil.copy2(os.path.join(root, fname), os.path.join(target_bin, fname))
                                except Exception:
                                    pass
                shutil.rmtree(extracted_dir, ignore_errors=True)

            if not os.path.exists(os.path.join(target_bin, 'ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg')):
                raise RuntimeError('FFmpeg extraction failed: ffmpeg executable not found')

            self.progress.emit(100)
        finally:
            try:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
            except OSError:
                pass

    def _install_ytdlp(self):
        """Download yt-dlp executable"""
        self.status.emit(self._t('Downloading {name}...', name='yt-dlp'))

        if sys.platform == 'win32':
            url = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe'
            dst = os.path.join(self.base_dir, 'yt-dlp.exe')
        else:
            url = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp'
            dst = os.path.join(self.base_dir, 'yt-dlp')

        if not self._fetch(url, dst):
            return  # cancelled

        if sys.platform != 'win32':
            try:
                os.chmod(dst, 0o755)
            except OSError:
                pass

        self.progress.emit(100)

    def _install_deno(self):
        """Download Deno (JS runtime needed by yt-dlp for YouTube)"""
        self.status.emit(self._t('Downloading {name}...', name='Deno'))
        zip_path = os.path.join(self.base_dir, 'deno.zip')
        try:
            if not self._fetch(DENO_DOWNLOAD_URL, zip_path):
                return  # cancelled

            self.status.emit(self._t('Extracting {name}...', name='Deno'))
            target_dir = os.path.join(self.base_dir, 'deno')
            os.makedirs(target_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(target_dir)

            self.progress.emit(100)
        finally:
            try:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
            except OSError:
                pass


__all__ = ['ToolInstallThread']
