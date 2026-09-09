from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QMouseEvent, QPixmap
from PySide6.QtWidgets import QLabel


class RemoteScreenWidget(QLabel):
    mouse_command = Signal(dict)

    def __init__(self) -> None:
        super().__init__("Waiting for remote screen…")
        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(640, 360)
        self.setStyleSheet("background: #090909; border: 1px solid #465064; border-radius: 8px; color: #7F8796;")
        self._image_size = None

    def set_frame(self, image: QImage) -> None:
        self._image_size = image.size()
        self.setPixmap(QPixmap.fromImage(image).scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event) -> None:
        if self.pixmap() and not self.pixmap().isNull():
            self.setPixmap(self.pixmap().scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        super().resizeEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.setFocus(Qt.MouseFocusReason)
        if event.button() == Qt.LeftButton:
            self.mouse_command.emit({"type": "mouse_button", "button": "left", "pressed": True})
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._image_size:
            x = int(max(0, min(1, event.position().x() / max(1, self.width()))) * self._image_size.width())
            y = int(max(0, min(1, event.position().y() / max(1, self.height()))) * self._image_size.height())
            self.mouse_command.emit({"type": "mouse_move", "x": x, "y": y})
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event) -> None:
        key = event.text() or self._special_key(event.key())
        if key:
            self.mouse_command.emit({"type": "key", "key": key, "pressed": True})
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        key = event.text() or self._special_key(event.key())
        if key:
            self.mouse_command.emit({"type": "key", "key": key, "pressed": False})
        super().keyReleaseEvent(event)

    @staticmethod
    def _special_key(key: int) -> str:
        return {
            Qt.Key_Return: "enter",
            Qt.Key_Enter: "enter",
            Qt.Key_Backspace: "backspace",
            Qt.Key_Tab: "tab",
            Qt.Key_Escape: "esc",
            Qt.Key_Space: "space",
            Qt.Key_Control: "ctrl",
            Qt.Key_Shift: "shift",
            Qt.Key_Alt: "alt",
            Qt.Key_Meta: "command",
            Qt.Key_Left: "left",
            Qt.Key_Right: "right",
            Qt.Key_Up: "up",
            Qt.Key_Down: "down",
        }.get(key, "")

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.mouse_command.emit({"type": "mouse_button", "button": "left", "pressed": False})
        super().mouseReleaseEvent(event)
