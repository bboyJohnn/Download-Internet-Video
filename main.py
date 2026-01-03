"""
Main entry point - Download Internet Video Application
"""
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette

from ui.main_window import YouTubeDownloader


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    
    # Set palette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(245, 245, 245))
    palette.setColor(QPalette.WindowText, Qt.black)
    palette.setColor(QPalette.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.AlternateBase, QColor(240, 240, 240))
    app.setPalette(palette)
    
    # Create and show main window
    window = YouTubeDownloader()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
