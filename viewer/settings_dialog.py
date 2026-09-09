from __future__ import annotations

from urllib.parse import urlparse

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from common.preferences import AppPreferences


class SettingsDialog(QDialog):
    def __init__(self, preferences: AppPreferences, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("RemoteX Settings")
        self.setMinimumWidth(480)
        self._preferences = preferences

        intro = QLabel(
            "Set the HTTPS control-server address used by this computer. "
            "To host the service, run `python3 run.py backend` separately."
        )
        intro.setWordWrap(True)
        intro.setObjectName("muted")

        self.server_url = QLineEdit(preferences.server_url)
        self.server_url.setPlaceholderText("https://remotex.chat-x.site")
        self.server_url.setToolTip("Public HTTPS/WSS domain used by other computers.")

        form = QFormLayout()
        form.addRow("Tunneled control domain", self.server_url)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def accept(self) -> None:
        value = self.server_url.text().strip().rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            QMessageBox.warning(
                self,
                "Invalid control domain",
                "Enter a full URL such as https://remotex.chat-x.site",
            )
            return
        self._preferences = AppPreferences(
            server_url=value,
        )
        super().accept()

    def preferences(self) -> AppPreferences:
        return self._preferences
