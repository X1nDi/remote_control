from __future__ import annotations

import sys
from pathlib import Path

if sys.platform == 'win32':
    import winreg

RUN_KEY_PATH = r'Software\\Microsoft\\Windows\\CurrentVersion\\Run'
RUN_VALUE_NAME = 'PCController'


def _build_command(start_minimized: bool = True) -> str:
    args = ['--minimized'] if start_minimized else []
    arg_string = f" {' '.join(args)}" if args else ''
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"{arg_string}'
    script_path = Path(sys.argv[0]).resolve()
    return f'"{sys.executable}" "{script_path}"{arg_string}'


def current_command() -> str:
    if sys.platform != 'win32':
        return ''
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE_NAME)
        return str(value)
    except FileNotFoundError:
        return ''


def is_enabled() -> bool:
    if sys.platform != 'win32':
        return False
    return bool(current_command())


def enable(start_minimized: bool = True) -> None:
    if sys.platform != 'win32':
        raise RuntimeError('Autostart is implemented only for Windows.')
    command = _build_command(start_minimized=start_minimized)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, command)


def disable() -> None:
    if sys.platform != 'win32':
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, RUN_VALUE_NAME)
    except FileNotFoundError:
        pass
