"""
UI Widgets - reusable UI components
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QProgressBar, QFrame, QGroupBox
)
from PyQt5.QtCore import Qt

from config import (
    STYLESHEET_PROGRESS_BAR, STYLESHEET_BUTTON_YELLOW,
    STYLESHEET_BUTTON_RED, STYLESHEET_BUTTON_GREEN, STYLESHEET_GROUPBOX
)


class DownloadItemWidget(QWidget):
    """Widget representing a single download item"""
    
    def __init__(self, title, media_type, parent=None):
        super().__init__(parent)
        self.media_type = media_type
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(6)
        
        # Title bar
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
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setStyleSheet(STYLESHEET_PROGRESS_BAR)
        self.layout.addWidget(self.progress_bar)
        
        # Details layout
        details_layout = QHBoxLayout()
        details_layout.setSpacing(6)
        
        # Speed frame
        speed_frame = QFrame()
        speed_frame.setStyleSheet("background-color: #e8f0fe; border: 1px solid #b3d9fd; border-radius: 4px;")
        speed_layout = QHBoxLayout(speed_frame)
        speed_layout.setContentsMargins(4, 2, 4, 2)
        speed_icon = QLabel("⏱")
        speed_icon.setStyleSheet("font-size: 8pt; color: #1a73e8;")
        speed_layout.addWidget(speed_icon)
        self.speed_label = QLabel("-")
        self.speed_label.setStyleSheet("color: #1a73e8; font-size: 8pt;")
        speed_layout.addWidget(self.speed_label)
        details_layout.addWidget(speed_frame)
        
        # Size frame
        size_frame = QFrame()
        size_frame.setStyleSheet("background-color: #e6f4ea; border: 1px solid #a8dab5; border-radius: 4px;")
        size_layout = QHBoxLayout(size_frame)
        size_layout.setContentsMargins(4, 2, 4, 2)
        size_icon = QLabel("📦")
        size_icon.setStyleSheet("font-size: 8pt; color: #0f9d58;")
        size_layout.addWidget(size_icon)
        self.size_label = QLabel("-/-")
        self.size_label.setStyleSheet("color: #0f9d58; font-size: 8pt;")
        size_layout.addWidget(self.size_label)
        details_layout.addWidget(size_frame)
        
        # ETA frame
        eta_frame = QFrame()
        eta_frame.setStyleSheet("background-color: #fef7e0; border: 1px solid #fcd34d; border-radius: 4px;")
        eta_layout = QHBoxLayout(eta_frame)
        eta_layout.setContentsMargins(4, 2, 4, 2)
        eta_icon = QLabel("⏳")
        eta_icon.setStyleSheet("font-size: 8pt; color: #f4b400;")
        eta_layout.addWidget(eta_icon)
        self.eta_label = QLabel("-")
        self.eta_label.setStyleSheet("color: #f4b400; font-size: 8pt;")
        eta_layout.addWidget(self.eta_label)
        details_layout.addWidget(eta_frame)
        
        # Status frame
        status_frame = QFrame()
        status_frame.setStyleSheet("background-color: #f1e6f6; border: 1px solid #e9d5ff; border-radius: 4px;")
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(4, 2, 4, 2)
        self.status_icon = QLabel("▶")
        self.status_icon.setStyleSheet("font-size: 8pt; color: #681da8;")
        status_layout.addWidget(self.status_icon)
        self.status_label = QLabel("Downloading")
        self.status_label.setStyleSheet("color: #681da8; font-size: 8pt;")
        status_layout.addWidget(self.status_label)
        details_layout.addWidget(status_frame)
        
        details_layout.addStretch(1)
        
        # Controls
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(6)
        
        self.pause_button = QPushButton("⏸ Pause")
        self.pause_button.setFixedHeight(24)
        self.pause_button.setStyleSheet(STYLESHEET_BUTTON_YELLOW)
        self.pause_button.setToolTip("Pause")
        
        self.cancel_button = QPushButton("✕ Cancel")
        self.cancel_button.setFixedHeight(24)
        self.cancel_button.setStyleSheet(STYLESHEET_BUTTON_RED)
        self.cancel_button.setToolTip("Cancel")
        
        controls_layout.addWidget(self.pause_button)
        controls_layout.addWidget(self.cancel_button)
        
        details_layout.addLayout(controls_layout)
        self.layout.addLayout(details_layout)

    def update_progress(self, percent, speed, size, eta):
        """Update progress display"""
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
        """Set paused/resumed state"""
        if paused:
            self.pause_button.setText("▶ Resume")
            self.pause_button.setStyleSheet(STYLESHEET_BUTTON_GREEN)
            self.status_icon.setText("⏸")
            self.status_label.setText("Paused")
            self.status_label.setStyleSheet("color: #681da8; font-size: 8pt;")
        else:
            self.pause_button.setText("⏸ Pause")
            self.pause_button.setStyleSheet(STYLESHEET_BUTTON_YELLOW)
            self.status_icon.setText("▶")
            self.status_label.setText("Downloading")
            self.status_label.setStyleSheet("color: #681da8; font-size: 8pt;")
    
    def set_completed(self):
        """Set completed state"""
        self.status_icon.setText("✅")
        self.status_label.setText("Completed")
        self.status_label.setStyleSheet("color: #0f9d58; font-size: 8pt;")
        
    def set_canceled(self):
        """Set canceled state"""
        self.status_icon.setText("⚠️")
        self.status_label.setText("Canceled")
        self.status_label.setStyleSheet("color: #db4437; font-size: 8pt;")
        
    def set_error(self):
        """Set error state"""
        self.status_icon.setText("❌")
        self.status_label.setText("Error")
        self.status_label.setStyleSheet("color: #db4437; font-size: 8pt;")
        
    def set_converting(self):
        """Set converting state"""
        self.status_icon.setText("🔄")
        self.status_label.setText("Converting")
        self.status_label.setStyleSheet("color: #1a73e8; font-size: 8pt;")


class ShadowGroupBox(QGroupBox):
    """Group box with modern styling"""
    
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.setStyleSheet(STYLESHEET_GROUPBOX)
