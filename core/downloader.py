"""
Download worker thread for video/audio downloads
"""
import os
import re
import sys
import time
import subprocess
import traceback
from PyQt5.QtCore import QThread, pyqtSignal

import config
from config import yt_dlp, get_js_runtimes, get_js_runtimes_cli

# Hide console windows of child processes (ffmpeg/yt-dlp) in windowed builds
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0

# [download]  45.3% of ~  10.55MiB at    2.50MiB/s ETA 00:03
_PROGRESS_RE = re.compile(
    r'\[download\]\s+(?P<percent>[\d.]+)%'
    r'(?:\s+of\s+~?\s*(?P<total>\S+))?'
    r'(?:\s+at\s+(?P<speed>\S+))?'
    r'(?:\s+ETA\s+(?P<eta>\S+))?'
)

# YouTube uses a typographic apostrophe in "you're", so match the prefix only
BOT_CHECK_MARKER = "Sign in to confirm you"
FALLBACK_MARKERS = (
    'Requested format is not available',
    'Signature extraction failed',
    'Only images are available',
)


class DownloadWorker(QThread):
    """Worker thread for downloading videos/audio files"""
    progress_signal = pyqtSignal(str, str, str, str)  # percent, speed, size, eta
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    title_signal = pyqtSignal(str)
    thumbnail_signal = pyqtSignal(bytes)  # raw preview image bytes
    log_signal = pyqtSignal(str)
    duplicate_signal = pyqtSignal(str)
    conversion_signal = pyqtSignal(str)

    def __init__(self, url, use_cookies, browser, media_type, resolution,
                 video_format, audio_format, output_dir,
                 overwrite=False, filename_suffix="", cookies_file=""):
        super().__init__()
        self.url = url
        self.use_cookies = use_cookies
        self.browser = browser
        self.media_type = media_type
        self.resolution = resolution
        self.video_format = video_format
        self.audio_format = audio_format
        self.output_dir = output_dir
        self.overwrite = overwrite
        self.cookies_file = cookies_file  # path to a cookies.txt, or ""
        # " (2)" etc. appended before the extension when saving a copy
        self.filename_suffix = str(filename_suffix).replace('%', '')
        self._is_running = True
        self.title = ""
        self.paused = False
        self.filename = ""
        self._file_found = False
        self._progress_counter = 0
        self._proc = None  # active yt-dlp.exe subprocess (for cancel)
        self._backend = None  # 'module' or 'exe'
        self._thumb_sent = False

    # ------------------------------------------------------------------ run

    def run(self):
        """Main download process"""
        try:
            ydl_opts = {
                'outtmpl': os.path.join(
                    self.output_dir, f'%(title)s{self.filename_suffix}.%(ext)s'),
                'progress_hooks': [self._progress_hook],
                'logger': self,
                'noplaylist': True,
                'retries': 10,
                'fragment_retries': 10,
                'socket_timeout': 30,
                'quiet': False,
                'no_warnings': False,
                # Deno solves YouTube JS challenges (required since late 2025)
                'js_runtimes': get_js_runtimes(),
            }

            if self.overwrite:
                ydl_opts['overwrites'] = True  # re-download over the old file

            if os.path.isdir(config.LOCAL_FFMPEG_BIN):
                ydl_opts['ffmpeg_location'] = config.LOCAL_FFMPEG_BIN

            self._setup_cookies(ydl_opts)

            if self.media_type == "Video":
                ydl_opts['format'] = self._get_format_string()
                ydl_opts['merge_output_format'] = self.video_format
                # Only re-encode when the container actually differs
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': self.video_format,
                }]
                # Sane encoder settings so converted files stay small
                ydl_opts['postprocessor_args'] = {
                    'videoconvertor': self._convert_args()
                }
            else:
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': self.audio_format,
                    'preferredquality': '192',
                }]

            def postprocessor_hook(d):
                if not isinstance(d, dict):
                    return
                if d.get('status') == 'started':
                    self.conversion_signal.emit('started')
                    self.progress_signal.emit("100", "0 B/s", "Converting...", "0:00")
                elif d.get('status') == 'finished':
                    self.conversion_signal.emit('finished')
                    self.progress_signal.emit("100", "0 B/s", "Ready", "0:00")
                    filename = d.get('filename') or d.get('info_dict', {}).get('filepath', '')
                    if filename:
                        self.filename = filename
                        self._file_found = True

            ydl_opts['postprocessor_hooks'] = [postprocessor_hook]

            self._backend = self._pick_backend()
            if self._backend == 'module':
                self._download_with_module(ydl_opts)
            elif self._backend == 'exe':
                self._download_with_exe(ydl_opts)
            else:
                raise RuntimeError(
                    'yt-dlp not available: neither the Python module nor a local '
                    'yt-dlp.exe was found. Open Settings -> Check/Install Tools.'
                )

        except Exception as e:
            self.error_signal.emit(str(e))
            self.log_signal.emit(f"Error downloading {self.media_type}: {str(e)}")
            self.log_signal.emit(f"Traceback:\n{traceback.format_exc()}")

    def _pick_backend(self):
        """Module gives real-time progress; a newer local exe wins over an
        older built-in module (exe builds get yt-dlp updates this way)"""
        module_ok = config.YTDLP_MODULE and yt_dlp
        exe_ok = config.YTDLP_EXE and os.path.exists(config.YTDLP_EXE)
        if module_ok and exe_ok:
            try:
                from tools.updater import (local_ytdlp_exe_version,
                                           local_ytdlp_module_version, version_tuple)
                exe_v = local_ytdlp_exe_version()
                mod_v = local_ytdlp_module_version()
                if exe_v and mod_v and version_tuple(exe_v) > version_tuple(mod_v):
                    self.log_signal.emit(f'Local yt-dlp.exe {exe_v} is newer than '
                                         f'the built-in module {mod_v}; using exe')
                    return 'exe'
            except Exception:
                pass
        if module_ok:
            return 'module'
        if exe_ok:
            return 'exe'
        return None

    # -------------------------------------------------------------- cookies

    def _setup_cookies(self, ydl_opts):
        """Pass cookies to yt-dlp: from a cookies.txt file or from a browser"""
        if self.cookies_file and os.path.exists(self.cookies_file):
            ydl_opts['cookiefile'] = self.cookies_file
            self.log_signal.emit(f"Using cookies file: {self.cookies_file}")
            return
        browser_name = (self.browser or '').lower()
        if self.use_cookies and browser_name and browser_name != 'disabled':
            ydl_opts['cookiesfrombrowser'] = (browser_name,)
            self.log_signal.emit(f"Using cookies from browser: {browser_name}")

    def _convert_args(self):
        """ffmpeg arguments for FFmpegVideoConvertor: good quality, small size"""
        if self.video_format == 'webm':
            return ['-c:v', 'libvpx-vp9', '-crf', '32', '-b:v', '0',
                    '-c:a', 'libopus', '-b:a', '160k']
        # mp4 / mkv / mov / avi / flv
        return ['-c:v', 'libx264', '-crf', '23', '-preset', 'medium',
                '-c:a', 'aac', '-b:a', '192k']

    # ------------------------------------------------------------ exe path

    def _download_with_exe(self, ydl_opts, retry_count=0, max_retries=3):
        """Download using external yt-dlp.exe, streaming progress output"""
        if retry_count == 0:
            self.log_signal.emit(f'[*] Using local yt-dlp exe: {config.YTDLP_EXE}')
            self._fetch_title_with_exe()

        cmd = self._build_cmd(config.YTDLP_EXE, ydl_opts)
        start_time = time.time()
        output_lines = []

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=_CREATE_NO_WINDOW,
            )
            for line in self._proc.stdout:
                if not self._is_running:
                    try:
                        self._proc.terminate()
                    except OSError:
                        pass
                    break
                line = line.rstrip()
                if not line:
                    continue
                m = _PROGRESS_RE.search(line)
                if m:
                    self.progress_signal.emit(
                        m.group('percent') or '0',
                        m.group('speed') or '?',
                        m.group('total') or '?',
                        m.group('eta') or '?',
                    )
                else:
                    output_lines.append(line)
                    if not line.startswith('[debug]'):
                        self.log_signal.emit(line)
            try:
                returncode = self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                returncode = self._proc.wait()
        finally:
            self._proc = None

        # Cancelled by the user: not an error
        if not self._is_running:
            self.log_signal.emit("Download canceled by user")
            return

        out = '\n'.join(output_lines)

        if returncode == 0:
            self._find_downloaded_file(start_time)
            self.finished_signal.emit(self.filename)
            return

        # Bot verification: wait and retry
        if BOT_CHECK_MARKER in out:
            if retry_count < max_retries:
                retry_count += 1
                wait_time = min(5 * retry_count, 30)
                self.log_signal.emit("")
                self.log_signal.emit("YouTube bot verification detected!")
                self.log_signal.emit(f"Waiting {wait_time}s before retry (attempt {retry_count}/{max_retries})...")
                time.sleep(wait_time)
                self._download_with_exe(ydl_opts, retry_count, max_retries)
            else:
                self._log_bot_check_help()
                self.error_signal.emit("YouTube bot verification failed. Please try the suggested solutions.")
            return

        if any(err in out for err in FALLBACK_MARKERS):
            self._retry_with_fallback(cmd, start_time)
        else:
            raise RuntimeError(f'yt-dlp exited with code {returncode}. See Logs tab for details.')

    def _fetch_title_with_exe(self):
        """Fetch video title and thumbnail via yt-dlp.exe (best-effort)"""
        try:
            cmd = [config.YTDLP_EXE, '--js-runtimes', get_js_runtimes_cli(),
                   '--no-playlist', '--print', 'title', '--print', 'thumbnail',
                   self.url]
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                               encoding='utf-8', errors='replace',
                               creationflags=_CREATE_NO_WINDOW)
            lines = (p.stdout or '').strip().splitlines()
            if lines:
                self.title = lines[0]
                self.title_signal.emit(self.title)
            if len(lines) > 1 and lines[1].startswith('http'):
                self._emit_thumbnail(lines[1])
        except subprocess.TimeoutExpired:
            self.log_signal.emit("Timeout fetching video title")
        except (OSError, ValueError) as e:
            self.log_signal.emit(f"Failed to get title: {type(e).__name__}")

    def _emit_thumbnail(self, url):
        """Download the preview image and hand it to the UI (best-effort)"""
        if not url or self._thumb_sent:
            return
        self._thumb_sent = True
        try:
            from tools.net import urlopen
            with urlopen(url, timeout=15) as resp:
                data = resp.read(3 * 1024 * 1024)
            if data:
                self.thumbnail_signal.emit(bytes(data))
        except Exception:
            pass

    def _build_cmd(self, exe, ydl_opts):
        """Build command line for external yt-dlp.exe"""
        cmd = [
            exe,
            '--js-runtimes', get_js_runtimes_cli(),
            '--no-playlist',
            '--newline',  # one progress update per line (parsed for the UI)
            '--socket-timeout', '30',
            '--retries', '10',
            '--fragment-retries', '10',
            '-o', ydl_opts['outtmpl'],
        ]

        if os.path.isdir(config.LOCAL_FFMPEG_BIN):
            cmd.extend(['--ffmpeg-location', config.LOCAL_FFMPEG_BIN])

        if self.overwrite:
            cmd.append('--force-overwrites')

        if ydl_opts.get('format'):
            cmd.extend(['-f', ydl_opts['format']])

        browser_name = (self.browser or '').lower()
        if self.cookies_file and os.path.exists(self.cookies_file):
            cmd.extend(['--cookies', self.cookies_file])
        elif self.use_cookies and browser_name and browser_name != 'disabled':
            cmd.extend(['--cookies-from-browser', browser_name])

        if self.media_type == 'Audio':
            audio_fmt = str(self.audio_format) if self.audio_format else 'mp3'
            cmd.extend(['--extract-audio', '--audio-format', audio_fmt, '--audio-quality', '192K'])
        elif self.video_format:
            cmd.extend(['--recode-video', str(self.video_format)])
            cmd.extend(['--ppa', 'VideoConvertor:' + ' '.join(self._convert_args())])

        cmd.append(str(self.url))
        return [str(x) for x in cmd if x]

    def _retry_with_fallback(self, cmd, start_time):
        """Retry exe download with format 'best'"""
        self.log_signal.emit('Retrying with fallback format: best')
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
        cmd2.insert(len(cmd2) - 1, '-f')
        cmd2.insert(len(cmd2) - 1, 'best')

        try:
            proc2 = subprocess.run(cmd2, check=True, capture_output=True, text=True,
                                   encoding='utf-8', errors='replace',
                                   creationflags=_CREATE_NO_WINDOW)
            self.log_signal.emit(proc2.stdout or proc2.stderr or '')
            self._find_downloaded_file(start_time)
            self.finished_signal.emit(self.filename)
        except subprocess.CalledProcessError as e2:
            self.log_signal.emit((e2.stdout or '') + (e2.stderr or ''))
            try:
                self.list_formats()
            except Exception:
                pass
            raise

    # --------------------------------------------------------- module path

    def _download_with_module(self, ydl_opts, retry_count=0, max_retries=3):
        """Download using Python yt_dlp module with retry logic"""
        if retry_count == 0:
            self.log_signal.emit('[*] Using Python yt_dlp module (real-time progress enabled)')

        try:
            self._run_module_download(ydl_opts)
        except Exception as e:
            err = str(e)
            self.log_signal.emit(f"[Attempt {retry_count + 1}] Download error: {err}")

            if not self._is_running:
                return

            # Bot verification: wait and retry
            if BOT_CHECK_MARKER in err:
                if retry_count < max_retries:
                    retry_count += 1
                    wait_time = min(5 * retry_count, 30)
                    self.log_signal.emit("")
                    self.log_signal.emit("YouTube bot verification detected!")
                    self.log_signal.emit(f"Waiting {wait_time}s before retry (attempt {retry_count}/{max_retries})...")
                    time.sleep(wait_time)
                    self._download_with_module(ydl_opts, retry_count, max_retries)
                else:
                    self._log_bot_check_help()
                    self.error_signal.emit("YouTube bot verification failed. Please try the suggested solutions.")
                return

            if 'empty' in err.lower() or 'fragment not found' in err.lower():
                self.log_signal.emit("\nDownload failed - empty file. Possible causes:")
                self.log_signal.emit("1. YouTube JS challenge solving failed (Deno runtime missing?)")
                self.log_signal.emit("2. HLS fragments not available")
                self.log_signal.emit("3. Video is age-restricted or protected")
                self.error_signal.emit("Download failed - empty file. Check logs for details.")
                self._try_list_formats()
                return

            if 'challenge solving failed' in err.lower() or 'Signature solving failed' in err:
                self.log_signal.emit("\nJS challenge solving failed!")
                self.log_signal.emit("Make sure the 'deno' folder with deno.exe is next to the application.")
                self.error_signal.emit("JS challenge solving failed. Deno runtime is missing or broken.")
                return

            if any(x in err for x in FALLBACK_MARKERS):
                self.log_signal.emit('Retrying with fallback format: best')
                ydl_opts['format'] = 'best'
                try:
                    self._run_module_download(ydl_opts)
                except Exception as e2:
                    self.error_signal.emit(str(e2))
                    self.log_signal.emit(f"Fallback failed: {e2}")
                    self._try_list_formats()
            else:
                self._try_list_formats()
                self.error_signal.emit(err)

    def _run_module_download(self, ydl_opts):
        """Single download attempt via the yt_dlp module"""
        start_time = time.time()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(self.url, download=False)
            if isinstance(info, dict):
                self.title = info.get('title', 'No title')
                self.title_signal.emit(self.title)
                self._emit_thumbnail(info.get('thumbnail'))
            else:
                self.title = 'No title'
            ydl.download([self.url])
            if not self._file_found:
                self._find_downloaded_file(start_time)
            self.finished_signal.emit(self.filename)

    # ------------------------------------------------------------- helpers

    def _log_bot_check_help(self):
        self.log_signal.emit("")
        self.log_signal.emit("YouTube bot verification - max retries reached!")
        self.log_signal.emit("YouTube is blocking automated downloads. Try these solutions:")
        self.log_signal.emit("1. Enable Cookies and pick the browser where you are logged in to YouTube")
        self.log_signal.emit("2. Visit YouTube.com in that browser and make sure you are logged in")
        self.log_signal.emit("3. Wait 30 minutes before trying again (YouTube rate limiting)")
        self.log_signal.emit("4. Try a different video")

    def _try_list_formats(self):
        try:
            self.list_formats()
        except Exception:
            pass

    def _find_downloaded_file(self, start_time):
        """Find the downloaded file in output directory"""
        if self._file_found:
            return

        newest = None
        newest_mtime = 0
        try:
            for entry in os.scandir(self.output_dir):
                if not entry.is_file():
                    continue
                if entry.name.endswith(('.part', '.ytdl', '.temp')):
                    continue
                try:
                    mtime = entry.stat().st_mtime
                except OSError:
                    continue
                if mtime >= start_time - 1 and mtime > newest_mtime:
                    newest = entry.path
                    newest_mtime = mtime

            if newest:
                file_size = os.path.getsize(newest)
                if file_size == 0:
                    self.log_signal.emit(f"Warning: downloaded file is empty: {newest}")
                    try:
                        os.remove(newest)
                    except OSError:
                        pass
                    raise RuntimeError("Downloaded file is empty - all fragments may have failed")
                self.filename = newest
                self.log_signal.emit(f"Downloaded file: {newest} ({file_size} bytes)")
        except RuntimeError:
            raise
        except Exception as e:
            self.log_signal.emit(f"Error finding downloaded file: {str(e)}")
            raise

    # --------------------------------------------- yt-dlp logger interface

    def debug(self, msg):
        msg = str(msg)
        if msg.startswith('[debug] '):
            return
        self.log_signal.emit(msg)

    def info(self, msg):
        self.log_signal.emit(str(msg))

    def warning(self, msg):
        self.log_signal.emit(f"Warning: {msg}")

    def error(self, msg):
        self.log_signal.emit(f"Error: {msg}")

    # ------------------------------------------------------ progress hook

    def _progress_hook(self, d):
        """Progress hook - throttled, tolerant to different yt-dlp versions"""
        if not isinstance(d, dict):
            return

        if not self._is_running:
            raise Exception("Download canceled")

        while self.paused:
            time.sleep(0.5)
            if not self._is_running:
                raise Exception("Download canceled")

        if d.get('status') == 'downloading':
            self._progress_counter += 1
            if self._progress_counter % 5 != 0:  # throttle UI updates
                return

            downloaded = d.get('downloaded_bytes')
            total = d.get('total_bytes') or d.get('total_bytes_estimate')

            if isinstance(downloaded, (int, float)) and isinstance(total, (int, float)) and total > 0:
                percent = str(int(100 * downloaded / total))
                size = f"{downloaded / 1024 / 1024:.1f}MB/{total / 1024 / 1024:.1f}MB"
            else:
                percent_str = str(d.get('_percent_str', '0%')).strip()
                percent = ''.join(c for c in percent_str if c.isdigit() or c == '.').rstrip('.') or '0'
                size = str(d.get('_total_bytes_str', '?'))

            speed = d.get('_speed_str', '')
            if not speed:
                raw_speed = d.get('speed')
                if isinstance(raw_speed, (int, float)):
                    speed = (f"{raw_speed / 1024 / 1024:.1f} MB/s" if raw_speed > 1024 * 1024
                             else f"{raw_speed / 1024:.1f} KB/s")
                else:
                    speed = '?'

            eta = str(d.get('_eta_str') or d.get('eta') or '?')

            try:
                self.progress_signal.emit(str(percent), str(speed), str(size), str(eta))
            except Exception as e:
                self.log_signal.emit(f"Progress emit error: {e}")
        elif d.get('status') == 'finished':
            self.progress_signal.emit("100", "0 B/s", "Processing...", "0:00")

    # ------------------------------------------------------------ controls

    def pause(self):
        """Pause/resume download (module backend only)"""
        if self._backend == 'exe':
            self.log_signal.emit("Pause is not supported for the yt-dlp.exe backend")
            return
        self.paused = not self.paused
        status = "paused" if self.paused else "resumed"
        self.log_signal.emit(f"Download {status}")

    def stop(self):
        """Stop download"""
        self._is_running = False
        self.paused = False
        proc = self._proc
        if proc is not None:
            try:
                proc.terminate()
            except OSError:
                pass
        self.log_signal.emit("Download canceled by user")

    # ------------------------------------------------------------- formats

    def _get_format_string(self):
        """Format string that prefers the target container natively, so most
        downloads need no re-encoding at all (faster, no quality loss)"""
        if self.media_type == "Audio":
            return 'bestaudio/best'

        res_num = ''.join(filter(str.isdigit, self.resolution or ''))
        limit = f'[height<={res_num}]' if res_num and self.resolution != "Original" else ''

        native = {'mp4': ('[ext=mp4]', '[ext=m4a]'),
                  'webm': ('[ext=webm]', '[ext=webm]')}.get(self.video_format)
        if native:
            v_ext, a_ext = native
            return (f'bestvideo{limit}{v_ext}+bestaudio{a_ext}/'
                    f'bestvideo{limit}+bestaudio/best{limit}/best')
        if limit:
            return f'bestvideo{limit}+bestaudio/best{limit}/best'
        return 'bestvideo+bestaudio/best'

    def list_formats(self):
        """List available formats for URL (diagnostics)"""
        self.log_signal.emit(f"Listing available formats for: {self.url}")
        browser_name = (self.browser or '').lower()

        if config.YTDLP_EXE and os.path.exists(config.YTDLP_EXE):
            try:
                cmd = [config.YTDLP_EXE, '--js-runtimes', get_js_runtimes_cli(),
                       '--no-playlist', '--list-formats']
                if self.use_cookies and browser_name and browser_name != 'disabled':
                    cmd.extend(['--cookies-from-browser', browser_name])
                cmd.append(self.url)
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                                      encoding='utf-8', errors='replace',
                                      creationflags=_CREATE_NO_WINDOW)
                for line in (proc.stdout or proc.stderr or '').splitlines():
                    self.log_signal.emit(line)
                return
            except Exception as e:
                self.log_signal.emit(f"External yt-dlp list error: {e}")

        if yt_dlp:
            try:
                ydl_opts = {'skip_download': True, 'js_runtimes': get_js_runtimes()}
                if self.use_cookies and browser_name and browser_name != 'disabled':
                    ydl_opts['cookiesfrombrowser'] = (browser_name,)

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(self.url, download=False)
                    if not isinstance(info, dict):
                        self.log_signal.emit('Invalid response from yt-dlp')
                        return
                    formats = info.get('formats', [])
                    if not formats:
                        self.log_signal.emit('No formats found via yt_dlp module.')
                        return
                    for f in formats:
                        if not isinstance(f, dict):
                            continue
                        self.log_signal.emit(
                            f"{f.get('format_id')} - {f.get('ext')} - {f.get('height', '')}p - "
                            f"{f.get('acodec', '')}/{f.get('vcodec', '')} - {f.get('tbr', '')}kbps"
                        )
                    return
            except Exception as e:
                self.log_signal.emit(f"yt_dlp list error: {e}")

        self.log_signal.emit('Unable to list formats: both exe and module unavailable.')


