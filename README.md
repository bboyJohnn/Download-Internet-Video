# [SYSTEM_INFO] Download-Internet-Video
> Version: 1.0
> Status: OPERATIONAL
> Last refresh: July 2026 (yt-dlp 2026.06.09 · Deno 2.9 · FFmpeg 8.1)

---

### // OVERVIEW
A powerful and user-friendly YouTube & media downloader with browser integration, format conversion, live theming and multilingual support. Built for speed and reliability. Works fully out of the box — all required tools are bundled or auto-downloaded.

[![Python](https://img.shields.io/badge/PYTHON-3-00ffff?style=flat-square)](https://www.python.org/)
[![License](https://img.shields.io/badge/LICENSE-MIT-ff00ff?style=flat-square)](https://github.com/bboyJohnn/Download-Internet-Video/blob/main/LICENSE)

---

### // MODULES_AND_CAPABILITIES

#### 📥 Universal Downloader
* **Site Support**: 1000+ platforms including YouTube, TikTok, Instagram, VK, Twitter (X), Facebook, and Twitch (powered by yt-dlp).
* **Channels & Playlists**: paste a channel/playlist link and pick the exact videos to grab — with thumbnails, titles, durations, search and select-all.
* **Download Queue**: sequential or parallel mode (2–10 simultaneous downloads).
* **Duplicate Guard**: re-downloading the same link asks to replace, save a copy or cancel.
* **Access Control**: cookies from Chrome/Firefox/Edge/Opera/Brave or from a cookies.txt file.

#### 🎛️ Advanced Media Processing
* **Video Formats**: MP4, WEBM, MKV, AVI, MOV, FLV.
* **Audio Extraction**: MP3, M4A, WAV, AAC, FLAC, OPUS, VORBIS.
* **Resolution**: Scalable from 144p to 8K (4320p).
* **Smart Conversion**: prefers native containers (no re-encode when possible); FFmpeg tuned for small, high-quality output.

#### 🎨 Live Theming
* Hue slider (0–360) recolors the whole app in real time (oklch color model).
* Saturation control, light / dark / system modes, advanced color picker with screen eyedropper.

#### 🛡️ Integration & Performance
* **JS Challenges**: bundled Deno runtime solves YouTube signature challenges out of the box.
* **Self-Updating Tools**: yt-dlp, FFmpeg and Deno update from Settings with atomic, rollback-safe swaps.
* **Localization**: 10 languages (EN, RU, ES, FR, DE, ZH, PT, AR, HI, JA).

---

### // RUN_FROM_SOURCE

```bash
pip install PyQt5 "yt-dlp[default]"
python main.py
```

On first run the app offers to download FFmpeg, yt-dlp and Deno into the `runtime/` folder automatically — nothing else to install.

### // BUILD_PORTABLE

```bash
pip install pyinstaller pillow
python build_release.py
```

Produces two ready-to-use distributions in `dist/`:
* a **portable folder** (fast startup) — copy anywhere and run;
* a **single EXE** with everything inside.

---

### // REPO_LAYOUT

```
main.py            entry point
config.py          paths, theme engine (oklch), settings
core/              download worker, playlist prober, tool checks
ui/                main window, download cards, dialogs
tools/             tool installer / updater, network helpers
locales/           10 UI translations
old/               previous versions of the source
```

> Note: binaries (FFmpeg, Deno, yt-dlp.exe, builds) are not stored in git — the app downloads them on first run.
