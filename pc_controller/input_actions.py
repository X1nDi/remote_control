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
except ImportError:
    pyautogui = None

try:
    import pyperclip
except ImportError:
    pyperclip = None

if pyautogui is not None:
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.03

AUTOACCEPT_DIR = APP_DIR / 'autoaccept_templates'

def _ensure_pyautogui() -> None:
    if pyautogui is None: raise RuntimeError('pyautogui is not installed.')

def _ensure_pyperclip() -> None:
    if pyperclip is None: raise RuntimeError('pyperclip is not installed. (pip install pyperclip)')

def type_text(text: str, interval: float = 0.01) -> CommandResult:
    _ensure_pyautogui()
    cleaned = (text or '').strip()
    if not cleaned: raise ValueError('Text is empty.')
    pyautogui.write(cleaned, interval=interval)
    return CommandResult(True, f'Text typed: {cleaned[:80]}')

def press_combination(keys: list[str]) -> CommandResult:
    _ensure_pyautogui()
    normalized = [_normalize_key(key) for key in keys if key.strip()]
    if not normalized: raise ValueError('No keys provided.')
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
    pyautogui.doubleClick()
    return CommandResult(True, 'Double left click completed.')

def middle_click() -> CommandResult:
    _ensure_pyautogui()
    pyautogui.middleClick()
    return CommandResult(True, 'Middle click completed.')

def right_hold(duration_seconds: float = 2.0) -> CommandResult:
    _ensure_pyautogui()
    pyautogui.mouseDown(button='right')
    time.sleep(max(0.1, duration_seconds))
    pyautogui.mouseUp(button='right')
    return CommandResult(True, f'Right button held for {duration_seconds}s.')

def move_mouse(x: int, y: int, duration_seconds: float = 0.15, relative: bool = False) -> CommandResult:
    _ensure_pyautogui()
    if relative:
        pyautogui.move(xOffset=x, yOffset=y, duration=max(0.0, min(duration_seconds, 5.0)))
        return CommandResult(True, f'Mouse moved relatively by ({x}, {y}).')
    else:
        pyautogui.moveTo(x=x, y=y, duration=max(0.0, min(duration_seconds, 5.0)))
        return CommandResult(True, f'Mouse moved to ({x}, {y}).')

def speak_text(text: str) -> CommandResult:
    try:
        import pyttsx3
        def _speak():
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        threading.Thread(target=_speak, daemon=True).start()
        return CommandResult(True, "Текст озвучен.")
    except ImportError:
        return CommandResult(False, "Установите pyttsx3: pip install pyttsx3")

def get_clipboard() -> CommandResult:
    _ensure_pyperclip()
    try:
        text = pyperclip.paste()
        if not text:
            return CommandResult(True, "Буфер обмена пуст или содержит не текст.")
        if len(text) > 3500:
            text = text[:3500] + "\n...[ОБРЕЗАНО]..."
        return CommandResult(True, text)
    except Exception as e:
        return CommandResult(False, f"Ошибка чтения буфера: {e}")

def set_clipboard(text: str) -> CommandResult:
    _ensure_pyperclip()
    try:
        pyperclip.copy(text)
        return CommandResult(True, "Текст скопирован в буфер обмена ПК.")
    except Exception as e:
        return CommandResult(False, f"Ошибка записи: {e}")

_afk_active = False
_afk_thread: threading.Thread | None = None

def is_anti_afk_active() -> bool:
    global _afk_active
    return _afk_active

def start_anti_afk() -> CommandResult:
    global _afk_active, _afk_thread
    _ensure_pyautogui()
    if _afk_active: return CommandResult(False, "Anti-AFK уже работает.")
    _afk_active = True
    def _afk_loop():
        import random
        while _afk_active:
            pyautogui.press('space')
            time.sleep(random.uniform(0.1, 0.3))
            key = random.choice(['w', 'a', 's', 'd'])
            pyautogui.keyDown(key)
            time.sleep(random.uniform(0.1, 0.5))
            pyautogui.keyUp(key)
            wait_time = random.uniform(10, 35)
            start_wait = time.time()
            while _afk_active and (time.time() - start_wait) < wait_time:
                time.sleep(0.5)
    _afk_thread = threading.Thread(target=_afk_loop, daemon=True)
    _afk_thread.start()
    return CommandResult(True, "Anti-AFK запущен.")

