from __future__ import annotations

import ctypes
import subprocess
import sys
import webbrowser
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(slots=True)
class CommandResult:
    ok: bool
    message: str
    code: str = ''


def parse_delay(raw_value: str | None, default_seconds: int = 30) -> int:
    if raw_value is None:
        return default_seconds
    value = int(raw_value)
    if value < 0 or value > 86_400:
        raise ValueError('Delay should be between 0 and 86400 seconds.')
    return value


def _ensure_windows() -> None:
    if sys.platform != 'win32':
        raise RuntimeError('This feature is only available on Windows.')


def schedule_shutdown(seconds: int = 30) -> CommandResult:
    _ensure_windows()
    subprocess.run(['shutdown', '/s', '/t', str(seconds)], check=True, capture_output=True, text=True)
    if seconds:
        return CommandResult(True, f'Shutdown scheduled in {seconds} seconds.')
    return CommandResult(True, 'Shutdown scheduled immediately.')


def schedule_reboot(seconds: int = 30) -> CommandResult:
    _ensure_windows()
    subprocess.run(['shutdown', '/r', '/t', str(seconds)], check=True, capture_output=True, text=True)
    if seconds:
        return CommandResult(True, f'Reboot scheduled in {seconds} seconds.')
    return CommandResult(True, 'Reboot scheduled immediately.')


def cancel_scheduled_power_action() -> CommandResult:
    _ensure_windows()
    try:
        subprocess.run(['shutdown', '/a'], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        # Windows returns 1116 when there is nothing to abort.
        if exc.returncode == 1116:
            return CommandResult(True, 'No scheduled shutdown/reboot was pending.', code='not_pending')
        raise
    return CommandResult(True, 'Scheduled power action cancelled.', code='cancelled')


def lock_workstation() -> CommandResult:
    _ensure_windows()
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    if user32.LockWorkStation() == 0:
        raise OSError(ctypes.get_last_error(), 'Unable to lock workstation.')
    return CommandResult(True, 'Workstation locked.')


def sleep_system() -> CommandResult:
    _ensure_windows()
    powrprof = ctypes.WinDLL('powrprof', use_last_error=True)
    ok = powrprof.SetSuspendState(False, True, False)
    if ok == 0:
        raise OSError(ctypes.get_last_error(), 'Unable to suspend system.')
    return CommandResult(True, 'Sleep mode requested.')


def hibernate_system() -> CommandResult:
    _ensure_windows()
    subprocess.run(['shutdown', '/h'], check=True, capture_output=True, text=True)
    return CommandResult(True, 'Hibernate requested.')


def open_url(url: str) -> CommandResult:
    cleaned = (url or '').strip()
    if not cleaned:
        raise ValueError('URL is empty.')

    parsed = urlparse(cleaned)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise ValueError('Only valid http/https URLs are allowed.')

    success = webbrowser.open(cleaned, new=0, autoraise=False)
    if not success:
        return CommandResult(False, 'URL was passed to OS but no browser acknowledged open request.')
    return CommandResult(True, f'URL opened: {cleaned}')


def run_cmd(command: str) -> CommandResult:
    _ensure_windows()
    try:
        # cp866 решает проблемы с кириллицей в Windows CMD
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60, encoding='cp866')
        out = result.stdout.strip()
        err = result.stderr.strip()
        res = out if out else err
        if not res:
            res = "Команда выполнена (нет вывода)."

        # Защита от огромных логов, чтобы не крашнуть отправку в ТГ
        if len(res) > 3500:
            res = res[:3500] + "\n...[ВЫВОД ОБРЕЗАН]..."

        return CommandResult(True, res)
    except subprocess.TimeoutExpired:
        return CommandResult(False, "Ошибка: Превышено время ожидания (60с).")
    except Exception as e:
        return CommandResult(False, f"Ошибка: {e}")
