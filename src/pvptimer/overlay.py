"""Transparent, always-on-top, click-through window that draws the active timers."""
import math
import time

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .router import UNKNOWN_SPEECH
from .settings import OverlaySettings
from .timers import TimerManager, TimerState, TimerView

ROW_GAP = 4
MAX_ROWS = 12
HEARD_S = 1.5
FADE_S = 1.0
RADIUS = 5.0
BACKGROUND = QColor(15, 23, 42, 190)
TEXT = QColor(241, 245, 249)
DARK_TEXT = QColor(15, 23, 42)
MUTED = QColor(203, 213, 225)
MOVE_SAMPLE = TimerView("sample", "Drag me", 12.0, 0.6, TimerState.RUNNING)
PREVIEW_ROWS = (
    TimerView("running", "Bloodletter E", 12.0, 0.6, TimerState.RUNNING),
    TimerView("warning", "Cleric Robe R", 2.4, 0.15, TimerState.WARNING),
    TimerView("ready", "Royal Cowl D", -0.1, 0.0, TimerState.READY),
)
LEFT = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
RIGHT = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight


def format_remaining(remaining_s: float) -> str:
    if remaining_s <= 0:
        return "READY"
    if remaining_s < 10:
        return f"{remaining_s:.1f}"
    return str(math.ceil(remaining_s))


def heard_message(text: str, has_abilities: bool) -> str:
    """Overlay line shown when push-to-talk produced no timer."""
    if text == UNKNOWN_SPEECH:
        return "? not a saved phrase" if has_abilities else "? no abilities saved – open Editor"
    return f'? heard: "{text}"' if text else "? heard nothing"


def text_color_for(bar: QColor) -> QColor:
    """Dark text on light bars, light text on dark bars (WCAG relative luminance)."""
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    luminance = (0.2126 * channel(bar.redF()) + 0.7152 * channel(bar.greenF())
                 + 0.0722 * channel(bar.blueF()))
    return DARK_TEXT if luminance > 0.3 else TEXT


def state_color(style: OverlaySettings, state: TimerState) -> QColor:
    return QColor({TimerState.RUNNING: style.color_running, TimerState.WARNING: style.color_warning,
                   TimerState.READY: style.color_ready}[state])


def bar_font(base: QFont, style: OverlaySettings) -> QFont:
    font = QFont(base)
    font.setPixelSize(max(10, round(style.bar_height * 0.5)))  # text grows with the bar
    font.setBold(True)
    return font


def draw_bar(painter: QPainter, rect: QRectF, view: TimerView, style: OverlaySettings,
             ready_display_s: float) -> None:
    """One timer row. Shared by the overlay and the settings preview so they always match."""
    color = state_color(style, view.state)
    fill_width = rect.width() * view.fraction
    opacity = 1.0
    if view.state is TimerState.READY:
        since_ready = -view.remaining_s
        opacity = max(0.0, min(1.0, (ready_display_s - since_ready) / FADE_S))
        color.setAlphaF(0.55 + 0.45 * abs(math.cos(since_ready * math.pi * 2)))  # pulse
        fill_width = rect.width()
    fill = QRectF(rect.x(), rect.y(), fill_width, rect.height())
    painter.save()
    painter.setOpacity(opacity)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(BACKGROUND)
    painter.drawRoundedRect(rect, RADIUS, RADIUS)
    painter.setBrush(color)
    painter.drawRoundedRect(fill, RADIUS, RADIUS)

    text_rect = rect.adjusted(8, 0, -8, 0)
    name = painter.fontMetrics().elidedText(view.name, Qt.TextElideMode.ElideRight,
                                            int(text_rect.width()) - painter.fontMetrics().height() * 3)
    remaining = format_remaining(view.remaining_s)
    # Text over the filled part takes a contrasting color; over the empty track it stays light.
    for clip, pen in ((fill, text_color_for(color)),
                      (QRectF(fill.right(), rect.y(), rect.right() - fill.right(), rect.height()), TEXT)):
        if clip.width() <= 0:
            continue
        painter.setClipRect(clip)
        painter.setPen(pen)
        painter.drawText(text_rect, LEFT, name)
        painter.drawText(text_rect, RIGHT, remaining)
    painter.restore()


def resolve_position(screens: list[QRect], screen: int, x: int, y: int) -> QPoint:
    """Global top-left for a saved (screen, x, y). Falls back to the first screen at the
    default offset when the saved screen is gone or the point is off that screen."""
    if 0 <= screen < len(screens):
        geometry = screens[screen]
        point = geometry.topLeft() + QPoint(x, y)
        if geometry.contains(point):
            return point
    default = OverlaySettings()
    origin = screens[0].topLeft() if screens else QPoint(0, 0)
    return origin + QPoint(default.x, default.y)