class PlaylistProbeWorker(QThread):
    """Fetch the flat list of videos in a channel/playlist URL (fast, no download)"""
    done = pyqtSignal(list)   # [{'url', 'title', 'duration', 'thumbnail'}, ...]
    failed = pyqtSignal(str)

    MAX_ITEMS = 500

    def __init__(self, url, use_cookies=False, browser="", cookies_file=""):
        super().__init__()
        self.url = url
        self.use_cookies = use_cookies
        self.browser = browser
        self.cookies_file = cookies_file

    def run(self):
        try:
            if not (config.YTDLP_MODULE and yt_dlp):
                raise RuntimeError('yt-dlp Python module is not available')

            opts = {
                'extract_flat': 'in_playlist',
                'skip_download': True,
                'quiet': True,
                'no_warnings': True,
                'playlistend': self.MAX_ITEMS,
                'socket_timeout': 30,
                'js_runtimes': get_js_runtimes(),
            }
            if self.cookies_file and os.path.exists(self.cookies_file):
                opts['cookiefile'] = self.cookies_file
            elif self.use_cookies and self.browser and self.browser != 'disabled':
                opts['cookiesfrombrowser'] = (self.browser,)

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)

            entries = []
            raw = info.get('entries') if isinstance(info, dict) else None
            for entry in (raw or []):
                if not isinstance(entry, dict):
                    continue
                # channel pages may nest tabs (Videos / Shorts) one level deep
                if entry.get('entries'):
                    for sub in entry['entries']:
                        if isinstance(sub, dict):
                            entries.append(sub)
                else:
                    entries.append(entry)

            items = []
            for e in entries[:self.MAX_ITEMS]:
                url = e.get('url') or e.get('webpage_url') or ''
                vid = e.get('id') or ''
                if url and not url.startswith('http'):
                    url = f'https://www.youtube.com/watch?v={url}'
                elif not url and vid:
                    url = f'https://www.youtube.com/watch?v={vid}'
                if not url:
                    continue
                thumb = ''
                thumbs = e.get('thumbnails')
                if isinstance(thumbs, list) and thumbs:
                    thumb = thumbs[-1].get('url', '')
                if not thumb and vid:
                    thumb = f'https://i.ytimg.com/vi/{vid}/mqdefault.jpg'
                items.append({
                    'url': url,
                    'title': e.get('title') or url,
                    'duration': e.get('duration'),
                    'thumbnail': thumb,
                })

            if not items:
                raise RuntimeError('No videos found at this link')
            self.done.emit(items)
        except Exception as e:
            self.failed.emit(str(e))
