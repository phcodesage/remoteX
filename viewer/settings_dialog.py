from __future__ import annotations

from urllib.parse import urlparse

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
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
            "Choose where this computer connects. Host mode starts the local FastAPI "
            "server; your tunnel must forward the public domain to that port."
        )
        intro.setWordWrap(True)
        intro.setObjectName("muted")

        self.host_mode = QCheckBox("Make this computer the host")
        self.host_mode.setChecked(preferences.host_mode)
        self.host_mode.setToolTip("Start the local control server on this computer.")

        self.server_url = QLineEdit(preferences.server_url)
        self.server_url.setPlaceholderText("https://remotex.chat-x.site")
        self.server_url.setToolTip("Public HTTPS/WSS domain used by other computers.")

        self.host_port = QSpinBox()
        self.host_port.setRange(1024, 65535)
        self.host_port.setValue(preferences.host_port)
        self.host_port.setSuffix("  (local FastAPI port)")

        form = QFormLayout()
        form.addRow(self.host_mode)
        form.addRow("Tunneled control domain", self.server_url)
        form.addRow("Host port", self.host_port)

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
            host_mode=self.host_mode.isChecked(),
            host_port=self.host_port.value(),
        )
        super().accept()

    def preferences(self) -> AppPreferences:
        return self._preferences
