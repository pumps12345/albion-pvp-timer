"""Transparent, always-on-top, click-through window that draws the active timers."""
import math
import time

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .router import UNKNOWN_SPEECH
from .settings import OverlaySettings
from .timers import TimerManager, TimerState, TimerView

ROW_W, ROW_H, ROW_GAP = 260, 26, 4
MAX_ROWS = 12
HEARD_S = 1.5
FADE_S = 1.0
RADIUS = 5.0
BACKGROUND = QColor(15, 23, 42, 190)
TEXT = QColor(241, 245, 249)
MUTED = QColor(203, 213, 225)
STATE_COLORS = {
    TimerState.RUNNING: QColor(100, 116, 139),
    TimerState.WARNING: QColor(245, 158, 11),
    TimerState.READY: QColor(34, 197, 94),
}
MOVE_SAMPLE = TimerView("sample", "Drag me", 12.0, 0.6, TimerState.RUNNING)
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


class OverlayWindow(QWidget):
    position_changed = Signal(int, int, int)  # screen index, x, y relative to that screen

    def __init__(self, timers: TimerManager, settings: OverlaySettings) -> None:
        super().__init__(None)
        self._timers = timers
        self._move_mode = False
        self._drag_offset: QPoint | None = None
        self._heard_message = ""
        self._heard_until = 0.0
        self.setWindowTitle("PVPTimer overlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(ROW_W, (ROW_H + ROW_GAP) * (MAX_ROWS + 1))
        self._apply_flags()
        self.apply_settings(settings)

    def apply_settings(self, settings: OverlaySettings) -> None:
        self.setWindowOpacity(settings.opacity)
        self.move(resolve_position(self._screens(), settings.screen, settings.x, settings.y))

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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(self.font())
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)

        views = self._timers.snapshot()[:MAX_ROWS]
        if self._move_mode:
            painter.setPen(QPen(TEXT, 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
            views = views or [MOVE_SAMPLE]

        y = 0.0
        for view in views:
            self._draw_row(painter, QRectF(0, y, ROW_W, ROW_H), view)
            y += ROW_H + ROW_GAP
        if time.monotonic() < self._heard_until:
            self._draw_heard(painter, QRectF(0, y, ROW_W, ROW_H))
        painter.end()

    def _draw_row(self, painter: QPainter, rect: QRectF, view: TimerView) -> None:
        color = QColor(STATE_COLORS[view.state])
        fill_width = rect.width() * view.fraction
        opacity = 1.0
        if view.state is TimerState.READY:
            since_ready = -view.remaining_s
            opacity = max(0.0, min(1.0, (self._timers.ready_display_s - since_ready) / FADE_S))
            color.setAlphaF(0.55 + 0.45 * abs(math.cos(since_ready * math.pi * 2)))  # pulse
            fill_width = rect.width()
        painter.setOpacity(opacity)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(BACKGROUND)
        painter.drawRoundedRect(rect, RADIUS, RADIUS)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(rect.x(), rect.y(), fill_width, rect.height()), RADIUS, RADIUS)
        text_rect = rect.adjusted(8, 0, -8, 0)
        name = painter.fontMetrics().elidedText(view.name, Qt.TextElideMode.ElideRight,
                                                int(text_rect.width()) - 56)
        painter.setPen(TEXT)
        painter.drawText(text_rect, LEFT, name)
        painter.drawText(text_rect, RIGHT, format_remaining(view.remaining_s))
        painter.setOpacity(1.0)

    def _draw_heard(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(BACKGROUND)
        painter.drawRoundedRect(rect, RADIUS, RADIUS)
        text = self._heard_message
        text_rect = rect.adjusted(8, 0, -8, 0)
        painter.setPen(MUTED)
        painter.drawText(text_rect, LEFT, painter.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideRight, int(text_rect.width())))
