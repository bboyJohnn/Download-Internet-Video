"""
Global configuration and constants
"""
import math
import os
import sys

APP_VERSION = "1.0"
APP_TITLE = f"Download Internet Video {APP_VERSION}"

# ===== PATHS =====
# APP_DIR      - persistent directory next to the executable/script.
#                Tools installed at runtime go here so they survive restarts.
# RESOURCE_DIR - directory with bundled resources. For PyInstaller onefile
#                builds this is the temporary extraction dir (sys._MEIPASS);
#                otherwise it is the same as APP_DIR.
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
    RESOURCE_DIR = getattr(sys, '_MEIPASS', APP_DIR)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCE_DIR = APP_DIR

# Kept for backward compatibility with older imports
BASE_DIR = RESOURCE_DIR

_EXE_SUFFIX = '.exe' if sys.platform == 'win32' else ''


def _find_first(candidates):
    """Return the first existing path from candidates, else None"""
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


# --- runtime folder: ALL external tools live here (ffmpeg, deno, yt-dlp) ---
RUNTIME_DIR = os.path.join(APP_DIR, 'runtime')
_RUNTIME_RES = os.path.join(RESOURCE_DIR, 'runtime')

# --- ffmpeg ---
FFMPEG_CANDIDATE_DIRS = [
    os.path.join(RUNTIME_DIR, 'ffmpeg', 'bin'),
    os.path.join(_RUNTIME_RES, 'ffmpeg', 'bin'),
    # legacy locations (pre-runtime layouts)
    os.path.join(APP_DIR, 'ffmpeg', 'bin'),
    os.path.join(RESOURCE_DIR, 'ffmpeg', 'bin'),
    os.path.join(os.path.dirname(APP_DIR), 'ffmpeg', 'bin'),
]
LOCAL_FFMPEG_BIN = _find_first(FFMPEG_CANDIDATE_DIRS) or FFMPEG_CANDIDATE_DIRS[0]
LOCAL_FFMPEG_EXE = os.path.join(LOCAL_FFMPEG_BIN, 'ffmpeg' + _EXE_SUFFIX)

# --- yt-dlp ---
YTDLP_CANDIDATES = [
    os.path.join(RUNTIME_DIR, 'yt-dlp' + _EXE_SUFFIX),
    os.path.join(_RUNTIME_RES, 'yt-dlp' + _EXE_SUFFIX),
    # legacy locations
    os.path.join(APP_DIR, 'yt-dlp' + _EXE_SUFFIX),
    os.path.join(RESOURCE_DIR, 'yt-dlp' + _EXE_SUFFIX),
    os.path.join(os.path.dirname(APP_DIR), 'yt-dlp' + _EXE_SUFFIX),
]
YTDLP_EXE = _find_first(YTDLP_CANDIDATES)

# --- Deno (JavaScript runtime used by yt-dlp to solve YouTube JS challenges) ---
DENO_CANDIDATES = [
    os.path.join(RUNTIME_DIR, 'deno', 'deno' + _EXE_SUFFIX),
    os.path.join(_RUNTIME_RES, 'deno', 'deno' + _EXE_SUFFIX),
    # legacy locations
    os.path.join(APP_DIR, 'deno', 'deno' + _EXE_SUFFIX),
    os.path.join(RESOURCE_DIR, 'deno', 'deno' + _EXE_SUFFIX),
    os.path.join(APP_DIR, 'deno' + _EXE_SUFFIX),
]
DENO_EXE = _find_first(DENO_CANDIDATES)

# --- application icon ---
APP_ICON = _find_first([
    os.path.join(RESOURCE_DIR, 'app.ico'),
    os.path.join(APP_DIR, 'app.ico'),
])


