"""
Global configuration and constants
"""
import os
import sys

# ===== PATHS =====
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOCAL_FFMPEG_BIN = os.path.join(BASE_DIR, 'ffmpeg', 'bin')
LOCAL_FFMPEG_EXE = os.path.join(LOCAL_FFMPEG_BIN, 'ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg')

YTDLP_EXE = None
candidate = os.path.join(BASE_DIR, 'yt-dlp.exe' if sys.platform == 'win32' else 'yt-dlp')
if os.path.exists(candidate):
    YTDLP_EXE = candidate

# ===== URLS =====
FFMPEG_DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
YTDLP_GITHUB_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"

# ===== CACHED STYLESHEETS (Performance optimization) =====
STYLESHEET_MAIN = """
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
"""

STYLESHEET_GROUPBOX = """
    QGroupBox {
        border: 2px solid #e0e0e0;
        border-radius: 5px;
        margin-top: 10px;
        padding-top: 15px;
        font-weight: bold;
        background-color: white;
        font-size: 9pt;
    }
"""

STYLESHEET_PROGRESS_BAR = """
    QProgressBar {
        border: 1px solid #ddd;
        border-radius: 5px;
        background: #f0f0f0;
    }
    QProgressBar::chunk {
        background-color: #34a853;
        border-radius: 5px;
    }
"""

STYLESHEET_BUTTON_YELLOW = """
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
"""

STYLESHEET_BUTTON_RED = """
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
"""

STYLESHEET_BUTTON_GREEN = """
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
"""

# Try to import yt_dlp module
try:
    import yt_dlp
    YTDLP_MODULE = True
except Exception:
    yt_dlp = None
    YTDLP_MODULE = False
