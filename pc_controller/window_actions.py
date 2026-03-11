from __future__ import annotations

import ctypes
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

import psutil
import win32con
import win32gui
import win32process
import win32ui
from PIL import Image, ImageGrab

from .system_actions import CommandResult


@dataclass(slots=True)
class WindowInfo:
    hwnd: int
    title: str
    pid: int
    process_name: str
    minimized: bool
    rect: tuple[int, int, int, int]


def list_open_windows() -> list[WindowInfo]:
    items: list[WindowInfo] = []
    foreground = win32gui.GetForegroundWindow()

    def _enum_callback(hwnd: int, _extra) -> None:
        try:
            if not win32gui.IsWindow(hwnd):
                return
            title = _normalize_window_text(win32gui.GetWindowText(hwnd))
            if not title:
                return
            if not win32gui.IsWindowVisible(hwnd):
                return
            if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
                return
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if ex_style & win32con.WS_EX_TOOLWINDOW:
                return
            rect = win32gui.GetWindowRect(hwnd)
            if rect[2] - rect[0] < 80 or rect[3] - rect[1] < 40:
                return
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                process_name = psutil.Process(pid).name()
            except Exception:
                process_name = 'unknown'
            items.append(
                WindowInfo(
                    hwnd=hwnd,
                    title=title,
                    pid=pid,
                    process_name=process_name,
                    minimized=bool(win32gui.IsIconic(hwnd)),
                    rect=rect,
                )
            )
        except Exception:
            return

    win32gui.EnumWindows(_enum_callback, None)
    return sorted(
        items,
        key=lambda item: (
            0 if item.hwnd == foreground else 1,
            item.process_name.lower(),
            item.title.lower(),
        ),
    )


def get_window_info(hwnd: int) -> WindowInfo:
    target = int(hwnd)
    for item in list_open_windows():
        if item.hwnd == target:
            return item
    raise RuntimeError('Окно не найдено или уже закрыто.')


def activate_window(hwnd: int) -> CommandResult:
    target = int(hwnd)
    _ensure_window(target)
    if win32gui.IsIconic(target):
        win32gui.ShowWindow(target, win32con.SW_RESTORE)
    else:
        win32gui.ShowWindow(target, win32con.SW_SHOW)
    try:
        win32gui.SetForegroundWindow(target)
    except Exception:
        ctypes.windll.user32.SwitchToThisWindow(target, True)
    info = get_window_info(target)
    return CommandResult(True, f'Окно активировано: {info.title}')


def minimize_window(hwnd: int) -> CommandResult:
    target = int(hwnd)
    _ensure_window(target)
    win32gui.ShowWindow(target, win32con.SW_MINIMIZE)
    info = get_window_info(target)
    return CommandResult(True, f'Окно свернуто: {info.title}')


def close_window(hwnd: int) -> CommandResult:
    target = int(hwnd)
    _ensure_window(target)
    info = get_window_info(target)
    win32gui.PostMessage(target, win32con.WM_CLOSE, 0, 0)
    return CommandResult(True, f'Команда закрытия отправлена: {info.title}')


def capture_window_bytes(hwnd: int) -> tuple[bytes, str]:
    info = get_window_info(hwnd)
    width = max(1, info.rect[2] - info.rect[0])
    height = max(1, info.rect[3] - info.rect[1])

    image = _capture_with_printwindow(info.hwnd, width, height)
    if image is None:
        if info.minimized:
            raise RuntimeError('Окно свернуто. Сначала активируйте его или разверните.')
        image = ImageGrab.grab(bbox=info.rect, all_screens=True)

    output = BytesIO()
    image.save(output, format='PNG')
    now = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_name = ''.join(ch for ch in info.process_name if ch.isalnum() or ch in ('_', '-')).strip() or 'window'
    return output.getvalue(), f'{safe_name}_{info.hwnd}_{now}.png'


def _capture_with_printwindow(hwnd: int, width: int, height: int) -> Image.Image | None:
    hwnd_dc = None
    mfc_dc = None
    save_dc = None
    bitmap = None
    try:
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        if not hwnd_dc:
            return None
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bitmap)

        result = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
        if result != 1:
            result = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 0)
        if result != 1:
            return None

        bmp_info = bitmap.GetInfo()
        bmp_str = bitmap.GetBitmapBits(True)
        return Image.frombuffer(
            'RGB',
            (bmp_info['bmWidth'], bmp_info['bmHeight']),
            bmp_str,
            'raw',
            'BGRX',
            0,
            1,
        )
    finally:
        if bitmap is not None:
            win32gui.DeleteObject(bitmap.GetHandle())
        if save_dc is not None:
            save_dc.DeleteDC()
        if mfc_dc is not None:
            mfc_dc.DeleteDC()
        if hwnd_dc is not None:
            win32gui.ReleaseDC(hwnd, hwnd_dc)


def _ensure_window(hwnd: int) -> None:
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError('Окно не существует.')


def _normalize_window_text(value: str) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    return ''.join(ch for ch in text if unicodedata.category(ch) not in {'Cc', 'Cf'}).strip()
