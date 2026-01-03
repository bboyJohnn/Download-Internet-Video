"""
Tool Installation Thread - Downloads and installs ffmpeg and yt-dlp
"""
import os
import sys
import shutil
import zipfile
import urllib.request
from PyQt5.QtCore import QThread, pyqtSignal


class ToolInstallThread(QThread):
    """Background thread for downloading and installing ffmpeg and yt-dlp"""
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, base_dir, install_ffmpeg=True, install_ytdlp=True, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.install_ffmpeg = install_ffmpeg
        self.install_ytdlp = install_ytdlp
        self._is_running = True

    def stop(self):
        """Stop the installation thread"""
        self._is_running = False

    def run(self):
        """Main installation thread execution"""
        try:
            # FFmpeg
            if self.install_ffmpeg and self._is_running:
                if not self._download_ffmpeg():
                    return

            # yt-dlp
            if self.install_ytdlp and self._is_running:
                if not self._download_ytdlp():
                    return

            self.finished.emit(True, 'Installation completed')
        except Exception as e:
            self.finished.emit(False, str(e))

    def _download_ffmpeg(self):
        """Download and extract FFmpeg"""
        try:
            self.status.emit('Downloading FFmpeg...')
            url = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
            zip_path = os.path.join(self.base_dir, 'ffmpeg.zip')

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp:
                total = resp.getheader('Content-Length')
                total = int(total) if total and total.isdigit() else None
                downloaded = 0
                chunk = 8192
                with open(zip_path, 'wb') as out_f:
                    while self._is_running:
                        data = resp.read(chunk)
                        if not data:
                            break
                        out_f.write(data)
                        downloaded += len(data)
                        if total:
                            pct = int(downloaded * 100 / total)
                            self.progress.emit(pct)

            self.status.emit('Extracting FFmpeg...')
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(self.base_dir)

            # Move bins
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
                    shutil.rmtree(extracted_dir, ignore_errors=True)
                else:
                    for root, dirs, files in os.walk(extracted_dir):
                        for fname in files:
                            if fname.lower() in ('ffmpeg.exe', 'ffmpeg'):
                                try:
                                    shutil.copy2(os.path.join(root, fname), os.path.join(target_bin, fname))
                                except Exception:
                                    pass
                    shutil.rmtree(extracted_dir, ignore_errors=True)

            try:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
            except Exception:
                pass

            self.progress.emit(100)
            return True

        except Exception as e:
            self.finished.emit(False, f'FFmpeg error: {e}')
            return False

    def _download_ytdlp(self):
        """Download yt-dlp executable"""
        try:
            self.status.emit('Downloading yt-dlp...')

            if sys.platform == 'win32':
                url = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe'
                dst = os.path.join(self.base_dir, 'yt-dlp.exe')
            else:
                url = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp'
                dst = os.path.join(self.base_dir, 'yt-dlp')

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp, open(dst, 'wb') as out_f:
                total = resp.getheader('Content-Length')
                total = int(total) if total and total.isdigit() else None
                downloaded = 0
                chunk = 8192
                while self._is_running:
                    data = resp.read(chunk)
                    if not data:
                        break
                    out_f.write(data)
                    downloaded += len(data)
                    if total:
                        pct = int(downloaded * 100 / total)
                        self.progress.emit(pct)

            if sys.platform != 'win32':
                try:
                    os.chmod(dst, 0o755)
                except Exception:
                    pass

            return True

        except Exception as e:
            self.finished.emit(False, f'yt-dlp error: {e}')
            return False


__all__ = ['ToolInstallThread']