def refresh_tools():
    """Re-resolve tool paths after tools were installed at runtime"""
    global LOCAL_FFMPEG_BIN, LOCAL_FFMPEG_EXE, YTDLP_EXE, DENO_EXE
    LOCAL_FFMPEG_BIN = _find_first(FFMPEG_CANDIDATE_DIRS) or FFMPEG_CANDIDATE_DIRS[0]
    LOCAL_FFMPEG_EXE = os.path.join(LOCAL_FFMPEG_BIN, 'ffmpeg' + _EXE_SUFFIX)
    YTDLP_EXE = _find_first(YTDLP_CANDIDATES)
    DENO_EXE = _find_first(DENO_CANDIDATES)


def get_downloads_dir():
    """User's real Downloads folder (handles OneDrive/shell redirection)"""
    if sys.platform == 'win32':
        try:
            import ctypes
            FOLDERID_Downloads = ctypes.c_char_p(
                b'\x90\xe2\x4d\x37\x3f\x12\x65\x45\x91\x64\x39\xc4\x92\x5e\x46\x7b')
            path_ptr = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(
                    FOLDERID_Downloads, 0, None, ctypes.byref(path_ptr)) == 0:
                path = path_ptr.value
                ctypes.windll.ole32.CoTaskMemFree(path_ptr)
                if path and os.path.isdir(path):
                    return path
        except Exception:
            pass
    return os.path.join(os.path.expanduser('~'), 'Downloads')


# ===== URLS =====
FFMPEG_DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
YTDLP_GITHUB_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
DENO_DOWNLOAD_URL = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
PROJECT_URL = "https://github.com/bboyJohnn/Download-Internet-Video"
DONATE_URL = PROJECT_URL  # placeholder until a donation link is provided

# ===== THEME =====
# Modern card design generated from a hue (0-360), a saturation multiplier
# and a light/dark switch - the same oklch formulas the reference site uses,
# so all three controls recolor the whole app live.

DEFAULT_HUE = 258          # blue, the classic app color
DEFAULT_SATURATION = 100   # percent; higher = more vivid colors
CURRENT_HUE = DEFAULT_HUE
CURRENT_SATURATION = DEFAULT_SATURATION
CURRENT_DARK = False


def is_system_dark():
    """Windows system-wide app theme (Settings -> Personalization -> Colors)"""
    if sys.platform == 'win32':
        try:
            import winreg
            with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                return winreg.QueryValueEx(key, 'AppsUseLightTheme')[0] == 0
        except Exception:
            pass
    return False


def _oklch(L, C, H):
    """oklch -> #rrggbb (same color model the reference site uses)"""
    h = math.radians(H)
    a, b = C * math.cos(h), C * math.sin(h)
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    r = +4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_
    g = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_
    bl = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_

    def srgb(c):
        c = max(0.0, min(1.0, c))
        c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
        return round(max(0.0, min(1.0, c)) * 255)

    return '#%02x%02x%02x' % (srgb(r), srgb(g), srgb(bl))


def _rainbow_stops():
    """qlineargradient stops for the hue slider groove (site's rainbow bar)"""
    return ', '.join(f'stop:{i / 12:.4f} {_oklch(.8, .1, i * 30)}'
                     for i in range(13))


