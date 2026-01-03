"""
Tool Management - Check and install ffmpeg, yt-dlp
"""
import os
import sys
from PyQt5.QtWidgets import QMessageBox
from ui.dialogs import ToolInstallDialog


def check_and_install_tools(parent, base_dir, local_ffmpeg_bin, local_ffmpeg_exe, ytdlp_candidates):
    """
    Check presence of local ffmpeg and yt-dlp; offer to download missing ones.
    
    Args:
        parent: Parent widget for message boxes
        base_dir: Application base directory
        local_ffmpeg_bin: Path to ffmpeg/bin directory
        local_ffmpeg_exe: Path to ffmpeg executable
        ytdlp_candidates: List of possible yt-dlp locations
    """
    ffmpeg_present = os.path.exists(local_ffmpeg_exe)
    ytdlp_present = any(os.path.exists(p) for p in ytdlp_candidates)

    # If both present — just inform and return
    if ffmpeg_present and ytdlp_present:
        QMessageBox.information(parent, "Tools", "ffmpeg and yt-dlp are present in application folder.")
        return

    # Automatically start installer dialog for missing tools
    dlg = ToolInstallDialog(
        base_dir=base_dir,
        install_ffmpeg=(not ffmpeg_present),
        install_ytdlp=(not ytdlp_present),
        parent=parent
    )
    dlg.exec_()

    # After dialog closed, ensure PATH updated
    if os.path.exists(local_ffmpeg_bin):
        os.environ['PATH'] = local_ffmpeg_bin + os.pathsep + os.environ.get('PATH', '')

    QMessageBox.information(parent, "Restart Required", "Installation finished. Please restart the application to apply changes.")


__all__ = ['check_and_install_tools']
