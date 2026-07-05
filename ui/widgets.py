"""
UI Widgets - reusable UI components
"""
import math

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QGroupBox, QSizePolicy, QToolButton
)
from PyQt5.QtCore import Qt, QRectF, QEvent, QPoint, QTimer
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


class BannerWidget(QWidget):
    """Site-style header: the app title on a colored 'picture', with the
    reference site's exact 'gentle wave' layers (filled with the page
    background color) drifting along the bottom edge. The content below
    sits at the foot of the waves, just like on the site."""

    def __init__(self, title, parent=None, height=104):
        super().__init__(parent)
        self._title = title
        self.setFixedHeight(height)
        self._t = 0.0        # animation clock, seconds
        self._boost = 0.0    # short burst after a tab switch
        self._animated = True
        self._timer = QTimer(self)
        self._timer.setInterval(40)  # ~25 fps
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def setTitle(self, title):
        self._title = title
        self.update()

    def set_animated(self, animated):
        """Toggle the animation (Settings -> Appearance)"""
        self._animated = bool(animated)
        if self._animated:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            self._boost = 0.0
            self.update()

    def splash(self):
        """React to a tab switch with a short faster-and-taller burst"""
        if self._animated:
            self._boost = 1.0

    def _tick(self):
        self._t += 0.04 * (1.0 + 2.0 * self._boost)
        if self._boost > 0.01:
            self._boost *= 0.94
        else:
            self._boost = 0.0
        self.update()

    @staticmethod
    def _gentle_wave_path():
        """The exact 'gentle-wave' path used by the reference site:
        M-160 44 c30 0 58-18 88-18 s58 18 88 18 s58-18 88-18 s58 18 88 18
        v48 h-352 z  (period 176 units, viewBox '0 20 150 32')"""
        path = QPainterPath()
        path.moveTo(-160, 44)
        path.cubicTo(-130, 44, -102, 26, -72, 26)
        path.cubicTo(-42, 26, -14, 44, 16, 44)
        path.cubicTo(46, 44, 74, 26, 104, 26)
        path.cubicTo(134, 26, 162, 44, 192, 44)
        path.lineTo(192, 92)
        path.lineTo(-160, 92)
        path.closeSubpath()
        return path

    def paintEvent(self, event):
        from PyQt5.QtGui import QColor, QLinearGradient, QFont
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), float(self.height())
        if w <= 0 or h <= 0:
            return

        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h), 12, 12)
        painter.setClipPath(clip)

        # the banner 'picture': theme-colored gradient with soft light blobs
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0.0, QColor(config.COLOR_PRIMARY_ACTIVE))
        grad.setColorAt(0.55, QColor(config.COLOR_PRIMARY))
        grad.setColorAt(1.0, QColor(config.COLOR_BTN_BG_ACTIVE))
        painter.fillPath(clip, grad)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 26))
        painter.drawEllipse(QRectF(w * 0.62, -h * 0.7, h * 1.7, h * 1.7))
        painter.drawEllipse(QRectF(w * 0.06, h * 0.35, h * 1.1, h * 1.1))

        # title over the picture
        painter.setPen(QColor(255, 255, 255))
        title_font = QFont("Segoe UI", 17)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(QRectF(0, 0, w, h - 26), Qt.AlignCenter, self._title)

        # gentle waves along the bottom, page-bg colored (site behaviour:
        # four layers, x-drift -90->85 over 7/10/13/20 s, y offsets 0/3/5/7)
        wave_h = 30.0 * (1.0 + 0.22 * self._boost)
        sx = w / 150.0
        sy = wave_h / 32.0
        top = h - wave_h
        base_path = self._gentle_wave_path()
        page = QColor(config.COLOR_PAGE_BG)
        for y_off, opacity, duration in ((0, 0.25, 7.0), (3, 0.50, 10.0),
                                         (5, 0.75, 13.0), (7, 1.00, 20.0)):
            phase = (self._t / duration) % 1.0
            x_units = 48.0 - 90.0 + phase * 175.0
            color = QColor(page)
            color.setAlphaF(opacity)
            painter.save()
            painter.translate(0, top - 20.0 * sy)
            painter.scale(sx, sy)
            painter.translate(x_units, y_off)
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawPath(base_path)
            painter.restore()
        painter.end()


class CollapsibleBox(QWidget):
    """Settings card with a clickable header that collapses its content"""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("collapsibleBox")
        self.setAttribute(Qt.WA_StyledBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 4, 8, 8)
        outer.setSpacing(2)

        self.toggle_button = QToolButton()
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.DownArrow)
        self.toggle_button.setCursor(Qt.PointingHandCursor)
        self.toggle_button.clicked.connect(self._on_toggled)
        outer.addWidget(self.toggle_button)

        self.content = QWidget()
        outer.addWidget(self.content)

        self.apply_theme()

    def _on_toggled(self):
        expanded = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.content.setVisible(expanded)

    def set_expanded(self, expanded):
        self.toggle_button.setChecked(bool(expanded))
        self._on_toggled()

    def is_expanded(self):
        return self.toggle_button.isChecked()

    def setTitle(self, title):
        self.toggle_button.setText(title)

    def setContentLayout(self, layout):
        self.content.setLayout(layout)

    def apply_theme(self):
        self.setStyleSheet(
            f"#collapsibleBox {{ background-color: {config.COLOR_CARD_BG}; "
            f"border: 1px solid {config.COLOR_CARD_BORDER}; border-radius: 12px; }}")
        self.toggle_button.setStyleSheet(
            f"QToolButton {{ border: none; background: transparent; "
            f"color: {config.COLOR_BTN_TEXT}; font-weight: 600; font-size: 9pt; "
            "padding: 4px 2px; }")


class ShadowGroupBox(QGroupBox):
    """Group box with modern card styling"""

    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.setStyleSheet(config.STYLESHEET_GROUPBOX)
