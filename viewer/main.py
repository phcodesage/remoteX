from __future__ import annotations

import os
import platform
import sys

from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from agent.desktop_worker import AgentWorker
from common.preferences import AppPreferences, load_preferences, save_preferences
from viewer.api_client import ApiClient, ApiError
from viewer.device_window import DashboardWindow
from viewer.settings_dialog import SettingsDialog
from viewer.theme.styles import stylesheet


class MainWindow(QMainWindow):
    def __init__(self, client: ApiClient, preferences: AppPreferences) -> None:
        super().__init__()
        self.client = client
        self.preferences = preferences
        self.setWindowTitle("RemoteX · Control Center")
        self.resize(1080, 720)
        top = QFrame()
        top.setObjectName("topbar")
        top_layout = QHBoxLayout(top)
        top_layout.addWidget(QLabel("REMOTEX   ·   CONTROL CENTER"))
        top_layout.addStretch()
        self.agent_status = QLabel("Starting this computer…")
        self.agent_status.setObjectName("muted")
        top_layout.addWidget(self.agent_status)
        side = QFrame()
        side.setObjectName("sidebar")
        side_layout = QVBoxLayout(side)
        side_layout.addWidget(QLabel("THIS COMPUTER"))
        side_layout.addWidget(QLabel(platform.node() or "This computer"))
        side_layout.addWidget(QLabel("● Ready for attended support"))
        side_layout.addSpacing(18)
        side_layout.addWidget(QLabel("WORKSPACE"))
        side_layout.addWidget(QLabel("Devices"))
        side_layout.addWidget(QLabel("Sessions"))
        side_layout.addWidget(QLabel("Files"))
        settings = QPushButton("Settings")
        settings.setObjectName("utility")
        settings.clicked.connect(self.open_settings)
        side_layout.addWidget(settings)
        side_layout.addStretch()
        mode = "Host mode" if preferences.host_mode else "Remote mode"
        side_layout.addWidget(QLabel(f"{mode} · {preferences.server_url}"))
        side_layout.addWidget(QLabel("Attended support only"))
        dashboard = DashboardWindow(client)
        content = QWidget()
        content.setLayout(QVBoxLayout())
        content.layout().addWidget(dashboard)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.addWidget(top)
        split = QWidget()
        split_layout = QHBoxLayout(split)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.addWidget(side, 0)
        split_layout.addWidget(content, 1)
        body_layout.addWidget(split, 1)
        self.setCentralWidget(body)
        self.dashboard = dashboard
        self.agent_worker = AgentWorker(
            client.base_url,
            client.token,
            os.getenv("REMOTE_DEVICE_NAME", platform.node() or "This computer"),
        )
        self.agent_worker.device_ready.connect(self.dashboard.set_local_device_id)
        self.agent_worker.status_changed.connect(self.on_agent_status)
        self.agent_worker.session_request.connect(self.handle_session_request)
        self.agent_worker.error.connect(self.on_agent_error)
        self.agent_worker.start()

    def on_agent_status(self, message: str) -> None:
        self.agent_status.setText(message)
        if message == "This computer is online":
            self.dashboard.load_devices()

    def on_agent_error(self, message: str) -> None:
        self.agent_status.setText(f"Agent: {message}")

    def handle_session_request(self, session_id: str, controller: str, pairing_code: str) -> None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Incoming remote-support request")
        dialog.setText("A controller is requesting access to this computer.")
        dialog.setInformativeText(
            f"Controller: {controller}\nPairing code: {pairing_code}\n\n"
            "Allowing access starts screen sharing and enables mouse/keyboard control."
        )
        dialog.setIcon(QMessageBox.Icon.Warning)
        allow = dialog.addButton("Allow Access", QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton("Reject", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        self.agent_worker.decide(session_id, dialog.clickedButton() is allow)

    def closeEvent(self, event) -> None:
        if self.agent_worker:
            self.agent_worker.stop()
        event.accept()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.preferences, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.preferences = dialog.preferences()
        save_preferences(self.preferences)
        QMessageBox.information(
            self,
            "Settings saved",
            "Restart RemoteX for the new host or tunnel settings to take effect.",
        )


def run_unified() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(stylesheet())
    preferences = load_preferences()
    client = ApiClient(preferences.effective_server_url)
    access_token = os.getenv("REMOTE_ACCESS_TOKEN") or os.getenv("REMOTE_OWNER_TOKEN")
    if access_token:
        client.token = access_token
    else:
        try:
            client.local_authenticate()
        except ApiError as exc:
            QMessageBox.critical(
                None,
                "RemoteX cannot connect",
                f"No local session is available. Set REMOTE_ACCESS_TOKEN for a shared server.\n\n{exc}",
            )
            return
    if not client.token:
        return
    window = MainWindow(client, preferences)
    window.show()
    sys.exit(app.exec())


def run_viewer() -> None:
    run_unified()
