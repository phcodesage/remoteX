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
        self.local_device_id: str | None = None
        self.device_layout = QVBoxLayout()
        self.message = QLabel("Ready")
        self.message.setObjectName("muted")
        refresh = QPushButton("Refresh")
        refresh.setObjectName("utility")
        refresh.clicked.connect(self.load_devices)
        heading = QHBoxLayout()
        heading.addWidget(QLabel("Other devices"))
        heading.addStretch()
        heading.addWidget(self.message)
        pair = QPushButton("Pairing code")
        pair.setObjectName("primary")
        pair.clicked.connect(self.claim_pairing)
        heading.addWidget(pair)
        heading.addWidget(refresh)
        root = QVBoxLayout(self)
        root.addLayout(heading)
        root.addLayout(self.device_layout)
        root.addStretch()
        self.load_devices()

    def load_devices(self) -> None:
        while self.device_layout.count():
            item = self.device_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        try:
            devices = self.client.devices()
            if self.local_device_id:
                devices = [device for device in devices if device["id"] != self.local_device_id]
            self.devices = devices
        except ApiError as exc:
            self.show_message(str(exc))
            return
        if not devices:
            empty = QLabel("No other devices yet. Start RemoteX on another computer to connect.")
            empty.setObjectName("muted")
            self.device_layout.addWidget(empty)
            return
        for device in devices:
            self.device_layout.addWidget(DeviceCard(self.client, device))

    def set_local_device_id(self, device_id: str) -> None:
        self.local_device_id = device_id
        self.load_devices()

    def claim_pairing(self) -> None:
        code, accepted = QInputDialog.getText(self, "Connect a remote device", "Enter pairing code (000-000):")
        if not accepted or not code.strip():
            return
        try:
            session = self.client.claim_pairing(code.strip())
        except ApiError as exc:
            self.show_message(str(exc))
            return
        device_name = next(
            (device["name"] for device in self.devices if device["id"] == session["device_id"]),
            "Remote device",
        )
        window = SessionWindow(self.client, session, device_name)
        window.show()
        self.session_windows.append(window)

    def show_message(self, message: str) -> None:
        self.message.setText(message)
