from __future__ import annotations

import json

import pyautogui

from common.protocol import InputCommand


class InputController:
    """Applies only the explicit control messages supported by the MVP."""

    def __init__(self) -> None:
        self.width, self.height = pyautogui.size()
        pyautogui.PAUSE = 0.01
        pyautogui.FAILSAFE = True

    def handle(self, raw: str | bytes) -> None:
        command = InputCommand.model_validate(json.loads(raw))
        if command.type == "mouse_move" and command.x is not None and command.y is not None:
            pyautogui.moveTo(min(command.x, self.width - 1), min(command.y, self.height - 1), _pause=False)
        elif command.type == "mouse_button" and command.button:
            if command.pressed is False:
                pyautogui.mouseUp(button=command.button)
            else:
                pyautogui.mouseDown(button=command.button)
        elif command.type == "mouse_scroll" and command.delta:
            pyautogui.scroll(command.delta)
        elif command.type == "key" and command.key:
            if command.pressed is False:
                pyautogui.keyUp(command.key.lower())
            else:
                pyautogui.keyDown(command.key.lower())
        elif command.type == "hotkey" and command.keys:
            pyautogui.hotkey(*(key.lower() for key in command.keys))

