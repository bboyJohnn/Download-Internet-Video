"""
UI Widgets - reusable UI components
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QGroupBox, QSizePolicy
)
from PyQt5.QtCore import Qt, QRectF, QEvent, QPoint
from PyQt5.QtGui import QPixmap, QPainter, QPainterPath

import config


def _rounded_pixmap(pm, width, height, radius):
    """Scale-crop a pixmap to width x height with rounded corners"""
    scaled = pm.scaled(width, height, Qt.KeepAspectRatioByExpanding,
                       Qt.SmoothTransformation)
    out = QPixmap(width, height)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, width, height), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap((width - scaled.width()) // 2,
                       (height - scaled.height()) // 2, scaled)
    painter.end()
    return out


def _stat_style():
    return f"color: {config.COLOR_TEXT_MUTED}; font-size: 8pt; background: transparent;"


def _status_style(color):
    return f"color: {color}; font-size: 8pt; font-weight: 600; background: transparent;"


def _title_style():
    return (f"font-weight: 600; font-size: 9pt; color: {config.COLOR_TEXT}; "
            "background: transparent;")


def _thumb_placeholder_style():
    return (f"background-color: {config.COLOR_THUMB_BG}; border-radius: 8px; "
            "font-size: 15pt;")


class DownloadItemWidget(QWidget):
    """Compact download card: thumbnail, title, progress and stats in one row"""

    THUMB_W = 96
    THUMB_H = 54

    def __init__(self, title, media_type, parent=None, tr=None):
        super().__init__(parent)
        self.media_type = media_type
        self._tr = tr or (lambda s: s)
        self._paused = False
        self._has_thumb = False
        self._full_thumb = None   # enlarged preview shown on hover
        self._zoom_popup = None
        self._status_state = ("▶", self._tr("Downloading"), "accent")

        self.setObjectName("downloadItem")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(config.STYLESHEET_ITEM_CARD)

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(12)

        # Thumbnail (placeholder icon until the preview arrives)
        self.thumb_label = QLabel("🎬" if media_type == "Video" else "🎧")
        self.thumb_label.setFixedSize(self.THUMB_W, self.THUMB_H)
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setStyleSheet(_thumb_placeholder_style())
        self.thumb_label.installEventFilter(self)  # hover zoom
        root.addWidget(self.thumb_label)

        right = QVBoxLayout()
        right.setSpacing(4)

        # Title row: title on the left, current status on the right
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setToolTip(title)
        self.title_label.setStyleSheet(_title_style())
        # Single line that clips instead of stretching the list horizontally
        self.title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        top_layout.addWidget(self.title_label, 1)

        self.status_icon = QLabel("▶")
        top_layout.addWidget(self.status_icon)
        self.status_label = QLabel(self._tr("Downloading"))
        top_layout.addWidget(self.status_label)
        right.addLayout(top_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setStyleSheet(config.STYLESHEET_PROGRESS_BAR)
        right.addWidget(self.progress_bar)

        # Stats row: only speed / size / time, with guaranteed gaps
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(14)

        self.speed_label = QLabel("⚡ —")
        self.speed_label.setMinimumWidth(84)
        stats_layout.addWidget(self.speed_label)

        self.size_label = QLabel("💾 —")
        self.size_label.setMinimumWidth(118)
        stats_layout.addWidget(self.size_label)

        self.eta_label = QLabel("🕒 —")
        self.eta_label.setMinimumWidth(58)
        stats_layout.addWidget(self.eta_label)

        stats_layout.addStretch(1)

        self.pause_button = QPushButton("⏸ " + self._tr("Pause"))
        self.pause_button.setFixedHeight(26)
        self.pause_button.setToolTip(self._tr("Pause"))
        stats_layout.addWidget(self.pause_button)

        self.cancel_button = QPushButton("✕ " + self._tr("Cancel"))
        self.cancel_button.setFixedHeight(26)
        self.cancel_button.setStyleSheet(config.STYLESHEET_BUTTON_RED)
        self.cancel_button.setToolTip(self._tr("Cancel"))
        stats_layout.addWidget(self.cancel_button)

        # Remove-from-list: a wide chip the size of Pause + Cancel together;
        # appears in their place when the download ends
        self.delete_button = QPushButton("🗑 " + self._tr("Remove from list"))
        self.delete_button.setFixedHeight(26)
        self.delete_button.setToolTip(self._tr("Remove from list"))
        self.delete_button.setStyleSheet(config.STYLESHEET_BUTTON_RED)
        self.delete_button.setVisible(False)
        stats_layout.addWidget(self.delete_button)

        right.addLayout(stats_layout)
        root.addLayout(right, 1)

        self.apply_theme()

    def apply_theme(self):
        """Re-apply hue-dependent styles (called live from the theme slider)"""
        self.setStyleSheet(config.STYLESHEET_ITEM_CARD)
        if not self._has_thumb:
            self.thumb_label.setStyleSheet(_thumb_placeholder_style())
        self.title_label.setStyleSheet(_title_style())
        self.progress_bar.setStyleSheet(config.STYLESHEET_PROGRESS_BAR)
        self.pause_button.setStyleSheet(
            config.STYLESHEET_BUTTON_GREEN if self._paused
            else config.STYLESHEET_BUTTON_YELLOW)
        self.cancel_button.setStyleSheet(config.STYLESHEET_BUTTON_RED)
        self.delete_button.setStyleSheet(config.STYLESHEET_BUTTON_RED)
        for label in (self.speed_label, self.size_label, self.eta_label):
            label.setStyleSheet(_stat_style())
        icon, text, kind = self._status_state
        self._set_status(icon, text, kind)

    def set_thumbnail(self, data):
        """Show the video preview image (raw image bytes from the worker)"""
        pm = QPixmap()
        if not data or not pm.loadFromData(data):
            return
        self._has_thumb = True
        self._full_thumb = _rounded_pixmap(pm, 320, 180, 12)  # hover-zoom version
        self.thumb_label.setStyleSheet("background: transparent;")
        self.thumb_label.setPixmap(
            _rounded_pixmap(pm, self.THUMB_W, self.THUMB_H, 8))

    # --------------------------------------------------- hover zoom preview

    def eventFilter(self, obj, event):
        if obj is self.thumb_label and self._full_thumb is not None:
            if event.type() == QEvent.Enter:
                self._show_zoom()
            elif event.type() in (QEvent.Leave, QEvent.Hide):
                self._hide_zoom()
        return super().eventFilter(obj, event)

    def _show_zoom(self):
        if self._zoom_popup is None:
            self._zoom_popup = QLabel(None, Qt.ToolTip | Qt.FramelessWindowHint)
            self._zoom_popup.setAttribute(Qt.WA_TranslucentBackground)
            self._zoom_popup.setStyleSheet("background: transparent;")
            # popup has no parent: tie its lifetime to this card
            self.destroyed.connect(self._zoom_popup.deleteLater)
        self._zoom_popup.setPixmap(self._full_thumb)
        self._zoom_popup.resize(self._full_thumb.size())
        pos = self.thumb_label.mapToGlobal(
            QPoint(self.thumb_label.width() + 10, -62))
        self._zoom_popup.move(pos)
        self._zoom_popup.show()

    def _hide_zoom(self):
        if self._zoom_popup is not None:
            self._zoom_popup.hide()

    def hideEvent(self, event):
        self._hide_zoom()
        super().hideEvent(event)

    def update_progress(self, percent, speed, size, eta):
        """Update progress display"""
        try:
            percent_clean = ''.join(c for c in percent if c.isdigit() or c == '.')
            percent_value = float(percent_clean) if percent_clean else 0
            self.progress_bar.setValue(int(percent_value))
        except ValueError:
            self.progress_bar.setValue(0)

        self.speed_label.setText(f"⏱ {speed}")
        self.size_label.setText(f"📦 {size}")
        self.eta_label.setText(f"⏳ {eta}")

    def _set_status(self, icon, text, kind):
        """kind: 'accent' (hue-tinted), 'green' or 'red' (fixed)"""
        self._status_state = (icon, text, kind)
        color = {"accent": config.COLOR_BTN_TEXT,
                 "green": config.COLOR_GREEN,
                 "red": config.COLOR_RED}[kind]
        style = _status_style(color)
        self.status_icon.setText(icon)
        self.status_icon.setStyleSheet(style)
        self.status_label.setText(text)
        self.status_label.setStyleSheet(style)

    def set_paused(self, paused):
        """Set paused/resumed state"""
        self._paused = paused
        if paused:
            self.pause_button.setText("▶ " + self._tr("Resume"))
            self.pause_button.setStyleSheet(config.STYLESHEET_BUTTON_GREEN)
            self._set_status("⏸", self._tr("Paused"), "accent")
        else:
            self.pause_button.setText("⏸ " + self._tr("Pause"))
            self.pause_button.setStyleSheet(config.STYLESHEET_BUTTON_YELLOW)
            self._set_status("▶", self._tr("Downloading"), "accent")

    def set_completed(self):
        """Set completed state"""
        self.progress_bar.setValue(100)
        self._set_status("✅", self._tr("Completed"), "green")

    def set_canceled(self):
        """Set canceled state"""
        self._set_status("⚠️", self._tr("Canceled"), "red")

    def set_error(self):
        """Set error state"""
        self._set_status("❌", self._tr("Error"), "red")

    def set_converting(self):
        """Set converting state"""
        self._set_status("🔄", self._tr("Converting"), "accent")

    def set_queued(self):
        """Waiting for a free download slot"""
        self.pause_button.setVisible(False)
        self._set_status("⏳", self._tr("Queued"), "accent")

    def set_started(self):
        """The queued job has started downloading"""
        self.pause_button.setVisible(True)
        self._set_status("▶", self._tr("Downloading"), "accent")


class WaveWidget(QWidget):
    """Decorative layered waves like on the reference site - the page 'dives'
    into a deeper background below them. Repaints with the current theme."""

    def __init__(self, parent=None, height=40):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, event):
        from PyQt5.QtGui import QColor
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        w, h = self.width(), float(self.height())
        base = QColor(config.COLOR_PRIMARY)
        # (alpha, baseline y, amplitude, phase-flip)
        for alpha, y0, amp, flip in ((0.16, h * 0.30, 9, False),
                                     (0.28, h * 0.50, 11, True),
                                     (0.45, h * 0.70, 12, False)):
            color = QColor(base)
            color.setAlphaF(alpha)
            painter.setBrush(color)
            path = QPainterPath()
            path.moveTo(0, h)
            path.lineTo(0, y0)
            step = w / 4.0
            up = not flip
            x = 0.0
            for _ in range(4):
                cy = y0 - amp if up else y0 + amp
                path.quadTo(x + step / 2, cy, x + step, y0)
                up = not up
                x += step
            path.lineTo(w, h)
            path.closeSubpath()
            painter.drawPath(path)
        painter.end()


class ShadowGroupBox(QGroupBox):
    """Group box with modern card styling"""

    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.setStyleSheet(config.STYLESHEET_GROUPBOX)
