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

from common.preferences import AppPreferences, configured_value, load_preferences, save_preferences
from viewer.api_client import ApiClient, ApiError
from viewer.settings_dialog import SettingsDialog
from viewer.theme.styles import stylesheet


class MainWindow(QMainWindow):
    def __init__(self, preferences: AppPreferences) -> None:
        super().__init__()
        self.client: ApiClient | None = None
        self.preferences = preferences
        self.dashboard = None
        self.agent_worker = None
        self.connection_panel = None
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
        self.mode_label = QLabel()
        self.mode_label.setWordWrap(True)
        side_layout.addWidget(self.mode_label)
        side_layout.addWidget(QLabel("Attended support only"))
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
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
        self.connection_panel = self._build_connection_panel()
        self.content_layout.addWidget(self.connection_panel)
        self.update_connection_panel()

    def _build_connection_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        title = QLabel("RemoteX is ready")
        title.setObjectName("title")
        layout.addWidget(title)
        self.connection_description = QLabel()
        self.connection_description.setWordWrap(True)
        self.connection_description.setObjectName("muted")
        layout.addWidget(self.connection_description)
        self.connection_status = QLabel("Choose Start to connect this computer.")
        self.connection_status.setWordWrap(True)
        layout.addWidget(self.connection_status)
        buttons = QHBoxLayout()
        start = QPushButton("Start connection")
        start.setObjectName("primary")
        start.clicked.connect(self.connect_to_server)
        buttons.addWidget(start)
        configure = QPushButton("Settings")
        configure.setObjectName("utility")
        configure.clicked.connect(self.open_settings)
        buttons.addWidget(configure)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.start_button = start
        return panel

    def update_connection_panel(self) -> None:
        mode = "Host mode" if self.preferences.host_mode else "Remote mode"
        target = self.preferences.effective_server_url
        public = self.preferences.server_url
        self.mode_label.setText(f"{mode}\n{public}")
        if self.preferences.host_mode:
            self.connection_description.setText(
                f"This computer will host the control server on {target}. "
                f"The tunnel domain for other computers is {public}."
            )
        else:
            self.connection_description.setText(
                f"This computer will connect to the tunneled control server at {public}."
            )

    def connect_to_server(self) -> None:
        self.start_button.setEnabled(False)
        self.connection_status.setText("Connecting…")
        try:
            if self.preferences.host_mode:
                from run import ensure_local_server

                ensure_local_server()
            client = ApiClient(self.preferences.effective_server_url)
            access_token = configured_value("REMOTE_ACCESS_TOKEN") or configured_value(
                "REMOTE_OWNER_TOKEN"
            )
            if access_token:
                client.token = access_token
            else:
                client.local_authenticate()
            self.attach_client(client)
        except (ApiError, OSError, RuntimeError) as exc:
            self.connection_status.setText(f"Connection unavailable: {exc}")
            self.start_button.setEnabled(True)

    def attach_client(self, client: ApiClient) -> None:
        from agent.desktop_worker import AgentWorker
        from viewer.device_window import DashboardWindow

        self.client = client
        if self.connection_panel:
            self.content_layout.removeWidget(self.connection_panel)
            self.connection_panel.deleteLater()
            self.connection_panel = None
        self.dashboard = DashboardWindow(client)
        self.content_layout.addWidget(self.dashboard)
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
        if message == "This computer is online" and self.dashboard:
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
        if self.agent_worker:
            self.agent_worker.stop()
            self.agent_worker = None
        if self.dashboard:
            self.dashboard.deleteLater()
            self.dashboard = None
        self.client = None
        if self.connection_panel:
            self.content_layout.removeWidget(self.connection_panel)
            self.connection_panel.deleteLater()
            self.connection_panel = None
        self.preferences = dialog.preferences()
        save_preferences(self.preferences)
        self.connection_panel = self._build_connection_panel()
        self.content_layout.addWidget(self.connection_panel)
        self.update_connection_panel()
        self.connection_status.setText("Settings saved. Choose Start connection to apply them.")


def run_unified() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(stylesheet())
    preferences = load_preferences()
    window = MainWindow(preferences)
    window.show()
    sys.exit(app.exec())


def run_viewer() -> None:
    run_unified()
