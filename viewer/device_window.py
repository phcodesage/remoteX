from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QInputDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from viewer.api_client import ApiClient, ApiError
from viewer.session_window import SessionWindow


class DeviceCard(QFrame):
    def __init__(self, client: ApiClient, device: dict) -> None:
        super().__init__()
        self.setObjectName("card")
        self.device = device
        title = QLabel(f"{'●' if device['online'] else '○'}  {device['name']}")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        info = QLabel(f"{device['platform']} · {'Online' if device['online'] else 'Offline'}")
        info.setObjectName("muted")
        connect = QPushButton("Connect")
        connect.setObjectName("primary")
        connect.setEnabled(device["online"])
        connect.clicked.connect(self.connect)
        details = QPushButton("Details")
        details.setObjectName("utility")
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(info)
        buttons = QHBoxLayout()
        buttons.addWidget(connect)
        buttons.addWidget(details)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.client = client

    def connect(self) -> None:
        try:
            session = self.client.create_session(self.device["id"])
        except ApiError as exc:
            self.find_parent_window().show_message(str(exc))
            return
        window = SessionWindow(self.client, session, self.device["name"])
        window.show()
        self.find_parent_window().session_windows.append(window)

    def find_parent_window(self):
        parent = self.parentWidget()
        while parent and not hasattr(parent, "show_message"):
            parent = parent.parentWidget()
        return parent


class DashboardWindow(QWidget):
    def __init__(self, client: ApiClient) -> None:
        super().__init__()
        self.client = client
        self.session_windows: list[SessionWindow] = []
        self.devices: list[dict] = []
        self.message = QLabel("Ready")
        self.message.setObjectName("muted")
        heading = QHBoxLayout()
        heading.addWidget(QLabel("Connect to another computer"))
        heading.addStretch()
        heading.addWidget(self.message)
        pair = QPushButton("Enter pairing code")
        pair.setObjectName("primary")
        pair.clicked.connect(self.claim_pairing)
        heading.addWidget(pair)
        instructions = QLabel(
            "Each computer shows its own six-digit pairing code in the left sidebar. "
            "Enter the OTHER computer's code here; the remote user must click Allow "
            "before screen control starts."
        )
        instructions.setObjectName("muted")
        instructions.setWordWrap(True)
        root = QVBoxLayout(self)
        root.addLayout(heading)
        root.addWidget(instructions)
        root.addStretch()
        self.load_devices()

    def load_devices(self) -> None:
        self.show_message("Ready — use the remote computer's pairing code.")

    def set_local_device_id(self, device_id: str) -> None:
        return

    def claim_pairing(self) -> None:
        code, accepted = QInputDialog.getText(
            self,
            "Connect a remote device",
            "Enter the other computer's pairing code (000-000):",
        )
        if not accepted or not code.strip():
            return
        try:
            session = self.client.claim_pairing(code.strip())
        except ApiError as exc:
            self.show_message(str(exc))
            return
        device_name = session.get("device_name") or "Remote device"
        window = SessionWindow(self.client, session, device_name)
        window.show()
        self.session_windows.append(window)

    def show_message(self, message: str) -> None:
        self.message.setText(message)
