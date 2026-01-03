"""
Download worker thread for video/audio downloads
"""
import os
import sys
import time
import tempfile
import subprocess
from PyQt5.QtCore import QThread, pyqtSignal

from config import YTDLP_EXE, YTDLP_MODULE, yt_dlp


class DownloadWorker(QThread):
    """Worker thread for downloading videos/audio files"""
    progress_signal = pyqtSignal(str, str, str, str)  # percent, speed, size, eta
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    title_signal = pyqtSignal(str)
    log_signal = pyqtSignal(str)
    duplicate_signal = pyqtSignal(str)
    conversion_signal = pyqtSignal(str)

    def __init__(self, url, use_cookies, browser, media_type, resolution, video_format, audio_format, output_dir):
        super().__init__()
        self.url = url
        self.use_cookies = use_cookies
        self.browser = browser
        self.media_type = media_type
        self.resolution = resolution
        self.video_format = video_format
        self.audio_format = audio_format
        self.output_dir = output_dir
        self._is_running = True
        self.title = ""
        self.paused = False
        self.filename = ""
        self._last_progress_emit = 0  # Throttle progress updates

    def run(self):
        """Main download process"""
        try:
            ydl_opts = {
                'outtmpl': os.path.join(self.output_dir, '%(title)s.%(ext)s'),
                'progress_hooks': [self._progress_hook],
                'logger': self,
                'merge_output_format': self.video_format if self.media_type == "Video" else self.audio_format
            }

            # Setup cookies
            self._setup_cookies(ydl_opts)

            # Configure format and postprocessors
            if self.media_type == "Video":
                ydl_opts['format'] = self._get_format_string()
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': self.video_format,
                }]
            else:
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': self.audio_format,
                    'preferredquality': '192',
                }]

            # Setup postprocessor hook
            def postprocessor_hook(d):
                if d['status'] == 'started':
                    self.conversion_signal.emit('started')
                    self.progress_signal.emit("100", "0 B/s", "Converting...", "0:00")
                elif d['status'] == 'finished':
                    self.conversion_signal.emit('finished')
                    self.progress_signal.emit("100", "0 B/s", "Ready", "0:00")
                    self.filename = d.get('filename', '')

            ydl_opts['postprocessor_hooks'] = [postprocessor_hook]

            # Download using appropriate backend
            if YTDLP_EXE and os.path.exists(YTDLP_EXE):
                self._download_with_exe(ydl_opts)
            elif YTDLP_MODULE and yt_dlp:
                self._download_with_module(ydl_opts)
            else:
                raise RuntimeError('yt-dlp not available: neither local exe nor Python module found')

        except Exception as e:
            self.error_signal.emit(str(e))
            self.log_signal.emit(f"Error downloading {self.media_type}: {str(e)}")

    def _setup_cookies(self, ydl_opts):
        """Setup cookie handling"""
        if self.use_cookies and self.browser != "Disabled":
            browser_name = self.browser.lower()
            try:
                # For frozen (exe) builds, use temp folder
                if getattr(sys, 'frozen', False):
                    cookies_dir = os.path.join(sys._MEIPASS, 'cookies_temp')
                    os.makedirs(cookies_dir, exist_ok=True)
                    cookie_file = os.path.join(cookies_dir, f'{browser_name}_cookies.txt')
                    ydl_opts['cookiefile'] = cookie_file
                
                ydl_opts['cookiesfrombrowser'] = (browser_name,)
                self.log_signal.emit(f"Using cookies from browser: {browser_name}")
            except Exception as e:
                self.log_signal.emit(f"Error setting cookies: {str(e)}")
                # Fallback: try browser_cookie3
                try:
                    import browser_cookie3
                    cj = getattr(browser_cookie3, browser_name)()
                    cookie_file = os.path.join(tempfile.gettempdir(), 'yt_dlp_cookies.txt')
                    cj.save(cookie_file)
                    ydl_opts['cookiefile'] = cookie_file
                    self.log_signal.emit(f"Used fallback cookie method: {cookie_file}")
                except Exception as fallback_e:
                    self.log_signal.emit(f"Fallback cookie error: {str(fallback_e)}")

    def _download_with_exe(self, ydl_opts):
        """Download using external yt-dlp.exe"""
        self.log_signal.emit(f'Using local yt-dlp from: {YTDLP_EXE}')
        exe = YTDLP_EXE
        
        # Get title
        try:
            p = subprocess.run([exe, '--get-title', self.url], capture_output=True, text=True, timeout=15)
            if p.stdout:
                self.title = p.stdout.strip().splitlines()[0]
                self.title_signal.emit(self.title)
        except Exception:
            pass

        # Build command
        cmd = self._build_cmd(exe, ydl_opts)
        
        # Execute
        start_time = time.time()
        try:
            proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
            self.log_signal.emit(proc.stdout or proc.stderr)
            self._find_downloaded_file(start_time)
            self.finished_signal.emit(self.filename)
        except subprocess.CalledProcessError as e:
            out = (e.stdout or '') + (e.stderr or '')
            self.log_signal.emit(out)
            if any(err in out for err in ['Requested format is not available', 'Signature extraction failed', 'Only images are available']):
                self._retry_with_fallback(cmd)
            else:
                raise

    def _download_with_module(self, ydl_opts):
        """Download using Python yt_dlp module"""
        self.log_signal.emit('Using Python yt_dlp module')
        
        tried_fallback = False
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                self.title = info.get('title', 'No title')
                self.title_signal.emit(self.title)
                ydl.download([self.url])
                self.finished_signal.emit(self.filename)
        except Exception as e:
            err = str(e)
            self.log_signal.emit(f"Download error: {err}")
            if any(x in err for x in ['Requested format is not available', 'Signature extraction failed', 'Only images are available']) and not tried_fallback:
                tried_fallback = True
                self.log_signal.emit('Retrying with fallback format: best')
                ydl_opts['format'] = 'best'
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(self.url, download=False)
                        self.title = info.get('title', 'No title')
                        self.title_signal.emit(self.title)
                        ydl.download([self.url])
                        self.finished_signal.emit(self.filename)
                except Exception as e2:
                    self.error_signal.emit(str(e2))
                    self.log_signal.emit(f"Fallback failed: {e2}")
                    try:
                        self.list_formats()
                    except Exception:
                        pass
            else:
                try:
                    self.list_formats()
                except Exception:
                    pass
                self.error_signal.emit(err)

    def _build_cmd(self, exe, ydl_opts):
        """Build command for external yt-dlp"""
        cmd = [exe, '-o', ydl_opts['outtmpl']]
        
        if 'format' in ydl_opts and ydl_opts['format']:
            cmd.extend(['-f', ydl_opts['format']])
        
        browser_name = (self.browser or '').lower()
        if self.use_cookies and browser_name and browser_name != 'disabled':
            cmd.extend(['--cookies-from-browser', browser_name])
        elif 'cookiefile' in ydl_opts and ydl_opts['cookiefile']:
            cmd.extend(['--cookies', ydl_opts['cookiefile']])
        
        if self.media_type == 'Audio':
            audio_fmt = str(self.audio_format) if self.audio_format else 'mp3'
            cmd.extend(['--extract-audio', '--audio-format', audio_fmt, '--audio-quality', '192K'])
        else:
            video_fmt = getattr(self, 'video_format', None)
            if video_fmt:
                cmd.extend(['--recode-video', str(video_fmt)])
        
        cmd.append(str(self.url) if self.url else '')
        # Filter out empty strings
        cmd = [str(x) for x in cmd if x]
        return cmd

    def _retry_with_fallback(self, cmd):
        """Retry download with format 'best'"""
        self.log_signal.emit('Retrying with format best')
        cmd2 = []
        skip_next = False
        for part in cmd:
            if skip_next:
                skip_next = False
                continue
            if part == '-f':
                skip_next = True
                continue
            cmd2.append(part)
        
        if len(cmd2) >= 1:
            cmd2.insert(len(cmd2)-1, 'best')
            cmd2.insert(len(cmd2)-1, '-f')
        
        try:
            proc2 = subprocess.run(cmd2, check=True, capture_output=True, text=True)
            self.log_signal.emit(proc2.stdout or proc2.stderr)
        except subprocess.CalledProcessError as e2:
            self.log_signal.emit((e2.stdout or '') + (e2.stderr or ''))
            try:
                self.list_formats()
            except Exception:
                pass
            raise

    def _find_downloaded_file(self, start_time):
        """Find the downloaded file in output directory"""
        try:
            newest = None
            for root, dirs, files in os.walk(self.output_dir):
                for fname in files:
                    path = os.path.join(root, fname)
                    try:
                        mtime = os.path.getmtime(path)
                        if mtime >= start_time - 1:
                            if newest is None or mtime > os.path.getmtime(newest):
                                newest = path
                    except Exception:
                        continue
            if newest:
                self.filename = newest
        except Exception:
            pass

    def debug(self, msg):
        """Debug logging"""
        if msg.startswith('[debug] '):
            return
        self.log_signal.emit(msg)

    def info(self, msg):
        """Info logging"""
        self.log_signal.emit(msg)

    def warning(self, msg):
        """Warning logging"""
        self.log_signal.emit(f"Warning: {msg}")

    def error(self, msg):
        """Error logging"""
        self.log_signal.emit(f"Error: {msg}")

    def _progress_hook(self, d):
        """Progress hook - throttled"""
        if not self._is_running:
            raise Exception("Download canceled")
        
        while self.paused:
            time.sleep(0.5)
            if not self._is_running:
                raise Exception("Download canceled")
            
        if d['status'] == 'downloading':
            current_time = time.time()
            # Throttle: only emit every 0.2 seconds
            if current_time - self._last_progress_emit < 0.2:
                return
            self._last_progress_emit = current_time
            
            percent_str = d.get('_percent_str', '0%').strip()
            percent = ''.join(c for c in percent_str if c.isdigit() or c in ('.', '%'))
            percent = percent.strip('%')
            
            speed = d.get('_speed_str', '?').strip()
            size = f"{d.get('_downloaded_bytes_str', '?')}/{d.get('_total_bytes_str', '?')}"
            eta = d.get('_eta_str', '?').strip()
            
            try:
                self.progress_signal.emit(percent, speed, size, eta)
            except:
                pass
        elif d['status'] == 'finished':
            self.progress_signal.emit("100", "0 B/s", "Processing...", "0:00")

    def pause(self):
        """Pause/resume download"""
        self.paused = not self.paused
        status = "paused" if self.paused else "resumed"
        self.log_signal.emit(f"Download {status}")

    def stop(self):
        """Stop download"""
        self._is_running = False
        self.paused = False
        self.log_signal.emit("Download canceled by user")

    def _get_format_string(self):
        """Get format string for video"""
        if self.media_type == "Audio":
            return 'bestaudio/best'
        
        if self.resolution == "Original":
            return 'bestvideo+bestaudio/best'
        
        res_num = ''.join(filter(str.isdigit, self.resolution))
        if res_num:
            return f"bestvideo[height<={res_num}]+bestaudio/best[height<={res_num}]"
        return 'bestvideo+bestaudio/best'

    def list_formats(self):
        """List available formats for URL"""
        try:
            self.log_signal.emit(f"Listing available formats for: {self.url}")
            browser_name = (self.browser or '').lower()
            
            # Try external exe first
            if YTDLP_EXE and os.path.exists(YTDLP_EXE):
                try:
                    self.log_signal.emit(f"Using local yt-dlp.exe to list formats: {YTDLP_EXE}")
                    cmd = [YTDLP_EXE, '--list-formats']
                    if self.use_cookies and browser_name and browser_name != 'disabled':
                        cmd.extend(['--cookies-from-browser', browser_name])
                    cmd.append(self.url)
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    for line in (proc.stdout or proc.stderr or '').splitlines():
                        self.log_signal.emit(line)
                    return
                except Exception as e:
                    self.log_signal.emit(f"External yt-dlp list error: {e}")
            
            # Fallback to Python module
            if yt_dlp:
                try:
                    self.log_signal.emit("Using Python yt_dlp module to list formats")
                    ydl_opts = {'skip_download': True}
                    if self.use_cookies and browser_name and browser_name != 'disabled':
                        try:
                            ydl_opts['cookiesfrombrowser'] = (browser_name,)
                            self.log_signal.emit(f"Listing using cookies from: {browser_name}")
                        except Exception:
                            pass

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(self.url, download=False)
                        formats = info.get('formats', [])
                        if not formats:
                            self.log_signal.emit('No formats found via yt_dlp module.')
                            return
                        for f in formats:
                            fmt_line = f"{f.get('format_id')} - {f.get('ext')} - {f.get('height', '')}p - {f.get('acodec','')}/{f.get('vcodec','')} - {f.get('tbr', '')}kbps"
                            self.log_signal.emit(fmt_line)
                        return
                except Exception as e:
                    self.log_signal.emit(f"yt_dlp list error: {e}")

            self.log_signal.emit('Unable to list formats: both exe and module unavailable.')
        except Exception as e:
            try:
                self.log_signal.emit(f"list_formats exception: {e}")
            except Exception:
                pass
