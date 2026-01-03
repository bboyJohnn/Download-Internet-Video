import os
import sys
import tempfile
import time
import json
import subprocess
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLineEdit, QPushButton, QComboBox, QLabel, 
    QFileDialog, QMessageBox, QGroupBox, QGridLayout,
    QListWidget, QListWidgetItem, QProgressBar, QTabWidget, QTextEdit,
    QFrame, QSizePolicy, QCheckBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QPalette, QColor, QIcon, QTextCursor
from PyQt5.QtWidgets import QGraphicsDropShadowEffect
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtCore import QSettings

# Добавляем путь к ffmpeg в PATH перед импортом yt-dlp
if getattr(sys, 'frozen', False):
    base_dir = sys._MEIPASS
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

ffmpeg_path = os.path.join(base_dir, 'ffmpeg')
if os.path.exists(ffmpeg_path):
    os.environ['PATH'] = ffmpeg_path + os.pathsep + os.environ['PATH']

import yt_dlp

class EmittingStream(QObject):
    textWritten = pyqtSignal(str)
    def write(self, text):
        self.textWritten.emit(str(text))
    def flush(self):
        pass


class DownloadWorker(QThread):
    progress_signal = pyqtSignal(str, str, str, str)
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

    def run(self):
        try:
            ydl_opts = {
                'outtmpl': os.path.join(self.output_dir, '%(title)s.%(ext)s'),
                'progress_hooks': [self._progress_hook],
                'logger': self,
                'merge_output_format': self.video_format if self.media_type == "Video" else self.audio_format
            }

            # Обработка кукисов в EXE-режиме
            if self.use_cookies and self.browser != "Disabled":
                browser_name = self.browser.lower()
                try:
                    # Для EXE-сборки используем временную папку для кукисов
                    if getattr(sys, 'frozen', False):
                        cookies_dir = os.path.join(sys._MEIPASS, 'cookies_temp')
                        os.makedirs(cookies_dir, exist_ok=True)
                        cookie_file = os.path.join(cookies_dir, f'{browser_name}_cookies.txt')
                        ydl_opts['cookiefile'] = cookie_file
                    
                    ydl_opts['cookiesfrombrowser'] = (browser_name,)
                    self.log_signal.emit(f"Using cookies from browser: {browser_name}")
                except Exception as e:
                    self.log_signal.emit(f"Error setting cookies: {str(e)}")
                    # Fallback для извлечения кукисов
                    try:
                        import browser_cookie3
                        cj = getattr(browser_cookie3, browser_name)()
                        cookie_file = os.path.join(tempfile.gettempdir(), 'yt_dlp_cookies.txt')
                        cj.save(cookie_file)
                        ydl_opts['cookiefile'] = cookie_file
                        self.log_signal.emit(f"Used fallback cookie method: {cookie_file}")
                    except Exception as fallback_e:
                        self.log_signal.emit(f"Fallback cookie error: {str(fallback_e)}")

            if self.media_type == "Video":
                if self.resolution == "Original":
                    format_str = f"bestvideo[ext={self.video_format}]+bestaudio/bestvideo+bestaudio"
                else:
                    res_num = ''.join(filter(str.isdigit, self.resolution))
                    format_str = f"bestvideo[height<={res_num}][ext={self.video_format}]+bestaudio/bestvideo[height<={res_num}]+bestaudio"
                
                ydl_opts['format'] = format_str
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

            def postprocessor_hook(d):
                if d['status'] == 'started':
                    self.conversion_signal.emit('started')
                    self.progress_signal.emit(
                        "100",
                        "0 B/s",
                        "Converting...",
                        "0:00"
                    )
                elif d['status'] == 'finished':
                    self.conversion_signal.emit('finished')
                    self.progress_signal.emit(
                        "100",
                        "0 B/s",
                        "Ready",
                        "0:00"
                    )
                    self.filename = d.get('filename', '')

            ydl_opts['postprocessor_hooks'] = [postprocessor_hook]

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self.log_signal.emit(f"Starting download in format: {self.video_format if self.media_type == 'Video' else self.audio_format}")
                info = ydl.extract_info(self.url, download=False)
                self.title = info.get('title', 'No title')
                self.title_signal.emit(self.title)
                ydl.download([self.url])
                self.finished_signal.emit(self.filename)

        except Exception as e:
            self.error_signal.emit(str(e))
            self.log_signal.emit(f"Error downloading {self.media_type}: {str(e)}")

    def debug(self, msg):
        if msg.startswith('[debug] '):
            return
        self.log_signal.emit(msg)

    def info(self, msg):
        self.log_signal.emit(msg)

    def warning(self, msg):
        self.log_signal.emit(f"Warning: {msg}")

    def error(self, msg):
        self.log_signal.emit(f"Error: {msg}")

    def _progress_hook(self, d):
        if not self._is_running:
            raise Exception("Download canceled")
        
        while self.paused:
            time.sleep(0.5)
            if not self._is_running:
                raise Exception("Download canceled")
            
        if d['status'] == 'downloading':
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
            self.progress_signal.emit(
                "100",
                "0 B/s",
                "Processing...",
                "0:00"
            )

    def pause(self):
        self.paused = not self.paused
        status = "paused" if self.paused else "resumed"
        self.log_signal.emit(f"Download {status}")

    def stop(self):
        self._is_running = False
        self.paused = False
        self.log_signal.emit("Download canceled by user")

    def _get_format_string(self):
        if self.media_type == "Audio":
            return 'bestaudio/best'
        
        if self.resolution == "Original":
            return 'bestvideo+bestaudio/best'
        else:
            res_num = ''.join(filter(str.isdigit, self.resolution))
            if res_num:
                return f"bestvideo[height<={res_num}]+bestaudio/best[height<={res_num}]"
            else:
                return 'bestvideo+bestaudio/best'


