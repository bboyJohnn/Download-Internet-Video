"""
Dialog Windows - Installation progress and other dialogs
"""
import os

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit, QCheckBox, QLineEdit, QListWidget,
    QListWidgetItem, QWidget, QSizePolicy
)
from PyQt5.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt5.QtGui import QPixmap

import config
from tools.installer import ToolInstallThread
from tools.updater import ToolUpdateThread


class ToolInstallDialog(QDialog):
    """Dialog for tool installation with progress tracking"""

    def __init__(self, base_dir, install_ffmpeg=True, install_ytdlp=True,
                 install_deno=False, parent=None, tr=None):
        super().__init__(parent)
        self._tr = tr or (lambda s: s)
        self.setWindowTitle(self._tr('Install Tools'))
        self.setModal(True)
        self.resize(480, 300)

        layout = QVBoxLayout(self)

        # Status label
        self.label = QLabel(self._tr('Preparing...'))
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
        self.btn_cancel = QPushButton(self._tr('Cancel'))
        self.btn_cancel.clicked.connect(self.cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        # Start installation thread
        self.thread = ToolInstallThread(
            base_dir=base_dir,
            install_ffmpeg=install_ffmpeg,
            install_ytdlp=install_ytdlp,
            install_deno=install_deno,
            tr=self._tr
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
            self.label.setText(self._tr('Done'))
            self.log_view.append(msg)
            self.progress.setValue(100)
            # Auto-close only on success; keep errors visible
            QTimer.singleShot(800, self.accept)
        else:
            self.label.setText(self._tr('Error'))
            self.log_view.append(msg)

        self.btn_cancel.setText(self._tr('Close'))
        self.btn_cancel.setEnabled(True)

    def cancel(self):
        """Cancel installation or close dialog"""
        if self.thread.isRunning():
            self.thread.stop()
            self.log_view.append(self._tr('Cancelling...'))
            self.btn_cancel.setEnabled(False)
        else:
            self.accept()

    def _shutdown_thread(self):
        """Make sure the install thread is stopped before the dialog dies"""
        if self.thread.isRunning():
            self.thread.stop()
            self.thread.wait(10000)

    def closeEvent(self, event):
        self._shutdown_thread()
        super().closeEvent(event)

    def reject(self):
        self._shutdown_thread()
        super().reject()


class ToolUpdateDialog(QDialog):
    """Dialog that checks tool versions and updates outdated ones"""

    def __init__(self, base_dir, parent=None, tr=None):
        super().__init__(parent)
        self._tr = tr or (lambda s: s)
        self.setWindowTitle(self._tr('Update Tools'))
        self.setModal(True)
        self.resize(520, 380)
        self.base_dir = base_dir
        self.thread = None

        layout = QVBoxLayout(self)

        self.label = QLabel(self._tr('Press "Check and update" to compare installed '
                                     'tool versions with the latest releases.'))
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

        self.chk_force = QCheckBox(self._tr('Reinstall everything (even if up to date)'))
        layout.addWidget(self.chk_force)

        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton(self._tr('Check and update'))
        self.btn_start.clicked.connect(self.start_update)
        self.btn_close = QPushButton(self._tr('Close'))
        self.btn_close.clicked.connect(self.close_or_cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def start_update(self):
        self.btn_start.setEnabled(False)
        self.chk_force.setEnabled(False)
        self.btn_close.setText(self._tr('Cancel'))
        self.label.setText(self._tr('Working...'))

        self.thread = ToolUpdateThread(
            base_dir=self.base_dir,
            force=self.chk_force.isChecked(),
            tr=self._tr
        )
        self.thread.progress.connect(self.progress.setValue)
        self.thread.status.connect(self.on_status)
        self.thread.log.connect(self.log_view.append)
        self.thread.finished_update.connect(self.on_finished)
        self.thread.start()

    def on_status(self, text):
        self.label.setText(text)
        self.log_view.append(text)

    def on_finished(self, ok, msg):
        self.label.setText(msg)
        self.log_view.append(msg)
        self.progress.setValue(100 if ok else self.progress.value())
        self.btn_start.setEnabled(True)
        self.chk_force.setEnabled(True)
        self.btn_close.setText(self._tr('Close'))

    def close_or_cancel(self):
        if self.thread is not None and self.thread.isRunning():
            self.thread.stop()
            self.log_view.append(self._tr('Cancelling...'))
            self.btn_close.setEnabled(False)
            self.thread.finished.connect(lambda: self.btn_close.setEnabled(True))
        else:
            self.accept()

    def _shutdown_thread(self):
        if self.thread is not None and self.thread.isRunning():
            self.thread.stop()
            self.thread.wait(15000)

    def closeEvent(self, event):
        self._shutdown_thread()
        super().closeEvent(event)

    def reject(self):
        self._shutdown_thread()
        super().reject()


def _fmt_duration(seconds):
    """123 -> 2:03, 3723 -> 1:02:03"""
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "—"
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class _ThumbFetchThread(QThread):
    """Fetch playlist thumbnails one by one in the background"""
    loaded = pyqtSignal(int, bytes)

    def __init__(self, urls, parent=None):
        super().__init__(parent)
        self.urls = urls
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        from tools.net import urlopen
        for index, url in enumerate(self.urls):
            if not self._is_running:
                return
            if not url:
                continue
            try:
                with urlopen(url, timeout=10) as resp:
                    data = resp.read(1024 * 1024)
                if data and self._is_running:
                    self.loaded.emit(index, bytes(data))
            except Exception:
                continue


class _VideoRow(QWidget):
    """One row of the video picker: checkbox, thumbnail, title, duration"""

    def __init__(self, item, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(10)

        self.check = QCheckBox()
        layout.addWidget(self.check)

        self.thumb = QLabel("🎬")
        self.thumb.setFixedSize(80, 45)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet(
            f"background-color: {config.COLOR_THUMB_BG}; border-radius: 6px; "
            "font-size: 12pt;")
        layout.addWidget(self.thumb)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.title_label = QLabel(item.get("title") or "")
        self.title_label.setToolTip(item.get("title") or "")
        self.title_label.setStyleSheet(
            f"font-size: 9pt; font-weight: 600; color: {config.COLOR_TEXT}; "
            "background: transparent;")
        self.title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        text_col.addWidget(self.title_label)
        self.duration_label = QLabel("🕒 " + _fmt_duration(item.get("duration")))
        self.duration_label.setStyleSheet(
            f"font-size: 8pt; color: {config.COLOR_TEXT_MUTED}; background: transparent;")
        text_col.addWidget(self.duration_label)
        layout.addLayout(text_col, 1)

    def set_thumb(self, data):
        from ui.widgets import _rounded_pixmap
        pm = QPixmap()
        if data and pm.loadFromData(data):
            self.thumb.setStyleSheet("background: transparent;")
            self.thumb.setPixmap(_rounded_pixmap(pm, 80, 45, 6))


class VideoSelectDialog(QDialog):
    """Pick which videos of a channel/playlist to download"""

    def __init__(self, items, parent=None, tr=None):
        super().__init__(parent)
        self._tr = tr or (lambda s: s)
        self.items = items
        self.setWindowTitle(self._tr("Select videos to download"))
        self.setModal(True)
        self.resize(660, 580)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 " + self._tr("Search..."))
        self.search_input.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search_input)

        self.list = QListWidget()
        self.list.setSpacing(2)
        self.list.setStyleSheet("QListWidget::item:selected { background: transparent; }")
        self.list.itemClicked.connect(self._toggle_row)
        layout.addWidget(self.list, 1)

        self.rows = []
        for item in self.items:
            row = _VideoRow(item)
            row.check.stateChanged.connect(self._update_count)
            list_item = QListWidgetItem()
            list_item.setSizeHint(row.sizeHint())
            self.list.addItem(list_item)
            self.list.setItemWidget(list_item, row)
            self.rows.append(row)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.select_all_btn = QPushButton("✅ " + self._tr("Select all"))
        self.select_all_btn.clicked.connect(lambda: self._set_all(True))
        controls.addWidget(self.select_all_btn)
        self.clear_all_btn = QPushButton("⬜ " + self._tr("Clear all"))
        self.clear_all_btn.clicked.connect(lambda: self._set_all(False))
        controls.addWidget(self.clear_all_btn)
        self.invert_btn = QPushButton("🔁 " + self._tr("Invert"))
        self.invert_btn.clicked.connect(self._invert)
        controls.addWidget(self.invert_btn)
        controls.addStretch()
        self.count_label = QLabel()
        self.count_label.setStyleSheet(
            f"color: {config.COLOR_TEXT_MUTED}; font-size: 9pt;")
        controls.addWidget(self.count_label)
        layout.addLayout(controls)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.download_btn = QPushButton("⬇ " + self._tr("Download selected"))
        self.download_btn.setStyleSheet(config.STYLESHEET_BUTTON_PRIMARY)
        self.download_btn.clicked.connect(self.accept)
        buttons.addWidget(self.download_btn)
        self.cancel_btn = QPushButton(self._tr("Cancel"))
        self.cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_btn)
        layout.addLayout(buttons)

        self._update_count()

        # fetch thumbnails in the background
        self._thumbs = _ThumbFetchThread([i.get("thumbnail", "") for i in self.items])
        self._thumbs.loaded.connect(self._on_thumb)
        self._thumbs.start()

    def _on_thumb(self, index, data):
        if 0 <= index < len(self.rows):
            self.rows[index].set_thumb(data)

    def _toggle_row(self, list_item):
        row = self.list.itemWidget(list_item)
        if row is not None:
            row.check.setChecked(not row.check.isChecked())

    def _set_all(self, checked):
        for i, row in enumerate(self.rows):
            if not self.list.isRowHidden(i):
                row.check.setChecked(checked)

    def _invert(self):
        for i, row in enumerate(self.rows):
            if not self.list.isRowHidden(i):
                row.check.setChecked(not row.check.isChecked())

    def _apply_filter(self, text):
        needle = text.strip().lower()
        for i, item in enumerate(self.items):
            hidden = bool(needle) and needle not in (item.get("title") or "").lower()
            self.list.setRowHidden(i, hidden)

    def _update_count(self):
        selected = sum(1 for r in self.rows if r.check.isChecked())
        self.count_label.setText(
            f'{self._tr("Selected:")} {selected} / {len(self.rows)}')
        self.download_btn.setEnabled(selected > 0)

    def selected_items(self):
        return [item for item, row in zip(self.items, self.rows)
                if row.check.isChecked()]

    def _shutdown(self):
        if self._thumbs.isRunning():
            self._thumbs.stop()
            self._thumbs.wait(3000)

    def accept(self):
        self._shutdown()
        super().accept()

    def reject(self):
        self._shutdown()
        super().reject()

    def closeEvent(self, event):
        self._shutdown()
        super().closeEvent(event)


__all__ = ['ToolInstallDialog', 'ToolUpdateDialog', 'VideoSelectDialog']