def relative_position(screens: list[QRect], point: QPoint) -> tuple[int, int, int]:
    """(screen index, x, y relative to that screen) for a global point."""
    for index, geometry in enumerate(screens):
        if geometry.contains(point):
            return index, point.x() - geometry.x(), point.y() - geometry.y()
    origin = screens[0].topLeft() if screens else QPoint(0, 0)
    return 0, point.x() - origin.x(), point.y() - origin.y()


class BarPreview(QWidget):
    """Three sample bars (counting down, warning, READY) drawn exactly like the overlay."""

    def __init__(self, style: OverlaySettings, parent=None) -> None:
        super().__init__(parent)
        self.style = style
        self.set_style(style)

    def set_style(self, style: OverlaySettings) -> None:
        self.style = style
        self.setMinimumSize(style.bar_width, len(PREVIEW_ROWS) * (style.bar_height + ROW_GAP))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(bar_font(self.font(), self.style))
        for index, view in enumerate(PREVIEW_ROWS):
            y = index * (self.style.bar_height + ROW_GAP)
            draw_bar(painter, QRectF(0, y, self.style.bar_width, self.style.bar_height), view,
                     self.style, ready_display_s=3.0)
        painter.end()


class OverlayWindow(QWidget):
    position_changed = Signal(int, int, int)  # screen index, x, y relative to that screen

    def __init__(self, timers: TimerManager, settings: OverlaySettings) -> None:
        super().__init__(None)
        self._timers = timers
        self._style = settings
        self._move_mode = False
        self._drag_offset: QPoint | None = None
        self._heard_message = ""
        self._heard_until = 0.0
        self.setWindowTitle("PVPTimer overlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._apply_flags()
        self.apply_settings(settings)

    def apply_settings(self, settings: OverlaySettings) -> None:
        self._style = settings
        self.setFixedSize(settings.bar_width, (settings.bar_height + ROW_GAP) * (MAX_ROWS + 1))
        self.setWindowOpacity(settings.opacity)
        self.move(resolve_position(self._screens(), settings.screen, settings.x, settings.y))
        self.update()

    def set_move_mode(self, on: bool) -> None:
        if on == self._move_mode:
            return
        was_visible = self.isVisible()
        self._move_mode = on
        self._apply_flags()
        if was_visible:
            self.show()  # changing window flags hides the window
        if not on:
            self.position_changed.emit(*relative_position(self._screens(), self.pos()))
        self.update()

    def show_heard(self, text: str, has_abilities: bool = True) -> None:
        self._heard_message = heard_message(text, has_abilities)
        self._heard_until = time.monotonic() + HEARD_S
        self.update()

    # window setup -------------------------------------------------------
    def _apply_flags(self) -> None:
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        if not self._move_mode:
            flags |= Qt.WindowType.WindowTransparentForInput  # clicks go through to the game
        self.setWindowFlags(flags)

    @staticmethod
    def _screens() -> list[QRect]:
        return [s.geometry() for s in QGuiApplication.screens()]

    # dragging (only possible in move mode, when the window accepts input) ---
    def mousePressEvent(self, event) -> None:
        if self._move_mode and event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_offset is not None:
            self._drag_offset = None
            self.position_changed.emit(*relative_position(self._screens(), self.pos()))

    # painting -----------------------------------------------------------
    def paintEvent(self, event) -> None:
        style = self._style
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(bar_font(self.font(), style))

        views = self._timers.snapshot()[:MAX_ROWS]
        if self._move_mode:
            painter.setPen(QPen(TEXT, 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
            views = views or [MOVE_SAMPLE]

        y = 0.0
        for view in views:
            draw_bar(painter, QRectF(0, y, style.bar_width, style.bar_height), view, style,
                     self._timers.ready_display_s)
            y += style.bar_height + ROW_GAP
        if time.monotonic() < self._heard_until:
            self._draw_heard(painter, QRectF(0, y, style.bar_width, style.bar_height))
        painter.end()

    def _draw_heard(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(BACKGROUND)
        painter.drawRoundedRect(rect, RADIUS, RADIUS)
        text_rect = rect.adjusted(8, 0, -8, 0)
        painter.setPen(MUTED)
        painter.drawText(text_rect, LEFT, painter.fontMetrics().elidedText(
            self._heard_message, Qt.TextElideMode.ElideRight, int(text_rect.width())))