class DownloadItemWidget(QWidget):
    def __init__(self, title, media_type, parent=None):
        super().__init__(parent)
        self.media_type = media_type
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(6)
        
        top_layout = QHBoxLayout()
        
        media_icon = QLabel("🎬" if media_type == "Video" else "🎵")
        media_icon.setToolTip("Video" if media_type == "Video" else "Audio")
        media_icon.setStyleSheet("font-size: 10pt; min-width: 24px;")
        top_layout.addWidget(media_icon)
        
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("""
            font-weight: bold; 
            font-size: 9pt;
            padding-right: 5px;
        """)
        top_layout.addWidget(self.title_label, 1)
        
        # Improved delete button - red cross
        self.delete_button = QPushButton("✕")
        self.delete_button.setFixedSize(22, 22)
        self.delete_button.setStyleSheet("""
            QPushButton {
                font-size: 10pt;
                font-weight: bold;
                color: white;
                background-color: #f44336;
                border-radius: 11px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:pressed {
                background-color: #b71c1c;
            }
        """)
        self.delete_button.setToolTip("Remove from list")
        self.delete_button.setVisible(False)
        top_layout.addWidget(self.delete_button)
        
        self.layout.addLayout(top_layout)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 5px;
                background: #f0f0f0;
            }
            QProgressBar::chunk {
                background-color: #34a853;
                border-radius: 5px;
            }
        """)
        self.layout.addWidget(self.progress_bar)
        
        details_layout = QHBoxLayout()
        details_layout.setSpacing(6)
        
        speed_frame = QFrame()
        speed_frame.setStyleSheet("background-color: #e8f0fe; border-radius: 4px;")
        speed_layout = QHBoxLayout(speed_frame)
        speed_layout.setContentsMargins(4, 2, 4, 2)
        speed_icon = QLabel("⏱")
        speed_icon.setStyleSheet("font-size: 8pt; color: #1a73e8;")
        speed_layout.addWidget(speed_icon)
        self.speed_label = QLabel("-")
        self.speed_label.setStyleSheet("color: #1a73e8; font-size: 8pt;")
        speed_layout.addWidget(self.speed_label)
        speed_shadow = QGraphicsDropShadowEffect()
        speed_shadow.setBlurRadius(3)
        speed_shadow.setXOffset(1)
        speed_shadow.setYOffset(1)
        speed_shadow.setColor(QColor(0, 0, 0, 30))
        speed_frame.setGraphicsEffect(speed_shadow)
        details_layout.addWidget(speed_frame)
        
        size_frame = QFrame()
        size_frame.setStyleSheet("background-color: #e6f4ea; border-radius: 4px;")
        size_layout = QHBoxLayout(size_frame)
        size_layout.setContentsMargins(4, 2, 4, 2)
        size_icon = QLabel("📦")
        size_icon.setStyleSheet("font-size: 8pt; color: #0f9d58;")
        size_layout.addWidget(size_icon)
        self.size_label = QLabel("-/-")
        self.size_label.setStyleSheet("color: #0f9d58; font-size: 8pt;")
        size_layout.addWidget(self.size_label)
        size_shadow = QGraphicsDropShadowEffect()
        size_shadow.setBlurRadius(3)
        size_shadow.setXOffset(1)
        size_shadow.setYOffset(1)
        size_shadow.setColor(QColor(0, 0, 0, 30))
        size_frame.setGraphicsEffect(size_shadow)
        details_layout.addWidget(size_frame)
        
        eta_frame = QFrame()
        eta_frame.setStyleSheet("background-color: #fef7e0; border-radius: 4px;")
        eta_layout = QHBoxLayout(eta_frame)
        eta_layout.setContentsMargins(4, 2, 4, 2)
        eta_icon = QLabel("⏳")
        eta_icon.setStyleSheet("font-size: 8pt; color: #f4b400;")
        eta_layout.addWidget(eta_icon)
        self.eta_label = QLabel("-")
        self.eta_label.setStyleSheet("color: #f4b400; font-size: 8pt;")
        eta_layout.addWidget(self.eta_label)
        eta_shadow = QGraphicsDropShadowEffect()
        eta_shadow.setBlurRadius(3)
        eta_shadow.setXOffset(1)
        eta_shadow.setYOffset(1)
        eta_shadow.setColor(QColor(0, 0, 0, 30))
        eta_frame.setGraphicsEffect(eta_shadow)
        details_layout.addWidget(eta_frame)
        
        status_frame = QFrame()
        status_frame.setStyleSheet("background-color: #f1e6f6; border-radius: 4px;")
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(4, 2, 4, 2)
        self.status_icon = QLabel("▶")
        self.status_icon.setStyleSheet("font-size: 8pt; color: #681da8;")
        status_layout.addWidget(self.status_icon)
        self.status_label = QLabel("Downloading")
        self.status_label.setStyleSheet("color: #681da8; font-size: 8pt;")
        status_layout.addWidget(self.status_label)
        status_shadow = QGraphicsDropShadowEffect()
        status_shadow.setBlurRadius(3)
        status_shadow.setXOffset(1)
        status_shadow.setYOffset(1)
        status_shadow.setColor(QColor(0, 0, 0, 30))
        status_frame.setGraphicsEffect(status_shadow)
        details_layout.addWidget(status_frame)
        
        details_layout.addStretch(1)
        
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(6)
        
        self.pause_button = QPushButton("⏸ Pause")
        self.pause_button.setFixedHeight(24)
        self.pause_button.setStyleSheet("""
            QPushButton {
                background-color: #f4b400; 
                color: white; 
                border-radius: 4px;
                font-size: 8pt;
                padding: 2px 6px;
            }
            QPushButton:hover {
                background-color: #e0a400;
            }
        """)
        self.pause_button.setToolTip("Pause")
        
        self.cancel_button = QPushButton("✕ Cancel")
        self.cancel_button.setFixedHeight(24)
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #db4437; 
                color: white; 
                border-radius: 4px;
                font-size: 8pt;
                padding: 2px 6px;
            }
            QPushButton:hover {
                background-color: #c63d31;
            }
        """)
        self.cancel_button.setToolTip("Cancel")
        
        controls_layout.addWidget(self.pause_button)
        controls_layout.addWidget(self.cancel_button)
        
        details_layout.addLayout(controls_layout)
        
        self.layout.addLayout(details_layout)

    def update_progress(self, percent, speed, size, eta):
        try:
            percent_clean = ''.join(c for c in percent if c.isdigit() or c == '.')
            percent_value = float(percent_clean) if percent_clean else 0
            self.progress_bar.setValue(int(percent_value))
        except ValueError:
            self.progress_bar.setValue(0)
        
        self.speed_label.setText(speed)
        self.size_label.setText(size)
        self.eta_label.setText(eta)

    def set_paused(self, paused):
        if paused:
            self.pause_button.setText("▶ Resume")
            self.pause_button.setStyleSheet("""
                QPushButton {
                    background-color: #0f9d58; 
                    color: white; 
                    border-radius: 4px;
                    font-size: 8pt;
                    padding: 2px 6px;
                }
                QPushButton:hover {
                    background-color: #0d8a4d;
                }
            """)
            self.status_icon.setText("⏸")
            self.status_label.setText("Paused")
            self.status_label.setStyleSheet("color: #681da8; font-size: 8pt;")
        else:
            self.pause_button.setText("⏸ Pause")
            self.pause_button.setStyleSheet("""
                QPushButton {
                    background-color: #f4b400; 
                    color: white; 
                    border-radius: 4px;
                    font-size: 8pt;
                    padding: 2px 6px;
                }
                QPushButton:hover {
                    background-color: #e0a400;
                }
            """)
            self.status_icon.setText("▶")
            self.status_label.setText("Downloading")
            self.status_label.setStyleSheet("color: #681da8; font-size: 8pt;")
    
    def set_completed(self):
        self.status_icon.setText("✅")
        self.status_label.setText("Completed")
        self.status_label.setStyleSheet("color: #0f9d58; font-size: 8pt;")
        
    def set_canceled(self):
        self.status_icon.setText("⚠️")
        self.status_label.setText("Canceled")
        self.status_label.setStyleSheet("color: #db4437; font-size: 8pt;")
        
    def set_error(self):
        self.status_icon.setText("❌")
        self.status_label.setText("Error")
        self.status_label.setStyleSheet("color: #db4437; font-size: 8pt;")
        
    def set_converting(self):
        self.status_icon.setText("🔄")
        self.status_label.setText("Converting")
        self.status_label.setStyleSheet("color: #1a73e8; font-size: 8pt;")