def stop_anti_afk() -> CommandResult:
    global _afk_active
    if not _afk_active: return CommandResult(False, "Anti-AFK не запущен.")
    _afk_active = False
    return CommandResult(True, "Anti-AFK остановлен.")

@dataclass(slots=True)
class AutoAcceptConfig:
    template_dir: Path
    interval_seconds: float = 1.0
    timeout_seconds: float = 300.0
    confidence: float = 0.85

class AutoAcceptService:
    def __init__(self) -> None:
        self._active = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def active(self) -> bool: return self._active

    def start(self, config: AutoAcceptConfig, on_match: Callable[[str], None], on_error: Callable[[str], None], on_finish: Callable[[str], None]) -> CommandResult:
        if self._active: return CommandResult(False, 'AutoAccept is already running.')
        if not config.template_dir.exists(): return CommandResult(False, 'Template directory does not exist.')
        templates = [p for p in config.template_dir.iterdir() if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp'}]
        if not templates: return CommandResult(False, 'No templates found in the directory.')

        self._active = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, args=(config, templates, on_match, on_error, on_finish), daemon=True)
        self._thread.start()
        return CommandResult(True, 'AutoAccept started.')

    def stop(self) -> CommandResult:
        if not self._active: return CommandResult(False, 'AutoAccept is not running.')
        self._stop_event.set()
        if self._thread and self._thread.is_alive(): self._thread.join(timeout=2.0)
        self._active = False
        return CommandResult(True, 'AutoAccept stopped by user.')

    def _run(self, config: AutoAcceptConfig, templates: list[Path], on_match: Callable[[str], None], on_error: Callable[[str], None], on_finish: Callable[[str], None]) -> None:
        _ensure_pyautogui()
        deadline = time.monotonic() + config.timeout_seconds
        last_errors: dict[str, str] = {}
        try:
            while not self._stop_event.is_set():
                if time.monotonic() >= deadline:
                    on_finish('AutoAccept: время ожидания вышло.')
                    return
                for template_path in templates:
                    if self._stop_event.is_set():
                        on_finish('AutoAccept: остановлен пользователем.')
                        return
                    try:
                        location = pyautogui.locateCenterOnScreen(str(template_path), confidence=config.confidence)
                        if location:
                            pyautogui.click(location)
                            on_match(f'AutoAccept: найден шаблон <b>{template_path.name}</b>')
                            on_finish('AutoAccept: успешно завершен.')
                            return
                    except Exception as exc:
                        if type(exc).__name__ == 'ImageNotFoundException' or 'image not found' in str(exc).lower() or not str(exc).strip(): pass
                        else:
                            error_message = f'AutoAccept ошибка ({template_path.name}): {exc}'
                            if last_errors.get(template_path.name) != error_message:
                                on_error(error_message)
                                last_errors[template_path.name] = error_message
                time.sleep(config.interval_seconds)
        finally:
            self._active = False
            self._stop_event.clear()

def _normalize_key(key: str) -> str:
    normalized = key.strip().lower().replace('+', '')
    aliases = {'control': 'ctrl', 'windows': 'win', 'return': 'enter', 'escape': 'esc', 'del': 'delete'}
    return aliases.get(normalized, normalized)

def press_media_key(key_code: int) -> CommandResult:
    # Получаем аппаратный скан-код (обязательно для Spotify и Яндекс.Музыки)
    scan_code = ctypes.windll.user32.MapVirtualKeyA(key_code, 0)
    # 1 = KEYEVENTF_EXTENDEDKEY, 2 = KEYEVENTF_KEYUP
    ctypes.windll.user32.keybd_event(key_code, scan_code, 1, 0) # Нажатие
    ctypes.windll.user32.keybd_event(key_code, scan_code, 1 | 2, 0) # Отпускание
    return CommandResult(True, 'Media key pressed.')