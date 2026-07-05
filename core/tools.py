"""
Tool Management - Check and install ffmpeg, yt-dlp, Deno
"""
import os
from PyQt5.QtWidgets import QMessageBox

import config


def tools_status():
    """Return (ffmpeg_present, ytdlp_present, deno_present) based on config.
    Uses the cheap module check so startup never pays the yt_dlp import."""
    ffmpeg_present = os.path.exists(config.LOCAL_FFMPEG_EXE)
    ytdlp_present = config.ytdlp_module_available() or (
        config.YTDLP_EXE is not None and os.path.exists(config.YTDLP_EXE))
    deno_present = config.DENO_EXE is not None and os.path.exists(config.DENO_EXE)
    return ffmpeg_present, ytdlp_present, deno_present


def check_and_install_tools(parent, base_dir):
    """
    Check presence of local ffmpeg, yt-dlp and Deno; offer to download missing ones.

    Args:
        parent: Parent widget for message boxes
        base_dir: Persistent application directory (tools are installed here)
    """
    # Imported lazily to avoid a circular import (ui imports core.tools)
    from ui.dialogs import ToolInstallDialog

    tr = getattr(parent, 'tr', None) or (lambda s: s)

    ffmpeg_present, ytdlp_present, deno_present = tools_status()

    if ffmpeg_present and ytdlp_present and deno_present:
        QMessageBox.information(parent, tr("Tools"),
                                tr("ffmpeg, yt-dlp and Deno are present in the application folder."))
        return

    dlg = ToolInstallDialog(
        base_dir=base_dir,
        install_ffmpeg=(not ffmpeg_present),
        install_ytdlp=(not ytdlp_present),
        install_deno=(not deno_present),
        parent=parent,
        tr=tr
    )
    dlg.exec_()

    # Pick up freshly installed tools without restarting
    config.refresh_tools()
    if os.path.exists(config.LOCAL_FFMPEG_BIN):
        os.environ['PATH'] = config.LOCAL_FFMPEG_BIN + os.pathsep + os.environ.get('PATH', '')

    ffmpeg_present, ytdlp_present, deno_present = tools_status()
    if ffmpeg_present and ytdlp_present and deno_present:
        QMessageBox.information(parent, tr("Tools"),
                                tr("All tools are installed and ready to use."))
    else:
        missing = [name for name, ok in (("ffmpeg", ffmpeg_present),
                                         ("yt-dlp", ytdlp_present),
                                         ("Deno", deno_present)) if not ok]
        try:
            msg = tr("Some tools are still missing: {names}. Downloads may not "
                     "work until they are installed.").format(names=", ".join(missing))
        except Exception:
            msg = "Some tools are still missing: " + ", ".join(missing)
        QMessageBox.warning(parent, tr("Tools"), msg)


__all__ = ['check_and_install_tools', 'tools_status']
