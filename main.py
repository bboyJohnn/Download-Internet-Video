"""
Main entry point - Download Internet Video Application
"""
import sys
import os
import traceback

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette, QFont


def main():
    """Main application entry point"""
    try:
        # Crisp rendering on high-DPI displays (must be set before QApplication)
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        # Own taskbar identity on Windows (icon grouping)
        if sys.platform == 'win32':
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    'DownloadInternetVideo.App.1.0')
            except Exception:
                pass

        app = QApplication(sys.argv)
        app.setFont(QFont("Segoe UI", 9))

        # Build the theme from saved settings before any window is created
        import config
        from PyQt5.QtCore import QSettings
        settings = QSettings("MyCompany", "YouTubeDownloader")
        theme_mode = settings.value("theme_mode", "light")
        config.set_theme(
            hue=settings.value("hue", config.DEFAULT_HUE, type=int),
            saturation=settings.value("saturation", config.DEFAULT_SATURATION, type=int),
            dark=config.is_system_dark() if theme_mode == "system"
            else (theme_mode == "dark"))

        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(config.COLOR_PAGE_BG))
        palette.setColor(QPalette.WindowText, QColor(config.COLOR_TEXT))
        palette.setColor(QPalette.Base, QColor(config.COLOR_INPUT_BG))
        palette.setColor(QPalette.AlternateBase, QColor(config.COLOR_ITEM_BG))
        palette.setColor(QPalette.Text, QColor(config.COLOR_TEXT))
        palette.setColor(QPalette.Button, QColor(config.COLOR_BTN_BG))
        palette.setColor(QPalette.ButtonText, QColor(config.COLOR_BTN_TEXT))
        palette.setColor(QPalette.Highlight, QColor(config.COLOR_PRIMARY))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        app.setPalette(palette)

        from ui.main_window import YouTubeDownloader

        # Create and show main window
        window = YouTubeDownloader()
        window.show()

        sys.exit(app.exec_())

    except Exception as e:
        error_msg = f"Application Error:\n\n{str(e)}\n\n{traceback.format_exc()}"
        print(error_msg)

        try:
            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "Error", error_msg)
        except Exception:
            print("Could not show error dialog")

        sys.exit(1)


if __name__ == '__main__':
    main()
