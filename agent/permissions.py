from __future__ import annotations

import asyncio
import os
import platform


def _desktop_approval(controller: str, pairing_code: str) -> bool:
    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance() or QApplication([])
    dialog = QMessageBox()
    dialog.setWindowTitle("Incoming remote-support request")
    dialog.setText("A controller is requesting access to this computer.")
    dialog.setInformativeText(f"Controller: {controller or 'authenticated controller'}\nPairing code: {pairing_code or 'verified'}")
    dialog.setIcon(QMessageBox.Icon.Warning)
    allow = dialog.addButton("Allow Access", QMessageBox.ButtonRole.AcceptRole)
    dialog.addButton("Reject", QMessageBox.ButtonRole.RejectRole)
    dialog.exec()
    return dialog.clickedButton() is allow


def _has_desktop() -> bool:
    return platform.system() == "Darwin" or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


async def ask_for_approval(controller: str, pairing_code: str, timeout_seconds: int = 120) -> bool:
    """Show an attended native prompt when possible, otherwise use the terminal."""
    if _has_desktop():
        return _desktop_approval(controller, pairing_code)
    print("\nIncoming remote-support request")
    print(f"Controller: {controller or 'authenticated controller'}")
    print(f"Pairing code: {pairing_code or 'already verified by server'}")
    print("Allow access? Type 'allow' or 'reject' (expires in 120 seconds): ", end="", flush=True)
    try:
        answer = await asyncio.wait_for(asyncio.to_thread(input), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        print("\nApproval timed out.")
        return False
    return answer.strip().lower() in {"allow", "a", "yes", "y"}
