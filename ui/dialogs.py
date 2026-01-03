"""
Dialog Windows - Installation progress and other dialogs
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QProgressBar, QTextEdit
)
from PyQt5.QtCore import QTimer
from tools.installer import ToolInstallThread


class ToolInstallDialog(QDialog):
    """Dialog for tool installation with progress tracking"""

    def __init__(self, base_dir, install_ffmpeg=True, install_ytdlp=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Install Tools')
        self.setModal(True)
        self.resize(480, 300)
        
        layout = QVBoxLayout(self)
        
        # Status label
        self.label = QLabel('Preparing...')
        layout.addWidget(self.label)
        
        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        
        # Log view
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton('Cancel')
        self.btn_cancel.clicked.connect(self.cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        # Start installation thread
        self.thread = ToolInstallThread(
            base_dir=base_dir,
            install_ffmpeg=install_ffmpeg,
            install_ytdlp=install_ytdlp
        )
        self.thread.progress.connect(self.on_progress)
        self.thread.status.connect(self.on_status)
        self.thread.finished.connect(self.on_finished)
        self.thread.start()

    def on_progress(self, val):
        """Update progress bar"""
        try:
            self.progress.setValue(int(val))
        except Exception:
            pass

    def on_status(self, text):
        """Update status and log"""
        self.label.setText(text)
        self.log_view.append(text)

    def on_finished(self, ok, msg):
        """Handle installation completion"""
        if ok:
            self.label.setText('Done')
            self.log_view.append(msg)
            self.progress.setValue(100)
        else:
            self.label.setText('Error')
            self.log_view.append(msg)
        
        self.btn_cancel.setText('Close')
        
        # Auto-close the dialog shortly after completion
        try:
            QTimer.singleShot(300, self.accept)
        except Exception:
            try:
                self.accept()
            except Exception:
                pass

    def cancel(self):
        """Cancel installation or close dialog"""
        if self.thread.isRunning():
            self.thread.stop()
            self.log_view.append('Cancelled by user')
            self.btn_cancel.setEnabled(False)
        else:
            self.accept()


__all__ = ['ToolInstallDialog']
