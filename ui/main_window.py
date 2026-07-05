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
    QTabWidget, QListWidget, QListWidgetItem, QCheckBox, QApplication,
    QTextEdit, QSlider, QGroupBox, QScrollArea, QFrame, QSpinBox,
    QColorDialog, QProgressDialog
)
from PyQt5.QtCore import Qt, QSettings, QTimer, QObject, pyqtSignal, QUrl, QEvent
from PyQt5.QtGui import QFont, QIcon, QTextCursor, QColor, QDesktopServices

import config
from config import APP_TITLE
from core.downloader import DownloadWorker, PlaylistProbeWorker
from core.tools import check_and_install_tools
from ui.widgets import (DownloadItemWidget, ShadowGroupBox, BannerWidget,
                        CollapsibleBox)


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
        self.setWindowTitle(APP_TITLE)
        if config.APP_ICON:
            self.setWindowIcon(QIcon(config.APP_ICON))
        else:
            self.setWindowIcon(QIcon(self.style().standardIcon(getattr(self.style(), 'SP_MediaPlay'))))
        self.setGeometry(100, 100, 800, 640)
        self.setMinimumSize(700, 520)

        # Language settings
        self.settings = QSettings("MyCompany", "YouTubeDownloader")
        self.current_lang = self.settings.value("language", "en")
        self.translations = {}
        self.load_translations()

        # Persisted user preferences (must be loaded before tabs are built)
        default_downloads = config.get_downloads_dir()
        self.output_dir = self.settings.value("output_dir", default_downloads)
        if not os.path.isdir(self.output_dir):
            self.output_dir = default_downloads
        self.cookies_file = self.settings.value("cookies_file", "")

        # Cache fonts for better performance (optimization #2)
        self.CACHED_FONT = QFont("Segoe UI", 9)
        self.CACHED_FONT_BOLD = QFont("Segoe UI", 9, QFont.Bold)
        self.CACHED_FONT_SMALL = QFont("Segoe UI", 8)

        # Theme (persisted; the controls in Settings change it live)
        theme_mode = self.settings.value("theme_mode", "light")
        config.set_theme(
            hue=self.settings.value("hue", config.DEFAULT_HUE, type=int),
            saturation=self.settings.value("saturation", config.DEFAULT_SATURATION, type=int),
            dark=config.is_system_dark() if theme_mode == "system" else (theme_mode == "dark"))
        self.setStyleSheet(config.STYLESHEET_MAIN)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setSpacing(6)
        self.main_layout.setContentsMargins(10, 10, 10, 6)

        # Site-style banner: the title on a colored 'picture' with gentle
        # waves along its bottom edge; the tab buttons sit at the waves' foot
        self.banner = BannerWidget(APP_TITLE)
        self.banner.set_animated(self.settings.value("wave_anim", True, type=bool))
        self.main_layout.addWidget(self.banner)

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

        self.paste_button = QPushButton("📋 " + self.tr("Paste"))
        self.paste_button.clicked.connect(self.paste_from_clipboard)
        url_layout.addWidget(self.paste_button)

        self.clear_button = QPushButton("✖ " + self.tr("Clear"))
        self.clear_button.clicked.connect(self.clear_url)
        self.clear_button.setStyleSheet(config.STYLESHEET_BUTTON_DANGER)
        url_layout.addWidget(self.clear_button)

        common_layout.addLayout(url_layout, 0, 1, 1, 2)

        # The tab buttons come right below the banner waves; the shared Link
        # card lives inside the Video/Audio pages (moved on tab switch)
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)
        self.tabs.currentChanged.connect(self.banner.splash)
        self.tabs.currentChanged.connect(self._place_common_group)

        self._sections = []  # collapsible settings cards

        # Video Tab
        self._setup_video_tab()

        # Audio Tab
        self._setup_audio_tab()

        # Logs Tab
        self._setup_logs_tab()

        # Settings Tab
        self._setup_settings_tab()

        # The shared Link card starts on the Video page
        self.video_tab_layout.insertWidget(0, self.common_group)

        # Footer: project links
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 2, 0, 0)
        footer_layout.addStretch()
        self.github_btn = QPushButton("🐙 GitHub")
        self.github_btn.setStyleSheet(config.STYLESHEET_BUTTON_LINK)
        self.github_btn.setCursor(Qt.PointingHandCursor)
        self.github_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(config.PROJECT_URL)))
        footer_layout.addWidget(self.github_btn)
        self.donate_btn = QPushButton("💛 " + self.tr("Donate"))
        self.donate_btn.setStyleSheet(config.STYLESHEET_BUTTON_LINK)
        self.donate_btn.setCursor(Qt.PointingHandCursor)
        self.donate_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(config.DONATE_URL)))
        footer_layout.addWidget(self.donate_btn)
        footer_layout.addStretch()
        self.main_layout.addLayout(footer_layout)

        self.video_workers = {}
        self.audio_workers = {}
        self.video_items = {}
        self.audio_items = {}
        self._zombie_workers = set()  # retired but possibly still-running threads
        self._download_seq = 0
        self._queue = []              # jobs waiting for a free download slot
        self._probe = None            # playlist/channel probe thread
        self._probe_dialog = None
        # Completed downloads history: "media|url" -> {"file": path, "count": n}
        try:
            self._history = json.loads(self.settings.value("download_history", "{}"))
            if not isinstance(self._history, dict):
                self._history = {}
        except Exception:
            self._history = {}
        self._restore_preferences()

        # All external tools (ffmpeg, deno, yt-dlp) live in the runtime folder
        self.app_base_dir = config.RUNTIME_DIR
        try:
            os.makedirs(config.RUNTIME_DIR, exist_ok=True)
        except OSError:
            pass

        # Add local ffmpeg to PATH if present
        if os.path.exists(config.LOCAL_FFMPEG_BIN):
            os.environ['PATH'] = config.LOCAL_FFMPEG_BIN + os.pathsep + os.environ.get('PATH', '')

        # Check tools after the window is shown (non-blocking startup)
        QTimer.singleShot(0, self._startup_tool_check)

        # Pre-load the heavy yt_dlp module in the background so the first
        # download starts instantly while startup itself stays fast
        QTimer.singleShot(1200, self._warmup_ytdlp)

    def _place_common_group(self, index):
        """Move the shared Link card into the currently shown Video/Audio page"""
        target = {0: getattr(self, "video_tab_layout", None),
                  1: getattr(self, "audio_tab_layout", None)}.get(index)
        if target is not None and target.indexOf(self.common_group) == -1:
            target.insertWidget(0, self.common_group)
            self.common_group.show()

    def _warmup_ytdlp(self):
        """Import the heavy yt_dlp module in the background after startup"""
        import threading
        threading.Thread(target=config.get_yt_dlp, daemon=True).start()

    def _make_section(self, key, title):
        """Collapsible settings card whose open/closed state is remembered"""
        box = CollapsibleBox(title)
        box.set_expanded(self.settings.value(f"section_{key}", True, type=bool))
        box.toggle_button.clicked.connect(
            lambda _, k=key, b=box: self.settings.setValue(f"section_{k}", b.is_expanded()))
        self._sections.append(box)
        return box

    def _populate_browser_combo(self, combo):
        """Fill a cookies combo; item data is language-independent"""
        combo.addItem(self.tr("Disabled"), "disabled")
        for name in ("chrome", "firefox", "edge", "opera", "brave"):
            combo.addItem(name, name)
        combo.addItem("📄 " + self.tr("From file (cookies.txt)"), "file")

    def _startup_tool_check(self):
        """On first run: if tools are missing, prompt the user to install them"""
        try:
            from core.tools import tools_status
            ffmpeg_present, ytdlp_present, deno_present = tools_status()
            if not (ffmpeg_present and ytdlp_present and deno_present):
                from ui.dialogs import ToolInstallDialog
                dlg = ToolInstallDialog(
                    base_dir=self.app_base_dir,
                    install_ffmpeg=(not ffmpeg_present),
                    install_ytdlp=(not ytdlp_present),
                    install_deno=(not deno_present),
                    parent=self,
                    tr=self.tr
                )
                dlg.exec_()
                config.refresh_tools()
                if os.path.exists(config.LOCAL_FFMPEG_BIN):
                    os.environ['PATH'] = (config.LOCAL_FFMPEG_BIN + os.pathsep
                                          + os.environ.get('PATH', ''))
        except Exception as e:
            self.log(f"Tool check failed: {e}")

    def _workers(self, media_type):
        return self.video_workers if media_type == "Video" else self.audio_workers

    def _items(self, media_type):
        return self.video_items if media_type == "Video" else self.audio_items

    def _downloads_list(self, media_type):
        return self.video_downloads_list if media_type == "Video" else self.audio_downloads_list

    def _field_column(self, label, widget):
        """Small caption above its control - used for the one-line settings row"""
        label.setStyleSheet(config.FIELD_LABEL_STYLE)
        column = QVBoxLayout()
        column.setSpacing(4)
        column.addWidget(label)
        column.addWidget(widget)
        return column

    def _button_column(self, button):
        """Align an action button with the combo row (empty caption above)"""
        spacer = QLabel(" ")
        spacer.setStyleSheet(config.FIELD_LABEL_STYLE)
        column = QVBoxLayout()
        column.setSpacing(4)
        column.addWidget(spacer)
        column.addWidget(button)
        return column

    def _setup_video_tab(self):
        """Setup Video tab"""
        video_tab = QWidget()
        self.tabs.addTab(video_tab, "🎬 " + self.tr("Video"))
        video_layout = QVBoxLayout(video_tab)
        video_layout.setSpacing(10)
        video_layout.setContentsMargins(10, 10, 10, 10)
        self.video_tab_layout = video_layout

        self.video_settings_group = ShadowGroupBox(self.tr("Video Settings"))
        video_settings_layout = QHBoxLayout(self.video_settings_group)
        video_settings_layout.setSpacing(12)
        video_settings_layout.setContentsMargins(14, 20, 14, 14)

        self.quality_label = QLabel(self.tr("Quality:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems([
            "Original", "4320p", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p", "144p"
        ])
        self.resolution_combo.setMinimumWidth(100)
        video_settings_layout.addLayout(
            self._field_column(self.quality_label, self.resolution_combo), 1)

        self.format_label = QLabel(self.tr("Format:"))
        self.video_format_combo = QComboBox()
        self.video_format_combo.addItems([
            "mp4", "webm", "mkv", "avi", "mov", "flv"
        ])
        self.video_format_combo.setMinimumWidth(90)
        video_settings_layout.addLayout(
            self._field_column(self.format_label, self.video_format_combo), 1)

        self.cookies_label = QLabel(self.tr("Cookies:"))
        self.video_browser_combo = QComboBox()
        self._populate_browser_combo(self.video_browser_combo)
        self.video_browser_combo.setMinimumWidth(100)
        video_settings_layout.addLayout(
            self._field_column(self.cookies_label, self.video_browser_combo), 1)

        self.download_video_btn = QPushButton("⬇ " + self.tr("Download Video"))
        self.download_video_btn.setStyleSheet(config.STYLESHEET_BUTTON_PRIMARY)
        self.download_video_btn.clicked.connect(lambda: self.start_download("Video"))
        video_settings_layout.addLayout(
            self._button_column(self.download_video_btn), 1)

        video_layout.addWidget(self.video_settings_group)

        self.video_downloads_group = ShadowGroupBox(self.tr("Active Downloads"))
        video_downloads_layout = QVBoxLayout(self.video_downloads_group)

        self.video_downloads_list = QListWidget()
        self.video_downloads_list.setSpacing(10)
        self.video_downloads_list.setMinimumHeight(150)
        video_downloads_layout.addWidget(self.video_downloads_list)

        clear_completed_layout = QHBoxLayout()
        clear_completed_layout.addStretch()
        self.clear_video_completed_btn = QPushButton("🧹 " + self.tr("Clear Completed"))
        self.clear_video_completed_btn.setFont(self.CACHED_FONT)
        self.clear_video_completed_btn.clicked.connect(self.clear_completed_video)
        clear_completed_layout.addWidget(self.clear_video_completed_btn)
        video_downloads_layout.addLayout(clear_completed_layout)

        video_layout.addWidget(self.video_downloads_group, 1)

    def _setup_audio_tab(self):
        """Setup Audio tab"""
        audio_tab = QWidget()
        self.tabs.addTab(audio_tab, "🎧 " + self.tr("Audio"))
        audio_layout = QVBoxLayout(audio_tab)
        audio_layout.setSpacing(10)
        audio_layout.setContentsMargins(10, 10, 10, 10)
        self.audio_tab_layout = audio_layout

        self.audio_settings_group = ShadowGroupBox(self.tr("Audio Settings"))
        audio_settings_layout = QHBoxLayout(self.audio_settings_group)
        audio_settings_layout.setSpacing(12)
        audio_settings_layout.setContentsMargins(14, 20, 14, 14)

        self.audio_format_label = QLabel(self.tr("Format:"))
        self.audio_combo = QComboBox()
        self.audio_combo.addItems([
            "mp3", "m4a", "wav", "aac", "opus", "vorbis", "flac"
        ])
        self.audio_combo.setMinimumWidth(90)
        audio_settings_layout.addLayout(
            self._field_column(self.audio_format_label, self.audio_combo), 1)

        self.audio_cookies_label = QLabel(self.tr("Cookies:"))
        self.audio_browser_combo = QComboBox()
        self._populate_browser_combo(self.audio_browser_combo)
        self.audio_browser_combo.setMinimumWidth(100)
        audio_settings_layout.addLayout(
            self._field_column(self.audio_cookies_label, self.audio_browser_combo), 1)

        self.download_audio_btn = QPushButton("⬇ " + self.tr("Download Audio"))
        self.download_audio_btn.setStyleSheet(config.STYLESHEET_BUTTON_PRIMARY)
        self.download_audio_btn.clicked.connect(lambda: self.start_download("Audio"))
        audio_settings_layout.addLayout(
            self._button_column(self.download_audio_btn), 1)

        audio_layout.addWidget(self.audio_settings_group)

        self.audio_downloads_group = ShadowGroupBox(self.tr("Active Downloads"))
        audio_downloads_layout = QVBoxLayout(self.audio_downloads_group)

        self.audio_downloads_list = QListWidget()
        self.audio_downloads_list.setSpacing(10)
        self.audio_downloads_list.setMinimumHeight(150)
        audio_downloads_layout.addWidget(self.audio_downloads_list)

        clear_completed_layout = QHBoxLayout()
        clear_completed_layout.addStretch()
        self.clear_audio_completed_btn = QPushButton("🧹 " + self.tr("Clear Completed"))
        self.clear_audio_completed_btn.setFont(self.CACHED_FONT)
        self.clear_audio_completed_btn.clicked.connect(self.clear_completed_audio)
        clear_completed_layout.addWidget(self.clear_audio_completed_btn)
        audio_downloads_layout.addLayout(clear_completed_layout)

        audio_layout.addWidget(self.audio_downloads_group, 1)

    def _setup_logs_tab(self):
        """Setup Logs tab"""
        logs_tab = QWidget()
        self.tabs.addTab(logs_tab, "🧾 " + self.tr("Logs"))
        logs_layout = QVBoxLayout(logs_tab)
        logs_layout.setContentsMargins(8, 8, 8, 8)

        self.logs_group = ShadowGroupBox(self.tr("Download Logs"))
        logs_group_layout = QVBoxLayout(self.logs_group)

        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setFont(QFont("Consolas", 9))
        logs_group_layout.addWidget(self.logs_text)

        logs_buttons_layout = QHBoxLayout()
        self.clear_logs_btn = QPushButton("🧹 " + self.tr("Clear Logs"))
        self.clear_logs_btn.setFont(self.CACHED_FONT)
        self.clear_logs_btn.clicked.connect(self.clear_logs)
        logs_buttons_layout.addWidget(self.clear_logs_btn)

        self.copy_logs_btn = QPushButton("📋 " + self.tr("Copy Logs"))
        self.copy_logs_btn.setFont(self.CACHED_FONT)
        self.copy_logs_btn.clicked.connect(self.copy_logs)
        logs_buttons_layout.addWidget(self.copy_logs_btn)

        logs_group_layout.addLayout(logs_buttons_layout)
        logs_layout.addWidget(self.logs_group)

    def _setup_settings_tab(self):
        """Setup Settings tab (scrollable so cards never squeeze each other)"""
        settings_tab = QWidget()
        self.tabs.addTab(settings_tab, "⚙️ " + self.tr("Settings"))
        outer_layout = QVBoxLayout(settings_tab)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }")
        outer_layout.addWidget(scroll)

        settings_content = QWidget()
        scroll.setWidget(settings_content)
        settings_layout = QVBoxLayout(settings_content)
        settings_layout.setContentsMargins(10, 10, 10, 10)
        settings_layout.setSpacing(8)

        self.dir_group = self._make_section("folder", self.tr("Download Folder"))
        dir_layout = QGridLayout()
        dir_layout.setSpacing(8)
        dir_layout.setContentsMargins(6, 4, 6, 4)

        self.default_folder_label = QLabel(self.tr("Default Folder:"))
        dir_layout.addWidget(self.default_folder_label, 0, 0)
        self.default_dir_input = QLineEdit(self.output_dir)
        self.default_dir_input.setReadOnly(True)
        self.default_dir_input.setFont(self.CACHED_FONT)
        dir_layout.addWidget(self.default_dir_input, 0, 1)

        self.default_dir_button = QPushButton("📂 " + self.tr("Choose"))
        self.default_dir_button.setFixedWidth(110)
        self.default_dir_button.setFont(self.CACHED_FONT)
        self.default_dir_button.clicked.connect(self.select_default_directory)
        dir_layout.addWidget(self.default_dir_button, 0, 2)

        self.dir_group.setContentLayout(dir_layout)
        settings_layout.addWidget(self.dir_group)

        # Download queue: sequential or parallel with a limit
        self.downloads_group = self._make_section("downloads", self.tr("Downloads"))
        dlmode_layout = QHBoxLayout()
        dlmode_layout.setContentsMargins(6, 4, 6, 4)
        dlmode_layout.setSpacing(10)

        self.dlmode_label = QLabel(self.tr("Mode:"))
        dlmode_layout.addWidget(self.dlmode_label)
        self.dlmode_combo = QComboBox()
        self.dlmode_combo.addItem(self.tr("Sequential (one by one)"), "sequential")
        self.dlmode_combo.addItem(self.tr("Parallel"), "parallel")
        mode_idx = self.dlmode_combo.findData(
            self.settings.value("download_mode", "parallel"))
        if mode_idx >= 0:
            self.dlmode_combo.setCurrentIndex(mode_idx)
        self.dlmode_combo.currentIndexChanged.connect(self._on_dlmode_changed)
        dlmode_layout.addWidget(self.dlmode_combo)

        self.parallel_label = QLabel(self.tr("Parallel downloads:"))
        dlmode_layout.addWidget(self.parallel_label)
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(2, 10)
        self.parallel_spin.setValue(
            self.settings.value("parallel_limit", 3, type=int))
        self.parallel_spin.valueChanged.connect(self._on_parallel_limit_changed)
        dlmode_layout.addWidget(self.parallel_spin)
        dlmode_layout.addStretch()
        self.parallel_spin.setEnabled(self.dlmode_combo.currentData() == "parallel")

        self.downloads_group.setContentLayout(dlmode_layout)
        settings_layout.addWidget(self.downloads_group)

        # Cookies file (used when a Cookies combo is set to "From file")
        self.cookies_group = self._make_section("cookies", self.tr("Cookies file"))
        cookies_layout = QHBoxLayout()
        cookies_layout.setContentsMargins(6, 4, 6, 4)
        cookies_layout.setSpacing(8)

        self.cookies_file_input = QLineEdit(self.cookies_file)
        self.cookies_file_input.setReadOnly(True)
        self.cookies_file_input.setPlaceholderText("cookies.txt")
        cookies_layout.addWidget(self.cookies_file_input, 1)

        self.cookies_choose_btn = QPushButton("📂 " + self.tr("Choose"))
        self.cookies_choose_btn.clicked.connect(self._choose_cookies_file)
        cookies_layout.addWidget(self.cookies_choose_btn)

        self.cookies_reset_btn = QPushButton("✖ " + self.tr("Reset"))
        self.cookies_reset_btn.setStyleSheet(config.STYLESHEET_BUTTON_DANGER)
        self.cookies_reset_btn.clicked.connect(self._reset_cookies_file)
        cookies_layout.addWidget(self.cookies_reset_btn)

        self.cookies_group.setContentLayout(cookies_layout)
        settings_layout.addWidget(self.cookies_group)

        self.notifications_group = self._make_section("notifications", self.tr("Notifications"))
        notifications_layout = QVBoxLayout()
        notifications_layout.setContentsMargins(6, 4, 6, 4)

        self.notifications_check = QCheckBox(self.tr("Show download completion notifications"))
        self.notifications_check.setChecked(True)
        self.notifications_check.setFont(self.CACHED_FONT)
        notifications_layout.addWidget(self.notifications_check)

        self.sound_notifications_check = QCheckBox(self.tr("Play sound on notification"))
        self.sound_notifications_check.setChecked(True)
        self.sound_notifications_check.setFont(self.CACHED_FONT)
        notifications_layout.addWidget(self.sound_notifications_check)

        self.notifications_group.setContentLayout(notifications_layout)
        settings_layout.addWidget(self.notifications_group)

        # Language Settings
        self.lang_group = self._make_section("language", self.tr("Language Settings"))
        lang_layout = QGridLayout()
        lang_layout.setSpacing(8)
        lang_layout.setContentsMargins(6, 4, 6, 4)

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
        self.lang_combo.setFont(self.CACHED_FONT)

        # Set current language
        index = self.lang_combo.findData(self.current_lang)
        if index >= 0:
            self.lang_combo.setCurrentIndex(index)

        lang_layout.addWidget(self.lang_combo, 0, 1)

        self.apply_lang_btn = QPushButton(self.tr("Apply"))
        self.apply_lang_btn.clicked.connect(self.apply_language)
        lang_layout.addWidget(self.apply_lang_btn, 1, 1)

        self.lang_group.setContentLayout(lang_layout)
        settings_layout.addWidget(self.lang_group)

        # Appearance: theme color, saturation, light/dark mode, wave animation
        self.theme_group = self._make_section("appearance", self.tr("Appearance"))
        theme_layout = QGridLayout()
        theme_layout.setContentsMargins(6, 4, 6, 4)
        theme_layout.setHorizontalSpacing(12)
        theme_layout.setVerticalSpacing(10)
        theme_layout.setColumnStretch(1, 1)

        self.theme_color_label = QLabel(self.tr("Color:"))
        theme_layout.addWidget(self.theme_color_label, 0, 0)
        hue_row = QHBoxLayout()
        hue_row.setSpacing(12)
        self.hue_slider = QSlider(Qt.Horizontal)
        self.hue_slider.setRange(0, 360)
        self.hue_slider.setValue(config.CURRENT_HUE)
        self.hue_slider.setStyleSheet(config.STYLESHEET_HUE_SLIDER)
        self.hue_slider.valueChanged.connect(self._on_hue_changed)
        self.hue_slider.sliderReleased.connect(
            lambda: self.settings.setValue("hue", self.hue_slider.value()))
        hue_row.addWidget(self.hue_slider, 1)
        self.hue_swatch = QLabel()
        self.hue_swatch.setFixedSize(22, 22)
        self.hue_swatch.setStyleSheet(
            f"background: {config.COLOR_PRIMARY}; border-radius: 11px;")
        hue_row.addWidget(self.hue_swatch)
        self.hue_value_label = QLabel(str(config.CURRENT_HUE))
        self.hue_value_label.setFixedWidth(30)
        self.hue_value_label.setAlignment(Qt.AlignCenter)
        hue_row.addWidget(self.hue_value_label)
        self.color_pick_btn = QPushButton("🎨")
        self.color_pick_btn.setFixedSize(28, 26)
        self.color_pick_btn.setToolTip(self.tr("Pick color..."))
        self.color_pick_btn.clicked.connect(self._pick_theme_color)
        hue_row.addWidget(self.color_pick_btn)
        theme_layout.addLayout(hue_row, 0, 1)

        self.saturation_label = QLabel(self.tr("Saturation:"))
        theme_layout.addWidget(self.saturation_label, 1, 0)
        sat_row = QHBoxLayout()
        sat_row.setSpacing(12)
        self.sat_slider = QSlider(Qt.Horizontal)
        self.sat_slider.setRange(50, 160)
        self.sat_slider.setValue(config.CURRENT_SATURATION)
        self.sat_slider.setStyleSheet(config.STYLESHEET_SAT_SLIDER)
        self.sat_slider.valueChanged.connect(self._on_saturation_changed)
        self.sat_slider.sliderReleased.connect(
            lambda: self.settings.setValue("saturation", self.sat_slider.value()))
        sat_row.addWidget(self.sat_slider, 1)
        self.sat_value_label = QLabel(f"{config.CURRENT_SATURATION}%")
        self.sat_value_label.setFixedWidth(100)  # aligns with controls above
        self.sat_value_label.setAlignment(Qt.AlignCenter)
        sat_row.addWidget(self.sat_value_label)
        theme_layout.addLayout(sat_row, 1, 1)

        self.appearance_mode_label = QLabel(self.tr("Mode:"))
        theme_layout.addWidget(self.appearance_mode_label, 2, 0)
        self.theme_mode_combo = QComboBox()
        self.theme_mode_combo.addItem(self.tr("Light"), "light")
        self.theme_mode_combo.addItem(self.tr("Dark"), "dark")
        self.theme_mode_combo.addItem(self.tr("System"), "system")
        mode_index = self.theme_mode_combo.findData(
            self.settings.value("theme_mode", "light"))
        if mode_index >= 0:
            self.theme_mode_combo.setCurrentIndex(mode_index)
        self.theme_mode_combo.setFixedWidth(170)
        self.theme_mode_combo.currentIndexChanged.connect(self._on_theme_mode_changed)
        theme_layout.addWidget(self.theme_mode_combo, 2, 1, Qt.AlignLeft)

        self.wave_anim_check = QCheckBox(self.tr("Animated waves"))
        self.wave_anim_check.setChecked(self.settings.value("wave_anim", True, type=bool))
        self.wave_anim_check.stateChanged.connect(self._on_wave_anim_toggled)
        theme_layout.addWidget(self.wave_anim_check, 3, 1)

        self.theme_group.setContentLayout(theme_layout)
        settings_layout.addWidget(self.theme_group)

        # Button to check and install local tools
        self.check_tools_btn = QPushButton("🧰 " + self.tr("Check/Install Tools"))
        self.check_tools_btn.clicked.connect(self.check_and_install_tools)
        settings_layout.addWidget(self.check_tools_btn)

        # Button to update tools to the latest versions
        self.update_tools_btn = QPushButton(self.tr("🔄 Update Tools"))
        self.update_tools_btn.clicked.connect(self.update_tools)
        settings_layout.addWidget(self.update_tools_btn)

        settings_layout.addStretch()

    # ------------------------------------------------------------- theme

    def _on_hue_changed(self, value):
        """Recolor the whole app live while the hue slider moves"""
        config.set_theme(hue=value)
        self._apply_theme()

    def _on_saturation_changed(self, value):
        """Softer or more vivid colors, live"""
        config.set_theme(saturation=value)
        self._apply_theme()

    def _on_theme_mode_changed(self):
        """Switch between light / dark / system appearance"""
        mode = self.theme_mode_combo.currentData() or "light"
        config.set_theme(dark=config.is_system_dark() if mode == "system"
                         else (mode == "dark"))
        self.settings.setValue("theme_mode", mode)
        self._apply_theme()

    def _on_wave_anim_toggled(self):
        animated = self.wave_anim_check.isChecked()
        self.settings.setValue("wave_anim", animated)
        self.banner.set_animated(animated)

    def _pick_theme_color(self):
        """Advanced color picker (palette, spectrum, hex, screen eyedropper) -
        the picked color is mapped onto the theme hue and saturation"""
        dlg = QColorDialog(self)
        dlg.setOption(QColorDialog.DontUseNativeDialog, True)
        dlg.setCurrentColor(QColor(config.COLOR_PRIMARY))
        dlg.setWindowTitle(self.tr("Pick color..."))
        if dlg.exec_():
            col = dlg.currentColor()
            _, C, H = config.srgb_to_oklch(col.red(), col.green(), col.blue())
            self.hue_slider.setValue(int(round(H)))
            self.sat_slider.setValue(max(50, min(160, int(round(C / 0.14 * 100)))))
            self.settings.setValue("hue", config.CURRENT_HUE)
            self.settings.setValue("saturation", config.CURRENT_SATURATION)

    def _apply_theme(self):
        """Re-apply all hue-dependent styles to existing widgets"""
        self.setStyleSheet(config.STYLESHEET_MAIN)
        for group in self.findChildren(QGroupBox):
            group.setStyleSheet(config.STYLESHEET_GROUPBOX)
        self.download_video_btn.setStyleSheet(config.STYLESHEET_BUTTON_PRIMARY)
        self.download_audio_btn.setStyleSheet(config.STYLESHEET_BUTTON_PRIMARY)
        for label in (self.quality_label, self.format_label, self.cookies_label,
                      self.audio_format_label, self.audio_cookies_label):
            label.setStyleSheet(config.FIELD_LABEL_STYLE)
        self.hue_slider.setStyleSheet(config.STYLESHEET_HUE_SLIDER)
        self.sat_slider.setStyleSheet(config.STYLESHEET_SAT_SLIDER)
        self.hue_swatch.setStyleSheet(
            f"background: {config.COLOR_PRIMARY}; border-radius: 11px;")
        self.hue_value_label.setText(str(config.CURRENT_HUE))
        self.sat_value_label.setText(f"{config.CURRENT_SATURATION}%")
        self.clear_button.setStyleSheet(config.STYLESHEET_BUTTON_DANGER)
        self.cookies_reset_btn.setStyleSheet(config.STYLESHEET_BUTTON_DANGER)
        self.github_btn.setStyleSheet(config.STYLESHEET_BUTTON_LINK)
        self.donate_btn.setStyleSheet(config.STYLESHEET_BUTTON_LINK)
        self.banner.update()
        for box in self._sections:
            box.apply_theme()
        for items in (self.video_items, self.audio_items):
            for _, item_widget in items.values():
                item_widget.apply_theme()

    # ------------------------------------------------------- preferences

    def _restore_preferences(self):
        """Restore user preferences saved in previous sessions"""
        def restore_combo(combo, key):
            value = self.settings.value(key, "")
            if value:
                index = combo.findText(value)
                if index >= 0:
                    combo.setCurrentIndex(index)

        def restore_combo_data(combo, key):
            value = self.settings.value(key, "")
            if value:
                index = combo.findData(value)
                if index >= 0:
                    combo.setCurrentIndex(index)

        restore_combo(self.resolution_combo, "video_resolution")
        restore_combo(self.video_format_combo, "video_format")
        restore_combo(self.audio_combo, "audio_format")
        restore_combo_data(self.video_browser_combo, "video_browser")
        restore_combo_data(self.audio_browser_combo, "audio_browser")
        self.notifications_check.setChecked(self.settings.value("notifications", True, type=bool))
        self.sound_notifications_check.setChecked(self.settings.value("sound", True, type=bool))

    def _save_preferences(self):
        """Persist user preferences"""
        self.settings.setValue("video_resolution", self.resolution_combo.currentText())
        self.settings.setValue("video_format", self.video_format_combo.currentText())
        self.settings.setValue("audio_format", self.audio_combo.currentText())
        self.settings.setValue("video_browser", self.video_browser_combo.currentData())
        self.settings.setValue("audio_browser", self.audio_browser_combo.currentData())
        self.settings.setValue("notifications", self.notifications_check.isChecked())
        self.settings.setValue("sound", self.sound_notifications_check.isChecked())
        self.settings.setValue("output_dir", self.output_dir)
        self.settings.setValue("hue", config.CURRENT_HUE)
        self.settings.setValue("saturation", config.CURRENT_SATURATION)
        self.settings.setValue("theme_mode",
                               self.theme_mode_combo.currentData() or "light")
        self.settings.setValue("download_mode",
                               self.dlmode_combo.currentData() or "parallel")
        self.settings.setValue("parallel_limit", self.parallel_spin.value())
        self.settings.setValue("cookies_file", self.cookies_file)

    def closeEvent(self, event):
        """Stop active downloads and save preferences before closing"""
        self._save_preferences()
        self._queue.clear()
        pending = [w for w in (*self.video_workers.values(),
                               *self.audio_workers.values(),
                               *self._zombie_workers) if w.isRunning()]
        for worker in pending:
            try:
                worker.stop()
            except Exception:
                pass
        for worker in pending:
            try:
                if not worker.wait(5000):
                    # Last resort: forcing is better than a Qt fatal at exit
                    worker.terminate()
                    worker.wait(2000)
            except Exception:
                pass
        event.accept()

    def tr(self, text):
        """Translate text using current translations"""
        return self.translations.get(self.current_lang, {}).get(text, text)

    def load_translations(self):
        """Load translations from JSON files in locales folder"""
        import config

        # Try to find locales directory
        locales_candidates = [
            os.path.join(config.BASE_DIR, "locales"),  # From config
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locales"),  # Parent dir
            os.path.join(os.path.dirname(config.BASE_DIR), "locales"),  # Sibling
            "locales",  # Current dir
        ]

        locales_dir = None
        for candidate in locales_candidates:
            if os.path.exists(candidate):
                locales_dir = candidate
                break

        if not locales_dir:
            # Try to create default
            locales_dir = locales_candidates[0]
            try:
                os.makedirs(locales_dir, exist_ok=True)
            except Exception as e:
                print(f"Error creating locales directory: {e}")
                return

        try:
            for file in os.listdir(locales_dir):
                if file.endswith(".json"):
                    lang_code = file.split(".")[0]
                    try:
                        with open(os.path.join(locales_dir, file), "r", encoding="utf-8") as f:
                            self.translations[lang_code] = json.load(f)
                    except Exception as e:
                        print(f"Error loading {file}: {str(e)}")
        except Exception as e:
            print(f"Error reading locales directory: {e}")

        if "en" not in self.translations:
            self.translations["en"] = {"Download Internet Video": "Download Internet Video"}

    def apply_language(self):
        """Apply selected language"""
        new_lang = self.lang_combo.currentData()
        if new_lang != self.current_lang:
            self.current_lang = new_lang
            self.settings.setValue("language", new_lang)

            # Update UI text
            self.setWindowTitle(APP_TITLE)
            self.banner.setTitle(APP_TITLE)

            self.tabs.setTabText(0, "🎬 " + self.tr("Video"))
            self.tabs.setTabText(1, "🎧 " + self.tr("Audio"))
            self.tabs.setTabText(2, "🧾 " + self.tr("Logs"))
            self.tabs.setTabText(3, "⚙️ " + self.tr("Settings"))

            self.common_group.setTitle(self.tr("Common Settings"))
            self.link_label.setText(self.tr("Link:"))
            self.paste_button.setText("📋 " + self.tr("Paste"))
            self.clear_button.setText("✖ " + self.tr("Clear"))

            self.video_settings_group.setTitle(self.tr("Video Settings"))
            self.quality_label.setText(self.tr("Quality:"))
            self.format_label.setText(self.tr("Format:"))
            self.cookies_label.setText(self.tr("Cookies:"))
            self.video_browser_combo.setItemText(0, self.tr("Disabled"))
            self.video_browser_combo.setItemText(
                self.video_browser_combo.count() - 1,
                "📄 " + self.tr("From file (cookies.txt)"))
            self.audio_browser_combo.setItemText(0, self.tr("Disabled"))
            self.audio_browser_combo.setItemText(
                self.audio_browser_combo.count() - 1,
                "📄 " + self.tr("From file (cookies.txt)"))
            self.download_video_btn.setText("⬇ " + self.tr("Download Video"))
            self.video_downloads_group.setTitle(self.tr("Active Downloads"))
            self.clear_video_completed_btn.setText("🧹 " + self.tr("Clear Completed"))

            self.audio_settings_group.setTitle(self.tr("Audio Settings"))
            self.audio_format_label.setText(self.tr("Format:"))
            self.audio_cookies_label.setText(self.tr("Cookies:"))
            self.download_audio_btn.setText("⬇ " + self.tr("Download Audio"))
            self.audio_downloads_group.setTitle(self.tr("Active Downloads"))
            self.clear_audio_completed_btn.setText("🧹 " + self.tr("Clear Completed"))

            self.logs_group.setTitle(self.tr("Download Logs"))
            self.clear_logs_btn.setText("🧹 " + self.tr("Clear Logs"))
            self.copy_logs_btn.setText("📋 " + self.tr("Copy Logs"))

            self.dir_group.setTitle(self.tr("Download Folder"))
            self.default_folder_label.setText(self.tr("Default Folder:"))
            self.default_dir_button.setText("📂 " + self.tr("Choose"))
            self.downloads_group.setTitle(self.tr("Downloads"))
            self.dlmode_label.setText(self.tr("Mode:"))
            self.dlmode_combo.setItemText(0, self.tr("Sequential (one by one)"))
            self.dlmode_combo.setItemText(1, self.tr("Parallel"))
            self.parallel_label.setText(self.tr("Parallel downloads:"))
            self.cookies_group.setTitle(self.tr("Cookies file"))
            self.cookies_choose_btn.setText("📂 " + self.tr("Choose"))
            self.cookies_reset_btn.setText("✖ " + self.tr("Reset"))
            self.notifications_group.setTitle(self.tr("Notifications"))
            self.notifications_check.setText(self.tr("Show download completion notifications"))
            self.sound_notifications_check.setText(self.tr("Play sound on notification"))
            self.lang_group.setTitle(self.tr("Language Settings"))
            self.theme_group.setTitle(self.tr("Appearance"))
            self.theme_color_label.setText(self.tr("Color:"))
            self.saturation_label.setText(self.tr("Saturation:"))
            self.appearance_mode_label.setText(self.tr("Mode:"))
            self.theme_mode_combo.setItemText(0, self.tr("Light"))
            self.theme_mode_combo.setItemText(1, self.tr("Dark"))
            self.theme_mode_combo.setItemText(2, self.tr("System"))
            self.wave_anim_check.setText(self.tr("Animated waves"))
            self.color_pick_btn.setToolTip(self.tr("Pick color..."))
            self.interface_lang_label.setText(self.tr("Interface Language:"))
            self.apply_lang_btn.setText(self.tr("Apply"))
            self.check_tools_btn.setText("🧰 " + self.tr("Check/Install Tools"))
            self.update_tools_btn.setText(self.tr("🔄 Update Tools"))
            self.donate_btn.setText("💛 " + self.tr("Donate"))

            self.update()
            QApplication.processEvents()

    # ----------------------------------------------------------- helpers

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
            self.settings.setValue("output_dir", directory)

    def _choose_cookies_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Select cookies file"), "",
            "cookies.txt (*.txt);;All files (*.*)")
        if path:
            self.cookies_file = path
            self.cookies_file_input.setText(path)
            self.settings.setValue("cookies_file", path)

    def _reset_cookies_file(self):
        self.cookies_file = ""
        self.cookies_file_input.clear()
        self.settings.setValue("cookies_file", "")

    def _cookie_params(self, media_type):
        """(use_cookies, browser, cookies_file) for the selected cookies mode"""
        combo = self.video_browser_combo if media_type == "Video" else self.audio_browser_combo
        data = combo.currentData() or "disabled"
        if data == "file":
            return False, "disabled", self.cookies_file
        return data != "disabled", data, ""

    def _on_dlmode_changed(self):
        mode = self.dlmode_combo.currentData() or "parallel"
        self.parallel_spin.setEnabled(mode == "parallel")
        self.settings.setValue("download_mode", mode)
        self._pump_queue()

    def _on_parallel_limit_changed(self, value):
        self.settings.setValue("parallel_limit", value)
        self._pump_queue()

    # ---------------------------------------------------- download queue

    def _download_limit(self):
        if (self.dlmode_combo.currentData() or "parallel") == "sequential":
            return 1
        return self.parallel_spin.value()

    def _running_count(self):
        return len(self.video_workers) + len(self.audio_workers)

    def _pump_queue(self):
        """Start queued downloads while there are free slots"""
        while self._queue and self._running_count() < self._download_limit():
            job = self._queue.pop(0)
            self._launch_job(job)

    def _url_busy(self, url, media_type):
        if any(w.url == url for w in self._workers(media_type).values()):
            return True
        return any(j["url"] == url and j["media_type"] == media_type
                   for j in self._queue)

    def _enqueue_url(self, url, media_type, overwrite=False, filename_suffix="",
                     title=None):
        """Create a download card and put the job into the queue"""
        if self._url_busy(url, media_type):
            return

        use_cookies, browser, cfile = self._cookie_params(media_type)

        self._download_seq += 1
        dl_id = f"{media_type}-{self._download_seq}"

        item_widget = DownloadItemWidget(
            title or self.tr("Preparing download..."), media_type, tr=self.tr)
        if title:
            item_widget.title_label.setToolTip(title)
        list_item = QListWidgetItem()
        list_item.setSizeHint(item_widget.sizeHint())
        downloads_list = self._downloads_list(media_type)
        downloads_list.addItem(list_item)
        downloads_list.setItemWidget(list_item, item_widget)
        self._items(media_type)[dl_id] = (list_item, item_widget)

        item_widget.cancel_button.clicked.connect(lambda _, d=dl_id: self.cancel_download(d, media_type))
        item_widget.pause_button.clicked.connect(lambda _, d=dl_id: self.pause_download(d, media_type))
        item_widget.delete_button.clicked.connect(lambda _, d=dl_id: self.remove_download(d, media_type))

        job = {
            "dl_id": dl_id,
            "media_type": media_type,
            "url": url,
            "use_cookies": use_cookies,
            "browser": browser,
            "cookies_file": cfile,
            "resolution": self.resolution_combo.currentText() if media_type == "Video" else "",
            "video_format": self.video_format_combo.currentText() if media_type == "Video" else "",
            "audio_format": self.audio_combo.currentText() if media_type == "Audio" else "",
            "output_dir": self.output_dir,
            "overwrite": overwrite,
            "filename_suffix": filename_suffix,
        }
        self._queue.append(job)
        item_widget.set_queued()
        self._pump_queue()

    def _launch_job(self, job):
        """Create and start the worker for a queued job"""
        media_type = job["media_type"]
        dl_id = job["dl_id"]
        pair = self._items(media_type).get(dl_id)
        if pair is None:
            return  # the card was removed while waiting
        _, item_widget = pair

        worker = DownloadWorker(
            url=job["url"],
            use_cookies=job["use_cookies"],
            browser=job["browser"],
            media_type=media_type,
            resolution=job["resolution"],
            video_format=job["video_format"],
            audio_format=job["audio_format"],
            output_dir=job["output_dir"],
            overwrite=job["overwrite"],
            filename_suffix=job["filename_suffix"],
            cookies_file=job["cookies_file"],
        )
        self.setup_worker(worker, dl_id, media_type, item_widget)
        self._workers(media_type)[dl_id] = worker
        item_widget.set_started()

    # ------------------------------------------------------ start download

    def _looks_like_collection(self, url):
        """Channel or playlist URL (multiple videos)?"""
        u = url.lower()
        if "watch?v=" in u or "/shorts/" in u:
            return False
        return any(p in u for p in ("playlist?list=", "/playlist/", "/channel/",
                                    "/c/", "/user/", "/@"))

    def start_download(self, media_type):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Enter video URL"))
            return

        # "From file" cookies mode needs a chosen file
        combo = self.video_browser_combo if media_type == "Video" else self.audio_browser_combo
        if (combo.currentData() or "") == "file" and not (
                self.cookies_file and os.path.exists(self.cookies_file)):
            QMessageBox.warning(self, self.tr("Error"),
                                self.tr("Select cookies file first (Settings)"))
            return

        # Channel / playlist: show the video picker
        if self._looks_like_collection(url):
            self._probe_collection(url, media_type)
            return

        if self._url_busy(url, media_type):
            QMessageBox.information(self, self.tr("Info"),
                                    self.tr("This URL is already being downloaded"))
            return

        # Was this link already downloaded before? Ask what to do.
        overwrite = False
        filename_suffix = ""
        entry = self._history.get(f"{media_type}|{url}")
        if isinstance(entry, dict):
            old_file = entry.get("file") or ""
            if old_file and os.path.exists(old_file):
                choice = self._ask_duplicate_action(old_file)
                if choice == "cancel":
                    return
                if choice == "replace":
                    overwrite = True
                elif choice == "copy":
                    filename_suffix = f" ({int(entry.get('count', 1)) + 1})"

        self._enqueue_url(url, media_type, overwrite, filename_suffix)

    # ------------------------------------------------- channel / playlist

    def _probe_collection(self, url, media_type):
        """Fetch the list of videos behind a channel/playlist link"""
        if self._probe is not None and self._probe.isRunning():
            return
        use_cookies, browser, cfile = self._cookie_params(media_type)
        self._probe_media = media_type
        self._probe = PlaylistProbeWorker(url, use_cookies, browser, cfile)
        self._probe.done.connect(self._on_probe_done)
        self._probe.failed.connect(self._on_probe_failed)

        self._probe_dialog = QProgressDialog(
            self.tr("Fetching video list..."), self.tr("Cancel"), 0, 0, self)
        self._probe_dialog.setWindowTitle(self.tr("Select videos to download"))
        self._probe_dialog.setWindowModality(Qt.WindowModal)
        self._probe_dialog.setMinimumDuration(0)
        self._probe_dialog.canceled.connect(self._cancel_probe)
        self._probe.start()
        self._probe_dialog.show()

    def _cancel_probe(self):
        if self._probe is not None:
            try:
                self._probe.done.disconnect(self._on_probe_done)
                self._probe.failed.disconnect(self._on_probe_failed)
            except Exception:
                pass

    def _close_probe_dialog(self):
        if self._probe_dialog is not None:
            try:
                self._probe_dialog.canceled.disconnect(self._cancel_probe)
            except Exception:
                pass
            self._probe_dialog.reset()
            self._probe_dialog = None

    def _on_probe_done(self, items):
        self._close_probe_dialog()
        from ui.dialogs import VideoSelectDialog
        dlg = VideoSelectDialog(items, parent=self, tr=self.tr)
        if dlg.exec_():
            selected = dlg.selected_items()
            for it in selected:
                self._enqueue_url(it["url"], self._probe_media, title=it["title"])
            if selected:
                self.log(f"Queued {len(selected)} video(s) from the list")

    def _on_probe_failed(self, msg):
        self._close_probe_dialog()
        QMessageBox.warning(self, self.tr("Error"),
                            self.tr("Failed to get video list") + f"\n{msg}")

    # --------------------------------------------------------- duplicates

    def _ask_duplicate_action(self, old_file):
        """The link was downloaded before - ask: replace, save a copy or cancel"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(self.tr("Already Downloaded"))
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setText(
            self.tr("This video was already downloaded:") + "\n"
            + os.path.basename(old_file) + "\n\n"
            + self.tr("What do you want to do?"))
        btn_replace = msg_box.addButton(self.tr("Download again (replace)"),
                                        QMessageBox.AcceptRole)
        btn_copy = msg_box.addButton(self.tr("Save as a copy"), QMessageBox.ActionRole)
        msg_box.addButton(self.tr("Cancel"), QMessageBox.RejectRole)
        msg_box.exec_()
        clicked = msg_box.clickedButton()
        if clicked == btn_replace:
            return "replace"
        if clicked == btn_copy:
            return "copy"
        return "cancel"

    def _record_download(self, media_type, url, filename, suffix):
        """Remember a finished download for future duplicate detection"""
        key = f"{media_type}|{url}"
        old = self._history.get(key)
        entry = old if isinstance(old, dict) else {}
        if suffix:
            digits = ''.join(ch for ch in suffix if ch.isdigit())
            count = int(digits) if digits else int(entry.get("count", 1)) + 1
        else:
            count = max(int(entry.get("count", 0) or 0), 1)
        self._history[key] = {"file": filename, "count": count}
        if len(self._history) > 300:
            for k in list(self._history)[:len(self._history) - 300]:
                del self._history[k]
        try:
            self.settings.setValue("download_history",
                                   json.dumps(self._history, ensure_ascii=False))
        except Exception:
            pass

    # -------------------------------------------------------- worker glue

    def _set_item_title(self, item_widget, title):
        item_widget.title_label.setText(title)
        item_widget.title_label.setToolTip(title)

    def setup_worker(self, worker, dl_id, media_type, item_widget):
        worker.title_signal.connect(lambda title: self._set_item_title(item_widget, title))
        worker.thumbnail_signal.connect(item_widget.set_thumbnail)
        worker.progress_signal.connect(item_widget.update_progress)
        worker.finished_signal.connect(lambda filename: self.download_completed(dl_id, media_type, item_widget, filename))
        worker.error_signal.connect(lambda msg: self.show_error(msg, dl_id, media_type, item_widget))
        worker.log_signal.connect(self.log)
        worker.conversion_signal.connect(lambda status: self.handle_conversion(status, item_widget))
        # Drop the reference kept in _zombie_workers once the thread really ends
        worker.finished.connect(lambda w=worker: self._zombie_workers.discard(w))
        worker.start()

    def _retire_worker(self, dl_id, media_type):
        """Remove worker from the active dict, keeping it alive until its thread ends"""
        worker = self._workers(media_type).pop(dl_id, None)
        if worker is not None and not worker.isFinished():
            self._zombie_workers.add(worker)

    def handle_conversion(self, status, item_widget):
        if status == 'started':
            item_widget.set_converting()
        elif status == 'finished':
            item_widget.set_completed()

    def download_completed(self, dl_id, media_type, item_widget, filename):
        self.log(f"{media_type} downloaded: {filename}")

        worker = self._workers(media_type).get(dl_id)
        if worker is not None and filename:
            self._record_download(media_type, worker.url, filename,
                                  worker.filename_suffix)

        item_widget.set_completed()
        item_widget.cancel_button.setVisible(False)
        item_widget.pause_button.setVisible(False)
        item_widget.delete_button.setVisible(True)
        item_widget.title_label.setStyleSheet(
            f"color: {config.COLOR_GREEN}; font-weight: 600; background: transparent;")

        self._retire_worker(dl_id, media_type)
        self._pump_queue()

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
        msg_box.addButton(self.tr("Close"), QMessageBox.RejectRole)

        msg_box.setIcon(QMessageBox.Information)

        if self.sound_notifications_check.isChecked():
            try:
                if sys.platform == "win32":
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
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

    def pause_download(self, dl_id, media_type):
        worker = self._workers(media_type).get(dl_id)
        if worker is None:
            return
        worker.pause()
        items = self._items(media_type)
        if dl_id in items:
            _, item_widget = items[dl_id]
            item_widget.set_paused(worker.paused)

    def cancel_download(self, dl_id, media_type):
        worker = self._workers(media_type).get(dl_id)

        if worker is None:
            # still waiting in the queue?
            for i, job in enumerate(self._queue):
                if job["dl_id"] == dl_id and job["media_type"] == media_type:
                    del self._queue[i]
                    break
            else:
                return
        else:
            worker.stop()
            worker.wait(5000)  # bounded so a stalled worker cannot freeze the UI

        items = self._items(media_type)
        if dl_id in items:
            _, item_widget = items[dl_id]
            item_widget.set_canceled()
            item_widget.cancel_button.setVisible(False)
            item_widget.pause_button.setVisible(False)
            item_widget.delete_button.setVisible(True)
            item_widget.title_label.setStyleSheet(
                f"color: {config.COLOR_RED}; font-weight: 600; background: transparent;")

        if worker is not None:
            self._retire_worker(dl_id, media_type)
            self.log(f"{media_type} download canceled: {worker.url}")
        self._pump_queue()

    def remove_download(self, dl_id, media_type):
        items = self._items(media_type)
        if dl_id in items:
            list_item, _ = items[dl_id]
            downloads_list = self._downloads_list(media_type)
            downloads_list.takeItem(downloads_list.row(list_item))
            del items[dl_id]

    def _clear_completed(self, media_type):
        items = self._items(media_type)
        downloads_list = self._downloads_list(media_type)
        for dl_id in [d for d, (_, w) in items.items() if w.delete_button.isVisible()]:
            list_item, _ = items[dl_id]
            downloads_list.takeItem(downloads_list.row(list_item))
            del items[dl_id]

    def clear_completed_video(self):
        self._clear_completed("Video")

    def clear_completed_audio(self):
        self._clear_completed("Audio")

    def show_error(self, message, dl_id, media_type, item_widget):
        QMessageBox.critical(self, self.tr("Error"), message)
        self.log(f"Error downloading {media_type}: {message}")

        item_widget.set_error()
        item_widget.cancel_button.setVisible(False)
        item_widget.pause_button.setVisible(False)
        item_widget.delete_button.setVisible(True)
        item_widget.title_label.setStyleSheet(
            f"color: {config.COLOR_RED}; font-weight: 600; background: transparent;")

        self._retire_worker(dl_id, media_type)
        self._pump_queue()

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
        check_and_install_tools(parent=self, base_dir=self.app_base_dir)

    def _has_active_downloads(self):
        return any(w.isRunning() for w in (*self.video_workers.values(),
                                           *self.audio_workers.values(),
                                           *self._zombie_workers))

    def update_tools(self):
        """Update yt-dlp, Deno and FFmpeg to the latest versions"""
        # Updating swaps tool binaries; never do that mid-download
        if self._has_active_downloads():
            QMessageBox.information(self, self.tr("Info"),
                                    self.tr("Please wait for active downloads to finish"))
            return
        from ui.dialogs import ToolUpdateDialog
        dlg = ToolUpdateDialog(base_dir=self.app_base_dir, parent=self, tr=self.tr)
        dlg.exec_()
        config.refresh_tools()
        if os.path.exists(config.LOCAL_FFMPEG_BIN):
            os.environ['PATH'] = (config.LOCAL_FFMPEG_BIN + os.pathsep
                                  + os.environ.get('PATH', ''))


__all__ = ['YouTubeDownloader']