class ShadowGroupBox(QGroupBox):
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.setStyleSheet("""
            QGroupBox {
                border: 1px solid #ddd;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 15px;
                font-weight: bold;
                background-color: white;
                font-size: 9pt;
            }
        """)
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(6)
        shadow.setXOffset(0)
        shadow.setYOffset(1)
        shadow.setColor(QColor(0, 0, 0, 40))
        self.setGraphicsEffect(shadow)


class YouTubeDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Download Internet Video v0.7182")
        self.setWindowIcon(QIcon(self.style().standardIcon(getattr(self.style(), 'SP_MediaPlay'))))
        self.setGeometry(100, 100, 800, 600)
        self.setMinimumSize(700, 500)
        
        # Language settings
        self.settings = QSettings("MyCompany", "YouTubeDownloader")
        self.current_lang = self.settings.value("language", "en")
        self.translations = {}
        self.load_translations()

        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
                font-family: Arial;
            }
            QLineEdit, QComboBox {
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 5px;
                min-height: 20px;
                background-color: white;
                font-size: 9pt;
            }
            QPushButton {
                background-color: #4285f4;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 8px;
                min-height: 20px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #3367d6;
            }
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 5px;
                background: white;
            }
            QTabWidget::pane {
                border: 1px solid #ddd;
                border-radius: 5px;
                margin-top: 5px;
                background: white;
            }
            QTabBar::tab {
                padding: 4px 6px;
                min-width: 40px;
                min-height: 24px;
                background: #f1f1f1;
                border: 1px solid #ddd;
                border-bottom: none;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                font-size: 8.5pt;
                text-align: center;
            }
            QTabBar::tab:selected {
                background: white;
                border-bottom: 1px solid white;
                margin-bottom: -1px;
            }
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 5px;
                font-family: monospace;
                font-size: 8pt;
                background: white;
            }
            QListWidget::item {
                margin-bottom: 8px;
            }
            QLabel {
                font-size: 9pt;
            }
        """)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setSpacing(8)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        self.title_label = QLabel("Download Internet Video v0.7182")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.title_label)

        self.common_group = ShadowGroupBox(self.tr("Common Settings"))
        common_layout = QGridLayout(self.common_group)
        common_layout.setSpacing(8)
        common_layout.setColumnStretch(1, 1)
        
        self.link_label = QLabel(self.tr("Link:"))
        common_layout.addWidget(self.link_label, 0, 0)
        
        url_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/...")
        url_layout.addWidget(self.url_input)
        
        self.paste_button = QPushButton(self.tr("📋 Paste"))
        self.paste_button.setFixedWidth(80)
        self.paste_button.clicked.connect(self.paste_from_clipboard)
        self.paste_button.setStyleSheet("""
            QPushButton {
                background-color: #5cb85c;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #4cae4c;
            }
        """)
        url_layout.addWidget(self.paste_button)
        
        self.clear_button = QPushButton(self.tr("❌ Clear"))
        self.clear_button.setFixedWidth(80)
        self.clear_button.clicked.connect(self.clear_url)
        self.clear_button.setStyleSheet("""
            QPushButton {
                background-color: #d9534f;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #c9302c;
            }
        """)
        url_layout.addWidget(self.clear_button)
        
        common_layout.addLayout(url_layout, 0, 1, 1, 2)
        
        self.main_layout.addWidget(self.common_group)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ddd;
                border-radius: 5px;
                margin-top: 5px;
                background: white;
            }
            QTabBar::tab {
                padding: 4px 6px;
                min-width: 40px;
                min-height: 24px;
                background: #f1f1f1;
                border: 1px solid #ddd;
                border-bottom: none;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                font-size: 8.5pt;
                text-align: center;
            }
            QTabBar::tab:selected {
                background: white;
                border-bottom: 1px solid white;
                margin-bottom: -1px;
            }
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(8)
        shadow.setXOffset(0)
        shadow.setYOffset(1)
        shadow.setColor(QColor(0, 0, 0, 30))
        self.tabs.setGraphicsEffect(shadow)
        
        self.main_layout.addWidget(self.tabs)

        # Video Tab
        video_tab = QWidget()
        self.tabs.addTab(video_tab, self.tr("🎬 Video"))
        video_layout = QVBoxLayout(video_tab)
        video_layout.setSpacing(10)
        video_layout.setContentsMargins(8, 8, 8, 8)
        
        self.video_settings_group = ShadowGroupBox(self.tr("Video Settings"))
        video_settings_layout = QGridLayout(self.video_settings_group)
        video_settings_layout.setSpacing(8)
        
        self.quality_label = QLabel(self.tr("Quality:"))
        video_settings_layout.addWidget(self.quality_label, 0, 0)
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems([
            "Original", "4320p", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p", "144p"
        ])
        self.resolution_combo.setFont(QFont("Arial", 9))
        video_settings_layout.addWidget(self.resolution_combo, 0, 1)
        
        self.format_label = QLabel(self.tr("Format:"))
        video_settings_layout.addWidget(self.format_label, 1, 0)
        self.video_format_combo = QComboBox()
        self.video_format_combo.addItems([
            "mp4", "webm", "mkv", "avi", "mov", "flv"
        ])
        self.video_format_combo.setFont(QFont("Arial", 9))
        video_settings_layout.addWidget(self.video_format_combo, 1, 1)
        
        self.cookies_label = QLabel(self.tr("Cookies:"))
        video_settings_layout.addWidget(self.cookies_label, 2, 0)
        self.video_browser_combo = QComboBox()
        self.video_browser_combo.addItems([self.tr("Disabled"), "chrome", "firefox", "edge", "opera", "brave"])
        self.video_browser_combo.setFont(QFont("Arial", 9))
        video_settings_layout.addWidget(self.video_browser_combo, 2, 1)
        
        self.download_video_btn = QPushButton(self.tr("🎬 Download Video"))
        self.download_video_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        self.download_video_btn.clicked.connect(lambda: self.start_download("Video"))
        video_settings_layout.addWidget(self.download_video_btn, 3, 0, 1, 2)

        video_layout.addWidget(self.video_settings_group)
        
        self.video_downloads_group = ShadowGroupBox(self.tr("Active Downloads"))
        video_downloads_layout = QVBoxLayout(self.video_downloads_group)
        
        self.video_downloads_list = QListWidget()
        self.video_downloads_list.setSpacing(10)
        self.video_downloads_list.setMinimumHeight(150)
        video_downloads_layout.addWidget(self.video_downloads_list)
        
        clear_completed_layout = QHBoxLayout()
        clear_completed_layout.addStretch()
        self.clear_video_completed_btn = QPushButton(self.tr("🧹 Clear Completed"))
        self.clear_video_completed_btn.setFont(QFont("Arial", 9))
        self.clear_video_completed_btn.clicked.connect(self.clear_completed_video)
        clear_completed_layout.addWidget(self.clear_video_completed_btn)
        video_downloads_layout.addLayout(clear_completed_layout)

        video_layout.addWidget(self.video_downloads_group, 1)

        # Audio Tab
        audio_tab = QWidget()
        self.tabs.addTab(audio_tab, self.tr("🎵 Audio"))
        audio_layout = QVBoxLayout(audio_tab)
        audio_layout.setSpacing(10)
        audio_layout.setContentsMargins(8, 8, 8, 8)
        
        self.audio_settings_group = ShadowGroupBox(self.tr("Audio Settings"))
        audio_settings_layout = QGridLayout(self.audio_settings_group)
        audio_settings_layout.setSpacing(8)
        
        self.audio_format_label = QLabel(self.tr("Format:"))
        audio_settings_layout.addWidget(self.audio_format_label, 0, 0)
        self.audio_combo = QComboBox()
        self.audio_combo.addItems([
            "mp3", "m4a", "wav", "aac", "opus", "vorbis", "flac"
        ])
        self.audio_combo.setFont(QFont("Arial", 9))
        audio_settings_layout.addWidget(self.audio_combo, 0, 1)
        
        self.audio_cookies_label = QLabel(self.tr("Cookies:"))
        audio_settings_layout.addWidget(self.audio_cookies_label, 1, 0)
        self.audio_browser_combo = QComboBox()
        self.audio_browser_combo.addItems([self.tr("Disabled"), "chrome", "firefox", "edge", "opera", "brave"])
        self.audio_browser_combo.setFont(QFont("Arial", 9))
        audio_settings_layout.addWidget(self.audio_browser_combo, 1, 1)
        
        self.download_audio_btn = QPushButton(self.tr("🎵 Download Audio"))
        self.download_audio_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        self.download_audio_btn.clicked.connect(lambda: self.start_download("Audio"))
        audio_settings_layout.addWidget(self.download_audio_btn, 2, 0, 1, 2)

        audio_layout.addWidget(self.audio_settings_group)
        
        self.audio_downloads_group = ShadowGroupBox(self.tr("Active Downloads"))
        audio_downloads_layout = QVBoxLayout(self.audio_downloads_group)
        
        self.audio_downloads_list = QListWidget()
        self.audio_downloads_list.setSpacing(10)
        self.audio_downloads_list.setMinimumHeight(150)
        audio_downloads_layout.addWidget(self.audio_downloads_list)
        
        clear_completed_layout = QHBoxLayout()
        clear_completed_layout.addStretch()
        self.clear_audio_completed_btn = QPushButton(self.tr("🧹 Clear Completed"))
        self.clear_audio_completed_btn.setFont(QFont("Arial", 9))
        self.clear_audio_completed_btn.clicked.connect(self.clear_completed_audio)
        clear_completed_layout.addWidget(self.clear_audio_completed_btn)
        audio_downloads_layout.addLayout(clear_completed_layout)

        audio_layout.addWidget(self.audio_downloads_group, 1)

        # Logs Tab
        logs_tab = QWidget()
        self.tabs.addTab(logs_tab, self.tr("📄 Logs"))
        logs_layout = QVBoxLayout(logs_tab)
        logs_layout.setContentsMargins(8, 8, 8, 8)
        
        self.logs_group = ShadowGroupBox(self.tr("Download Logs"))
        logs_group_layout = QVBoxLayout(self.logs_group)
        
        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setFont(QFont("Courier", 9))
        logs_group_layout.addWidget(self.logs_text)
        
        logs_buttons_layout = QHBoxLayout()
        self.clear_logs_btn = QPushButton(self.tr("🧹 Clear Logs"))
        self.clear_logs_btn.setFont(QFont("Arial", 9))
        self.clear_logs_btn.clicked.connect(self.clear_logs)
        logs_buttons_layout.addWidget(self.clear_logs_btn)
        
        self.copy_logs_btn = QPushButton(self.tr("📋 Copy Logs"))
        self.copy_logs_btn.setFont(QFont("Arial", 9))
        self.copy_logs_btn.clicked.connect(self.copy_logs)
        logs_buttons_layout.addWidget(self.copy_logs_btn)
        
        logs_group_layout.addLayout(logs_buttons_layout)
        logs_layout.addWidget(self.logs_group)

        # Settings Tab
        settings_tab = QWidget()
        self.tabs.addTab(settings_tab, self.tr("⚙️ Settings"))
        settings_layout = QVBoxLayout(settings_tab)
        settings_layout.setContentsMargins(8, 8, 8, 8)
        
        self.dir_group = ShadowGroupBox(self.tr("Download Folder"))
        dir_layout = QGridLayout(self.dir_group)
        dir_layout.setSpacing(8)
        
        self.default_folder_label = QLabel(self.tr("Default Folder:"))
        dir_layout.addWidget(self.default_folder_label, 0, 0)
        self.default_dir_input = QLineEdit(os.path.expanduser("~/Downloads"))
        self.default_dir_input.setReadOnly(True)
        self.default_dir_input.setFont(QFont("Arial", 9))
        dir_layout.addWidget(self.default_dir_input, 0, 1)
        
        self.default_dir_button = QPushButton(self.tr("📁 Choose"))
        self.default_dir_button.setFixedWidth(100)
        self.default_dir_button.setFont(QFont("Arial", 9))
        self.default_dir_button.clicked.connect(self.select_default_directory)
        dir_layout.addWidget(self.default_dir_button, 0, 2)
        
        settings_layout.addWidget(self.dir_group)
        
        self.notifications_group = ShadowGroupBox(self.tr("Notifications"))
        notifications_layout = QVBoxLayout(self.notifications_group)
        
        self.notifications_check = QCheckBox(self.tr("Show download completion notifications"))
        self.notifications_check.setChecked(True)
        self.notifications_check.setFont(QFont("Arial", 9))
        notifications_layout.addWidget(self.notifications_check)
        
        self.sound_notifications_check = QCheckBox(self.tr("Play sound on notification"))
        self.sound_notifications_check.setChecked(True)
        self.sound_notifications_check.setFont(QFont("Arial", 9))
        notifications_layout.addWidget(self.sound_notifications_check)
        
        settings_layout.addWidget(self.notifications_group)
        
        # Language Settings
        self.lang_group = ShadowGroupBox(self.tr("Language Settings"))
        lang_layout = QGridLayout(self.lang_group)
        lang_layout.setSpacing(8)
        
        self.interface_lang_label = QLabel(self.tr("Interface Language:"))
        lang_layout.addWidget(self.interface_lang_label, 0, 0)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("English", "en")
        self.lang_combo.addItem("Русский (Russian)", "ru")
        self.lang_combo.addItem("Español (Spanish)", "es")
        self.lang_combo.addItem("Français (French)", "fr")
        self.lang_combo.addItem("Deutsch (German)", "de")
        self.lang_combo.addItem("中文 (Chinese)", "zh")
        self.lang_combo.addItem("Português (Portuguese)", "pt")
        self.lang_combo.addItem("العربية (Arabic)", "ar")
        self.lang_combo.addItem("हिन्दी (Hindi)", "hi")
        self.lang_combo.addItem("日本語 (Japanese)", "ja")
        self.lang_combo.setFont(QFont("Arial", 9))
        
        # Set current language
        index = self.lang_combo.findData(self.current_lang)
        if index >= 0:
            self.lang_combo.setCurrentIndex(index)
        
        lang_layout.addWidget(self.lang_combo, 0, 1)
        
        self.apply_lang_btn = QPushButton(self.tr("Apply"))
        self.apply_lang_btn.clicked.connect(self.apply_language)
        lang_layout.addWidget(self.apply_lang_btn, 1, 1)
        
        settings_layout.addWidget(self.lang_group)
        
        settings_layout.addStretch()

        self.video_workers = {}
        self.audio_workers = {}
        self.video_items = {}
        self.audio_items = {}
        self.output_dir = os.path.expanduser("~/Downloads")
        self.show_notifications = True
        self.play_sound = True

        # Настройка перенаправления stdout/stderr
        sys.stdout = EmittingStream()
        sys.stderr = EmittingStream()
        sys.stdout.textWritten.connect(self.append_log)
        sys.stderr.textWritten.connect(self.append_log)

        # Инициализация временной папки для кукисов после создания логов
        if getattr(sys, 'frozen', False):
            self.cookies_dir = os.path.join(sys._MEIPASS, 'cookies_temp')
            os.makedirs(self.cookies_dir, exist_ok=True)
            self.log(f"Created cookies temp dir: {self.cookies_dir}")

    def tr(self, text):
        """Translate text using current translations"""
        return self.translations.get(self.current_lang, {}).get(text, text)

    def load_translations(self):
        """Load translations from JSON files in locales folder"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        locales_dir = os.path.join(base_dir, "locales")
        
        if not os.path.exists(locales_dir):
            os.makedirs(locales_dir)
            # Create default English file if not exists
            default_translations = {
                "Download Internet Video": "Download Internet Video",
                "Common Settings": "Common Settings",
                "Link:": "Link:",
                "📋 Paste": "📋 Paste",
                "❌ Clear": "❌ Clear",
                "🎬 Video": "🎬 Video",
                "🎵 Audio": "🎵 Audio",
                "📄 Logs": "📄 Logs",
                "⚙️ Settings": "⚙️ Settings",
                "Video Settings": "Video Settings",
                "Quality:": "Quality:",
                "Format:": "Format:",
                "Cookies:": "Cookies:",
                "Disabled": "Disabled",
                "🎬 Download Video": "🎬 Download Video",
                "Active Downloads": "Active Downloads",
                "🧹 Clear Completed": "🧹 Clear Completed",
                "Audio Settings": "Audio Settings",
                "🎵 Download Audio": "🎵 Download Audio",
                "Download Logs": "Download Logs",
                "🧹 Clear Logs": "🧹 Clear Logs",
                "📋 Copy Logs": "📋 Copy Logs",
                "Download Folder": "Download Folder",
                "Default Folder:": "Default Folder:",
                "📁 Choose": "📁 Choose",
                "Notifications": "Notifications",
                "Show download completion notifications": "Show download completion notifications",
                "Play sound on notification": "Play sound on notification",
                "Language Settings": "Language Settings",
                "Interface Language:": "Interface Language:",
                "Apply": "Apply",
                "Download canceled by user": "Download canceled by user",
                "Download paused": "Download paused",
                "Download resumed": "Download resumed",
                "Error downloading": "Error downloading",
                "Enter video URL": "Enter video URL",
                "Error": "Error",
                "Download Complete": "Download Complete",
                "downloaded successfully": "downloaded successfully",
                "Play": "Play",
                "Open Folder": "Open Folder",
                "Close": "Close",
                "Error opening file": "Error opening file",
                "Error opening folder": "Error opening folder",
                "Remove from list": "Remove from list",
                "Preparing download...": "Preparing download...",
                "Logs copied to clipboard": "Logs copied to clipboard",
                "File": "File",
                "already exists": "already exists",
                "Duplicate File": "Duplicate File",
                "Replace": "Replace",
                "Create Copy": "Create Copy",
                "Skip": "Skip"
            }
            with open(os.path.join(locales_dir, "en.json"), "w", encoding="utf-8") as f:
                json.dump(default_translations, f, ensure_ascii=False, indent=2)
        
        # Load all available translations
        for file in os.listdir(locales_dir):
            if file.endswith(".json"):
                lang_code = file.split(".")[0]
                try:
                    with open(os.path.join(locales_dir, file), "r", encoding="utf-8") as f:
                        self.translations[lang_code] = json.load(f)
                except Exception as e:
                    print(f"Error loading {file}: {str(e)}")
        
        # Ensure at least English is loaded
        if "en" not in self.translations:
            self.translations["en"] = {
                "Download Internet Video": "Download Internet Video",
                "Common Settings": "Common Settings",
                "Link:": "Link:",
                "📋 Paste": "📋 Paste",
                "❌ Clear": "❌ Clear",
                "🎬 Video": "🎬 Video",
                "🎵 Audio": "🎵 Audio",
                "📄 Logs": "📄 Logs",
                "⚙️ Settings": "⚙️ Settings"
            }

    def apply_language(self):
        """Apply selected language"""
        new_lang = self.lang_combo.currentData()
        if new_lang != self.current_lang:
            self.current_lang = new_lang
            self.settings.setValue("language", new_lang)
            
            # Update window title
            self.setWindowTitle("Download Internet Video v0.7182")
            
            # Update main title
            self.title_label.setText("Download Internet Video v0.7182")
            
            # Update tab names
            self.tabs.setTabText(0, self.tr("🎬 Video"))
            self.tabs.setTabText(1, self.tr("🎵 Audio"))
            self.tabs.setTabText(2, self.tr("📄 Logs"))
            self.tabs.setTabText(3, self.tr("⚙️ Settings"))
            
            # Common settings
            self.common_group.setTitle(self.tr("Common Settings"))
            self.link_label.setText(self.tr("Link:"))
            self.paste_button.setText(self.tr("📋 Paste"))
            self.clear_button.setText(self.tr("❌ Clear"))
            
            # Video tab
            self.video_settings_group.setTitle(self.tr("Video Settings"))
            self.quality_label.setText(self.tr("Quality:"))
            self.format_label.setText(self.tr("Format:"))
            self.cookies_label.setText(self.tr("Cookies:"))
            
            # Update browser combo items
            current_video_browser = self.video_browser_combo.currentText()
            self.video_browser_combo.clear()
            self.video_browser_combo.addItems([self.tr("Disabled"), "chrome", "firefox", "edge", "opera", "brave"])
            if current_video_browser in [self.tr("Disabled"), "chrome", "firefox", "edge", "opera", "brave"]:
                index = self.video_browser_combo.findText(current_video_browser)
                if index >= 0:
                    self.video_browser_combo.setCurrentIndex(index)
            
            self.download_video_btn.setText(self.tr("🎬 Download Video"))
            self.video_downloads_group.setTitle(self.tr("Active Downloads"))
            self.clear_video_completed_btn.setText(self.tr("🧹 Clear Completed"))
            
            # Audio tab
            self.audio_settings_group.setTitle(self.tr("Audio Settings"))
            self.audio_format_label.setText(self.tr("Format:"))
            self.audio_cookies_label.setText(self.tr("Cookies:"))
            
            current_audio_browser = self.audio_browser_combo.currentText()
            self.audio_browser_combo.clear()
            self.audio_browser_combo.addItems([self.tr("Disabled"), "chrome", "firefox", "edge", "opera", "brave"])
            if current_audio_browser in [self.tr("Disabled"), "chrome", "firefox", "edge", "opera", "brave"]:
                index = self.audio_browser_combo.findText(current_audio_browser)
                if index >= 0:
                    self.audio_browser_combo.setCurrentIndex(index)
            
            self.download_audio_btn.setText(self.tr("🎵 Download Audio"))
            self.audio_downloads_group.setTitle(self.tr("Active Downloads"))
            self.clear_audio_completed_btn.setText(self.tr("🧹 Clear Completed"))
            
            # Logs tab
            self.logs_group.setTitle(self.tr("Download Logs"))
            self.clear_logs_btn.setText(self.tr("🧹 Clear Logs"))
            self.copy_logs_btn.setText(self.tr("📋 Copy Logs"))
            
            # Settings tab
            self.dir_group.setTitle(self.tr("Download Folder"))
            self.default_folder_label.setText(self.tr("Default Folder:"))
            self.default_dir_button.setText(self.tr("📁 Choose"))
            self.notifications_group.setTitle(self.tr("Notifications"))
            self.notifications_check.setText(self.tr("Show download completion notifications"))
            self.sound_notifications_check.setText(self.tr("Play sound on notification"))
            self.lang_group.setTitle(self.tr("Language Settings"))
            self.interface_lang_label.setText(self.tr("Interface Language:"))
            self.apply_lang_btn.setText(self.tr("Apply"))
            
            # Update status messages in download items
            self.update_download_items_text()
            
            # Force UI update
            self.update()
            QApplication.processEvents()

    def update_download_items_text(self):
        """Update text in existing download items"""
        # Video items
        for i in range(self.video_downloads_list.count()):
            item = self.video_downloads_list.item(i)
            widget = self.video_downloads_list.itemWidget(item)
            if widget:
                widget.pause_button.setText("⏸ " + self.tr("Pause") if not widget.paused else "▶ " + self.tr("Resume"))
                widget.cancel_button.setText("✕ " + self.tr("Cancel"))
                widget.delete_button.setToolTip(self.tr("Remove from list"))
                
                if widget.status_label.text() == "Downloading":
                    widget.status_label.setText(self.tr("Downloading"))
                elif widget.status_label.text() == "Paused":
                    widget.status_label.setText(self.tr("Paused"))
                elif widget.status_label.text() == "Completed":
                    widget.status_label.setText(self.tr("Completed"))
                elif widget.status_label.text() == "Canceled":
                    widget.status_label.setText(self.tr("Canceled"))
                elif widget.status_label.text() == "Error":
                    widget.status_label.setText(self.tr("Error"))
                elif widget.status_label.text() == "Converting":
                    widget.status_label.setText(self.tr("Converting"))
        
        # Audio items
        for i in range(self.audio_downloads_list.count()):
            item = self.audio_downloads_list.item(i)
            widget = self.audio_downloads_list.itemWidget(item)
            if widget:
                widget.pause_button.setText("⏸ " + self.tr("Pause") if not widget.paused else "▶ " + self.tr("Resume"))
                widget.cancel_button.setText("✕ " + self.tr("Cancel"))
                widget.delete_button.setToolTip(self.tr("Remove from list"))
                
                if widget.status_label.text() == "Downloading":
                    widget.status_label.setText(self.tr("Downloading"))
                elif widget.status_label.text() == "Paused":
                    widget.status_label.setText(self.tr("Paused"))
                elif widget.status_label.text() == "Completed":
                    widget.status_label.setText(self.tr("Completed"))
                elif widget.status_label.text() == "Canceled":
                    widget.status_label.setText(self.tr("Canceled"))
                elif widget.status_label.text() == "Error":
                    widget.status_label.setText(self.tr("Error"))
                elif widget.status_label.text() == "Converting":
                    widget.status_label.setText(self.tr("Converting"))

    def paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        self.url_input.setText(clipboard.text())

    def clear_url(self):
        self.url_input.clear()

    def select_default_directory(self):
        directory = QFileDialog.getExistingDirectory(self, self.tr("Select Default Folder"))
        if directory:
            self.output_dir = directory
            self.default_dir_input.setText(directory)

    def start_download(self, media_type):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Enter video URL"))
            return
        
        browser_combo = self.video_browser_combo if media_type == "Video" else self.audio_browser_combo
        
        # Проверка доступности браузера для кукисов
        browser_name = browser_combo.currentText().lower()
        if browser_combo.currentText() != self.tr("Disabled") and getattr(sys, 'frozen', False):
            try:
                # Проверяем, доступен ли браузер в EXE-режиме
                import browser_cookie3
                browser_module = getattr(browser_cookie3, browser_name, None)
                if not browser_module:
                    QMessageBox.warning(self, self.tr("Warning"), 
                                        self.tr(f"Browser {browser_name} is not supported in portable mode"))
                    return
            except ImportError:
                self.log(f"browser_cookie3 not available in portable mode")
        
        if media_type == "Video":
            item_widget = DownloadItemWidget(self.tr("Preparing download..."), media_type)
            list_item = QListWidgetItem()
            list_item.setSizeHint(item_widget.sizeHint())
            self.video_downloads_list.addItem(list_item)
            self.video_downloads_list.setItemWidget(list_item, item_widget)
            self.video_items[url] = (list_item, item_widget)
            
            worker = DownloadWorker(
                url=url,
                use_cookies=browser_combo.currentText() != self.tr("Disabled"),
                browser=browser_name,
                media_type="Video",
                resolution=self.resolution_combo.currentText(),
                video_format=self.video_format_combo.currentText(),
                audio_format="",
                output_dir=self.output_dir
            )
            
            self.setup_worker(worker, url, "Video", item_widget)
            self.video_workers[url] = worker
            
        elif media_type == "Audio":
            item_widget = DownloadItemWidget(self.tr("Preparing download..."), media_type)
            list_item = QListWidgetItem()
            list_item.setSizeHint(item_widget.sizeHint())
            self.audio_downloads_list.addItem(list_item)
            self.audio_downloads_list.setItemWidget(list_item, item_widget)
            self.audio_items[url] = (list_item, item_widget)
            
            worker = DownloadWorker(
                url=url,
                use_cookies=browser_combo.currentText() != self.tr("Disabled"),
                browser=browser_name,
                media_type="Audio",
                resolution="",
                video_format="",
                audio_format=self.audio_combo.currentText(),
                output_dir=self.output_dir
            )
            
            self.setup_worker(worker, url, "Audio", item_widget)
            self.audio_workers[url] = worker
        
        item_widget.cancel_button.clicked.connect(lambda: self.cancel_download(url, media_type))
        item_widget.pause_button.clicked.connect(lambda: self.pause_download(url, media_type))
        item_widget.delete_button.clicked.connect(lambda: self.remove_download(url, media_type))

    def setup_worker(self, worker, url, media_type, item_widget):
        worker.title_signal.connect(lambda title: item_widget.title_label.setText(title))
        worker.progress_signal.connect(item_widget.update_progress)
        worker.finished_signal.connect(lambda filename: self.download_completed(url, media_type, item_widget, filename))
        worker.error_signal.connect(lambda msg: self.show_error(msg, url, media_type, item_widget))
        worker.log_signal.connect(self.log)
        worker.conversion_signal.connect(lambda status: self.handle_conversion(status, item_widget))
        worker.start()

    def handle_conversion(self, status, item_widget):
        if status == 'started':
            item_widget.set_converting()
        elif status == 'finished':
            item_widget.set_completed()

    def download_completed(self, url, media_type, item_widget, filename):
        self.log(f"{media_type} downloaded: {url}")
        
        item_widget.set_completed()
        item_widget.cancel_button.setVisible(False)
        item_widget.pause_button.setVisible(False)
        item_widget.delete_button.setVisible(True)
        item_widget.title_label.setStyleSheet("color: #0f9d58; font-weight: bold;")
            
        if media_type == "Video" and url in self.video_workers:
            del self.video_workers[url]
                
        elif media_type == "Audio" and url in self.audio_workers:
            del self.audio_workers[url]
            
        if self.notifications_check.isChecked():
            self.show_notification(filename, media_type)

    def show_notification(self, filename, media_type):
        base_name = os.path.basename(filename)
        file_name, _ = os.path.splitext(base_name)
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(self.tr("Download Complete"))
        msg_box.setText(f"{media_type} \"{file_name}\" {self.tr('downloaded successfully')}")
        
        play_button = msg_box.addButton("▶ " + self.tr("Play"), QMessageBox.ActionRole)
        open_button = msg_box.addButton("📂 " + self.tr("Open Folder"), QMessageBox.ActionRole)
        close_button = msg_box.addButton(self.tr("Close"), QMessageBox.RejectRole)
        
        msg_box.setIcon(QMessageBox.Information)
        
        if self.sound_notifications_check.isChecked():
            try:
                if sys.platform == "win32":
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except:
                pass
        
        msg_box.exec_()
        
        if msg_box.clickedButton() == play_button:
            self.open_file(filename)
        elif msg_box.clickedButton() == open_button:
            self.open_folder(filename)

    def open_file(self, filepath):
        try:
            if sys.platform == "win32":
                os.startfile(filepath)
            elif sys.platform == "darwin":
                subprocess.run(["open", filepath])
            else:
                subprocess.run(["xdg-open", filepath])
        except Exception as e:
            self.log(f"{self.tr('Error opening file')}: {str(e)}")

    def open_folder(self, filepath):
        try:
            folder = os.path.dirname(filepath)
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.run(["open", folder])
            else:
                subprocess.run(["xdg-open", folder])
        except Exception as e:
            self.log(f"{self.tr('Error opening folder')}: {str(e)}")

    def pause_download(self, url, media_type):
        if media_type == "Video" and url in self.video_workers:
            worker = self.video_workers[url]
            worker.pause()
            if url in self.video_items:
                _, item_widget = self.video_items[url]
                item_widget.set_paused(worker.paused)
                item_widget.pause_button.setText("▶ " + self.tr("Resume") if worker.paused else "⏸ " + self.tr("Pause"))
                item_widget.status_label.setText(self.tr("Paused") if worker.paused else self.tr("Downloading"))
        elif media_type == "Audio" and url in self.audio_workers:
            worker = self.audio_workers[url]
            worker.pause()
            if url in self.audio_items:
                _, item_widget = self.audio_items[url]
                item_widget.set_paused(worker.paused)
                item_widget.pause_button.setText("▶ " + self.tr("Resume") if worker.paused else "⏸ " + self.tr("Pause"))
                item_widget.status_label.setText(self.tr("Paused") if worker.paused else self.tr("Downloading"))

    def cancel_download(self, url, media_type):
        if media_type == "Video" and url in self.video_workers:
            worker = self.video_workers[url]
            worker.stop()
            worker.wait()
            
            # Automatically remove item on cancel
            if url in self.video_items:
                list_item, item_widget = self.video_items[url]
                item_widget.set_canceled()
                item_widget.cancel_button.setVisible(False)
                item_widget.pause_button.setVisible(False)
                item_widget.delete_button.setVisible(True)
                item_widget.status_label.setText(self.tr("Canceled"))
                item_widget.title_label.setStyleSheet("color: #db4437; font-weight: bold;")

            if url in self.video_workers:
                del self.video_workers[url]
            
            self.log(f"{self.tr('Video download canceled')}: {url}")
            
        elif media_type == "Audio" and url in self.audio_workers:
            worker = self.audio_workers[url]
            worker.stop()
            worker.wait()
            
            # Automatically remove item on cancel
            if url in self.audio_items:
                list_item, item_widget = self.audio_items[url]
                item_widget.set_canceled()
                item_widget.cancel_button.setVisible(False)
                item_widget.pause_button.setVisible(False)
                item_widget.delete_button.setVisible(True)
                item_widget.status_label.setText(self.tr("Canceled"))
                item_widget.title_label.setStyleSheet("color: #db4437; font-weight: bold;")

            if url in self.audio_workers:
                del self.audio_workers[url]
            
            self.log(f"{self.tr('Audio download canceled')}: {url}")

    def remove_download(self, url, media_type):
        if media_type == "Video" and url in self.video_items:
            list_item, _ = self.video_items[url]
            row = self.video_downloads_list.row(list_item)
            self.video_downloads_list.takeItem(row)
            del self.video_items[url]
        elif media_type == "Audio" and url in self.audio_items:
            list_item, _ = self.audio_items[url]
            row = self.audio_downloads_list.row(list_item)
            self.audio_downloads_list.takeItem(row)
            del self.audio_items[url]

    def clear_completed_video(self):
        items_to_remove = []
        for url, (list_item, item_widget) in self.video_items.items():
            if item_widget.delete_button.isVisible():
                items_to_remove.append((url, list_item))
        
        for url, list_item in items_to_remove:
            row = self.video_downloads_list.row(list_item)
            self.video_downloads_list.takeItem(row)
            del self.video_items[url]

    def clear_completed_audio(self):
        items_to_remove = []
        for url, (list_item, item_widget) in self.audio_items.items():
            if item_widget.delete_button.isVisible():
                items_to_remove.append((url, list_item))
        
        for url, list_item in items_to_remove:
            row = self.audio_downloads_list.row(list_item)
            self.audio_downloads_list.takeItem(row)
            del self.audio_items[url]

    def show_error(self, message, url, media_type, item_widget):
        QMessageBox.critical(self, self.tr("Error"), message)
        self.log(f"{self.tr('Error downloading')} {media_type}: {message}")
        
        item_widget.set_error()
        item_widget.cancel_button.setVisible(False)
        item_widget.pause_button.setVisible(False)
        item_widget.delete_button.setVisible(True)
        item_widget.title_label.setStyleSheet("color: #db4437; font-weight: bold;")
        item_widget.status_label.setText(self.tr("Error"))
            
        if media_type == "Video" and url in self.video_workers:
            del self.video_workers[url]
            
        elif media_type == "Audio" and url in self.audio_workers:
            del self.audio_workers[url]

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        self.logs_text.append(f"[{timestamp}] {message}")
        self.logs_text.moveCursor(QTextCursor.End)

    def clear_logs(self):
        self.logs_text.clear()

    def copy_logs(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.logs_text.toPlainText())
        self.log(self.tr("Logs copied to clipboard"))

    def append_log(self, text):
        self.logs_text.moveCursor(QTextCursor.End)
        self.logs_text.insertPlainText(text)
        self.logs_text.moveCursor(QTextCursor.End)

    def show_duplicate_dialog(self, filename):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Question)
        msg.setText(f"{self.tr('File')} {filename} {self.tr('already exists')}")
        msg.setWindowTitle(self.tr("Duplicate File"))
        
        replace_button = msg.addButton(self.tr("Replace"), QMessageBox.ActionRole)
        duplicate_button = msg.addButton(self.tr("Create Copy"), QMessageBox.ActionRole)
        skip_button = msg.addButton(self.tr("Skip"), QMessageBox.ActionRole)
        
        msg.exec_()
        
        if msg.clickedButton() == replace_button:
            return "replace"
        elif msg.clickedButton() == duplicate_button:
            return "duplicate"
        else:
            return "skip"


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(245, 245, 245))
    palette.setColor(QPalette.WindowText, Qt.black)
    palette.setColor(QPalette.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.AlternateBase, QColor(240, 240, 240))
    app.setPalette(palette)
    
    window = YouTubeDownloader()
    window.show()
    sys.exit(app.exec_())
