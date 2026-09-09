from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from viewer.api_client import ApiClient, ApiError
from viewer.screen_widget import RemoteScreenWidget
from viewer.viewer_rtc import ViewerRtcWorker


class SessionWindow(QMainWindow):
    def __init__(self, client: ApiClient, session: dict, device_name: str) -> None:
        super().__init__()
        self.client = client
        self.session_data = session
        self.device_name = device_name
        self.worker: ViewerRtcWorker | None = None
        self.setWindowTitle(f"Remote Desktop · {device_name}")
        self.resize(1100, 760)
        self.screen = RemoteScreenWidget()
        self.status = QLabel(f"Pairing code: {session.get('pairing_code', 'sent to remote user')} · Waiting for approval")
        self.status.setObjectName("muted")
        end = QPushButton("End session")
        end.setObjectName("danger")
        end.clicked.connect(self.end_session)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel(device_name))
        toolbar.addStretch()
        toolbar.addWidget(self.status)
        toolbar.addWidget(end)
        actions = QHBoxLayout()
        for label, object_name in [("Mouse", "primary"), ("Keyboard", "primary"), ("Clipboard", "utility"), ("Files", "warning"), ("Audio", "warning")]:
            button = QPushButton(label)
            button.setObjectName(object_name)
            actions.addWidget(button)
        layout = QVBoxLayout()
        layout.addLayout(toolbar)
        layout.addWidget(self.screen, 1)
        layout.addLayout(actions)
        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)
        self.screen.mouse_command.connect(self.send_control)
        self.poller = QTimer(self)
        self.poller.timeout.connect(self.check_session)
        self.poller.start(1000)

    def check_session(self) -> None:
        try:
            session = self.client.session(self.session_data["id"])
        except ApiError as exc:
            self.status.setText(str(exc))
            return
        if session["status"] == "active" and self.worker is None:
            self.poller.stop()
            self.start_worker()
        elif session["status"] in {"rejected", "expired", "revoked", "ended"}:
            self.status.setText(f"Session {session['status']}")
            self.poller.stop()

    def start_worker(self) -> None:
        self.worker = ViewerRtcWorker(
            self.client.base_url,
            self.session_data.get("signaling_token", self.client.token),
            self.session_data["id"],
            self.client.ice_servers(),
        )
        self.worker.frame_ready.connect(self.screen.set_frame)
        self.worker.status_changed.connect(self.status.setText)
        self.worker.error.connect(self.status.setText)
        self.worker.start()

    def send_control(self, command: dict) -> None:
        if self.worker:
            self.worker.send_control(command)

    def end_session(self) -> None:
        try:
            self.client.revoke_session(self.session_data["id"])
        except ApiError as exc:
            self.status.setText(str(exc))
        self.close()

    def closeEvent(self, event) -> None:
        if self.worker:
            self.worker.stop()
        event.accept()
