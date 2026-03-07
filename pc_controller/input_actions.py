from __future__ import annotations

import ctypes
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import APP_DIR
from .system_actions import CommandResult

try:
    import pyautogui
except ImportError:  # pragma: no cover - dependency is expected at runtime
    pyautogui = None

if pyautogui is not None:
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.03

AUTOACCEPT_DIR = APP_DIR / 'autoaccept_templates'


def type_text(text: str, interval: float = 0.01) -> CommandResult:
    _ensure_pyautogui()
    cleaned = (text or '').strip()
    if not cleaned:
        raise ValueError('Text is empty.')
    pyautogui.write(cleaned, interval=interval)
    return CommandResult(True, f'Text typed: {cleaned[:80]}')


def press_combination(keys: list[str]) -> CommandResult:
    _ensure_pyautogui()
    normalized = [_normalize_key(key) for key in keys if key.strip()]
    if not normalized:
        raise ValueError('No keys provided.')
    pyautogui.hotkey(*normalized)
    return CommandResult(True, f'Combination pressed: {" + ".join(normalized)}')


def left_click() -> CommandResult:
    _ensure_pyautogui()
    pyautogui.leftClick()
    return CommandResult(True, 'Left click completed.')


def right_click() -> CommandResult:
    _ensure_pyautogui()
    pyautogui.rightClick()
    return CommandResult(True, 'Right click completed.')


def double_left_click() -> CommandResult:
    _ensure_pyautogui()
    pyautogui.doubleClick(button='left')
    return CommandResult(True, 'Double left click completed.')


def middle_click() -> CommandResult:
    _ensure_pyautogui()
    pyautogui.middleClick()
    return CommandResult(True, 'Middle click completed.')


def right_hold(duration_seconds: float = 2.0) -> CommandResult:
    _ensure_pyautogui()
    if duration_seconds <= 0 or duration_seconds > 30:
        raise ValueError('Hold duration should be between 0 and 30 seconds.')
    pyautogui.mouseDown(button='right')
    time.sleep(duration_seconds)
    pyautogui.mouseUp(button='right')
    return CommandResult(True, f'Right button held for {duration_seconds:.1f}s.')


def move_mouse(x: int, y: int, duration_seconds: float = 0.15) -> CommandResult:
    _ensure_pyautogui()
    pyautogui.moveTo(x=x, y=y, duration=max(0.0, min(duration_seconds, 5.0)))
    return CommandResult(True, f'Mouse moved to ({x}, {y}).')


def show_message(text: str, title: str = 'PC Controller') -> CommandResult:
    cleaned = (text or '').strip()
    if not cleaned:
        raise ValueError('Message text is empty.')
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    flags = 0x00001000 | 0x00040000  # MB_SYSTEMMODAL | MB_TOPMOST
    user32.MessageBoxW(None, cleaned, title, flags)
    return CommandResult(True, 'Screen message shown.')


def speak_text(text: str) -> CommandResult:
    cleaned = (text or '').strip()
    if not cleaned:
        raise ValueError('Speech text is empty.')
    try:
        from win32com.client import Dispatch
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError('win32com is unavailable.') from exc

    speaker = Dispatch('SAPI.SpVoice')
    speaker.Volume = 100
    speaker.Rate = 0
    speaker.Speak(cleaned)
    return CommandResult(True, 'Speech played.')


@dataclass(slots=True)
class AutoAcceptConfig:
    template_dir: Path
    interval_seconds: float = 0.35
    timeout_seconds: int = 300


class AutoAcceptService:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def start(
            self,
            config: AutoAcceptConfig,
            on_match: Callable[[str], None],
            on_error: Callable[[str], None],
            on_finish: Callable[[str], None],
    ) -> CommandResult:
        _ensure_pyautogui()
        if self._active:
            raise RuntimeError('Auto-accept is already active.')

        template_dir = config.template_dir.resolve(strict=False)
        template_dir.mkdir(parents=True, exist_ok=True)

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(config, on_match, on_error, on_finish),
            name='autoaccept-watcher',
            daemon=True,
        )
        self._active = True
        self._thread.start()
        return CommandResult(True, f'Auto-accept started. Watching: {template_dir}')

    def stop(self) -> CommandResult:
        if not self._active:
            return CommandResult(True, 'Auto-accept is already stopped.')
        self._stop_event.set()
        return CommandResult(True, 'Auto-accept stop requested.')

    def _run(
            self,
            config: AutoAcceptConfig,
            on_match: Callable[[str], None],
            on_error: Callable[[str], None],
            on_finish: Callable[[str], None],
    ) -> None:
        deadline = time.monotonic() + max(1, config.timeout_seconds)
        template_dir = config.template_dir.resolve(strict=False)

        last_errors: dict[str, str] = {}

        try:
            import cv2
            has_cv2 = True
        except ImportError:
            has_cv2 = False

        try:
            while not self._stop_event.is_set():
                template_paths = [path for path in template_dir.iterdir() if
                                  path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp'}]
                if not template_paths:
                    time.sleep(config.interval_seconds)
                    if time.monotonic() >= deadline:
                        on_finish('ℹ️ AutoAccept: остановлен, нет шаблонов.')
                        return
                    continue

                for template_path in template_paths:
                    if self._stop_event.is_set():
                        on_finish('AutoAccept: остановлен пользователем.')
                        return
                    try:
                        if has_cv2:
                            point = pyautogui.locateCenterOnScreen(str(template_path), grayscale=True,
                                                                   confidence=0.7)
                        else:
                            point = pyautogui.locateCenterOnScreen(str(template_path), grayscale=True)

                        if point is not None:
                            pyautogui.click(point.x, point.y)
                            on_match(f'AutoAccept: найден шаблон <b>{template_path.name}</b>')
                            on_finish('AutoAccept: успешно завершен.')
                            return
                    except Exception as exc:  # noqa: BLE001
                        if type(exc).__name__ == 'ImageNotFoundException' or 'image not found' in str(
                                exc).lower() or not str(exc).strip():
                            pass
                        else:
                            error_message = f'AutoAccept ошибка ({template_path.name}): {exc}'
                            if last_errors.get(template_path.name) != error_message:
                                on_error(error_message)
                                last_errors[template_path.name] = error_message

                    time.sleep(config.interval_seconds)

                if time.monotonic() >= deadline:
                    on_finish('ℹ️ AutoAccept: время ожидания вышло.')
                    return
        finally:
            self._active = False
            self._stop_event.clear()

def _normalize_key(key: str) -> str:
    normalized = key.strip().lower().replace('+', '')
    aliases = {
        'control': 'ctrl',
        'windows': 'win',
        'return': 'enter',
        'escape': 'esc',
        'del': 'delete',
    }
    return aliases.get(normalized, normalized)

def _ensure_pyautogui() -> None:
    if pyautogui is None:
        raise RuntimeError('pyautogui is not installed.')
