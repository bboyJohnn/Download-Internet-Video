"""
Main Window - YouTubeDownloader application main window
"""
import os
import sys
import json
import time
import subprocess
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QMessageBox, QFileDialog,
    QTabWidget, QListWidget, QListWidgetItem, QCheckBox, QApplication, QTextEdit
)
from PyQt5.QtCore import Qt, QSettings, QTimer, QObject, pyqtSignal
from PyQt5.QtGui import QFont, QIcon, QTextCursor

from config import STYLESHEET_MAIN
from core.downloader import DownloadWorker
from core.tools import check_and_install_tools
from ui.widgets import DownloadItemWidget, ShadowGroupBox


class EmittingStream(QObject):
    """Stream for redirecting stdout/stderr to UI"""
    textWritten = pyqtSignal(str)
    
    def write(self, text):
        self.textWritten.emit(str(text))
    
    def flush(self):
        pass


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

        self.setStyleSheet(STYLESHEET_MAIN)

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
        
        self.main_layout.addWidget(self.tabs)

        # Video Tab
        self._setup_video_tab()
        
        # Audio Tab
        self._setup_audio_tab()

        # Logs Tab
        self._setup_logs_tab()

        # Settings Tab
        self._setup_settings_tab()

        self.video_workers = {}
        self.audio_workers = {}
        self.video_items = {}
        self.audio_items = {}
        self.output_dir = os.path.expanduser("~/Downloads")
        self.show_notifications = True
        self.play_sound = True

        # Paths for local tools
        if getattr(sys, 'frozen', False):
            base_dir = sys._MEIPASS
        else:
            # Go up two directories: ui/main_window.py -> ui -> . (root)
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        self.app_base_dir = base_dir
        self.local_ffmpeg_bin = os.path.join(self.app_base_dir, 'ffmpeg', 'bin')
        self.local_ffmpeg_exe = os.path.join(self.local_ffmpeg_bin, 'ffmpeg.exe') if sys.platform == 'win32' else os.path.join(self.local_ffmpeg_bin, 'ffmpeg')
        self.ytdlp_candidates = [
            os.path.join(self.app_base_dir, 'yt-dlp.exe'),
            os.path.join(self.app_base_dir, 'yt-dlp', 'yt-dlp.exe')
        ]

        # Add local ffmpeg to PATH if present
        if os.path.exists(self.local_ffmpeg_bin):
            os.environ['PATH'] = self.local_ffmpeg_bin + os.pathsep + os.environ.get('PATH', '')

        # On first run: if tools missing, prompt user to install
        try:
            ffmpeg_present = os.path.exists(self.local_ffmpeg_exe)
            ytdlp_present = any(os.path.exists(p) for p in self.ytdlp_candidates)
            if not ffmpeg_present or not ytdlp_present:
                dlg_module = __import__('ui.dialogs', fromlist=['ToolInstallDialog'])
                ToolInstallDialog = dlg_module.ToolInstallDialog
                dlg = ToolInstallDialog(base_dir=base_dir, install_ffmpeg=(not ffmpeg_present), install_ytdlp=(not ytdlp_present), parent=self)
                dlg.exec_()
        except Exception:
            pass

    def _setup_video_tab(self):
        """Setup Video tab"""
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

    def _setup_audio_tab(self):
        """Setup Audio tab"""
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

    def _setup_logs_tab(self):
        """Setup Logs tab"""
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

    def _setup_settings_tab(self):
        """Setup Settings tab"""
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
        
        # Button to check and install local tools
        self.check_tools_btn = QPushButton(self.tr("Check/Install Tools"))
        self.check_tools_btn.clicked.connect(self.check_and_install_tools)
        settings_layout.addWidget(self.check_tools_btn)

        settings_layout.addStretch()

    def tr(self, text):
        """Translate text using current translations"""
        return self.translations.get(self.current_lang, {}).get(text, text)

    def load_translations(self):
        """Load translations from JSON files in locales folder"""
        # Go up two directories to get to app root
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        locales_dir = os.path.join(base_dir, "locales")
        
        if not os.path.exists(locales_dir):
            os.makedirs(locales_dir)

        for file in os.listdir(locales_dir):
            if file.endswith(".json"):
                lang_code = file.split(".")[0]
                try:
                    with open(os.path.join(locales_dir, file), "r", encoding="utf-8") as f:
                        self.translations[lang_code] = json.load(f)
                except Exception as e:
                    print(f"Error loading {file}: {str(e)}")
        
        if "en" not in self.translations:
            self.translations["en"] = {"Download Internet Video": "Download Internet Video"}

    def apply_language(self):
        """Apply selected language"""
        new_lang = self.lang_combo.currentData()
        if new_lang != self.current_lang:
            self.current_lang = new_lang
            self.settings.setValue("language", new_lang)
            
            # Update UI text
            self.setWindowTitle("Download Internet Video v0.7182")
            self.title_label.setText("Download Internet Video v0.7182")
            
            self.tabs.setTabText(0, self.tr("🎬 Video"))
            self.tabs.setTabText(1, self.tr("🎵 Audio"))
            self.tabs.setTabText(2, self.tr("📄 Logs"))
            self.tabs.setTabText(3, self.tr("⚙️ Settings"))
            
            self.common_group.setTitle(self.tr("Common Settings"))
            self.link_label.setText(self.tr("Link:"))
            self.paste_button.setText(self.tr("📋 Paste"))
            self.clear_button.setText(self.tr("❌ Clear"))
            
            self.video_settings_group.setTitle(self.tr("Video Settings"))
            self.quality_label.setText(self.tr("Quality:"))
            self.format_label.setText(self.tr("Format:"))
            self.cookies_label.setText(self.tr("Cookies:"))
            self.download_video_btn.setText(self.tr("🎬 Download Video"))
            self.video_downloads_group.setTitle(self.tr("Active Downloads"))
            self.clear_video_completed_btn.setText(self.tr("🧹 Clear Completed"))
            
            self.audio_settings_group.setTitle(self.tr("Audio Settings"))
            self.audio_format_label.setText(self.tr("Format:"))
            self.audio_cookies_label.setText(self.tr("Cookies:"))
            self.download_audio_btn.setText(self.tr("🎵 Download Audio"))
            self.audio_downloads_group.setTitle(self.tr("Active Downloads"))
            self.clear_audio_completed_btn.setText(self.tr("🧹 Clear Completed"))
            
            self.logs_group.setTitle(self.tr("Download Logs"))
            self.clear_logs_btn.setText(self.tr("🧹 Clear Logs"))
            self.copy_logs_btn.setText(self.tr("📋 Copy Logs"))
            
            self.dir_group.setTitle(self.tr("Download Folder"))
            self.default_folder_label.setText(self.tr("Default Folder:"))
            self.default_dir_button.setText(self.tr("📁 Choose"))
            self.notifications_group.setTitle(self.tr("Notifications"))
            self.notifications_check.setText(self.tr("Show download completion notifications"))
            self.sound_notifications_check.setText(self.tr("Play sound on notification"))
            self.lang_group.setTitle(self.tr("Language Settings"))
            self.interface_lang_label.setText(self.tr("Interface Language:"))
            self.apply_lang_btn.setText(self.tr("Apply"))
            self.check_tools_btn.setText(self.tr("Check/Install Tools"))
            
            self.update()
            QApplication.processEvents()

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
                browser=browser_combo.currentText().lower(),
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
                browser=browser_combo.currentText().lower(),
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
            
            self.log(f"Video download canceled: {url}")
            
        elif media_type == "Audio" and url in self.audio_workers:
            worker = self.audio_workers[url]
            worker.stop()
            worker.wait()
            
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
            
            self.log(f"Audio download canceled: {url}")

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
        self.log(f"Error downloading {media_type}: {message}")
        
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

    def check_and_install_tools(self):
        """Check and install missing tools"""
        check_and_install_tools(
            parent=self,
            base_dir=self.app_base_dir,
            local_ffmpeg_bin=self.local_ffmpeg_bin,
            local_ffmpeg_exe=self.local_ffmpeg_exe,
            ytdlp_candidates=self.ytdlp_candidates
        )


__all__ = ['YouTubeDownloader']