def srgb_to_oklch(r, g, b):
    """#rrggbb components (0-255) -> (L, C, H) - inverse of _oklch, used by
    the advanced color picker to map any picked color onto the theme"""
    def linear(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = linear(r), linear(g), linear(b)
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    C = math.sqrt(a * a + bb * bb)
    H = math.degrees(math.atan2(bb, a)) % 360
    return L, C, H


def set_theme(hue=None, saturation=None, dark=None):
    """Rebuild the whole color theme; any argument left as None is unchanged"""
    global CURRENT_HUE, CURRENT_SATURATION, CURRENT_DARK
    global COLOR_PAGE_BG, COLOR_PAGE_BG_DEEP, COLOR_CARD_BG, COLOR_CARD_BORDER, COLOR_INPUT_BG
    global COLOR_PRIMARY, COLOR_PRIMARY_HOVER, COLOR_PRIMARY_ACTIVE
    global COLOR_BTN_BG, COLOR_BTN_BG_HOVER, COLOR_BTN_BG_ACTIVE, COLOR_BTN_TEXT
    global COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_ITEM_BG, COLOR_TRACK, COLOR_THUMB_BG
    global COLOR_GREEN, COLOR_RED
    global STYLESHEET_MAIN, STYLESHEET_GROUPBOX, STYLESHEET_PROGRESS_BAR
    global STYLESHEET_BUTTON_PRIMARY, STYLESHEET_BUTTON_YELLOW
    global STYLESHEET_BUTTON_RED, STYLESHEET_BUTTON_GREEN, STYLESHEET_BUTTON_DELETE
    global STYLESHEET_BUTTON_DANGER, STYLESHEET_BUTTON_LINK
    global STYLESHEET_ITEM_CARD, STYLESHEET_HUE_SLIDER, STYLESHEET_SAT_SLIDER
    global FIELD_LABEL_STYLE

    if hue is not None:
        CURRENT_HUE = max(0, min(360, int(hue)))
    if saturation is not None:
        CURRENT_SATURATION = max(50, min(160, int(saturation)))
    if dark is not None:
        CURRENT_DARK = bool(dark)

    h = CURRENT_HUE
    s = CURRENT_SATURATION / 100.0

    def c(base):
        return base * s

    if CURRENT_DARK:
        # Dark palette (formulas from the reference site's :root.dark)
        COLOR_PRIMARY = _oklch(.75, c(.14), h)
        COLOR_PRIMARY_HOVER = _oklch(.70, c(.14), h)
        COLOR_PRIMARY_ACTIVE = _oklch(.65, c(.13), h)
        COLOR_PAGE_BG = _oklch(.16, c(.014), h)
        COLOR_PAGE_BG_DEEP = _oklch(.10, c(.014), h)
        COLOR_CARD_BG = _oklch(.23, c(.015), h)
        COLOR_CARD_BORDER = _oklch(.33, c(.02), h)
        COLOR_INPUT_BG = _oklch(.19, c(.012), h)
        COLOR_BTN_BG = _oklch(.33, c(.035), h)
        COLOR_BTN_BG_HOVER = _oklch(.38, c(.04), h)
        COLOR_BTN_BG_ACTIVE = _oklch(.43, c(.045), h)
        COLOR_BTN_TEXT = _oklch(.80, c(.10), h)
        COLOR_TEXT = _oklch(.93, c(.01), h)
        COLOR_TEXT_MUTED = _oklch(.68, c(.02), h)
        COLOR_ITEM_BG = _oklch(.26, c(.015), h)
        COLOR_TRACK = _oklch(.34, c(.02), h)
        COLOR_THUMB_BG = _oklch(.30, c(.015), h)
        COLOR_GREEN = _oklch(.75, .13, 150)
        COLOR_RED = _oklch(.72, .16, 25)
        chip_red_bg, chip_red_bg_hover = _oklch(.30, .06, 25), _oklch(.35, .07, 25)
        chip_red_text = _oklch(.80, .13, 25)
        chip_green_bg, chip_green_bg_hover = _oklch(.30, .05, 150), _oklch(.35, .06, 150)
        chip_green_text = _oklch(.80, .11, 150)
    else:
        # Light palette (formulas from the reference site's :root)
        COLOR_PRIMARY = _oklch(.70, c(.14), h)
        COLOR_PRIMARY_HOVER = _oklch(.63, c(.13), h)
        COLOR_PRIMARY_ACTIVE = _oklch(.58, c(.12), h)
        COLOR_PAGE_BG = _oklch(.95, c(.01), h)
        COLOR_PAGE_BG_DEEP = _oklch(.86, c(.03), h)
        COLOR_CARD_BG = "#ffffff"
        COLOR_CARD_BORDER = _oklch(.90, c(.012), h)
        COLOR_INPUT_BG = "#ffffff"
        COLOR_BTN_BG = _oklch(.95, c(.025), h)
        COLOR_BTN_BG_HOVER = _oklch(.90, c(.05), h)
        COLOR_BTN_BG_ACTIVE = _oklch(.85, c(.08), h)
        COLOR_BTN_TEXT = _oklch(.55, c(.12), h)
        COLOR_TEXT = _oklch(.25, c(.02), h)
        COLOR_TEXT_MUTED = _oklch(.55, c(.02), h)
        COLOR_ITEM_BG = _oklch(.975, c(.008), h)
        COLOR_TRACK = _oklch(.92, c(.02), h)
        COLOR_THUMB_BG = _oklch(.93, c(.015), h)
        COLOR_GREEN = _oklch(.62, .14, 150)
        COLOR_RED = _oklch(.55, .19, 25)
        chip_red_bg, chip_red_bg_hover = _oklch(.95, .03, 25), _oklch(.91, .05, 25)
        chip_red_text = _oklch(.55, .18, 25)
        chip_green_bg, chip_green_bg_hover = _oklch(.95, .04, 150), _oklch(.91, .06, 150)
        chip_green_text = _oklch(.55, .13, 150)

    STYLESHEET_MAIN = f"""
        QMainWindow {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {COLOR_PAGE_BG}, stop:0.35 {COLOR_PAGE_BG},
                stop:1 {COLOR_PAGE_BG_DEEP});
        }}
        QDialog {{
            background-color: {COLOR_PAGE_BG};
        }}
        QWidget {{
            font-family: 'Segoe UI', Arial, sans-serif;
        }}
        QLabel {{
            font-size: 9pt;
            color: {COLOR_TEXT};
            background: transparent;
        }}
        QLineEdit, QComboBox {{
            border: 1px solid {COLOR_CARD_BORDER};
            border-radius: 8px;
            padding: 6px 10px;
            background-color: {COLOR_INPUT_BG};
            font-size: 9pt;
            color: {COLOR_TEXT};
            selection-background-color: {COLOR_BTN_BG_HOVER};
            selection-color: {COLOR_TEXT};
        }}
        QLineEdit:focus, QComboBox:focus {{
            border: 1px solid {COLOR_PRIMARY};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox QAbstractItemView {{
            background: {COLOR_INPUT_BG};
            border: 1px solid {COLOR_CARD_BORDER};
            border-radius: 8px;
            color: {COLOR_TEXT};
            selection-background-color: {COLOR_BTN_BG};
            selection-color: {COLOR_BTN_TEXT};
            outline: none;
        }}
        QPushButton {{
            background-color: {COLOR_BTN_BG};
            color: {COLOR_BTN_TEXT};
            border: none;
            border-radius: 8px;
            padding: 7px 14px;
            font-size: 9pt;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background-color: {COLOR_BTN_BG_HOVER};
        }}
        QPushButton:pressed {{
            background-color: {COLOR_BTN_BG_ACTIVE};
        }}
        QPushButton:disabled {{
            background-color: {COLOR_PAGE_BG};
            color: {COLOR_TEXT_MUTED};
        }}
        QTabWidget::pane {{
            border: none;
            background: transparent;
        }}
        QTabBar::tab {{
            background: transparent;
            color: {COLOR_TEXT_MUTED};
            padding: 7px 16px;
            margin: 0 6px 8px 0;
            border-radius: 8px;
            font-size: 9pt;
            font-weight: 600;
        }}
        QTabBar::tab:selected {{
            background: {COLOR_PRIMARY};
            color: white;
        }}
        QTabBar::tab:hover:!selected {{
            background: {COLOR_BTN_BG_HOVER};
            color: {COLOR_BTN_TEXT};
        }}
        QListWidget {{
            border: none;
            background: transparent;
        }}
        QListWidget::item {{
            margin-bottom: 6px;
        }}
        QListWidget::item:selected {{
            background: transparent;
        }}
        QTextEdit {{
            border: 1px solid {COLOR_CARD_BORDER};
            border-radius: 10px;
            font-family: Consolas, monospace;
            font-size: 8.5pt;
            background: {COLOR_INPUT_BG};
            color: {COLOR_TEXT};
        }}
        QCheckBox {{
            font-size: 9pt;
            color: {COLOR_TEXT};
            spacing: 8px;
            background: transparent;
        }}
        QProgressBar {{
            border: none;
            border-radius: 4px;
            background: {COLOR_TRACK};
        }}
        QProgressBar::chunk {{
            background-color: {COLOR_PRIMARY};
            border-radius: 4px;
        }}
        QScrollBar:vertical {{
            border: none;
            background: transparent;
            width: 10px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {COLOR_CARD_BORDER};
            border-radius: 4px;
            min-height: 30px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
        QMessageBox, QMessageBox QLabel {{
            background-color: {COLOR_CARD_BG};
            color: {COLOR_TEXT};
        }}
    """

    STYLESHEET_GROUPBOX = f"""
        QGroupBox {{
            border: 1px solid {COLOR_CARD_BORDER};
            border-radius: 12px;
            margin-top: 12px;
            padding-top: 14px;
            font-weight: 600;
            background-color: {COLOR_CARD_BG};
            font-size: 9pt;
            color: {COLOR_BTN_TEXT};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 14px;
            top: 2px;
            padding: 0 4px;
            background: transparent;
        }}
    """

    STYLESHEET_PROGRESS_BAR = f"""
        QProgressBar {{
            border: none;
            border-radius: 4px;
            background: {COLOR_TRACK};
        }}
        QProgressBar::chunk {{
            background-color: {COLOR_PRIMARY};
            border-radius: 4px;
        }}
    """

    # Primary (accent) action button - used for the Download buttons
    STYLESHEET_BUTTON_PRIMARY = f"""
        QPushButton {{
            background-color: {COLOR_PRIMARY};
            color: white;
            border: none;
            border-radius: 8px;
            padding: 7px 16px;
            font-size: 9.5pt;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background-color: {COLOR_PRIMARY_HOVER};
        }}
        QPushButton:pressed {{
            background-color: {COLOR_PRIMARY_ACTIVE};
        }}
    """

    # Chip buttons inside download items (Pause / Cancel / state colors)
    STYLESHEET_BUTTON_YELLOW = f"""
        QPushButton {{
            background-color: {COLOR_BTN_BG};
            color: {COLOR_BTN_TEXT};
            border-radius: 7px;
            font-size: 9pt;
            font-weight: 600;
            padding: 4px 14px;
        }}
        QPushButton:hover {{
            background-color: {COLOR_BTN_BG_HOVER};
        }}
    """

    STYLESHEET_BUTTON_RED = f"""
        QPushButton {{
            background-color: {chip_red_bg};
            color: {chip_red_text};
            border-radius: 7px;
            font-size: 9pt;
            font-weight: 600;
            padding: 4px 14px;
        }}
        QPushButton:hover {{
            background-color: {chip_red_bg_hover};
        }}
    """

    STYLESHEET_BUTTON_GREEN = f"""
        QPushButton {{
            background-color: {chip_green_bg};
            color: {chip_green_text};
            border-radius: 7px;
            font-size: 9pt;
            font-weight: 600;
            padding: 4px 14px;
        }}
        QPushButton:hover {{
            background-color: {chip_green_bg_hover};
        }}
    """

    # Round remove-from-list button
    STYLESHEET_BUTTON_DELETE = f"""
        QPushButton {{
            font-size: 10pt;
            font-weight: 600;
            color: {chip_red_text};
            background-color: {chip_red_bg};
            border-radius: 13px;
            padding: 0;
        }}
        QPushButton:hover {{
            background-color: {chip_red_bg_hover};
        }}
    """

    # Full-size destructive button (e.g. Clear URL)
    STYLESHEET_BUTTON_DANGER = f"""
        QPushButton {{
            background-color: {chip_red_bg};
            color: {chip_red_text};
            border: none;
            border-radius: 8px;
            padding: 7px 14px;
            font-size: 9pt;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background-color: {chip_red_bg_hover};
        }}
    """

    # Footer link buttons (GitHub / Donate)
    STYLESHEET_BUTTON_LINK = f"""
        QPushButton {{
            background: transparent;
            color: {COLOR_TEXT_MUTED};
            border: none;
            padding: 4px 10px;
            font-size: 9pt;
            font-weight: 600;
        }}
        QPushButton:hover {{
            color: {COLOR_BTN_TEXT};
            text-decoration: underline;
        }}
    """

    # Download item card
    STYLESHEET_ITEM_CARD = f"""
        #downloadItem {{
            background-color: {COLOR_ITEM_BG};
            border: 1px solid {COLOR_CARD_BORDER};
            border-radius: 10px;
        }}
    """

    # Rainbow hue slider (live theme color picker, like on the site)
    STYLESHEET_HUE_SLIDER = f"""
        QSlider::groove:horizontal {{
            height: 10px;
            border-radius: 5px;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {_rainbow_stops()});
        }}
        QSlider::handle:horizontal {{
            width: 18px;
            height: 18px;
            margin: -5px 0;
            border-radius: 10px;
            background: {COLOR_CARD_BG};
            border: 3px solid {COLOR_PRIMARY};
        }}
        QSlider::add-page:horizontal, QSlider::sub-page:horizontal {{
            background: transparent;
        }}
    """

    # Saturation slider: soft -> vivid version of the current hue
    STYLESHEET_SAT_SLIDER = f"""
        QSlider::groove:horizontal {{
            height: 10px;
            border-radius: 5px;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {_oklch(.7, .01, h)}, stop:1 {_oklch(.7, .24, h)});
        }}
        QSlider::handle:horizontal {{
            width: 18px;
            height: 18px;
            margin: -5px 0;
            border-radius: 10px;
            background: {COLOR_CARD_BG};
            border: 3px solid {COLOR_PRIMARY};
        }}
        QSlider::add-page:horizontal, QSlider::sub-page:horizontal {{
            background: transparent;
        }}
    """

    # Small caption above form fields
    FIELD_LABEL_STYLE = (f"color: {COLOR_TEXT_MUTED}; font-size: 8.5pt; "
                         f"font-weight: 600; background: transparent;")


def set_hue(hue):
    """Backward-compatible helper: change only the hue"""
    set_theme(hue=hue)


# Build the default theme at import time
set_theme()

# The yt_dlp module is HEAVY to import (~1 s), so it is loaded lazily on
# first use - in a worker thread, never blocking application startup.
yt_dlp = None
YTDLP_MODULE = None  # None = not tried yet; True/False once known


def get_yt_dlp():
    """Import the yt_dlp module on first use and cache it"""
    global yt_dlp, YTDLP_MODULE
    if YTDLP_MODULE is None:
        try:
            import yt_dlp as _module
            yt_dlp = _module
            YTDLP_MODULE = True
        except Exception:
            yt_dlp = None
            YTDLP_MODULE = False
    return yt_dlp


def ytdlp_module_available():
    """Cheap check that the yt_dlp module CAN be imported (no actual import)"""
    if YTDLP_MODULE is not None:
        return YTDLP_MODULE
    import importlib.util
    try:
        return importlib.util.find_spec('yt_dlp') is not None
    except Exception:
        return False


def get_js_runtimes():
    """JS runtime config for the yt_dlp module (Deno solves YouTube JS challenges)"""
    if DENO_EXE:
        return {'deno': {'path': DENO_EXE}}
    return {'deno': {}}  # fall back to deno from PATH if present


def get_js_runtimes_cli():
    """Value for the --js-runtimes CLI option of yt-dlp.exe"""
    if DENO_EXE:
        return f'deno:{DENO_EXE}'
    return 'deno'


def ensure_ytdlp():
    """Ensure yt-dlp is available (as module or exe)"""
    if ytdlp_module_available():
        return True
    if YTDLP_EXE and os.path.exists(YTDLP_EXE):
        return True
    return False
