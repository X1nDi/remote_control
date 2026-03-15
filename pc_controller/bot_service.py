from __future__ import annotations

import asyncio
import base64
import html
import json
import os
import re
import shutil
import tempfile
import threading
import time
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Callable

import psutil
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout, QApplication
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputFile
from telegram.constants import ParseMode
from telegram.error import NetworkError, RetryAfter, TimedOut
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import AppConfig
from .clipboard_history import ClipboardHistoryService
from .input_actions import (
    AUTOACCEPT_DIR,
    AutoAcceptConfig,
    AutoAcceptService,
    double_left_click,
    left_click,
    middle_click,
    move_mouse,
    press_combination,
    right_click,
    right_hold,
    speak_text,
    type_text,
    get_clipboard,
    set_clipboard,
    start_anti_afk,
    stop_anti_afk,
)
from .logging_setup import LOG_FILE
from .ocr_actions import extract_text_from_image_bytes, find_matching_lines
from .scheduler_store import ScheduledJob, SchedulerStore
from .system_actions import (
    cancel_scheduled_power_action,
    hibernate_system,
    lock_workstation,
    open_url,
    parse_delay,
    schedule_reboot,
    schedule_shutdown,
    sleep_system,
    run_cmd,
)
from .system_metrics import (
    capture_screenshot_bytes,
    capture_webcam_photo,
    capture_webcam_video,
    collect_snapshot,
    format_uptime,
    get_hardware_info,
    get_now_playing,
    record_audio,
    start_security,
    stop_security,
    is_security_active
)
from .window_actions import (
    activate_window,
    capture_window_bytes as capture_window_bytes_for_window,
    close_window,
    get_window_info,
    list_open_windows,
    minimize_window,
)

from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout, QApplication
from PySide6.QtCore import Qt


class OverlayWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("")
        self.label.setStyleSheet(
            "color: #00ffcc; font-size: 38px; font-weight: bold; background-color: rgba(0, 0, 0, 210); padding: 35px; border-radius: 20px; font-family: 'Segoe UI', Arial; border: 2px solid #3b82f6;")
        self.label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.label)
        self._user_hidden = False  # Флаг: скрыл ли юзер окно

    def show_text(self, text: str, position: str = "top-right", force_show: bool = True):
        if force_show:
            self._user_hidden = False  # Новое сообщение принудительно открывает окно

        if self._user_hidden:
            return  # Если юзер скрыл таймер, не показываем его каждую секунду

        html_text = text.replace('\n', '<br>')
        self.label.setTextFormat(Qt.RichText)
        self.label.setText(
            f"{html_text}<br><br><span style='font-size: 16px; color: #94a3b8;'>(Кликни по окну, чтобы закрыть)</span>")
        self.adjustSize()
        screen = QApplication.primaryScreen().geometry()
        if position == "center":
            self.move(screen.width() // 2 - self.width() // 2, screen.height() // 2 - self.height() // 2)
        else:
            self.move(screen.width() - self.width() - 40, 40)
        self.show()

    def mousePressEvent(self, event):
        self._user_hidden = True  # Запоминаем, что юзер кликнул
        self.hide()


MAX_DOWNLOAD_FILE_SIZE = 45 * 1024 * 1024
MAX_LIST_ITEMS = 120
WINDOWS_PAGE_SIZE = 8
CLIPBOARD_HISTORY_PAGE_SIZE = 6
ALLOWED_SCHEDULE_ACTIONS = {
    'screenshot',
    'logsave',
    'status',
    'hwinfo',
    'ocrscreen',
    'clipboard',
    'tasklist',
    'windows',
    'report',
    'music',
    'playpause',
    'nexttrack',
    'prevtrack',
    'cancelshutdown',
    'shutdown',
    'reboot',
    'hibernate',
    'lock',
    'sleep',
    'webcam',
    'webcamvid',
    'audio',
}

HELP_TEXT = """✨ <b>PC Controller — Список команд</b> ✨

📌 <b>Основное:</b>
🔸 /panel - Открыть красивую панель управления
🔸 /help - Показать все команды
🔸 /myid - Твой Telegram ID
🔸 /ping - Проверка связи
🔸 /uptime - Время работы системы

🎥 <b>Медиа:</b>
🔸 /webcam - Фото с веб-камеры
🔸 /webcamvid [sec] - Видео с веб-камеры
🔸 /audio [sec] - Запись микрофона

🔋 <b>Питание:</b>
🔸 /lock - Заблокировать ПК
🔸 /sleep - Спящий режим
🔸 /hibernate - Гибернация
🔸 /shutdown [sec] - Выключение
🔸 /reboot [sec] - Перезагрузка
🔸 /cancelshutdown - Отмена питания

🗂 <b>Файлы:</b>
🔸 /pwd, /ls, /cd, /mkdir, /rm, /rmr
🔸 /download, /upload, /cancelupload
🔸 /drives - Список всех дисков

⚙️ <b>Процессы и Система:</b>
🔸 /tasklist [filter] - Список
🔸 /kill_PID - Быстрое завершение (PID)
🔸 /cmd &lt;команда&gt; - Выполнить в CMD
🔸 /windows - Живые окна с действиями

⌨️ <b>Ввод и управление:</b>
🔸 /printtext &lt;text&gt;
🔸 /combination &lt;keys...&gt;
🔸 /movemouse &lt;x&gt; &lt;y&gt; [sec]
🔸 /message, /voice
🔸 /clip [text] - Буфер обмена
🔸 /cliphistory - История буфера
🔸 /antiafkon, /antiafkoff - Anti-AFK
🔸 /autoaccepton, /autoacceptoff

🌐 <b>Прочее:</b>
🔸 /ocr [query] - OCR текущего экрана
🔸 /schedulein &lt;delay&gt; &lt;actions...&gt; [--if-cpu-below N] [--if-cpu-above N] [--if-ram-below N] [--if-ram-above N] [--comment text]
🔸 /scheduleat &lt;HH:MM&gt; &lt;actions...&gt; [--note text]
🔸 /jobs, /jobcancel &lt;JOB_ID&gt;
🔸 /openurl &lt;link&gt;, /logtail [n]"""


class TelegramBotService(QObject):
    log_message = Signal(str)
    state_changed = Signal(bool)
    overlay_show_signal = Signal(str, str, bool) # Добавили 3 аргумент: force_show
    overlay_hide_signal = Signal()

    def __init__(
            self,
            config_provider: Callable[[], AppConfig],
            config_saver: Callable[[AppConfig], AppConfig] | None = None,
    ) -> None:
        super().__init__()
        self._config_provider = config_provider
        self._config_saver = config_saver

        self.overlay_show_signal.connect(self._do_show_overlay)
        self.overlay_hide_signal.connect(self._do_hide_overlay)
        self._overlay_widget = None

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._application: Application | None = None
        self._stop_event = threading.Event()
        self._running = False
        self._cwd_by_user: dict[int, Path] = {}
        self._pending_upload_by_user: dict[int, Path] = {}
        self._pending_action_by_user: dict[int, str] = {}
        self._process_filter_by_user: dict[int, str] = {}
        self._pending_rename_by_user: dict[int, Path] = {}
        self._aa_upload_msg_id_by_user: dict[int, int] = {}
        self._aa_list_msg_id_by_user: dict[int, int] = {}
        self._aa_menu_messages: dict[int, int] = {}
        self._menu_msg_id_by_user: dict[int, int] = {}
        self._media_menu_msg_id_by_user: dict[int, int] = {}
        self._live_stream_stop_events: dict[int, asyncio.Event] = {}
        self._live_stream_tasks: dict[int, asyncio.Task] = {}
        self._dir_items_by_user: dict[int, list[str]] = {}
        self._hibernate_task: asyncio.Task | None = None
        self._auto_accept_service = AutoAcceptService()
        self._clipboard_history = ClipboardHistoryService()
        self._scheduler_store = SchedulerStore()
        self._scheduler_task: asyncio.Task | None = None
        self._active_timers: dict[str, tuple[asyncio.Task, str]] = {}  # id -> (task, description)
        self._timer_targets: dict[str, float] = {}  # Хранит точное время завершения таймеров
        self._timer_counter = 0
        self._overlay_pause_until = 0.0
        self._startup_state_path = Path(tempfile.gettempdir()) / 'pc_controller_startup_state.json'
        self._last_notified_boot_time = self._load_last_notified_boot_time()
        self._runtime_lock = threading.Lock()
        self._runtime_stats: dict[str, float | str | None] = {
            'last_ping': None,
            'last_screenshot': None,
            'last_screenshot_detail': None,
            'last_webcam': None,
            'last_webcam_detail': None,
            'last_ocr': None,
            'last_ocr_detail': None,
            'last_successful_reconnect': None,
            'last_error_time': None,
            'last_error_message': None,
        }

    def _do_show_overlay(self, text: str, pos: str = "top-right", force: bool = True):
        if not self._overlay_widget:
            self._overlay_widget = OverlayWidget()
        self._overlay_widget.show_text(text, pos, force)

    def _do_hide_overlay(self):
        if self._overlay_widget:
            self._overlay_widget.hide()

    def _load_last_notified_boot_time(self) -> float | None:
        try:
            if not self._startup_state_path.exists():
                return None
            payload = json.loads(self._startup_state_path.read_text(encoding='utf-8'))
            value = payload.get('boot_time')
            return float(value) if value is not None else None
        except Exception:
            return None

    def _save_last_notified_boot_time(self, boot_time: float) -> None:
        try:
            payload = {'boot_time': float(boot_time), 'saved_at': time.time()}
            self._startup_state_path.write_text(json.dumps(payload), encoding='utf-8')
            self._last_notified_boot_time = float(boot_time)
        except Exception as exc:
            self.log_message.emit(f'Failed to persist startup state: {exc}')

    def _should_send_boot_notification(self, boot_time: float) -> bool:
        last_boot_time = self._last_notified_boot_time
        if last_boot_time is None:
            return True
        return abs(last_boot_time - boot_time) > 1.0

    @property
    def running(self) -> bool:
        return self._running

    def _update_runtime_metrics(self, **changes: float | str | None) -> None:
        with self._runtime_lock:
            self._runtime_stats.update(changes)

    def _record_runtime_activity(self, metric_name: str, detail: str | None = None) -> None:
        updates: dict[str, float | str | None] = {metric_name: time.time()}
        if detail is not None:
            updates[f'{metric_name}_detail'] = detail
        self._update_runtime_metrics(**updates)

    def _record_runtime_error(self, message: str) -> None:
        self._update_runtime_metrics(
            last_error_time=time.time(),
            last_error_message=str(message or '').strip()[:500] or None,
        )

    def get_runtime_snapshot(self) -> dict[str, float | str | bool | int | None]:
        with self._runtime_lock:
            snapshot = dict(self._runtime_stats)
        snapshot['running'] = self._running
        snapshot['scheduler_jobs'] = len(self._scheduler_store.list_jobs())
        return snapshot

    @staticmethod
    def _normalize_autoaccept_timeout(timeout: int) -> int:
        return max(10, min(int(timeout), 3600))

    def _current_autoaccept_timeout(self) -> int:
        config = self._config_provider()
        value = getattr(config, 'autoaccept_timeout_seconds', 600) or 600
        return self._normalize_autoaccept_timeout(value)

    @staticmethod
    def _format_autoaccept_timeout(timeout: int) -> str:
        timeout = int(timeout)
        if timeout % 3600 == 0:
            hours = timeout // 3600
            return f'{hours} ч'
        if timeout % 60 == 0:
            minutes = timeout // 60
            return f'{minutes} мин'
        return f'{timeout} сек'

    def _set_autoaccept_timeout(self, timeout: int) -> int:
        normalized = self._normalize_autoaccept_timeout(timeout)
        config = self._config_provider()
        config.autoaccept_timeout_seconds = normalized
        if self._config_saver is not None:
            try:
                self._config_saver(config)
            except Exception as exc:
                self.log_message.emit(f'Failed to save AutoAccept timeout: {exc}')
        return normalized

    def start(self) -> None:
        if self._running:
            self.log_message.emit('Bot is already running.')
            return

        config = self._config_provider()
        if not config.bot_token.strip():
            self._record_runtime_error('Bot token is empty. Set it in settings first.')
            self.log_message.emit('Bot token is empty. Set it in settings first.')
            return
        if not config.admins:
            self._record_runtime_error('Admins list is empty. Add at least one admin.')
            self.log_message.emit('Admins list is empty. Add at least one admin.')
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_in_thread, name='telegram-bot-thread', daemon=True)
        self._thread.start()

    def stop(self) -> None:
        thread_alive = self._thread is not None and self._thread.is_alive()
        if not self._running and not thread_alive:
            self.log_message.emit('Bot is already stopped.')
            return

        self._stop_event.set()
        if self._loop is not None:
            self._loop.call_soon_threadsafe(lambda: None)

    def shutdown(self) -> None:
        self.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=4)
        self._thread = None

    async def _ensure_admin(self, update: Update, required_perm: str | None = None) -> bool:
        user = update.effective_user
        user_id = getattr(user, 'id', None)
        if user_id is None:
            return False

        admin_str = str(user_id)
        admins = self._config_provider().admins
        if admin_str not in admins:
            self.log_message.emit(f'Access denied for user_id={user_id}')
            await self._safe_reply(update, '❌ Доступ запрещен. Ваш Telegram ID не найден в списке администраторов.',
                                   show_alert=True)
            return False

        if required_perm:
            perms = admins[admin_str]
            has_perm = getattr(perms, required_perm, False)
            if not has_perm:
                await self._safe_reply(update, '❌ У вас нет прав на эту категорию кнопок!',
                                       show_alert=True)
                return False

        return True

    async def _command_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return

        if context.args:
            arg = context.args[0]

            if arg.startswith('aa_'):
                encoded = arg[3:]
                try:
                    padding = '=' * (4 - len(encoded) % 4)
                    filename = base64.urlsafe_b64decode(encoded + padding).decode('utf-8')
                    target = self._autoaccept_template_dir() / filename
                    if target.exists() and target.is_file():
                        with target.open('rb') as f:
                            await update.effective_chat.send_photo(
                                photo=f,
                                caption=f'📸 <b>Шаблон:</b> <code>{html.escape(filename)}</code>',
                                parse_mode=ParseMode.HTML,
                                reply_markup=self._dismiss_markup()
                            )
                        return
                    else:
                        await self._safe_reply(update, "❌ Файл шаблона больше не существует.", dismissable=True,
                                               as_toast=True)
                        return
                except Exception as e:
                    await self._safe_reply(update, f"❌ Ошибка чтения файла: {e}", dismissable=True, as_toast=True)
                    return

            if arg.startswith('rmaa_'):
                encoded = arg[5:]
                try:
                    padding = '=' * (4 - len(encoded) % 4)
                    filename = base64.urlsafe_b64decode(encoded + padding).decode('utf-8')
                    target = self._autoaccept_template_dir() / filename
                    if target.exists() and target.is_file():
                        target.unlink()
                        await self._refresh_aa_listing_message(update.effective_user.id)
                        await self._safe_reply(update, f'🗑 Шаблон <b>{html.escape(filename)}</b> удален.',
                                               parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)
                    else:
                        await self._safe_reply(update, '❌ Шаблон не найден.', dismissable=True, as_toast=True)
                except Exception as exc:
                    await self._safe_reply(update, f'❌ Ошибка: {exc}', dismissable=True, as_toast=True)
                return

            if arg.startswith('kill_'):
                if not await self._ensure_admin(update, 'process'): return
                pid_str = arg[5:]
                try:
                    pid = int(pid_str)
                    message = await asyncio.to_thread(self._terminate_pid, pid)
                    await self._safe_reply(update, f'☠️ <b>{html.escape(message)}</b>', parse_mode=ParseMode.HTML,
                                           dismissable=True, as_toast=True)
                except Exception as exc:
                    await self._safe_reply(update, f'❌ Ошибка: {exc}', dismissable=True, as_toast=True)
                return

            if arg.startswith('win_'):
                if not await self._ensure_admin(update, 'process'): return
                try:
                    _, hwnd_str, page_str = arg.split('_', 2)
                    hwnd = int(hwnd_str)
                    page = int(page_str)
                    text = await asyncio.to_thread(self._window_detail_text, hwnd)
                    markup = self._window_detail_markup(hwnd, page)
                    msg_id = self._menu_msg_id_by_user.get(update.effective_user.id)
                    if msg_id:
                        try:
                            await context.bot.edit_message_text(
                                chat_id=update.effective_user.id,
                                message_id=msg_id,
                                text=text,
                                reply_markup=markup,
                                parse_mode=ParseMode.HTML,
                            )
                            return
                        except Exception:
                            pass
                    await self._safe_reply(update, text, parse_mode=ParseMode.HTML, reply_markup=markup)
                except Exception as exc:
                    await self._safe_reply(update, f'❌ Ошибка окна: <code>{html.escape(str(exc))}</code>',
                                           parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)
                return

            if arg.startswith('proc_'):
                if not await self._ensure_admin(update, 'process'): return
                try:
                    _, pid_str, page_str = arg.split('_', 2)
                    pid = int(pid_str)
                    page = int(page_str)
                    text = await asyncio.to_thread(self._process_detail_text, pid)
                    markup = self._process_detail_markup(pid, page)
                    msg_id = self._menu_msg_id_by_user.get(update.effective_user.id)
                    if msg_id:
                        try:
                            await context.bot.edit_message_text(
                                chat_id=update.effective_user.id,
                                message_id=msg_id,
                                text=text,
                                reply_markup=markup,
                                parse_mode=ParseMode.HTML,
                            )
                            return
                        except Exception:
                            pass
                    await self._safe_reply(update, text, parse_mode=ParseMode.HTML, reply_markup=markup)
                except Exception as exc:
                    await self._safe_reply(update, f'❌ Ошибка процесса: <code>{html.escape(str(exc))}</code>',
                                           parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)
                return

            if arg.startswith('sjdel_'):
                if not await self._ensure_admin(update): return
                user_id = update.effective_user.id
                job_id = arg[6:].strip()
                removed = self._scheduler_store.remove_job(job_id)
                bot_username = context.bot.username
                text, markup = self._build_scheduler_jobs_view(bot_username)
                msg_id = self._menu_msg_id_by_user.get(user_id)
                if msg_id:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=user_id,
                            message_id=msg_id,
                            text=text,
                            reply_markup=markup,
                            parse_mode=ParseMode.HTML,
                        )
                    except Exception:
                        pass
                await self._safe_reply(
                    update,
                    '🗑 <b>Задача удалена.</b>' if removed else '❌ <b>Задача не найдена.</b>',
                    parse_mode=ParseMode.HTML,
                    dismissable=True,
                    as_toast=True,
                )
                return

            if arg.startswith('rmf_'):
                if not await self._ensure_admin(update, 'files'): return
                user_id = update.effective_user.id
                idx = int(arg[4:])
                items = self._dir_items_by_user.get(user_id, [])
                if 0 <= idx < len(items):
                    filename = items[idx]
                    text = f'⚠️ <b>Подтверждение удаления:</b>\nВы действительно хотите удалить <code>{html.escape(filename)}</code>?'
                    markup = InlineKeyboardMarkup([
                        [InlineKeyboardButton('✅ Подтвердить', callback_data=f'panel:files:rm_yes:{idx}'),
                         InlineKeyboardButton('❌ Отмена', callback_data='panel:files:ls')]
                    ])
                    msg_id = self._menu_msg_id_by_user.get(user_id)
                    if msg_id:
                        try:
                            await context.bot.edit_message_text(chat_id=user_id, message_id=msg_id, text=text,
                                                                reply_markup=markup, parse_mode=ParseMode.HTML)
                        except Exception:
                            pass
                return

            if arg == 'cdup' or arg.startswith('cd_'):
                if not await self._ensure_admin(update, 'files'): return
                user_id = update.effective_user.id
                if arg == 'cdup':
                    target_name = '..'
                else:
                    idx = int(arg[3:])
                    items = self._dir_items_by_user.get(user_id, [])
                    target_name = items[idx] if 0 <= idx < len(items) else None

                if target_name:
                    try:
                        target = self._resolve_user_path(user_id, target_name)
                        if target.exists() and target.is_dir():
                            self._cwd_by_user[user_id] = target
                            msg_id = self._menu_msg_id_by_user.get(user_id)
                            if msg_id:
                                bot_username = context.bot.username
                                text, total_pages = await asyncio.to_thread(self._build_interactive_dir_page, user_id,
                                                                            target, bot_username, 0)
                                markup = self._files_list_markup(0, total_pages)
                                try:
                                    await context.bot.edit_message_text(chat_id=user_id, message_id=msg_id, text=text,
                                                                        reply_markup=markup, parse_mode=ParseMode.HTML)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                return

            if arg.startswith('dl_'):
                if not await self._ensure_admin(update, 'files'): return
                user_id = update.effective_user.id
                idx = int(arg[3:])
                items = self._dir_items_by_user.get(user_id, [])
                if 0 <= idx < len(items):
                    target_name = items[idx]
                    try:
                        target = self._resolve_user_path(user_id, target_name)
                        if target.exists() and target.is_file():
                            size = target.stat().st_size
                            if size > 45 * 1024 * 1024:
                                raise ValueError('Файл слишком большой (>45MB).')
                            temp_msg = await self._send_temporary_status(update, '⏳ <b>Отправка файла...</b>')
                            try:
                                with target.open('rb') as f:
                                    suf = target.suffix.lower()
                                    if suf in {'.png', '.jpg', '.jpeg', '.bmp'}:
                                        await update.effective_chat.send_photo(photo=f,
                                                                               caption=html.escape(target.name),
                                                                               reply_markup=self._dismiss_markup())
                                    elif suf in {'.mp4', '.avi', '.mov', '.mkv'}:
                                        await update.effective_chat.send_video(video=f,
                                                                               caption=html.escape(target.name),
                                                                               reply_markup=self._dismiss_markup())
                                    else:
                                        await update.effective_chat.send_document(document=f, filename=target.name,
                                                                                  caption=html.escape(target.name),
                                                                                  reply_markup=self._dismiss_markup())
                            finally:
                                await self._delete_message_safe(temp_msg)
                    except Exception as e:
                        await self._safe_reply(update, f'❌ Ошибка: {e}', dismissable=True)
                return

        await self._safe_reply(update, HELP_TEXT, reply_markup=self._panel_main_markup(), parse_mode=ParseMode.HTML)

    async def _command_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._command_start(update, context)

    async def _command_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        await self._safe_reply(update, self._panel_main_text(), reply_markup=self._panel_main_markup(),
                               parse_mode=ParseMode.HTML)

    async def _command_myid(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        user = update.effective_user
        if user is None:
            return
        await self._safe_reply(update, f'🪪 Твой Telegram ID: <code>{user.id}</code>', parse_mode=ParseMode.HTML,
                               dismissable=True)

    async def _command_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        self._record_runtime_activity('last_ping')
        await self._safe_reply(update, '🟢 <b>Pong!</b> Связь с ПК установлена.', parse_mode=ParseMode.HTML,
                               dismissable=True)

    async def _command_hw(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'process'): return

        query = update.callback_query
        temp_msg = None
        if query:
            await query.edit_message_text('⏳ <b>Опрашиваю датчики...</b>', parse_mode=ParseMode.HTML)
        else:
            temp_msg = await self._send_temporary_status(update, '⏳ <b>Опрашиваю датчики...</b>')

        try:
            info = await asyncio.to_thread(get_hardware_info)
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton('🔄 Обновить', callback_data='panel:proc:hw:refresh')],
                [InlineKeyboardButton('⬅️ Назад', callback_data='panel:process')]
            ])
            if query:
                await query.edit_message_text(info, parse_mode=ParseMode.HTML, reply_markup=markup)
            elif temp_msg:
                await temp_msg.edit_text(info, parse_mode=ParseMode.HTML, reply_markup=markup)
            else:
                await self._safe_reply(update, info, parse_mode=ParseMode.HTML, reply_markup=markup)
        except Exception as exc:
            if temp_msg: await self._delete_message_safe(temp_msg)
            await self._safe_reply(update, f'❌ Ошибка: {exc}', dismissable=True)

    async def _command_music(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'media'): return

        query = update.callback_query
        temp_msg = None
        if query:
            await query.edit_message_text('⏳ <b>Получаю инфо о треке...</b>', parse_mode=ParseMode.HTML)
        else:
            temp_msg = await self._send_temporary_status(update, '⏳ <b>Получаю инфо о треке...</b>')

        try:
            text, thumb_bytes = await get_now_playing()
            markup = InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад', callback_data='panel:media')]])

            if thumb_bytes:
                # В ТГ нельзя поменять текст на фото. Поэтому старое меню удаляем и кидаем фото с кнопкой Назад.
                if query:
                    await self._delete_message_safe(query.message)
                if temp_msg:
                    await self._delete_message_safe(temp_msg)

                stream = BytesIO(thumb_bytes)
                stream.name = 'cover.jpg'
                if update.effective_chat:
                    await update.effective_chat.send_photo(photo=stream, caption=text, parse_mode=ParseMode.HTML,
                                                           reply_markup=markup)
            else:
                # А вот если обложки нет, красиво изменяем текущее сообщение
                if query:
                    await self._edit_panel_message(query, text, markup)
                elif temp_msg:
                    await temp_msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
                else:
                    await self._safe_reply(update, text, parse_mode=ParseMode.HTML, reply_markup=markup)
        except Exception as exc:
            if temp_msg: await self._delete_message_safe(temp_msg)
            await self._safe_reply(update, f'❌ Ошибка: {exc}', dismissable=True)

    async def _command_media_action(self, update: Update, key_code: int, toast_text: str) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'media'): return
        try:
            from .input_actions import press_media_key
            await asyncio.to_thread(press_media_key, key_code)
            await self._safe_reply(update, f'🎵 <b>{toast_text}</b>', parse_mode=ParseMode.HTML, dismissable=True,
                                   as_toast=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка: {exc}', dismissable=True, as_toast=True)

    async def _command_playpause(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._command_media_action(update, 0xB3, 'Play / Pause')

    async def _command_nexttrack(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._command_media_action(update, 0xB0, 'Следующий трек')

    async def _command_prevtrack(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._command_media_action(update, 0xB1, 'Предыдущий трек')

    async def _command_vol(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'media'): return
        if not context.args: return
        direction = context.args[0].lower()
        try:
            from .input_actions import press_media_key
            if direction == 'up':
                for _ in range(5): await asyncio.to_thread(press_media_key, 0xAF)
                await self._safe_reply(update, '🔊 <b>Громкость +</b>', parse_mode=ParseMode.HTML, dismissable=True,
                                       as_toast=True)
            elif direction == 'down':
                for _ in range(5): await asyncio.to_thread(press_media_key, 0xAE)
                await self._safe_reply(update, '🔉 <b>Громкость -</b>', parse_mode=ParseMode.HTML, dismissable=True,
                                       as_toast=True)
            elif direction == 'mute':
                await asyncio.to_thread(press_media_key, 0xAD)
                await self._safe_reply(update, '🔇 <b>Звук переключен</b>', parse_mode=ParseMode.HTML, dismissable=True,
                                       as_toast=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка: {exc}', dismissable=True, as_toast=True)

    async def _command_mute(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        context.args = ['mute']
        await self._command_vol(update, context)

    async def _command_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return

        config = self._config_provider()
        snapshot = await asyncio.to_thread(
            collect_snapshot,
            len(config.admins),
            config.autostart,
            self._running,
        )

        text = (
            f"🌟 <b>Обзор системы</b> 🌟\n\n"
            f"💻 <b>Хост:</b> <code>{html.escape(snapshot.hostname)}</code> ({html.escape(snapshot.os_name)} {html.escape(snapshot.os_release)})\n"
            f"🌐 <b>Public IP:</b> <code>{html.escape(snapshot.ip_address)}</code>\n"
            f"🐍 <b>Python:</b> <code>{html.escape(snapshot.python_version)}</code>\n"
            f"🧠 <b>CPU:</b> <code>{snapshot.cpu_percent:.1f}%</code>\n"
            f"💽 <b>RAM:</b> <code>{snapshot.memory_percent:.1f}%</code>\n"
            f"💾 <b>Disk:</b> <code>{snapshot.disk_percent:.1f}%</code>\n"
            f"⏱ <b>Uptime:</b> <code>{format_uptime(snapshot.uptime_seconds)}</code>\n"
            f"👥 <b>Admins:</b> <code>{snapshot.admin_count}</code>\n"
            f"🚀 <b>Autostart:</b> {'🟢 ВКЛ' if snapshot.autostart_enabled else '🔴 ВЫКЛ'}\n"
            f"🤖 <b>Bot:</b> {'🟢 Работает' if snapshot.bot_running else '🔴 Остановлен'}"
        )

        await self._safe_reply(update, text, parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_uptime(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return

        config = self._config_provider()
        snapshot = await asyncio.to_thread(
            collect_snapshot,
            len(config.admins),
            config.autostart,
            self._running,
        )
        await self._safe_reply(update, f'⏱ <b>Uptime:</b> <code>{format_uptime(snapshot.uptime_seconds)}</code>',
                               parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_screenshot(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return

        query = update.callback_query
        temp_msg = None
        if query:
            await query.edit_message_text('⏳ <b>Делаю скриншот...</b>', parse_mode=ParseMode.HTML)
        else:
            temp_msg = await self._send_temporary_status(update, '⏳ <b>Делаю скриншот...</b>')

        try:
            screenshot_bytes, file_name = await asyncio.to_thread(capture_screenshot_bytes)

            if query:
                await query.edit_message_text('⏳ <b>Отправка...</b>', parse_mode=ParseMode.HTML)
            elif temp_msg:
                await temp_msg.edit_text('⏳ <b>Отправка...</b>', parse_mode=ParseMode.HTML)

            stream = BytesIO(screenshot_bytes)
            stream.name = file_name
            if update.effective_chat:
                await update.effective_chat.send_photo(
                    photo=stream,
                    caption='🖼 <b>Текущий скриншот рабочего стола</b>',
                    parse_mode=ParseMode.HTML,
                    reply_markup=self._dismiss_markup(),
                    read_timeout=60,
                    write_timeout=60
                )
            self._record_runtime_activity('last_screenshot', 'экран')
            self.log_message.emit(f'Screenshot sent to admin {update.effective_user.id}.')
        except Exception as exc:
            self._record_runtime_error(f'Failed to capture screenshot: {exc}')
            self.log_message.emit(f'Failed to capture screenshot: {exc}')
            await self._safe_reply(update, f'❌ Ошибка создания скриншота: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)
        finally:
            if query:
                await query.edit_message_text(self._panel_main_text(), reply_markup=self._panel_main_markup(),
                                              parse_mode=ParseMode.HTML)
            elif temp_msg:
                await self._delete_message_safe(temp_msg)

    async def _command_webcam(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'media'):
            return

        query = update.callback_query
        temp_msg = None
        if query:
            await query.edit_message_text('⏳ <b>Делаю фото с веб-камеры...</b>', parse_mode=ParseMode.HTML)
        else:
            temp_msg = await self._send_temporary_status(update, '⏳ <b>Делаю фото с веб-камеры...</b>')

        try:
            from .system_metrics import capture_webcam_photo
            photo_bytes, file_name = await asyncio.to_thread(capture_webcam_photo)

            if query:
                await query.edit_message_text('⏳ <b>Отправка...</b>', parse_mode=ParseMode.HTML)
            elif temp_msg:
                await temp_msg.edit_text('⏳ <b>Отправка...</b>', parse_mode=ParseMode.HTML)

            stream = BytesIO(photo_bytes)
            stream.name = file_name
            if update.effective_chat:
                await update.effective_chat.send_photo(
                    photo=stream,
                    caption='📸 <b>Фото с веб-камеры</b>',
                    parse_mode=ParseMode.HTML,
                    reply_markup=self._dismiss_markup(),
                    read_timeout=60,
                    write_timeout=60
                )
            self._record_runtime_activity('last_webcam', 'фото')
            self.log_message.emit(f'Webcam photo sent to admin {update.effective_user.id}.')
        except Exception as exc:
            self._record_runtime_error(f'Failed to capture webcam: {exc}')
            self.log_message.emit(f'Failed to capture webcam: {exc}')
            await self._safe_reply(update, f'❌ Ошибка камеры: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)
        finally:
            if query:
                await query.edit_message_text(self._panel_media_text(), reply_markup=self._panel_media_markup(),
                                              parse_mode=ParseMode.HTML)
            elif temp_msg:
                await self._delete_message_safe(temp_msg)

    async def _command_webcamvid(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'media'):
            return

        duration = 5
        if context.args:
            try:
                duration = max(1, min(60, int(context.args[0])))
            except ValueError:
                pass

        query = update.callback_query
        temp_msg = None
        if query:
            await query.edit_message_text(f'⏳ <b>Запись видео ({duration}с)...</b>', parse_mode=ParseMode.HTML)
        else:
            temp_msg = await self._send_temporary_status(update, f'⏳ <b>Запись видео ({duration}с)...</b>')

        try:
            from .system_metrics import capture_webcam_video
            video_bytes, file_name = await asyncio.to_thread(capture_webcam_video, duration)

            if query:
                await query.edit_message_text('⏳ <b>Отправка...</b>', parse_mode=ParseMode.HTML)
            elif temp_msg:
                await temp_msg.edit_text('⏳ <b>Отправка...</b>', parse_mode=ParseMode.HTML)

            stream = BytesIO(video_bytes)
            stream.name = file_name
            if update.effective_chat:
                await update.effective_chat.send_video(
                    video=stream,
                    caption=f'🎥 <b>Видео с веб-камеры ({duration}с)</b>',
                    parse_mode=ParseMode.HTML,
                    reply_markup=self._dismiss_markup(),
                    read_timeout=120,
                    write_timeout=120
                )
            self._record_runtime_activity('last_webcam', f'видео {duration}с')
            self.log_message.emit(f'Webcam video sent to admin {update.effective_user.id}.')
        except Exception as exc:
            self._record_runtime_error(f'Failed to capture webcam video: {exc}')
            self.log_message.emit(f'Failed to capture webcam video: {exc}')
            await self._safe_reply(update, f'❌ Ошибка камеры: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)
        finally:
            if query:
                await query.edit_message_text(self._panel_media_text(), reply_markup=self._panel_media_markup(),
                                              parse_mode=ParseMode.HTML)
            elif temp_msg:
                await self._delete_message_safe(temp_msg)

    async def _command_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'media'):
            return

        duration = 5
        if context.args:
            try:
                duration = max(1, min(60, int(context.args[0])))
            except ValueError:
                pass

        query = update.callback_query
        temp_msg = None
        if query:
            await query.edit_message_text(f'⏳ <b>Записываю аудио ({duration}с)...</b>', parse_mode=ParseMode.HTML)
        else:
            temp_msg = await self._send_temporary_status(update, f'⏳ <b>Записываю аудио ({duration}с)...</b>')

        try:
            from .system_metrics import record_audio
            audio_bytes, file_name = await asyncio.to_thread(record_audio, duration)

            if query:
                await query.edit_message_text('⏳ <b>Отправка...</b>', parse_mode=ParseMode.HTML)
            elif temp_msg:
                await temp_msg.edit_text('⏳ <b>Отправка...</b>', parse_mode=ParseMode.HTML)

            if update.effective_chat:
                await self._send_voice_note(
                    chat=update.effective_chat,
                    audio_bytes=audio_bytes,
                    file_name=file_name,
                    caption=f'🎙 <b>Аудиозапись ({duration}с)</b>',
                    reply_markup=self._dismiss_markup(),
                    read_timeout=120,
                    write_timeout=120,
                )
            self.log_message.emit(f'Audio sent to admin {update.effective_user.id}.')
        except Exception as exc:
            self.log_message.emit(f'Failed to record audio: {exc}')
            await self._safe_reply(update, f'❌ Ошибка записи аудио: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)
        finally:
            if query:
                await self._restore_media_menu(update)
            elif temp_msg:
                await self._delete_message_safe(temp_msg)

    async def _command_stream(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'media'): return

        user_id = update.effective_user.id
        active_task = self._live_stream_tasks.get(user_id)
        if active_task and not active_task.done():
            await self._safe_reply(
                update,
                'ℹ️ <b>LIVE-стрим уже запущен.</b>\nИспользуйте /stopstream или кнопку «Завершить».',
                parse_mode=ParseMode.HTML,
                dismissable=True,
                as_toast=bool(update.callback_query),
            )
            return

        task = asyncio.create_task(self._run_live_stream_session(update))
        self._live_stream_tasks[user_id] = task

        def _cleanup_live_stream(done_task: asyncio.Task, target_user_id: int = user_id) -> None:
            if self._live_stream_tasks.get(target_user_id) is done_task:
                self._live_stream_tasks.pop(target_user_id, None)
            try:
                done_task.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                self.log_message.emit(f'LIVE stream task failed for {target_user_id}: {exc}')

        task.add_done_callback(_cleanup_live_stream)

    async def _run_live_stream_session(self, update: Update) -> None:
        query = update.callback_query
        temp_msg = None
        if query:
            await query.edit_message_text('📡 <b>Запуск LIVE-трансляции...</b>', parse_mode=ParseMode.HTML)
        else:
            temp_msg = await self._send_temporary_status(update, '📡 <b>Запуск LIVE-трансляции...</b>')

        user_id = update.effective_user.id
        previous_stop_event = self._live_stream_stop_events.get(user_id)
        if previous_stop_event:
            previous_stop_event.set()

        stop_event = asyncio.Event()
        self._live_stream_stop_events[user_id] = stop_event
        first_frame = True
        last_msg = None

        try:
            while self._running and not stop_event.is_set():
                screenshot_bytes, file_name = await asyncio.to_thread(capture_screenshot_bytes)
                current_time = time.strftime('%H:%M:%S')
                caption_text = f"🔴 <b>LIVE: Трансляция экрана</b>\n<i>Обновлено: {current_time}</i>"

                if first_frame:
                    if query and query.message:
                        self._clear_media_menu_tracking(update.effective_user.id, query.message.message_id)
                        await self._delete_message_safe(query.message)
                    elif temp_msg:
                        await self._delete_message_safe(temp_msg)

                    if update.effective_chat:
                        last_msg = await self._send_live_stream_frame(
                            update.effective_chat,
                            screenshot_bytes=screenshot_bytes,
                            file_name=file_name,
                            caption_text=caption_text,
                        )
                    first_frame = False
                else:
                    if update.effective_chat:
                        replacement_msg = await self._send_live_stream_frame(
                            update.effective_chat,
                            screenshot_bytes=screenshot_bytes,
                            file_name=file_name,
                            caption_text=caption_text,
                        )
                        await self._delete_message_safe(last_msg)
                        last_msg = replacement_msg

                await asyncio.sleep(2.0)

        except Exception as exc:
            await self._safe_reply(update, f"❌ Ошибка трансляции: {exc}", dismissable=True)
        finally:
            tracked_stop_event = self._live_stream_stop_events.get(user_id)
            if tracked_stop_event is stop_event:
                self._live_stream_stop_events.pop(user_id, None)
            try:
                if last_msg and not first_frame:
                    await last_msg.edit_caption(
                        caption="⏹ <b>LIVE-Трансляция завершена.</b>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=self._dismiss_markup(),
                    )
            except:
                pass

            if query:
                await self._restore_media_menu(update)

    async def _command_stopstream(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'media'):
            return

        user_id = getattr(update.effective_user, 'id', None)
        if self._request_live_stream_stop(user_id):
            await self._safe_reply(update, '⏹ <b>LIVE-стрим останавливается...</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
        else:
            await self._safe_reply(update, 'ℹ️ <b>Активного LIVE-стрима нет.</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)

    async def _command_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'media'): return

        query = update.callback_query
        temp_msg = None
        if query:
            await query.edit_message_text('🕵️‍♂️ <b>Собираю отчет (Экран + Вебка + 5с Аудио)...</b>',
                                          parse_mode=ParseMode.HTML)
        else:
            temp_msg = await self._send_temporary_status(update,
                                                         '🕵️‍♂️ <b>Собираю отчет (Экран + Вебка + 5с Аудио)...</b>')

        try:
            from .system_metrics import capture_screenshot_bytes, capture_webcam_photo, record_audio
            screen_bytes, screen_name = await asyncio.to_thread(capture_screenshot_bytes)

            webcam_bytes, webcam_name, webcam_err = None, None, None
            try:
                webcam_bytes, webcam_name = await asyncio.to_thread(capture_webcam_photo)
            except Exception as e:
                webcam_err = str(e)  # Захватываем текст ошибки, чтобы показать тебе

            audio_bytes, audio_name, audio_err = None, None, None
            try:
                audio_bytes, audio_name = await asyncio.to_thread(record_audio, 5)
            except Exception as e:
                audio_err = str(e)  # Захватываем текст ошибки аудио

            if query:
                await query.edit_message_text('⏳ <b>Отправка...</b>', parse_mode=ParseMode.HTML)
            elif temp_msg:
                await temp_msg.edit_text('⏳ <b>Отправка...</b>', parse_mode=ParseMode.HTML)

            if update.effective_chat:
                # Отправка экрана
                s_stream = BytesIO(screen_bytes)
                s_stream.name = screen_name
                await update.effective_chat.send_photo(
                    photo=s_stream,
                    caption="🖼 <b>Экран</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=self._dismiss_markup(),
                )

                # Отправка вебки
                if webcam_bytes:
                    w_stream = BytesIO(webcam_bytes)
                    w_stream.name = webcam_name
                    await update.effective_chat.send_photo(
                        photo=w_stream,
                        caption="📸 <b>Веб-камера</b>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=self._dismiss_markup(),
                    )
                else:
                    await update.effective_chat.send_message(
                        f"❌ <b>Веб-камера:</b> Недоступна\n<i>Причина: {html.escape(webcam_err or 'unknown')}</i>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=self._dismiss_markup(),
                    )

                # Отправка микрофона
                if audio_bytes:
                    await self._send_voice_note(
                        chat=update.effective_chat,
                        audio_bytes=audio_bytes,
                        file_name=audio_name,
                        caption="🎙 <b>Окружение (5с)</b>",
                        reply_markup=self._dismiss_markup(),
                    )
                else:
                    await update.effective_chat.send_message(
                        f"❌ <b>Микрофон:</b> Недоступен\n<i>Причина: {html.escape(audio_err or 'unknown')}</i>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=self._dismiss_markup(),
                    )

        except Exception as exc:
            await self._safe_reply(update, f"❌ Ошибка отчета: {exc}", dismissable=True)
        finally:
            if query:
                await self._restore_media_menu(update)
            elif temp_msg:
                await self._delete_message_safe(temp_msg)

    async def _announce_power_action(self, update: Update, text: str) -> None:
        await self._safe_reply(
            update,
            f'⏳ <b>{html.escape(text)}</b>',
            parse_mode=ParseMode.HTML,
            reply_markup=self._power_reply_markup(),
        )
        # Let Telegram deliver the status before the PC changes power state.
        await asyncio.sleep(0.5)

    async def _command_lock(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'power'):
            return

        try:
            await self._announce_power_action(update, 'Блокирую компьютер...')
            result = await asyncio.to_thread(lock_workstation)
            self.log_message.emit(result.message)
        except Exception as exc:
            self.log_message.emit(f'Lock command failed: {exc}')
            await self._safe_reply(update, f'❌ Ошибка блокировки: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, reply_markup=self._power_reply_markup())

    async def _command_shutdown(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'power'):
            return

        try:
            delay = parse_delay(context.args[0] if context.args else None)
            if delay == 0:
                await self._announce_power_action(update, 'Выключаю компьютер...')
            result = await asyncio.to_thread(schedule_shutdown, delay)
            self.log_message.emit(result.message)
            if delay != 0:
                await self._safe_reply(update, f'⏻ <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                       reply_markup=self._power_reply_markup())
        except ValueError as exc:
            await self._safe_reply(update,
                                   f'Использование: <code>/shutdown [seconds]</code>\nОшибка: {html.escape(str(exc))}',
                                   parse_mode=ParseMode.HTML, reply_markup=self._power_reply_markup())
        except Exception as exc:
            self.log_message.emit(f'Shutdown command failed: {exc}')
            await self._safe_reply(update, f'❌ Ошибка выключения: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, reply_markup=self._power_reply_markup())

    async def _command_reboot(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'power'):
            return

        try:
            delay = parse_delay(context.args[0] if context.args else None)
            if delay == 0:
                await self._announce_power_action(update, 'Перезагружаю компьютер...')
            result = await asyncio.to_thread(schedule_reboot, delay)
            self.log_message.emit(result.message)
            if delay != 0:
                await self._safe_reply(update, f'🔄 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                       reply_markup=self._power_reply_markup())
        except ValueError as exc:
            await self._safe_reply(update,
                                   f'Использование: <code>/reboot [seconds]</code>\nОшибка: {html.escape(str(exc))}',
                                   parse_mode=ParseMode.HTML, reply_markup=self._power_reply_markup())
        except Exception as exc:
            self.log_message.emit(f'Reboot command failed: {exc}')
            await self._safe_reply(update, f'❌ Ошибка перезагрузки: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, reply_markup=self._power_reply_markup())

    async def _command_cancel_shutdown(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'power'):
            return

        try:
            cancelled_hibernate = False
            if self._hibernate_task and not self._hibernate_task.done():
                self._hibernate_task.cancel()
                self._hibernate_task = None
                cancelled_hibernate = True

            result = await asyncio.to_thread(cancel_scheduled_power_action)
            if result.code == 'not_pending':
                message = 'Таймер гибернации отменён.' if cancelled_hibernate else 'Нечего отменять: отложенное выключение или ребут не были запланированы.'
            elif cancelled_hibernate:
                message = 'Отложенное выключение/ребут и таймер гибернации отменены.'
            else:
                message = result.message

            self.log_message.emit(message)
            await self._safe_reply(update,
                                   f'✋ <b>{html.escape(message)}</b>',
                                   parse_mode=ParseMode.HTML, reply_markup=self._power_reply_markup())
        except Exception as exc:
            self.log_message.emit(f'Cancel shutdown command failed: {exc}')
            await self._safe_reply(update, f'❌ Ошибка отмены: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, reply_markup=self._power_reply_markup())

    async def _command_sleep(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'power'):
            return

        try:
            await self._announce_power_action(update, 'Перевожу компьютер в спящий режим...')
            result = await asyncio.to_thread(sleep_system)
            self.log_message.emit(result.message)
        except Exception as exc:
            self.log_message.emit(f'Sleep command failed: {exc}')
            await self._safe_reply(update, f'❌ Ошибка перехода в сон: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, reply_markup=self._power_reply_markup())

    async def _command_hibernate(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'power'):
            return

        try:
            await self._announce_power_action(update, 'Перевожу компьютер в гибернацию...')
            result = await asyncio.to_thread(hibernate_system)
            self.log_message.emit(result.message)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка гибернации: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, reply_markup=self._power_reply_markup())

    async def _command_open_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'open_url'):
            return

        if not context.args:
            await self._safe_reply(update, 'Использование: <code>/openurl &lt;https://example.com&gt;</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
            return

        url = context.args[0].strip()
        try:
            result = await asyncio.to_thread(open_url, url)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🌐 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
        except ValueError as exc:
            await self._safe_reply(update, f'Неверная ссылка: {html.escape(str(exc))}', dismissable=True)
        except Exception as exc:
            self.log_message.emit(f'Open URL command failed: {exc}')
            await self._safe_reply(update, f'❌ Ошибка открытия ссылки: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_log_tail(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return

        lines_count = 40
        if context.args:
            try:
                lines_count = max(1, min(200, int(context.args[0])))
            except ValueError:
                await self._safe_reply(update, 'Использование: <code>/logtail [1..200]</code>',
                                       parse_mode=ParseMode.HTML, dismissable=True)
                return

        text = await asyncio.to_thread(self._read_log_tail, lines_count)
        await self._safe_reply(update, f'🧾 <b>Логи:</b>\n<pre>{html.escape(text)}</pre>', parse_mode=ParseMode.HTML,
                               dismissable=True)

    async def _command_pwd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'files'): return
        user_id = update.effective_user.id
        allow_all = self._config_provider().allow_all_files
        root = self._base_root()
        cwd = self._cwd_by_user.get(user_id, root)
        if not allow_all and not self._is_allowed_path(cwd, root):
            cwd = root
            self._cwd_by_user[user_id] = root

        root_text = "ВСЕ ДИСКИ" if allow_all else html.escape(str(root))
        markup = InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад', callback_data='panel:files')]])
        await self._safe_reply(update,
                               f'📂 <b>Корень:</b> <code>{root_text}</code>\n📍 <b>Текущая папка:</b> <code>{html.escape(str(cwd))}</code>',
                               parse_mode=ParseMode.HTML, reply_markup=markup)

    async def _command_drives(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'files'): return
        if not self._config_provider().allow_all_files:
            await self._safe_reply(update, '❌ Отключено.', dismissable=True, as_toast=True)
            return

        drives = [p.mountpoint for p in psutil.disk_partitions() if p.fstype]
        text = "💾 <b>Доступные диски:</b>\n\n"
        for d in drives:
            text += f"• <code>{d}</code> (Используйте <code>/cd {d}</code>)\n"

        markup = InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад', callback_data='panel:files')]])
        await self._safe_reply(update, text, parse_mode=ParseMode.HTML, reply_markup=markup)

    async def _command_ls(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'files'): return
        user_id = update.effective_user.id
        raw_path = ' '.join(context.args).strip() if context.args else ''
        try:
            target = self._resolve_user_path(user_id, raw_path)
            bot_username = self._application.bot.username
            text, total_pages = await asyncio.to_thread(self._build_interactive_dir_page, user_id, target, bot_username,
                                                        0)
            markup = self._files_list_markup(0, total_pages)
            await self._safe_reply(update, text, parse_mode=ParseMode.HTML, reply_markup=markup)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /ls: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_cd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'files'):
            return

        if not context.args:
            await self._safe_reply(update, 'Использование: <code>/cd &lt;path&gt;</code>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
            return

        user_id = update.effective_user.id
        raw_path = ' '.join(context.args).strip()
        try:
            target = self._resolve_user_path(user_id, raw_path)
            if not target.exists() or not target.is_dir():
                raise ValueError('Directory does not exist.')
            self._cwd_by_user[user_id] = target
            await self._safe_reply(update,
                                   f'✅ <b>Текущая папка изменена на:</b>\n<code>{html.escape(str(target))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /cd: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_mkdir(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'files'):
            return

        if not context.args:
            await self._safe_reply(update, 'Использование: <code>/mkdir &lt;path&gt;</code>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
            return

        user_id = update.effective_user.id
        raw_path = ' '.join(context.args).strip()
        try:
            target = self._resolve_user_path(user_id, raw_path)
            target.mkdir(parents=True, exist_ok=False)
            await self._safe_reply(update, f'✅ <b>Папка создана:</b>\n<code>{html.escape(str(target))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
        except FileExistsError:
            await self._safe_reply(update, '❌ Папка уже существует.', dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /mkdir: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_rm(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'files'):
            return

        if not context.args:
            await self._safe_reply(update, 'Использование: <code>/rm &lt;path&gt;</code>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
            return

        user_id = update.effective_user.id
        raw_path = ' '.join(context.args).strip()
        try:
            target = self._resolve_user_path(user_id, raw_path)
            await asyncio.to_thread(self._remove_path, target, False)
            await self._safe_reply(update, f'🗑 <b>Удалено:</b>\n<code>{html.escape(str(target))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /rm: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_rmr(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'files'):
            return

        if not context.args:
            await self._safe_reply(update, 'Использование: <code>/rmr &lt;path&gt;</code>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
            return

        user_id = update.effective_user.id
        raw_path = ' '.join(context.args).strip()
        try:
            target = self._resolve_user_path(user_id, raw_path)
            await asyncio.to_thread(self._remove_path, target, True)
            await self._safe_reply(update, f'🗑 <b>Рекурсивно удалено:</b>\n<code>{html.escape(str(target))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /rmr: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_download(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'files'):
            return

        if not context.args:
            await self._safe_reply(update, 'Использование: <code>/download &lt;path&gt;</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
            return

        user_id = update.effective_user.id
        raw_path = ' '.join(context.args).strip()
        try:
            target = self._resolve_user_path(user_id, raw_path)
            if not target.exists() or not target.is_file():
                raise ValueError('File does not exist.')
            size = target.stat().st_size
            if size > MAX_DOWNLOAD_FILE_SIZE:
                raise ValueError(
                    f'File is too large ({self._format_bytes(size)}). Limit is {self._format_bytes(MAX_DOWNLOAD_FILE_SIZE)}.'
                )

            temp_msg = await self._send_temporary_status(update,
                                                         f'⏳ <b>Подготовка файла {html.escape(target.name)}...</b>')
            try:
                if update.effective_chat:
                    with target.open('rb') as file_stream:
                        await update.effective_chat.send_document(
                            document=file_stream,
                            filename=target.name,
                            caption=f'📥 <b>{html.escape(target.name)}</b> ({self._format_bytes(size)})',
                            parse_mode=ParseMode.HTML,
                            reply_markup=self._dismiss_markup(),
                            read_timeout=120,
                            write_timeout=120
                        )
                self.log_message.emit(f'File sent to admin {user_id}: {target}')
            finally:
                await self._delete_message_safe(temp_msg)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /download: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'files'): return
        user_id = update.effective_user.id
        raw_path = ' '.join(context.args).strip() if context.args else ''
        try:
            target_dir = self._resolve_user_path(user_id, raw_path)
            if not target_dir.exists() or not target_dir.is_dir():
                raise ValueError('Target directory does not exist.')
            self._pending_upload_by_user[user_id] = target_dir
            markup = InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад', callback_data='panel:files')]])
            await self._safe_reply(
                update,
                f'📤 <b>Режим загрузки включен для:</b>\n<code>{html.escape(str(target_dir))}</code>\n\nПрикрепите документ или медиа в чат.',
                parse_mode=ParseMode.HTML, reply_markup=markup
            )
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /upload: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_cancel_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return

        user_id = update.effective_user.id
        pending_template = self._pending_rename_by_user.pop(user_id, None)
        if pending_template and pending_template.exists():
            try:
                pending_template.unlink()
            except Exception:
                pass
        if pending_template is not None and user_id not in self._pending_upload_by_user:
            aa_msg_id = self._aa_upload_msg_id_by_user.pop(user_id, None)
            if aa_msg_id and self._application:
                try:
                    await context.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=aa_msg_id,
                        text=self._autoaccept_menu_text(),
                        reply_markup=self._autoaccept_menu_markup(),
                        parse_mode=ParseMode.HTML,
                    )
                    self._aa_menu_messages[user_id] = aa_msg_id
                    return
                except Exception:
                    pass
            await self._safe_reply(update, '✋ <b>Загрузка шаблона отменена.</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
            return
        if user_id in self._pending_upload_by_user:
            self._pending_upload_by_user.pop(user_id, None)
            aa_msg_id = self._aa_upload_msg_id_by_user.pop(user_id, None)
            if aa_msg_id and self._application:
                try:
                    await context.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=aa_msg_id,
                        text=self._autoaccept_menu_text(),
                        reply_markup=self._autoaccept_menu_markup(),
                        parse_mode=ParseMode.HTML,
                    )
                    self._aa_menu_messages[user_id] = aa_msg_id
                    return
                except Exception:
                    pass
            await self._safe_reply(update, '✋ <b>Режим загрузки файла отменен.</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
            return
        await self._safe_reply(update, 'ℹ️ Режим загрузки файла сейчас не активен.', dismissable=True)

    async def _handle_document_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'files'):
            return

        user_id = update.effective_user.id
        target_dir = self._pending_upload_by_user.get(user_id)
        if target_dir is None:
            return

        message = update.effective_message
        if message is None:
            return

        file_obj = None
        file_name = "uploaded_file.bin"

        if message.document:
            file_obj = await message.document.get_file()
            file_name = self._sanitize_upload_name(message.document.file_name)
        elif message.photo:
            file_obj = await message.photo[-1].get_file()
            file_name = f"photo_{int(time.time())}.jpg"

        if not file_obj:
            return

        try:
            root = self._base_root()
            aa_dir = self._autoaccept_template_dir()

            is_aa_dir = False
            try:
                target_dir.relative_to(aa_dir)
                is_aa_dir = True
            except ValueError:
                pass

            if not is_aa_dir and not self._config_provider().allow_all_files and not self._is_allowed_path(target_dir,
                                                                                                           root):
                raise ValueError('Upload target is outside allowed root.')

            target_dir.mkdir(parents=True, exist_ok=True)
            destination = self._build_unique_destination(target_dir / file_name)

            await file_obj.download_to_drive(custom_path=str(destination))
            size = destination.stat().st_size
            self.log_message.emit(f'File uploaded by admin {user_id}: {destination}')

            if is_aa_dir:
                self._pending_rename_by_user[user_id] = destination
                upload_msg_id = self._aa_upload_msg_id_by_user.get(user_id)
                if upload_msg_id:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=user_id,
                            message_id=upload_msg_id,
                            text=self._aa_upload_text(awaiting_name=True),
                            reply_markup=self._aa_upload_markup(),
                            parse_mode=ParseMode.HTML,
                        )
                    except Exception:
                        await self._safe_reply(update, self._aa_upload_text(awaiting_name=True),
                                               parse_mode=ParseMode.HTML, reply_markup=self._aa_upload_markup())
                else:
                    await self._safe_reply(update, self._aa_upload_text(awaiting_name=True),
                                           parse_mode=ParseMode.HTML, reply_markup=self._aa_upload_markup())
                return
            else:
                await self._safe_reply(update,
                                       f'✅ <b>Успешно загружено:</b>\n📁 <code>{html.escape(destination.name)}</code>\n⚖️ Размер: {self._format_bytes(size)}',
                                       parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка загрузки: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
        finally:
            self._pending_upload_by_user.pop(user_id, None)

    async def _handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return

        user_id = update.effective_user.id
        message = update.effective_message
        if not message or not message.text:
            return
        text = message.text

        if user_id in self._pending_rename_by_user:
            old_path = self._pending_rename_by_user.pop(user_id)
            new_name = text.strip()
            if not new_name.lower().endswith(('.jpg', '.png', '.jpeg', '.bmp')):
                new_name += old_path.suffix

            new_name = "".join(c for c in new_name if c.isalnum() or c in (' ', '.', '_', '-')).strip()
            if not new_name:
                new_name = old_path.name

            new_path = old_path.with_name(new_name)
            new_path = self._build_unique_destination(new_path)
            old_path.rename(new_path)

            upload_msg_id = self._aa_upload_msg_id_by_user.pop(user_id, None)
            success_text = f'✅ <b>Шаблон сохранен как {html.escape(new_path.name)}</b>'
            if upload_msg_id and self._application:
                try:
                    bot_username = self._application.bot.username
                    listing_text = await asyncio.to_thread(
                        self._build_aa_listing_text,
                        self._autoaccept_template_dir(),
                        bot_username,
                    )
                    self._aa_list_msg_id_by_user[user_id] = upload_msg_id
                    await context.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=upload_msg_id,
                        text=f'{success_text}\n\n{listing_text}',
                        reply_markup=self._aa_listing_markup(),
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    await self._safe_reply(update, success_text, parse_mode=ParseMode.HTML, dismissable=True)
            else:
                await self._safe_reply(update, success_text, parse_mode=ParseMode.HTML, dismissable=True)
            return


        action = self._pending_action_by_user.pop(user_id, None)
        if not action:
            return

        if action == 'aa_timeout':
            msg_id = self._menu_msg_id_by_user.get(user_id)
            try:
                timeout = self._set_autoaccept_timeout(self._parse_duration_token(text.strip()))
                success_text = (
                    f'✅ <b>Таймаут AutoAccept обновлен:</b> '
                    f'<code>{html.escape(self._format_autoaccept_timeout(timeout))}</code>\n\n'
                    f'{self._autoaccept_menu_text()}'
                )
                if msg_id:
                    await context.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=msg_id,
                        text=success_text,
                        reply_markup=self._autoaccept_menu_markup(),
                        parse_mode=ParseMode.HTML,
                    )
                    self._aa_menu_messages[user_id] = msg_id
                else:
                    await self._safe_reply(update, success_text, parse_mode=ParseMode.HTML,
                                           reply_markup=self._autoaccept_menu_markup())
            except Exception as exc:
                self._pending_action_by_user[user_id] = 'aa_timeout'
                error_text = (
                    f'❌ <b>Не удалось распознать время:</b> <code>{html.escape(str(exc))}</code>\n\n'
                    f'{self._aa_timeout_text()}'
                )
                if msg_id:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=user_id,
                            message_id=msg_id,
                            text=error_text,
                            reply_markup=self._aa_timeout_markup(),
                            parse_mode=ParseMode.HTML,
                        )
                    except Exception:
                        await self._safe_reply(update, error_text, parse_mode=ParseMode.HTML,
                                               reply_markup=self._aa_timeout_markup())
                else:
                    await self._safe_reply(update, error_text, parse_mode=ParseMode.HTML,
                                           reply_markup=self._aa_timeout_markup())
            return

        if action == 'ocr_query':
            if not await self._ensure_admin(update):
                return
            await self._run_screen_ocr(update, query=text.strip(), reply_markup=self._ocr_reply_markup())
            return

        if action == 'schedule_create':
            if not await self._ensure_admin(update):
                return
            user_id = update.effective_user.id
            msg_id = self._menu_msg_id_by_user.get(user_id)
            raw_text = text.strip()
            lowered = raw_text.lower()
            try:
                if lowered.startswith('/schedulein '):
                    tokens = raw_text.split()[1:]
                    mode = 'in'
                elif lowered.startswith('/scheduleat '):
                    tokens = raw_text.split()[1:]
                    mode = 'at'
                elif lowered.startswith('in '):
                    tokens = raw_text.split()[1:]
                    mode = 'in'
                elif lowered.startswith('at '):
                    tokens = raw_text.split()[1:]
                    mode = 'at'
                else:
                    raise ValueError('Начните строку с <code>in</code> или <code>at</code>.')

                if len(tokens) < 2:
                    raise ValueError('Нужно указать время/задержку и хотя бы одно действие.')

                job = await self._create_scheduled_job_from_mode(update, mode, tokens[0], tokens[1:])
                if msg_id:
                    await context.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=msg_id,
                        text=f'✅ <b>Задача создана</b>\n{self._format_scheduled_job(job)}\n\n{self._scheduler_panel_text()}',
                        reply_markup=self._scheduler_panel_markup(),
                        parse_mode=ParseMode.HTML,
                    )
                else:
                    await self._safe_reply(update, f'✅ <b>Задача создана</b>\n{self._format_scheduled_job(job)}',
                                           parse_mode=ParseMode.HTML, dismissable=True)
            except PermissionError:
                return
            except Exception as exc:
                self._pending_action_by_user[user_id] = 'schedule_create'
                error_text = (
                    f'❌ <b>Ошибка создания задачи:</b> <code>{html.escape(str(exc))}</code>\n\n'
                    f'{self._scheduler_add_text()}'
                )
                if msg_id:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=user_id,
                            message_id=msg_id,
                            text=error_text,
                            reply_markup=self._scheduler_add_markup(),
                            parse_mode=ParseMode.HTML,
                        )
                    except Exception:
                        await self._safe_reply(update, error_text, parse_mode=ParseMode.HTML,
                                               reply_markup=self._scheduler_add_markup())
                else:
                    await self._safe_reply(update, error_text, parse_mode=ParseMode.HTML,
                                           reply_markup=self._scheduler_add_markup())
            return

        if action in ('type', 'printtext', 'combination', 'message', 'voice', 'cmd', 'clip_set', 'custom_remind'):
            if not await self._ensure_admin(update, 'input'): return
            user_id = update.effective_user.id
            msg_id = self._menu_msg_id_by_user.get(user_id)

            if msg_id:
                try:
                    await context.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=msg_id,
                        text='⏳ <b>Выполняю...</b>',
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass

            try:
                if action in ('type', 'printtext'):
                    result = await asyncio.to_thread(type_text, text)
                elif action == 'combination':
                    keys = self._parse_combination_args(text.split())
                    if not keys:
                        raise ValueError('Клавиши не распознаны.')
                    result = await asyncio.to_thread(press_combination, keys)
                elif action == 'message':
                    self.overlay_show_signal.emit(f"📩 Сообщение:\n{text}", "center", True)
                    from .system_actions import CommandResult
                    result = CommandResult(True, "Сообщение выведено по центру экрана.")
                elif action == 'custom_remind':
                    import re
                    from datetime import datetime, timedelta
                    match = re.match(r'^(\d{1,2}):(\d{2})\s+(.+)$', text.strip())
                    if not match:
                        if msg_id:
                            # Изменили callback_data на новую кнопку
                            markup = InlineKeyboardMarkup(
                                [[InlineKeyboardButton('❌ Отменить', callback_data='panel:rem:cancel_custom')]])
                            await context.bot.edit_message_text(
                                chat_id=user_id, message_id=msg_id,
                                text='❌ <b>Неверный формат!</b>\nНужно: <code>HH:MM Текст</code>\n<i>Пример: 15:30 Пойти есть</i>',
                                reply_markup=markup, parse_mode=ParseMode.HTML
                            )
                            msg_id = None  # Предотвращаем сброс меню в finally
                            self._pending_action_by_user[user_id] = 'custom_remind'  # Оставляем в режиме ожидания
                        from .system_actions import CommandResult
                        result = CommandResult(False, "Неверный формат напоминания.")
                    else:
                        target_h, target_m = int(match.group(1)), int(match.group(2))
                        remind_text = match.group(3)
                        now = datetime.now()
                        target_time = now.replace(hour=target_h, minute=target_m, second=0, microsecond=0)
                        if target_time < now:
                            target_time += timedelta(days=1)
                        delay = (target_time - now).total_seconds()

                        self._timer_counter = getattr(self, '_timer_counter', 0) + 1
                        tid = f"t_{self._timer_counter}"
                        desc = f"⏰ {target_time.strftime('%H:%M')} - {remind_text[:15]}..."
                        task = asyncio.create_task(
                            self._start_overlay_timer(int(delay), f"Напоминание: {remind_text}", tid))
                        self._active_timers[tid] = (task, desc)
                        task.add_done_callback(lambda t, timer_id=tid: self._active_timers.pop(timer_id, None))

                        if msg_id:
                            markup = InlineKeyboardMarkup(
                                [[InlineKeyboardButton('⬅️ Назад', callback_data='panel:input:reminders')]])
                            await context.bot.edit_message_text(
                                chat_id=user_id, message_id=msg_id,
                                text=f"✅ <b>Напоминание установлено на {target_time.strftime('%H:%M')}</b>\n\n<i>{html.escape(remind_text)}</i>",
                                reply_markup=markup, parse_mode=ParseMode.HTML
                            )
                            msg_id = None  # Предотвращаем перерисовку старого меню

                        from .system_actions import CommandResult
                        result = CommandResult(True, f"Напоминание установлено на {target_time.strftime('%H:%M')}")
                elif action == 'voice':
                    result = await asyncio.to_thread(speak_text, text)
                elif action == 'clip_set':
                    result = await asyncio.to_thread(set_clipboard, text)
                    if result.ok:
                        self._clipboard_history.add_text(text)
                elif action == 'cmd':
                    result = await asyncio.to_thread(run_cmd, text)
                    self.log_message.emit(f"CMD run: {text}")
                    await self._safe_reply(update,
                                           f"💻 <b>Терминал:</b> <code>{html.escape(text)}</code>\n\n<pre>{html.escape(result.message)}</pre>",
                                           parse_mode=ParseMode.HTML, dismissable=True)

                if action != 'cmd':
                    self.log_message.emit(result.message)
            except Exception as exc:
                await self._safe_reply(update, f'❌ Ошибка: <code>{html.escape(str(exc))}</code>',
                                       parse_mode=ParseMode.HTML, dismissable=True)
            finally:
                if action == 'clip_set' and msg_id:
                    try:
                        self._pending_action_by_user[user_id] = 'clip_set'
                        panel_text, panel_markup = await self._build_clipboard_panel_view(
                            status_text=result.message if 'result' in locals() else 'Ошибка буфера обмена.',
                            is_error=not result.ok if 'result' in locals() else True,
                        )
                        await context.bot.edit_message_text(
                            chat_id=user_id,
                            message_id=msg_id,
                            text=panel_text,
                            reply_markup=panel_markup,
                            parse_mode=ParseMode.HTML,
                        )
                        msg_id = None
                    except Exception:
                        pass
                if msg_id:
                    try:
                        markup = self._panel_process_markup() if action == 'cmd' else self._panel_input_markup()
                        text_menu = self._panel_process_text() if action == 'cmd' else self._panel_input_text()
                        await context.bot.edit_message_text(
                            chat_id=user_id,
                            message_id=msg_id,
                            text=text_menu,
                            reply_markup=markup,
                            parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        pass

        elif action == 'proc_search':
            if not await self._ensure_admin(update, 'process'): return
            user_id = update.effective_user.id
            filter_text = text.strip().lower()
            self._process_filter_by_user[user_id] = filter_text
            bot_username = self._application.bot.username
            msg_id = self._menu_msg_id_by_user.get(user_id)
            try:
                msg_text, total_pages = await asyncio.to_thread(self._build_tasklist_page, filter_text, bot_username, 0)
                markup = self._tasklist_markup(0, total_pages)
                if msg_id:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=user_id,
                            message_id=msg_id,
                            text=msg_text,
                            reply_markup=markup,
                            parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        await self._safe_reply(update, msg_text, reply_markup=markup, parse_mode=ParseMode.HTML,
                                               dismissable=True)
                else:
                    await self._safe_reply(update, msg_text, reply_markup=markup, parse_mode=ParseMode.HTML,
                                           dismissable=True)
            except Exception as exc:
                await self._safe_reply(update, f'❌ Ошибка: {exc}', dismissable=True)

    async def _command_tasklist(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'process'):
            return

        user_id = update.effective_user.id
        filter_text = ' '.join(context.args).strip().lower() if context.args else ''
        self._process_filter_by_user[user_id] = filter_text
        bot_username = self._application.bot.username

        text, total_pages = await asyncio.to_thread(self._build_tasklist_page, filter_text, bot_username, 0)
        markup = self._tasklist_markup(0, total_pages)
        await self._safe_reply(update, text, reply_markup=markup, parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_taskkill(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'process'):
            return

        if not context.args:
            await self._safe_reply(update, 'Использование: <code>/taskkill <pid></code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
            return

        try:
            pid = int(context.args[0])
            message = await asyncio.to_thread(self._terminate_pid, pid)
            await self._safe_reply(update, f'☠️ <b>{html.escape(message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
        except ValueError:
            await self._safe_reply(update, '❌ PID должен быть целым числом.', dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /taskkill: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'process'): return
        command = ' '.join(context.args).strip()
        if not command:
            await self._safe_reply(update, 'Использование: <code>/cmd <команда></code>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
            return

        temp_msg = await self._send_temporary_status(update, '⏳ <b>Выполняю команду...</b>')
        try:
            result = await asyncio.to_thread(run_cmd, command)
            self.log_message.emit(f"CMD run: {command}")
            text = f"💻 <b>Терминал:</b> <code>{html.escape(command)}</code>\n\n<pre>{html.escape(result.message)}</pre>"
            if temp_msg:
                await temp_msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=self._dismiss_markup())
            else:
                await self._safe_reply(update, text, parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            if temp_msg: await self._delete_message_safe(temp_msg)
            await self._safe_reply(update, f'❌ Ошибка: {exc}', dismissable=True)

    async def _command_kill_regex(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'process'):
            return

        text = update.effective_message.text
        pid_str = text.split('_')[1]
        try:
            pid = int(pid_str)
            message = await asyncio.to_thread(self._terminate_pid, pid)
            await self._safe_reply(update, f'☠️ <b>{html.escape(message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True, as_toast=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка: {exc}', dismissable=True, as_toast=True)

    async def _command_rmaa_regex(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'input'):
            return

        text = update.effective_message.text
        encoded = text.split('_', 1)[1]
        try:
            padding = '=' * (4 - len(encoded) % 4)
            filename = base64.urlsafe_b64decode(encoded + padding).decode('utf-8')
            target = self._autoaccept_template_dir() / filename
            if target.exists() and target.is_file():
                target.unlink()
                await self._refresh_aa_listing_message(update.effective_user.id)
                await self._safe_reply(update, f'🗑 Шаблон <b>{html.escape(filename)}</b> удален.',
                                       parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)
            else:
                await self._safe_reply(update, '❌ Шаблон не найден.', dismissable=True, as_toast=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка: {exc}', dismissable=True, as_toast=True)

    async def _command_printtext(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update):
            return

        text = ' '.join(context.args).strip()
        if not text:
            await self._safe_reply(update, 'Использование: <code>/printtext <text></code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
            return

        try:
            result = await asyncio.to_thread(type_text, text)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'⌨️ <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /printtext: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_combination(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update):
            return

        keys = self._parse_combination_args(context.args)
        if not keys:
            await self._safe_reply(update,
                                   'Использование: <code>/combination <keys...></code>\nПример: <code>/combination win d</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
            return

        try:
            result = await asyncio.to_thread(press_combination, keys)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🪟 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /combination: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update):
            return

        text = ' '.join(context.args).strip()
        if not text:
            await self._safe_reply(update, 'Использование: <code>/message <text></code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
            return

        try:
            # Выводим оверлей прямо по центру экрана
            self.overlay_show_signal.emit(f"📩 Сообщение:\n{text}", "center", True)

            success_msg = "Сообщение выведено по центру экрана."
            self.log_message.emit(success_msg)
            await self._safe_reply(update, f'💬 <b>{success_msg}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /message: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_remind(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update): return

        if len(context.args) < 2:
            await self._safe_reply(update,
                                   'Использование: <code>/remind HH:MM Текст</code>\nПример: <code>/remind 15:30 Выключить духовку</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
            return

        time_str = context.args[0]
        text = ' '.join(context.args[1:])

        import re
        from datetime import datetime, timedelta
        match = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
        if not match:
            await self._safe_reply(update, '❌ Неверный формат времени. Используйте HH:MM (например, 15:30).',
                                   dismissable=True)
            return

        target_h, target_m = int(match.group(1)), int(match.group(2))
        now = datetime.now()
        target_time = now.replace(hour=target_h, minute=target_m, second=0, microsecond=0)

        # Если указанное время уже прошло сегодня, ставим на завтра
        if target_time < now:
            target_time += timedelta(days=1)

        delay = (target_time - now).total_seconds()

        self._timer_counter = getattr(self, '_timer_counter', 0) + 1
        tid = f"t_{self._timer_counter}"
        desc = f"⏰ {target_time.strftime('%H:%M')} - {text[:15]}..."
        task = asyncio.create_task(self._start_overlay_timer(int(delay), f"Напоминание: {text}", tid))
        self._active_timers[tid] = (task, desc)
        task.add_done_callback(lambda t, timer_id=tid: self._active_timers.pop(timer_id, None))

        await self._safe_reply(update,
                               f'✅ Напоминание <b>"{html.escape(text)}"</b> установлено на <b>{target_time.strftime("%H:%M")}</b>.',
                               parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)

    async def _command_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update):
            return

        text = ' '.join(context.args).strip()
        if not text:
            await self._safe_reply(update, 'Использование: <code>/voice <text></code>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
            return

        try:
            result = await asyncio.to_thread(speak_text, text)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🗣 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /voice: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_clip(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'input'): return
        text = ' '.join(context.args).strip() if context.args else ''
        try:
            if text:
                result = await asyncio.to_thread(set_clipboard, text)
                if result.ok:
                    self._clipboard_history.add_text(text)
                await self._safe_reply(update, f'📋 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)
            else:
                result = await asyncio.to_thread(get_clipboard)
                if result.ok:
                    markup = self._clipboard_reply_markup()
                    msg_text = f'📋 <b>Текст из буфера обмена ПК:</b>\n\n<code>{html.escape(result.message)}</code>'
                    if update.callback_query:
                        await self._edit_panel_message(update.callback_query, msg_text, markup)
                    else:
                        await self._safe_reply(update, msg_text, parse_mode=ParseMode.HTML, reply_markup=markup)
                else:
                    await self._safe_reply(update, f'❌ {html.escape(result.message)}', dismissable=True, as_toast=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка: {exc}', dismissable=True)

    async def _command_antiafk_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'input'): return
        try:
            result = await asyncio.to_thread(start_anti_afk)
            await self._safe_reply(update, f'🎮 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True, as_toast=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка: {exc}', dismissable=True)

    async def _command_antiafk_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'input'): return
        try:
            result = await asyncio.to_thread(stop_anti_afk)
            await self._safe_reply(update, f'🛑 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True, as_toast=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка: {exc}', dismissable=True)

    async def _command_leftclick(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update):
            return
        try:
            result = await asyncio.to_thread(left_click)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🖱 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка клика: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_rightclick(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update):
            return
        try:
            result = await asyncio.to_thread(right_click)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🖱 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка клика: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_leftdoubleclick(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update):
            return
        try:
            result = await asyncio.to_thread(double_left_click)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🖱 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка двойного клика: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_middleclick(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update):
            return
        try:
            result = await asyncio.to_thread(middle_click)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🖱 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка среднего клика: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_righthold(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update):
            return

        try:
            duration = float(context.args[0]) if context.args else 2.0
            result = await asyncio.to_thread(right_hold, duration)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🖱 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
        except ValueError:
            await self._safe_reply(update, 'Использование: <code>/righthold [seconds]</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка удержания: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_movemouse(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update):
            return

        if len(context.args) < 2:
            await self._safe_reply(update, 'Использование: <code>/movemouse <x> <y> [seconds]</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
            return

        try:
            x_str = context.args[0]
            y_str = context.args[1]
            is_relative = x_str.startswith(('+', '-')) or y_str.startswith(('+', '-'))

            x = int(x_str)
            y = int(y_str)
            duration = float(context.args[2]) if len(context.args) > 2 else 0.15
            result = await asyncio.to_thread(move_mouse, x, y, duration, relative=is_relative)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🖱 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
        except ValueError:
            await self._safe_reply(update, 'Использование: <code>/movemouse <x> <y> [seconds]</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка мыши: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_autoaccept_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update):
            return

        try:
            timeout = self._current_autoaccept_timeout()
            if context.args:
                timeout = self._parse_duration_token(context.args[0])
            timeout = self._set_autoaccept_timeout(timeout)
            template_dir = self._autoaccept_template_dir()
            result = await asyncio.to_thread(
                self._auto_accept_service.start,
                AutoAcceptConfig(template_dir=template_dir, timeout_seconds=timeout),
                self._handle_autoaccept_match,
                self._handle_autoaccept_error,
                self._handle_autoaccept_finish,
            )
            self.log_message.emit(result.message)
            await self._safe_reply(
                update,
                f'🤖 <b>{html.escape(result.message)}</b>\n📁 Шаблоны: <code>{html.escape(str(template_dir))}</code>\n⏱ Таймаут: {timeout}с',
                parse_mode=ParseMode.HTML, dismissable=True, as_toast=True
            )
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /autoaccepton: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)

    async def _command_autoaccept_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update):
            return

        try:
            result = await asyncio.to_thread(self._auto_accept_service.stop)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🤖 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True, as_toast=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /autoacceptoff: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)

    async def _command_clip_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'input'):
            return
        text, markup = self._build_clipboard_history_page(0)
        await self._safe_reply(update, text, parse_mode=ParseMode.HTML, reply_markup=markup)

    async def _command_windows(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'process'):
            return
        bot_username = self._application.bot.username
        text, total_pages = await asyncio.to_thread(self._build_windows_page, bot_username, 0)
        markup = self._windows_list_markup(0, total_pages)
        await self._safe_reply(update, text, parse_mode=ParseMode.HTML, reply_markup=markup)

    async def _command_ocr(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        query = ' '.join(context.args).strip() if context.args else ''
        await self._run_screen_ocr(update, query=query or None, reply_markup=self._dismiss_markup())

    @staticmethod
    def _trim_button_label(text: str, max_len: int = 30) -> str:
        cleaned = ' '.join((text or '').split())
        if len(cleaned) <= max_len:
            return cleaned
        return cleaned[:max_len - 1] + '…'

    def _build_clipboard_history_page(self, page: int) -> tuple[str, InlineKeyboardMarkup]:
        entries = self._clipboard_history.snapshot()
        total_pages = max(1, (len(entries) + CLIPBOARD_HISTORY_PAGE_SIZE - 1) // CLIPBOARD_HISTORY_PAGE_SIZE)
        safe_page = max(0, min(page, total_pages - 1))
        start = safe_page * CLIPBOARD_HISTORY_PAGE_SIZE
        current_items = entries[start:start + CLIPBOARD_HISTORY_PAGE_SIZE]

        lines = ['📋 <b>История буфера обмена</b>']
        if current_items:
            lines.append('')
            for index, entry in enumerate(current_items, start=start + 1):
                stamp = datetime.fromtimestamp(entry.created_at).strftime('%H:%M:%S')
                preview = html.escape(self._clipboard_history.preview(entry.text, max_len=70))
                lines.append(f'{index}. <code>{stamp}</code> — {preview}')
        else:
            lines.append('\nИстория пока пуста.')

        buttons: list[list[InlineKeyboardButton]] = []
        for index, entry in enumerate(current_items, start=start + 1):
            label = f'{index}. {self._trim_button_label(self._clipboard_history.preview(entry.text, max_len=26), 26)}'
            buttons.append([InlineKeyboardButton(label, callback_data=f'panel:cliphist:view:{entry.entry_id}:{safe_page}')])

        nav_row = []
        if safe_page > 0:
            nav_row.append(InlineKeyboardButton('⬅️', callback_data=f'panel:cliphist:page:{safe_page - 1}'))
        if safe_page < total_pages - 1:
            nav_row.append(InlineKeyboardButton('➡️', callback_data=f'panel:cliphist:page:{safe_page + 1}'))
        if nav_row:
            buttons.append(nav_row)
        buttons.append([InlineKeyboardButton('⬅️ Назад', callback_data='panel:input:clip')])
        return '\n'.join(lines), InlineKeyboardMarkup(buttons)

    def _build_clipboard_entry_view(self, entry_id: str, page: int) -> tuple[str, InlineKeyboardMarkup]:
        entry = self._clipboard_history.get(entry_id)
        if entry is None:
            return (
                '❌ <b>Элемент истории не найден.</b>',
                InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад', callback_data=f'panel:cliphist:page:{page}')]]),
            )

        stamp = datetime.fromtimestamp(entry.created_at).strftime('%d.%m.%Y %H:%M:%S')
        text = (
            f'📋 <b>Элемент истории буфера</b>\n'
            f'🕒 <code>{stamp}</code>\n\n'
            f'<code>{html.escape(entry.text[:3500])}</code>'
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton('♻️ Вернуть в буфер', callback_data=f'panel:cliphist:restore:{entry.entry_id}:{page}')],
            [InlineKeyboardButton('⬅️ Назад', callback_data=f'panel:cliphist:page:{page}')],
        ])
        return text, markup

    @staticmethod
    def _clipboard_panel_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('🕘 История буфера', callback_data='panel:input:clip_history')],
            [InlineKeyboardButton('❌ Отменить', callback_data='panel:input:cancel_text')],
        ])

    @staticmethod
    def _build_clipboard_panel_text(clipboard_text: str, status_text: str | None = None, is_error: bool = False) -> str:
        status_block = ''
        if status_text:
            prefix = '❌' if is_error else '✅'
            status_block = f'{prefix} <b>{html.escape(status_text)}</b>\n\n'
        return (
            '📋 <b>Буфер обмена</b>\n\n'
            f'{status_block}'
            '<b>Текущее содержимое:</b>\n'
            f'<code>{html.escape(clipboard_text)}</code>\n\n'
            'Отправьте текст, чтобы заменить содержимое буфера обмена ПК.'
        )

    async def _build_clipboard_panel_view(
            self,
            status_text: str | None = None,
            is_error: bool = False,
    ) -> tuple[str, InlineKeyboardMarkup]:
        result = await asyncio.to_thread(get_clipboard)
        current_text = result.message if result.ok else f'Ошибка чтения буфера: {result.message}'
        return self._build_clipboard_panel_text(current_text, status_text=status_text, is_error=is_error), self._clipboard_panel_markup()

    def _build_windows_page(self, bot_username: str, page: int) -> tuple[str, int]:
        windows = list_open_windows()
        total_pages = max(1, (len(windows) + WINDOWS_PAGE_SIZE - 1) // WINDOWS_PAGE_SIZE)
        safe_page = max(0, min(page, total_pages - 1))
        start = safe_page * WINDOWS_PAGE_SIZE
        current_items = windows[start:start + WINDOWS_PAGE_SIZE]

        lines = ['🪟 <b>Живые окна</b>']
        if current_items:
            lines.append('')
            for index, info in enumerate(current_items, start=start + 1):
                state = 'свернуто' if info.minimized else 'открыто'
                action_link = f'https://t.me/{bot_username}?start=win_{info.hwnd}_{safe_page}'
                lines.append(
                    f'{index}. 🪟 <a href="{action_link}">{html.escape(info.title)}</a>\n'
                    f'   <code>{html.escape(info.process_name)}</code> • HWND <code>{info.hwnd}</code> • {state}'
                )
        else:
            lines.append('\nОткрытые окна не найдены.')

        return '\n'.join(lines), total_pages

    def _window_detail_text(self, hwnd: int) -> str:
        info = get_window_info(hwnd)
        left, top, right, bottom = info.rect
        width = max(0, right - left)
        height = max(0, bottom - top)
        state = 'Свернуто' if info.minimized else 'Открыто'
        return (
            f'🪟 <b>Окно</b>\n'
            f'📌 <b>Заголовок:</b> <code>{html.escape(info.title)}</code>\n'
            f'⚙️ <b>Процесс:</b> <code>{html.escape(info.process_name)}</code> (PID <code>{info.pid}</code>)\n'
            f'🆔 <b>HWND:</b> <code>{info.hwnd}</code>\n'
            f'📐 <b>Размер:</b> <code>{width}x{height}</code>\n'
            f'📦 <b>Состояние:</b> <code>{state}</code>'
        )

    @staticmethod
    def _windows_list_markup(page: int, total_pages: int) -> InlineKeyboardMarkup:
        safe_page = max(0, min(page, max(total_pages - 1, 0)))
        buttons = []
        nav_row = []
        if safe_page > 0:
            nav_row.append(InlineKeyboardButton('⬅️ Вверх', callback_data=f'panel:win:page:{safe_page - 1}'))
        if safe_page < total_pages - 1:
            nav_row.append(InlineKeyboardButton('Вниз ➡️', callback_data=f'panel:win:page:{safe_page + 1}'))
        if nav_row:
            buttons.append(nav_row)
        buttons.append([InlineKeyboardButton('🔄 Обновить', callback_data=f'panel:win:page:{safe_page}')])
        buttons.append([InlineKeyboardButton('⬅️ Назад', callback_data='panel:process')])
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def _window_detail_markup(hwnd: int, page: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('🎯 Активировать', callback_data=f'panel:win:activate:{hwnd}:{page}'),
             InlineKeyboardButton('🗕 Свернуть', callback_data=f'panel:win:minimize:{hwnd}:{page}')],
            [InlineKeyboardButton('📸 Скрин окна', callback_data=f'panel:win:screenshot:{hwnd}:{page}'),
             InlineKeyboardButton('🔎 OCR окна', callback_data=f'panel:win:ocr:{hwnd}:{page}')],
            [InlineKeyboardButton('❌ Закрыть окно', callback_data=f'panel:win:close:{hwnd}:{page}')],
            [InlineKeyboardButton('⬅️ Назад', callback_data=f'panel:win:page:{page}')],
        ])

    @staticmethod
    def _window_reply_markup(hwnd: int, page: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('⬅️ Назад к окну', callback_data=f'panel:win:view:{hwnd}:{page}')]
        ])

    def _process_detail_text(self, pid: int) -> str:
        try:
            process = psutil.Process(int(pid))
        except psutil.NoSuchProcess as exc:
            raise RuntimeError('Процесс не найден или уже завершён.') from exc

        def safe(callable_obj, default: str = 'недоступно'):
            try:
                value = callable_obj()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                return default
            except Exception:
                return default
            if value in (None, ''):
                return default
            return value

        with process.oneshot():
            name = str(safe(process.name, 'unknown'))
            status = str(safe(process.status))
            exe = str(safe(process.exe))
            cwd = str(safe(process.cwd))
            username = str(safe(process.username))
            created_at_value = safe(process.create_time, 0.0)
            if isinstance(created_at_value, (int, float)) and created_at_value:
                created_at = datetime.fromtimestamp(created_at_value).strftime('%d.%m.%Y %H:%M:%S')
            else:
                created_at = 'недоступно'
            cmdline_value = safe(process.cmdline, [])
            if isinstance(cmdline_value, list):
                cmdline = ' '.join(str(part) for part in cmdline_value if str(part).strip())
            else:
                cmdline = str(cmdline_value)
            cmdline = cmdline or 'недоступно'
            cmdline = cmdline[:1200]
            memory_info = safe(process.memory_info)
            if memory_info == 'недоступно':
                rss_text = 'недоступно'
                vms_text = 'недоступно'
            else:
                rss_text = self._format_bytes(int(memory_info.rss))
                vms_text = self._format_bytes(int(memory_info.vms))
            num_threads = safe(process.num_threads)
            ppid = safe(process.ppid)

        window_count = 0
        try:
            window_count = sum(1 for item in list_open_windows() if item.pid == int(pid))
        except Exception:
            window_count = 0

        return (
            '⚙️ <b>Процесс</b>\n'
            f'📌 <b>Имя:</b> <code>{html.escape(name)}</code>\n'
            f'🆔 <b>PID:</b> <code>{pid}</code>\n'
            f'📁 <b>Путь:</b> <code>{html.escape(str(exe)[:1200])}</code>\n'
            f'📂 <b>CWD:</b> <code>{html.escape(str(cwd)[:1000])}</code>\n'
            f'👤 <b>Пользователь:</b> <code>{html.escape(username)}</code>\n'
            f'📦 <b>Статус:</b> <code>{html.escape(status)}</code>\n'
            f'🕒 <b>Запущен:</b> <code>{html.escape(created_at)}</code>\n'
            f'🧠 <b>RAM RSS:</b> <code>{html.escape(rss_text)}</code>\n'
            f'💾 <b>VMS:</b> <code>{html.escape(vms_text)}</code>\n'
            f'🧵 <b>Потоки:</b> <code>{html.escape(str(num_threads))}</code>\n'
            f'🌳 <b>PPID:</b> <code>{html.escape(str(ppid))}</code>\n'
            f'🪟 <b>Окон:</b> <code>{window_count}</code>\n\n'
            f'⌨️ <b>Командная строка:</b>\n<code>{html.escape(cmdline)}</code>'
        )

    @staticmethod
    def _process_detail_markup(pid: int, page: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('🔄 Обновить', callback_data=f'panel:proc:info:{pid}:{page}')],
            [InlineKeyboardButton('☠️ Завершить процесс', callback_data=f'panel:proc:kill:{pid}:{page}')],
            [InlineKeyboardButton('⬅️ Назад', callback_data=f'panel:proc:page:{page}')],
        ])

    @staticmethod
    def _close_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('👌 Закрыть', callback_data='panel:dismiss')]
        ])

    @staticmethod
    def _clipboard_reply_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('⬅️ Назад', callback_data='panel:input:clip')]
        ])

    @staticmethod
    def _ocr_reply_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('⬅️ Назад', callback_data='panel:ocr')]
        ])

    @staticmethod
    def _ocr_menu_text() -> str:
        return (
            '🔎 <b>OCR</b>\n\n'
            'Распознавание текста с текущего экрана.\n'
            'Можно получить весь текст или отправить запрос для поиска фразы, кода или номера.'
        )

    @staticmethod
    def _ocr_menu_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('🖼 OCR экрана', callback_data='panel:ocr:screen')],
            [InlineKeyboardButton('🔎 Найти текст на экране', callback_data='panel:ocr:find')],
            [InlineKeyboardButton('⬅️ Назад', callback_data='panel:main')],
        ])

    def _format_ocr_report(self, result, source_label: str, query: str | None = None) -> str:
        if not result.text:
            return f'🔎 <b>OCR: {html.escape(source_label)}</b>\n\nТекст не найден.'

        if query:
            matches = find_matching_lines(result.lines, query)
            if matches:
                body = '\n'.join(f'• {html.escape(line)}' for line in matches[:20])
                if len(matches) > 20:
                    body += f'\n• … ещё {len(matches) - 20}'
                return (
                    f'🔎 <b>OCR: {html.escape(source_label)}</b>\n'
                    f'Ищу: <code>{html.escape(query)}</code>\n\n{body}'
                )
            return (
                f'🔎 <b>OCR: {html.escape(source_label)}</b>\n'
                f'Ищу: <code>{html.escape(query)}</code>\n\nСовпадений не найдено.'
            )

        text = result.text[:3500]
        if len(result.text) > 3500:
            text += '\n...[ОБРЕЗАНО]...'
        return f'🔎 <b>OCR: {html.escape(source_label)}</b>\n\n<pre>{html.escape(text)}</pre>'

    async def _run_screen_ocr(
            self,
            update: Update,
            query: str | None = None,
            reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        temp_msg = None
        if not update.callback_query:
            temp_msg = await self._send_temporary_status(update, '⏳ <b>Распознаю текст с экрана...</b>')

        try:
            screenshot_bytes, _ = await asyncio.to_thread(capture_screenshot_bytes)
            ocr_result = await extract_text_from_image_bytes(screenshot_bytes)
            text = self._format_ocr_report(ocr_result, 'экран', query=query)
            self._record_runtime_activity('last_ocr', 'экран')
            await self._safe_reply(
                update,
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup or self._ocr_menu_markup(),
            )
        except Exception as exc:
            self._record_runtime_error(f'OCR error: {exc}')
            await self._safe_reply(
                update,
                f'❌ Ошибка OCR: <code>{html.escape(str(exc))}</code>',
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup or self._ocr_menu_markup(),
            )
        finally:
            if temp_msg:
                await self._delete_message_safe(temp_msg)

    async def _run_window_ocr(self, update: Update, hwnd: int, page: int) -> None:
        try:
            image_bytes, _ = await asyncio.to_thread(capture_window_bytes_for_window, hwnd)
            ocr_result = await extract_text_from_image_bytes(image_bytes)
            text = self._format_ocr_report(ocr_result, f'окно {hwnd}')
            self._record_runtime_activity('last_ocr', f'окно {hwnd}')
            await self._safe_reply(
                update,
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=self._window_reply_markup(hwnd, page),
            )
        except Exception as exc:
            self._record_runtime_error(f'Window OCR error: {exc}')
            await self._safe_reply(
                update,
                f'❌ Ошибка OCR окна: <code>{html.escape(str(exc))}</code>',
                parse_mode=ParseMode.HTML,
                reply_markup=self._window_reply_markup(hwnd, page),
            )

    @staticmethod
    def _format_schedule_action(action: str) -> str:
        action_name, action_value = TelegramBotService._parse_scheduled_action_spec(action)
        mapping = {
            'screenshot': 'скриншот',
            'logsave': 'сохранить лог',
            'status': 'статус системы',
            'hwinfo': 'железо и датчики',
            'ocrscreen': 'OCR экрана',
            'clipboard': 'буфер обмена',
            'tasklist': 'список процессов',
            'windows': 'живые окна',
            'report': 'полный отчет',
            'music': 'что играет',
            'playpause': 'play/pause',
            'nexttrack': 'следующий трек',
            'prevtrack': 'предыдущий трек',
            'cancelshutdown': 'отмена выключения',
            'shutdown': 'выключение',
            'reboot': 'перезагрузка',
            'hibernate': 'гибернация',
            'lock': 'блокировка',
            'sleep': 'сон',
            'webcam': 'фото с вебки',
            'webcamvid': f'видео с вебки {action_value}с' if action_value is not None else 'видео с вебки',
            'audio': f'аудио {action_value}с' if action_value is not None else 'аудио',
        }
        return mapping.get(action_name, action)

    @staticmethod
    def _parse_duration_token(raw: str) -> int:
        value = str(raw or '').strip().lower()
        match = re.fullmatch(r'(\d+)([smhd]?)', value)
        if not match:
            raise ValueError('Неверный формат задержки. Используйте 120, 10m, 2h или 1d.')
        amount = int(match.group(1))
        suffix = match.group(2) or 's'
        multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        return amount * multipliers[suffix]

    @staticmethod
    def _normalize_schedule_token(raw_token: str) -> str:
        token = str(raw_token or '').strip()
        if not token:
            return ''
        dash_chars = '\u2010\u2011\u2012\u2013\u2014\u2015\u2212'
        for dash in dash_chars:
            token = token.replace(dash, '-')
        if token.startswith('-') and not token.startswith('--') and len(token) > 1 and token[1].isalpha():
            token = '-' + token
        return token

    @staticmethod
    def _parse_scheduled_action_spec(action: str) -> tuple[str, int | None]:
        raw = TelegramBotService._normalize_schedule_token(action).lower()
        if raw == 'webcam':
            return 'webcam', None
        if raw in {
            'status',
            'hwinfo',
            'ocr',
            'ocrscreen',
            'clipboard',
            'clip',
            'tasklist',
            'tasks',
            'processes',
            'windows',
            'windowlist',
            'report',
            'music',
            'track',
            'playpause',
            'play',
            'pause',
            'nexttrack',
            'next',
            'prevtrack',
            'prev',
            'cancelshutdown',
            'cancelpower',
            'screenshot',
            'logsave',
            'shutdown',
            'reboot',
            'hibernate',
            'lock',
            'sleep',
        }:
            if raw in {'ocr', 'ocrscreen'}:
                return 'ocrscreen', None
            if raw in {'clipboard', 'clip'}:
                return 'clipboard', None
            if raw in {'tasklist', 'tasks', 'processes'}:
                return 'tasklist', None
            if raw in {'windows', 'windowlist'}:
                return 'windows', None
            if raw in {'music', 'track'}:
                return 'music', None
            if raw in {'playpause', 'play', 'pause'}:
                return 'playpause', None
            if raw in {'nexttrack', 'next'}:
                return 'nexttrack', None
            if raw in {'prevtrack', 'prev'}:
                return 'prevtrack', None
            if raw in {'cancelshutdown', 'cancelpower'}:
                return 'cancelshutdown', None
            return raw, None

        webcam_match = re.fullmatch(r'(?:webcamvid|webcam)(?::|=)?(\d+)', raw)
        if webcam_match:
            return 'webcamvid', max(1, min(300, int(webcam_match.group(1))))

        audio_match = re.fullmatch(r'audio(?::|=)?(\d+)', raw)
        if audio_match:
            return 'audio', max(1, min(300, int(audio_match.group(1))))

        raise ValueError(f'Неизвестное действие: {action}')

    def _parse_schedule_actions(self, args: list[str]) -> tuple[list[str], dict[str, float | str], str]:
        if not args:
            raise ValueError('Не указаны действия для планировщика.')

        actions: list[str] = []
        options: dict[str, float | str] = {}
        note = ''
        idx = 0
        while idx < len(args):
            token = self._normalize_schedule_token(args[idx])
            if not token:
                idx += 1
                continue
            if token == '--if-cpu-below':
                idx += 1
                if idx >= len(args):
                    raise ValueError('После --if-cpu-below нужно указать число.')
                options['cpu_below'] = float(str(args[idx]).replace('%', '').replace(',', '.'))
                idx += 1
                continue
            if token == '--if-cpu-above':
                idx += 1
                if idx >= len(args):
                    raise ValueError('После --if-cpu-above нужно указать число.')
                options['cpu_above'] = float(str(args[idx]).replace('%', '').replace(',', '.'))
                idx += 1
                continue
            if token == '--if-ram-below':
                idx += 1
                if idx >= len(args):
                    raise ValueError('После --if-ram-below нужно указать число.')
                options['ram_below'] = float(str(args[idx]).replace('%', '').replace(',', '.'))
                idx += 1
                continue
            if token == '--if-ram-above':
                idx += 1
                if idx >= len(args):
                    raise ValueError('После --if-ram-above нужно указать число.')
                options['ram_above'] = float(str(args[idx]).replace('%', '').replace(',', '.'))
                idx += 1
                continue
            if token in {'--comment', '--note'}:
                idx += 1
                note_parts: list[str] = []
                while idx < len(args):
                    candidate = self._normalize_schedule_token(args[idx])
                    if candidate in {'--if-cpu-below', '--if-cpu-above', '--if-ram-below', '--if-ram-above', '--comment', '--note'}:
                        break
                    if candidate:
                        note_parts.append(candidate)
                    idx += 1
                if not note_parts:
                    raise ValueError('После --comment/--note нужно указать текст комментария.')
                note = ' '.join(note_parts).strip()[:160]
                continue

            for part in token.split(','):
                cleaned = self._normalize_schedule_token(part).strip().lower()
                if cleaned:
                    action_name, action_value = self._parse_scheduled_action_spec(cleaned)
                    if action_value is None:
                        actions.append(action_name)
                    else:
                        actions.append(f'{action_name}:{action_value}')
            idx += 1

        if not actions:
            raise ValueError('Не удалось распознать действия планировщика.')

        invalid = []
        for action in actions:
            try:
                action_name, _ = self._parse_scheduled_action_spec(action)
            except ValueError:
                invalid.append(action)
                continue
            if action_name not in ALLOWED_SCHEDULE_ACTIONS:
                invalid.append(action)
        if invalid:
            raise ValueError(f'Неизвестные действия: {", ".join(invalid)}')
        return actions, options, note

    async def _ensure_schedule_permissions(self, update: Update, actions: list[str]) -> bool:
        action_names = [self._parse_scheduled_action_spec(action)[0] for action in actions]
        power_actions = {'shutdown', 'reboot', 'hibernate', 'lock', 'sleep', 'cancelshutdown'}
        media_actions = {'webcam', 'webcamvid', 'audio', 'report', 'music', 'playpause', 'nexttrack', 'prevtrack'}
        process_actions = {'tasklist', 'windows'}
        if any(action in power_actions for action in action_names):
            if not await self._ensure_admin(update, 'power'):
                return False
        if any(action in media_actions for action in action_names):
            if not await self._ensure_admin(update, 'media'):
                return False
        if any(action in process_actions for action in action_names):
            if not await self._ensure_admin(update, 'process'):
                return False
        return await self._ensure_admin(update)

    @staticmethod
    def _format_schedule_note(note: str) -> str:
        cleaned = str(note or '').strip()
        if not cleaned:
            return ''
        return f'\n💬 <i>{html.escape(cleaned)}</i>'

    def _format_scheduled_job(self, job: ScheduledJob) -> str:
        when = datetime.fromtimestamp(job.run_at).strftime('%d.%m %H:%M:%S')
        actions = ', '.join(self._format_schedule_action(action) for action in job.actions)
        conditions = []
        if job.cpu_below is not None:
            conditions.append(f'CPU ≤ {job.cpu_below:.1f}%')
        if job.cpu_above is not None:
            conditions.append(f'CPU ≥ {job.cpu_above:.1f}%')
        if job.ram_below is not None:
            conditions.append(f'RAM ≤ {job.ram_below:.1f}%')
        if job.ram_above is not None:
            conditions.append(f'RAM ≥ {job.ram_above:.1f}%')
        conditions_text = f' • {" • ".join(conditions)}' if conditions else ''
        return f'<code>{job.job_id}</code> • {when} • {html.escape(actions)}{conditions_text}{self._format_schedule_note(job.note)}'

    @staticmethod
    def _scheduler_add_text() -> str:
        return (
            '➕ <b>Добавить задачу</b>\n\n'
            'Отправьте одной строкой задачу в формате:\n'
            '<code>in 2h screenshot logsave --comment Ночной скрин</code>\n'
            '<code>at 03:00 reboot --note Ночной ребут</code>\n'
            '<code>in 25m webcam:15 audio:20 —comment Ночная проверка</code>\n'
            '<code>in 20m ocrscreen clipboard --if-ram-below 70 --comment Что на экране и в буфере</code>\n\n'
            'Поддерживается:\n'
            '<code>in DELAY actions... [--if-cpu-below N] [--if-cpu-above N] [--if-ram-below N] [--if-ram-above N] [--comment Текст]</code>\n'
            '<code>at HH:MM actions... [--if-cpu-below N] [--if-cpu-above N] [--if-ram-below N] [--if-ram-above N] [--note Текст]</code>\n\n'
            'Действия: <code>screenshot</code>, <code>logsave</code>, <code>status</code>, <code>hwinfo</code>, <code>ocrscreen</code>, <code>clipboard</code>, '
            '<code>tasklist</code>, <code>windows</code>, '
            '<code>report</code>, <code>music</code>, <code>playpause</code>, <code>nexttrack</code>, <code>prevtrack</code>, <code>webcam</code>, '
            '<code>webcam:15</code>/<code>webcamvid:15</code>, <code>audio:20</code>, <code>lock</code>, <code>sleep</code>, '
            '<code>hibernate</code>, <code>cancelshutdown</code>, <code>shutdown</code>, <code>reboot</code>'
        )

    @staticmethod
    def _scheduler_add_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('❓ Справка', callback_data='panel:sched:help')],
            [InlineKeyboardButton('⬅️ Назад', callback_data='panel:sched')],
        ])

    def _scheduler_panel_text(self) -> str:
        jobs = self._scheduler_store.list_jobs()
        examples = (
            '<code>/schedulein 15m webcam --comment Проверка вебки</code>\n'
            '<code>/schedulein 30m screenshot logsave status --comment Ночной лог</code>\n'
            '<code>/schedulein 25m webcam:15 audio:20 --if-cpu-below 12 --comment Ночная проверка</code>\n'
            '<code>/schedulein 2h shutdown --if-cpu-below 10 --if-ram-below 60 --note Выключить если простаивает</code>\n'
            '<code>/schedulein 20m ocrscreen clipboard --if-cpu-above 15 --comment Проверить экран и буфер</code>\n'
            '<code>/schedulein 15m tasklist windows --comment Что открыто на ПК</code>\n'
            '<code>/schedulein 10m report music --comment Ночной контроль</code>\n'
            '<code>/scheduleat 03:00 screenshot logsave hwinfo reboot --comment Ночной ребут</code>\n'
            '<code>/jobs</code> • <code>/jobcancel JOB_ID</code>'
        )
        return (
            '🗓 <b>Планировщик</b>\n\n'
            f'Активных задач: <code>{len(jobs)}</code>\n\n'
            'Через кнопку ниже можно добавить задачу прямо из панели.\n\n'
            'Поддерживаемые действия: <code>screenshot</code>, <code>logsave</code>, <code>status</code>, <code>hwinfo</code>, <code>ocrscreen</code>, '
            '<code>clipboard</code>, <code>tasklist</code>, <code>windows</code>, <code>report</code>, <code>music</code>, <code>playpause</code>, <code>nexttrack</code>, <code>prevtrack</code>, '
            '<code>webcam</code>, <code>webcam:15</code>, <code>audio:20</code>, <code>shutdown</code>, '
            '<code>reboot</code>, <code>hibernate</code>, <code>cancelshutdown</code>, <code>lock</code>, <code>sleep</code>\n\n'
            f'{examples}'
        )

    @staticmethod
    def _scheduler_panel_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('➕ Добавить задачу', callback_data='panel:sched:add')],
            [InlineKeyboardButton('📋 Активные задачи', callback_data='panel:sched:list')],
            [InlineKeyboardButton('❓ Справка и команды', callback_data='panel:sched:help')],
            [InlineKeyboardButton('🧹 Очистить всё', callback_data='panel:sched:clear')],
            [InlineKeyboardButton('⬅️ Назад', callback_data='panel:main')],
        ])

    def _scheduler_help_text(self) -> str:
        return (
            '🗓 <b>Справка по планировщику</b>\n\n'
            'Комментарии:\n'
            '• Используйте <code>--comment Текст</code> или <code>--note Текст</code>\n'
            '• Комментарий сохраняется в задаче, показывается в списке и приходит в уведомлениях\n\n'
            'Telegram-особенность:\n'
            '• Длинное тире <code>—comment</code> и <code>–if-cpu-below</code> тоже понимается как обычное <code>--comment</code>\n\n'
            'Условия:\n'
            '• <code>--if-cpu-below 10</code> выполнит задачу только если CPU не выше 10%\n\n'
            '• <code>--if-cpu-above 70</code> выполнит задачу только если CPU не ниже 70%\n'
            '• <code>--if-ram-below 60</code> выполнит задачу только если RAM не выше 60%\n'
            '• <code>--if-ram-above 90</code> выполнит задачу только если RAM не ниже 90%\n\n'
            'Команды:\n'
            '<code>/schedulein 15m screenshot --comment Быстрый скрин</code>\n'
            '<code>/schedulein 30m screenshot logsave status --note Логи перед сном</code>\n'
            '<code>/schedulein 20m webcam --comment Проверка камеры</code>\n'
            '<code>/schedulein 25m audio:20 --comment Что слышно</code>\n'
            '<code>/schedulein 40m webcam:15 --comment Короткое видео</code>\n'
            '<code>/schedulein 20m ocrscreen --comment Прочитать экран</code>\n'
            '<code>/schedulein 20m clipboard --comment Отправить буфер</code>\n'
            '<code>/schedulein 15m tasklist windows --comment Что открыто на ПК</code>\n'
            '<code>/schedulein 15m report --comment Полный отчет</code>\n'
            '<code>/schedulein 30m music playpause --comment Музыкальная пауза</code>\n'
            '<code>/schedulein 1h sleep --comment Усыпить ПК</code>\n'
            '<code>/schedulein 2h shutdown --if-cpu-below 10 --if-ram-below 60 --note Выключить если простаивает</code>\n'
            '<code>/scheduleat 03:00 reboot --comment Ночной ребут</code>\n'
            '<code>/scheduleat 03:00 screenshot logsave hwinfo reboot --comment Ночной ребут с логами</code>\n'
            '<code>/jobs</code>\n'
            '<code>/jobcancel JOB_ID</code>\n\n'
            'Действия:\n'
            '• <code>screenshot</code> — скриншот экрана\n'
            '• <code>logsave</code> — сохранить текущий лог\n'
            '• <code>status</code> — краткий статус системы\n'
            '• <code>hwinfo</code> — железо и датчики\n'
            '• <code>ocr</code> / <code>ocrscreen</code> — распознать текст с текущего экрана\n'
            '• <code>clip</code> / <code>clipboard</code> — отправить текущий текст из буфера обмена\n'
            '• <code>tasklist</code> — список процессов с deep-link переходами\n'
            '• <code>windows</code> — список живых окон с deep-link переходами\n'
            '• <code>report</code> — экран + вебка + 5с аудио одним пакетом\n'
            '• <code>music</code> — показать текущий трек\n'
            '• <code>playpause</code>, <code>nexttrack</code>, <code>prevtrack</code> — управление медиаплеером\n'
            '• <code>webcam</code> — фото с веб-камеры\n'
            '• <code>webcam:15</code> или <code>webcamvid:15</code> — видео с вебки 15 секунд\n'
            '• <code>audio:20</code> — запись микрофона 20 секунд\n'
            '• <code>cancelshutdown</code> — отменить запланированное выключение/ребут\n'
            '• <code>lock</code>, <code>sleep</code>, <code>hibernate</code>, <code>shutdown</code>, <code>reboot</code>'
        )

    @staticmethod
    def _scheduler_help_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('➕ Добавить задачу', callback_data='panel:sched:add')],
            [InlineKeyboardButton('📋 Активные задачи', callback_data='panel:sched:list')],
            [InlineKeyboardButton('⬅️ Назад', callback_data='panel:sched')],
        ])

    def _build_scheduler_jobs_view(self, bot_username: str) -> tuple[str, InlineKeyboardMarkup]:
        jobs = self._scheduler_store.list_jobs()
        if not jobs:
            return (
                '🗓 <b>Планировщик</b>\n\nНет активных задач.',
                InlineKeyboardMarkup([
                    [InlineKeyboardButton('➕ Добавить задачу', callback_data='panel:sched:add')],
                    [InlineKeyboardButton('⬅️ Назад', callback_data='panel:sched')],
                ]),
            )

        lines = ['🗓 <b>Активные задачи</b>', '']
        buttons: list[list[InlineKeyboardButton]] = []
        for job in jobs[:20]:
            delete_link = f'https://t.me/{bot_username}?start=sjdel_{job.job_id}'
            lines.append(f'<a href="{delete_link}">❌</a> {self._format_scheduled_job(job)}')
        buttons.append([InlineKeyboardButton('➕ Добавить задачу', callback_data='panel:sched:add')])
        buttons.append([InlineKeyboardButton('⬅️ Назад', callback_data='panel:sched')])
        return '\n'.join(lines), InlineKeyboardMarkup(buttons)

    @staticmethod
    def _parse_schedule_clock(raw_value: str) -> datetime:
        match = re.fullmatch(r'(\d{1,2}):(\d{2})', raw_value.strip())
        if not match:
            raise ValueError('Время должно быть в формате HH:MM.')
        target_h = int(match.group(1))
        target_m = int(match.group(2))
        now = datetime.now()
        run_at_dt = now.replace(hour=target_h, minute=target_m, second=0, microsecond=0)
        if run_at_dt <= now:
            run_at_dt += timedelta(days=1)
        return run_at_dt

    async def _create_scheduled_job_from_mode(
            self,
            update: Update,
            mode: str,
            schedule_value: str,
            args: list[str],
    ) -> ScheduledJob:
        actions, options, note = self._parse_schedule_actions(args)
        if not await self._ensure_schedule_permissions(update, actions):
            raise PermissionError('Недостаточно прав для выбранных действий.')

        if mode == 'in':
            run_at = time.time() + self._parse_duration_token(schedule_value)
        elif mode == 'at':
            run_at = self._parse_schedule_clock(schedule_value).timestamp()
        else:
            raise ValueError('Неизвестный режим планировщика.')

        return self._scheduler_store.add_job(
            run_at=run_at,
            actions=actions,
            created_by=update.effective_user.id,
            cpu_below=float(options['cpu_below']) if options.get('cpu_below') is not None else None,
            cpu_above=float(options['cpu_above']) if options.get('cpu_above') is not None else None,
            ram_below=float(options['ram_below']) if options.get('ram_below') is not None else None,
            ram_above=float(options['ram_above']) if options.get('ram_above') is not None else None,
            note=note,
        )

    async def _command_schedule_in(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        if len(context.args) < 2:
            await self._safe_reply(
                update,
                'Использование:\n'
                '<code>/schedulein 20m webcam:15 audio:20 --if-cpu-below 12 --comment Ночная проверка</code>\n'
                '<code>/schedulein 20m ocrscreen clipboard —comment Проверить экран и буфер</code>\n'
                '<code>/schedulein 2h shutdown --if-cpu-below 10 --if-ram-below 60 --note Выключить если простаивает</code>',
                parse_mode=ParseMode.HTML,
                dismissable=True,
            )
            return

        try:
            job = await self._create_scheduled_job_from_mode(update, 'in', context.args[0], context.args[1:])
            await self._safe_reply(
                update,
                f'✅ <b>Задача создана</b>\n{self._format_scheduled_job(job)}',
                parse_mode=ParseMode.HTML,
                dismissable=True,
            )
        except PermissionError:
            return
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка планировщика: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_schedule_at(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        if len(context.args) < 2:
            await self._safe_reply(
                update,
                'Использование:\n'
                '<code>/scheduleat 03:00 reboot --comment Ночной ребут</code>\n'
                '<code>/scheduleat 03:00 screenshot logsave hwinfo reboot --note Ночной ребут с логами</code>\n'
                '<code>/scheduleat 06:30 clipboard status --comment Утренний отчёт</code>',
                parse_mode=ParseMode.HTML,
                dismissable=True,
            )
            return

        try:
            job = await self._create_scheduled_job_from_mode(update, 'at', context.args[0], context.args[1:])
            await self._safe_reply(
                update,
                f'✅ <b>Задача создана</b>\n{self._format_scheduled_job(job)}',
                parse_mode=ParseMode.HTML,
                dismissable=True,
            )
        except PermissionError:
            return
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка планировщика: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_jobs(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        text, markup = self._build_scheduler_jobs_view(self._application.bot.username)
        if update.effective_chat:
            message = await update.effective_chat.send_message(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
            self._menu_msg_id_by_user[update.effective_user.id] = message.message_id
            return
        await self._safe_reply(update, text, parse_mode=ParseMode.HTML, reply_markup=markup)

    async def _command_jobcancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        if not context.args:
            await self._safe_reply(update, 'Использование: <code>/jobcancel JOB_ID</code>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
            return

        removed = self._scheduler_store.remove_job(context.args[0].strip())
        if removed is None:
            await self._safe_reply(update, '❌ Задача не найдена.', dismissable=True)
            return
        await self._safe_reply(update, f'🗑 <b>Задача отменена:</b>\n{self._format_scheduled_job(removed)}',
                               parse_mode=ParseMode.HTML, dismissable=True)

    async def _scheduler_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                due_jobs = self._scheduler_store.pop_due(time.time())
                for job in due_jobs:
                    try:
                        await self._execute_scheduled_job(job)
                    except Exception as exc:
                        self.log_message.emit(f'Scheduled job failed {job.job_id}: {exc}')
                        await self._notify_admins(
                            f'❌ <b>Планировщик:</b> ошибка задачи <code>{job.job_id}</code>\n<code>{html.escape(str(exc))}</code>'
                        )
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass

    async def _execute_scheduled_job(self, job: ScheduledJob) -> None:
        actions_text = ', '.join(self._format_schedule_action(action) for action in job.actions)
        note_block = self._format_schedule_note(job.note)
        cpu_percent: float | None = None
        if job.cpu_below is not None or job.cpu_above is not None:
            cpu_percent = await asyncio.to_thread(psutil.cpu_percent, 0.6)
        if job.cpu_below is not None:
            if cpu_percent > job.cpu_below:
                message = (
                    f'⏭️ <b>Планировщик:</b> задача <code>{job.job_id}</code> пропущена.\n'
                    f'CPU сейчас <code>{cpu_percent:.1f}%</code>, порог <code>{job.cpu_below:.1f}%</code>.'
                )
                if note_block:
                    message += note_block
                self.log_message.emit(message)
                await self._notify_admins(message)
                return
        if job.cpu_above is not None:
            if cpu_percent < job.cpu_above:
                message = (
                    f'⏭️ <b>Планировщик:</b> задача <code>{job.job_id}</code> пропущена.\n'
                    f'CPU сейчас <code>{cpu_percent:.1f}%</code>, нужен минимум <code>{job.cpu_above:.1f}%</code>.'
                )
                if note_block:
                    message += note_block
                self.log_message.emit(message)
                await self._notify_admins(message)
                return
        memory_percent: float | None = None
        if job.ram_below is not None or job.ram_above is not None:
            memory_percent = psutil.virtual_memory().percent
        if job.ram_below is not None and memory_percent > job.ram_below:
            message = (
                f'⏭️ <b>Планировщик:</b> задача <code>{job.job_id}</code> пропущена.\n'
                f'RAM сейчас <code>{memory_percent:.1f}%</code>, порог <code>{job.ram_below:.1f}%</code>.'
            )
            if note_block:
                message += note_block
            self.log_message.emit(message)
            await self._notify_admins(message)
            return
        if job.ram_above is not None and memory_percent < job.ram_above:
            message = (
                f'⏭️ <b>Планировщик:</b> задача <code>{job.job_id}</code> пропущена.\n'
                f'RAM сейчас <code>{memory_percent:.1f}%</code>, нужен минимум <code>{job.ram_above:.1f}%</code>.'
            )
            if note_block:
                message += note_block
            self.log_message.emit(message)
            await self._notify_admins(message)
            return

        start_message = (
            f'⏰ <b>Планировщик:</b> выполняю задачу <code>{job.job_id}</code>\n'
            f'Действия: <code>{html.escape(actions_text)}</code>{note_block}'
        )
        self.log_message.emit(start_message)
        status_refs = await self._send_message_to_admins(start_message, reply_markup=self._dismiss_markup())
        disruptive_actions = {'shutdown', 'reboot', 'hibernate', 'sleep'}

        try:
            for raw_action in job.actions:
                action, action_value = self._parse_scheduled_action_spec(raw_action)
                if action == 'screenshot':
                    screenshot_bytes, file_name = await asyncio.to_thread(capture_screenshot_bytes)
                    saved_path = await asyncio.to_thread(self._save_artifact_bytes, file_name, screenshot_bytes)
                    await self._send_photo_to_admins(
                        screenshot_bytes,
                        file_name,
                        f'🖼 <b>Планировщик:</b> скриншот задачи <code>{job.job_id}</code>\n<code>{html.escape(saved_path.name)}</code>{note_block}',
                    )
                    self._record_runtime_activity('last_screenshot', 'планировщик')
                    continue

                if action == 'logsave':
                    saved_path = await asyncio.to_thread(self._save_log_snapshot, job.job_id)
                    await self._send_document_to_admins(
                        saved_path.read_bytes(),
                        saved_path.name,
                        f'🧾 <b>Планировщик:</b> лог задачи <code>{job.job_id}</code>{note_block}',
                    )
                    continue

                if action == 'status':
                    snapshot = await asyncio.to_thread(
                        collect_snapshot,
                        len(self._config_provider().admins),
                        self._config_provider().autostart,
                        self._running,
                    )
                    status_text = (
                        f'📊 <b>Планировщик:</b> статус задачи <code>{job.job_id}</code>\n'
                        f'💻 <b>Хост:</b> <code>{html.escape(snapshot.hostname)}</code>\n'
                        f'🧠 <b>CPU:</b> <code>{snapshot.cpu_percent:.1f}%</code>\n'
                        f'💽 <b>RAM:</b> <code>{snapshot.memory_percent:.1f}%</code>\n'
                        f'💾 <b>Disk:</b> <code>{snapshot.disk_percent:.1f}%</code>\n'
                        f'⏱ <b>Uptime:</b> <code>{format_uptime(snapshot.uptime_seconds)}</code>{note_block}'
                    )
                    await self._notify_admins(status_text)
                    continue

                if action == 'hwinfo':
                    hw_text = await asyncio.to_thread(get_hardware_info)
                    await self._notify_admins(f'🧰 <b>Планировщик:</b> железо задачи <code>{job.job_id}</code>\n{hw_text}{note_block}')
                    continue

                if action == 'ocrscreen':
                    screenshot_bytes, _ = await asyncio.to_thread(capture_screenshot_bytes)
                    ocr_result = await extract_text_from_image_bytes(screenshot_bytes)
                    ocr_text = self._format_ocr_report(ocr_result, 'экран')
                    await self._notify_admins(
                        f'🔎 <b>Планировщик:</b> OCR задачи <code>{job.job_id}</code>\n\n{ocr_text}{note_block}'
                    )
                    self._record_runtime_activity('last_ocr', 'планировщик')
                    continue

                if action == 'clipboard':
                    clip_result = await asyncio.to_thread(get_clipboard)
                    if clip_result.ok:
                        clip_body = html.escape(clip_result.message or '')
                        if len(clip_body) > 3500:
                            clip_body = clip_body[:3500] + '\n...[ОБРЕЗАНО]...'
                        clip_text = (
                            f'📋 <b>Планировщик:</b> буфер обмена задачи <code>{job.job_id}</code>\n\n'
                            f'<code>{clip_body}</code>{note_block}'
                        )
                    else:
                        clip_text = (
                            f'❌ <b>Планировщик:</b> не удалось прочитать буфер для задачи <code>{job.job_id}</code>\n'
                            f'<code>{html.escape(clip_result.message)}</code>{note_block}'
                        )
                    await self._notify_admins(clip_text)
                    continue

                if action == 'tasklist':
                    bot_username = getattr(getattr(self._application, 'bot', None), 'username', '') or ''
                    tasklist_text, _ = await asyncio.to_thread(self._build_tasklist_page, '', bot_username, 0)
                    await self._notify_admins(
                        f'🔝 <b>Планировщик:</b> процессы по задаче <code>{job.job_id}</code>\n\n{tasklist_text}{note_block}'
                    )
                    continue

                if action == 'windows':
                    bot_username = getattr(getattr(self._application, 'bot', None), 'username', '') or ''
                    windows_text, _ = await asyncio.to_thread(self._build_windows_page, bot_username, 0)
                    await self._notify_admins(
                        f'🪟 <b>Планировщик:</b> окна по задаче <code>{job.job_id}</code>\n\n{windows_text}{note_block}'
                    )
                    continue

                if action == 'report':
                    screen_bytes, screen_name = await asyncio.to_thread(capture_screenshot_bytes)
                    screen_path = await asyncio.to_thread(self._save_artifact_bytes, screen_name, screen_bytes)
                    await self._send_photo_to_admins(
                        screen_bytes,
                        screen_name,
                        f'🖼 <b>Планировщик:</b> экран по задаче <code>{job.job_id}</code>\n<code>{html.escape(screen_path.name)}</code>{note_block}',
                    )
                    self._record_runtime_activity('last_screenshot', 'планировщик отчет')

                    try:
                        webcam_bytes, webcam_name = await asyncio.to_thread(capture_webcam_photo)
                    except Exception as exc:
                        await self._notify_admins(
                            f'❌ <b>Планировщик:</b> веб-камера недоступна для задачи <code>{job.job_id}</code>\n'
                            f'<code>{html.escape(str(exc))}</code>{note_block}'
                        )
                    else:
                        webcam_path = await asyncio.to_thread(self._save_artifact_bytes, webcam_name, webcam_bytes)
                        await self._send_photo_to_admins(
                            webcam_bytes,
                            webcam_name,
                            f'📸 <b>Планировщик:</b> веб-камера по задаче <code>{job.job_id}</code>\n<code>{html.escape(webcam_path.name)}</code>{note_block}',
                        )
                        self._record_runtime_activity('last_webcam', 'планировщик отчет')

                    try:
                        audio_bytes, audio_name = await asyncio.to_thread(record_audio, 5)
                    except Exception as exc:
                        await self._notify_admins(
                            f'❌ <b>Планировщик:</b> микрофон недоступен для задачи <code>{job.job_id}</code>\n'
                            f'<code>{html.escape(str(exc))}</code>{note_block}'
                        )
                    else:
                        audio_path = await asyncio.to_thread(self._save_artifact_bytes, audio_name, audio_bytes)
                        await self._send_audio_to_admins(
                            audio_bytes,
                            audio_name,
                            f'🎙 <b>Планировщик:</b> окружение 5с по задаче <code>{job.job_id}</code>\n<code>{html.escape(audio_path.name)}</code>{note_block}',
                        )
                    continue

                if action == 'music':
                    music_text, thumb_bytes = await get_now_playing()
                    caption = f'🎵 <b>Планировщик:</b> музыка по задаче <code>{job.job_id}</code>\n{music_text}{note_block}'
                    if thumb_bytes:
                        await self._send_photo_to_admins(thumb_bytes, 'cover.jpg', caption)
                    else:
                        await self._notify_admins(caption)
                    continue

                if action in {'playpause', 'nexttrack', 'prevtrack'}:
                    from .input_actions import press_media_key

                    key_code = {
                        'playpause': 0xB3,
                        'nexttrack': 0xB0,
                        'prevtrack': 0xB1,
                    }[action]
                    await asyncio.to_thread(press_media_key, key_code)
                    continue

                if action == 'webcam':
                    photo_bytes, file_name = await asyncio.to_thread(capture_webcam_photo)
                    saved_path = await asyncio.to_thread(self._save_artifact_bytes, file_name, photo_bytes)
                    await self._send_photo_to_admins(
                        photo_bytes,
                        file_name,
                        f'📸 <b>Планировщик:</b> фото с вебки по задаче <code>{job.job_id}</code>\n<code>{html.escape(saved_path.name)}</code>{note_block}',
                    )
                    self._record_runtime_activity('last_webcam', 'планировщик фото')
                    continue

                if action == 'webcamvid':
                    duration = action_value or 5
                    video_bytes, file_name = await asyncio.to_thread(capture_webcam_video, duration)
                    saved_path = await asyncio.to_thread(self._save_artifact_bytes, file_name, video_bytes)
                    await self._send_video_to_admins(
                        video_bytes,
                        file_name,
                        f'🎥 <b>Планировщик:</b> видео с вебки {duration}с по задаче <code>{job.job_id}</code>\n<code>{html.escape(saved_path.name)}</code>{note_block}',
                    )
                    self._record_runtime_activity('last_webcam', f'планировщик видео {duration}с')
                    continue

                if action == 'audio':
                    duration = action_value or 5
                    audio_bytes, file_name = await asyncio.to_thread(record_audio, duration)
                    saved_path = await asyncio.to_thread(self._save_artifact_bytes, file_name, audio_bytes)
                    await self._send_audio_to_admins(
                        audio_bytes,
                        file_name,
                        f'🎙 <b>Планировщик:</b> аудио {duration}с по задаче <code>{job.job_id}</code>\n<code>{html.escape(saved_path.name)}</code>{note_block}',
                    )
                    continue

                if action == 'cancelshutdown':
                    cancelled_hibernate = False
                    if self._hibernate_task and not self._hibernate_task.done():
                        self._hibernate_task.cancel()
                        self._hibernate_task = None
                        cancelled_hibernate = True

                    result = await asyncio.to_thread(cancel_scheduled_power_action)
                    if result.code == 'not_pending':
                        message = 'Таймер гибернации отменён.' if cancelled_hibernate else 'Нечего отменять: отложенное выключение или ребут не были запланированы.'
                    elif cancelled_hibernate:
                        message = 'Отложенное выключение/ребут и таймер гибернации отменены.'
                    else:
                        message = result.message
                    self.log_message.emit(message)
                    continue

                if action == 'lock':
                    result = await asyncio.to_thread(lock_workstation)
                    self.log_message.emit(result.message)
                    continue

                if action in disruptive_actions:
                    final_text = (
                        f'✅ <b>Планировщик:</b> задача <code>{job.job_id}</code> выполнена.\n'
                        f'Действия: <code>{html.escape(actions_text)}</code>{note_block}'
                    )
                    await self._edit_messages_for_admins(status_refs, final_text, reply_markup=self._dismiss_markup())
                    await asyncio.sleep(0.5)
                    if action == 'shutdown':
                        result = await asyncio.to_thread(schedule_shutdown, 0)
                    elif action == 'reboot':
                        result = await asyncio.to_thread(schedule_reboot, 0)
                    elif action == 'hibernate':
                        result = await asyncio.to_thread(hibernate_system)
                    else:
                        result = await asyncio.to_thread(sleep_system)
                    self.log_message.emit(result.message)
                    return
        except Exception:
            error_text = f'❌ <b>Планировщик:</b> задача <code>{job.job_id}</code> завершилась ошибкой.{note_block}'
            self._record_runtime_error(error_text)
            await self._edit_messages_for_admins(status_refs, error_text, reply_markup=self._dismiss_markup())
            raise

        final_text = (
            f'✅ <b>Планировщик:</b> задача <code>{job.job_id}</code> выполнена.\n'
            f'Действия: <code>{html.escape(actions_text)}</code>{note_block}'
        )
        await self._edit_messages_for_admins(status_refs, final_text, reply_markup=self._dismiss_markup())

    def _save_artifact_bytes(self, file_name: str, payload: bytes) -> Path:
        target_dir = Path(LOG_FILE).parent / 'scheduled_artifacts'
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / file_name
        target_path.write_bytes(payload)
        return target_path

    def _save_log_snapshot(self, job_id: str) -> Path:
        source_path = Path(LOG_FILE)
        if not source_path.exists():
            raise RuntimeError('Лог-файл ещё не создан.')
        target_dir = source_path.parent / 'scheduled_artifacts'
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        target_path = target_dir / f'log_{job_id}_{stamp}.log'
        target_path.write_bytes(source_path.read_bytes())
        return target_path

    async def _send_message_to_admins(
            self,
            text: str,
            reply_markup: InlineKeyboardMarkup | None = None,
    ) -> list[tuple[int | str, int]]:
        application = self._application
        if application is None:
            return []
        sent_refs: list[tuple[int | str, int]] = []
        for admin_id in self._config_provider().admins.keys():
            try:
                message = await application.bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    read_timeout=60,
                    write_timeout=60,
                )
                sent_refs.append((admin_id, message.message_id))
            except Exception as exc:
                self.log_message.emit(f'Failed to send scheduled status to admin {admin_id}: {exc}')
        return sent_refs

    async def _edit_messages_for_admins(
            self,
            refs: list[tuple[int | str, int]],
            text: str,
            reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        application = self._application
        if application is None:
            return
        for admin_id, message_id in refs:
            try:
                await application.bot.edit_message_text(
                    chat_id=admin_id,
                    message_id=message_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    read_timeout=60,
                    write_timeout=60,
                )
            except Exception as exc:
                self.log_message.emit(f'Failed to update scheduled status for admin {admin_id}: {exc}')

    async def _send_photo_to_admins(self, payload: bytes, file_name: str, caption: str) -> None:
        application = self._application
        if application is None:
            return
        for admin_id in self._config_provider().admins.keys():
            try:
                await application.bot.send_photo(
                    chat_id=admin_id,
                    photo=InputFile(BytesIO(payload), filename=file_name),
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=self._dismiss_markup(),
                    read_timeout=60,
                    write_timeout=60,
                )
            except Exception as exc:
                self.log_message.emit(f'Failed to send scheduled photo to admin {admin_id}: {exc}')

    async def _send_video_to_admins(self, payload: bytes, file_name: str, caption: str) -> None:
        application = self._application
        if application is None:
            return
        for admin_id in self._config_provider().admins.keys():
            try:
                await application.bot.send_video(
                    chat_id=admin_id,
                    video=InputFile(BytesIO(payload), filename=file_name),
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=self._dismiss_markup(),
                    read_timeout=120,
                    write_timeout=120,
                )
            except Exception as exc:
                self.log_message.emit(f'Failed to send scheduled video to admin {admin_id}: {exc}')

    async def _send_document_to_admins(self, payload: bytes, file_name: str, caption: str) -> None:
        application = self._application
        if application is None:
            return
        for admin_id in self._config_provider().admins.keys():
            try:
                await application.bot.send_document(
                    chat_id=admin_id,
                    document=InputFile(BytesIO(payload), filename=file_name),
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=self._dismiss_markup(),
                    read_timeout=60,
                    write_timeout=60,
                )
            except Exception as exc:
                self.log_message.emit(f'Failed to send scheduled document to admin {admin_id}: {exc}')

    async def _send_audio_to_admins(self, payload: bytes, file_name: str, caption: str) -> None:
        application = self._application
        if application is None:
            return
        for admin_id in self._config_provider().admins.keys():
            try:
                await self._send_voice_note(
                    audio_bytes=payload,
                    file_name=file_name,
                    caption=caption,
                    bot=application.bot,
                    chat_id=admin_id,
                    reply_markup=self._dismiss_markup(),
                    read_timeout=120,
                    write_timeout=120,
                )
            except Exception as exc:
                self.log_message.emit(f'Failed to send scheduled audio to admin {admin_id}: {exc}')

    async def _show_autoaccept_menu(self, query) -> None:
        await self._edit_panel_message(query, self._autoaccept_menu_text(), self._autoaccept_menu_markup())
        self._aa_menu_messages[query.message.chat_id] = query.message.message_id

    def _autoaccept_menu_text(self) -> str:
        timeout = self._format_autoaccept_timeout(self._current_autoaccept_timeout())
        state = '\u0432\u043a\u043b\u044e\u0447\u0435\u043d' if self._auto_accept_service.active else '\u0432\u044b\u043a\u043b\u044e\u0447\u0435\u043d'
        return (
            '\U0001f916 <b>\u0423\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 AutoAccept</b>\n\n'
            '\u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u0435 \u0441\u043a\u0440\u0438\u043d\u0448\u043e\u0442\u044b \u0448\u0430\u0431\u043b\u043e\u043d\u043e\u0432 \u0434\u043b\u044f \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u043e\u0433\u043e \u043f\u043e\u0438\u0441\u043a\u0430 \u0438 \u043a\u043b\u0438\u043a\u0430 \u043d\u0430 \u044d\u043a\u0440\u0430\u043d\u0435.\n'
            f'\u23f1 <b>\u0410\u0432\u0442\u043e\u0432\u044b\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435:</b> <code>{html.escape(timeout)}</code>\n'
            f'\U0001f4e1 <b>\u0421\u0442\u0430\u0442\u0443\u0441:</b> <code>{state}</code>'
        )

    def _autoaccept_menu_markup(self) -> InlineKeyboardMarkup:
        is_active = self._auto_accept_service.active
        current_timeout = self._current_autoaccept_timeout()

        def timeout_button(label: str, seconds: int) -> InlineKeyboardButton:
            prefix = '\u2705 ' if current_timeout == seconds else ''
            return InlineKeyboardButton(f'{prefix}{label}', callback_data=f'panel:aa:timeout:{seconds}')

        toggle_btn = InlineKeyboardButton('\u23f9 \u0412\u044b\u043a\u043b\u044e\u0447\u0438\u0442\u044c AutoAccept',
                                          callback_data='panel:input:autoaccept:off') if is_active else InlineKeyboardButton(
            '\u25b6\ufe0f \u0412\u043a\u043b\u044e\u0447\u0438\u0442\u044c AutoAccept', callback_data='panel:input:autoaccept:on')
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('\U0001f4f8 \u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0441\u043a\u0440\u0438\u043d\u0448\u043e\u0442', callback_data='panel:aa:upload')],
            [InlineKeyboardButton('\U0001f4c2 \u0421\u043f\u0438\u0441\u043e\u043a \u0448\u0430\u0431\u043b\u043e\u043d\u043e\u0432', callback_data='panel:aa:ls'),
             InlineKeyboardButton('\U0001f5d1 \u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c \u0432\u0441\u0451', callback_data='panel:aa:clear')],
            [timeout_button('1\u043c', 60), timeout_button('5\u043c', 300), timeout_button('10\u043c', 600)],
            [timeout_button('30\u043c', 1800), timeout_button('60\u043c', 3600),
             InlineKeyboardButton('\u270f\ufe0f \u0421\u0432\u043e\u0435', callback_data='panel:aa:timeout:custom')],
            [toggle_btn], [InlineKeyboardButton('\u2b05\ufe0f \u041d\u0430\u0437\u0430\u0434', callback_data='panel:input')]
        ])

    @staticmethod
    def _aa_timeout_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[InlineKeyboardButton('\u2b05\ufe0f \u041d\u0430\u0437\u0430\u0434', callback_data='panel:aa:main')]])

    def _aa_timeout_text(self) -> str:
        timeout = self._format_autoaccept_timeout(self._current_autoaccept_timeout())
        return (
            '\u23f1 <b>\u0422\u0430\u0439\u043c\u0430\u0443\u0442 AutoAccept</b>\n\n'
            f'\u0421\u0435\u0439\u0447\u0430\u0441: <code>{html.escape(timeout)}</code>\n'
            '\u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0432\u0440\u0435\u043c\u044f \u043e\u0434\u043d\u0438\u043c \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435\u043c.\n'
            '<i>\u041f\u0440\u0438\u043c\u0435\u0440\u044b: 600, 10m, 30m, 1h</i>\n'
            '\u0414\u043e\u043f\u0443\u0441\u0442\u0438\u043c\u044b\u0439 \u0434\u0438\u0430\u043f\u0430\u0437\u043e\u043d: <code>10..3600</code> \u0441\u0435\u043a.'
        )

    @staticmethod
    def _aa_listing_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('📸 Загрузить шаблон', callback_data='panel:aa:upload')],
            [InlineKeyboardButton('⬅️ Назад', callback_data='panel:aa:main')],
        ])

    @staticmethod
    def _aa_upload_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[InlineKeyboardButton('❌ Отменить', callback_data='panel:aa:cancelupload')]])

    @staticmethod
    def _aa_upload_text(awaiting_name: bool = False) -> str:
        if awaiting_name:
            return (
                '✏️ <b>Шаблон загружен.</b>\n'
                'Теперь отправьте одним сообщением имя шаблона.\n'
                '<i>Пример: accept_btn</i>'
            )
        return (
            '📸 <b>Отправь скриншот/шаблон как фото или файл.</b>\n'
            'Он будет сохранен для AutoAccept.'
        )

    async def _refresh_aa_listing_message(self, user_id: int) -> None:
        application = self._application
        message_id = self._aa_list_msg_id_by_user.get(user_id)
        if application is None or message_id is None:
            return
        try:
            bot_username = application.bot.username
            text = await asyncio.to_thread(self._build_aa_listing_text, self._autoaccept_template_dir(), bot_username)
            await application.bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=text,
                reply_markup=self._aa_listing_markup(),
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:
            if 'Message is not modified' not in str(exc):
                self.log_message.emit(f'Failed to refresh AutoAccept listing for {user_id}: {exc}')
                self._aa_list_msg_id_by_user.pop(user_id, None)

    # === НАЧАЛО НОВЫХ ФУНКЦИЙ ГОЛОСА, ОВЕРЛЕЯ И ОХРАНЫ ===
    async def _start_overlay_timer(self, total_seconds: int, title: str, tid: str):
        target_time = time.time() + total_seconds
        self._timer_targets[tid] = target_time
        try:
            first_tick = True
            while True:
                if not self._running: break
                now = time.time()
                remaining = target_time - now
                if remaining <= 0:
                    break

                # Если сейчас не показывается уведомление о завершении другого таймера
                if getattr(self, '_overlay_pause_until', 0) < now and self._timer_targets:
                    # Ищем таймер, у которого время завершения самое маленькое
                    closest_tid = min(self._timer_targets.keys(), key=lambda k: self._timer_targets[k])

                    # Если ЭТОТ таймер самый ближний - он обновляет экран!
                    if closest_tid == tid:
                        mins, secs = divmod(int(remaining), 60)
                        hours, mins = divmod(mins, 60)
                        time_str = f"{hours:02d}:{mins:02d}:{secs:02d}" if hours > 0 else f"{mins:02d}:{secs:02d}"

                        display_title = title
                        if len(display_title) > 25:
                            display_title = display_title[:25] + "..."

                        self.overlay_show_signal.emit(f"⏳ {display_title}:<br>{time_str}", "top-right", first_tick)
                        first_tick = False

                await asyncio.sleep(1)

            if not self._running: return

            # Таймер завершен! Делаем паузу на 5 секунд, чтобы сообщение повисело
            self._overlay_pause_until = time.time() + 5
            self.overlay_show_signal.emit(f"✅ <b>{title}</b> завершен!", "center", True)

            # --- ВОСПРОИЗВЕДЕНИЕ ЗВУКА ---
            try:
                import winsound
                # Асинхронно проигрываем системный звук "Внимание" (SystemAsterisk)
                winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
            except Exception:
                pass
            # -----------------------------

            from .input_actions import speak_text
            await asyncio.to_thread(speak_text, f"{title} завершен")
            await asyncio.sleep(5)

            # Если после паузы больше нет активных таймеров, прячем оверлей
            if not self._timer_targets:
                self.overlay_hide_signal.emit()

        except asyncio.CancelledError:
            pass
        finally:
            self._timer_targets.pop(tid, None)

    def _on_security_motion(self, video_bytes: bytes, audio_bytes: bytes | None = None):
        asyncio.run_coroutine_threadsafe(self._notify_motion(video_bytes, audio_bytes), self._loop)

    async def _notify_motion(self, video_bytes: bytes, audio_bytes: bytes | None = None):
        text = "🚨 <b>ВНИМАНИЕ! ЗАМЕЧЕНО ДВИЖЕНИЕ!</b> 🚨\n<i>Запись 3с до и 5с после. Охрана автоматически выключена.</i>"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton('👌 Закрыть', callback_data='panel:dismiss')]])

        for admin_id in self._config_provider().admins.keys():
            try:
                async def _send_motion_video():
                    stream = BytesIO(video_bytes)
                    stream.name = 'alert.mp4'
                    return await self._application.bot.send_video(
                        chat_id=admin_id,
                        video=stream,
                        caption=text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=markup,
                        read_timeout=300,
                        write_timeout=300,
                        connect_timeout=60,
                    )

                await self._run_telegram_call_with_retry(
                    f'motion video notify for admin {admin_id}',
                    _send_motion_video,
                    attempts=4,
                    base_delay=5.0,
                )
                if audio_bytes:
                    await self._send_voice_note(
                        bot=self._application.bot,
                        chat_id=int(admin_id),
                        audio_bytes=audio_bytes,
                        file_name='alert_audio.wav',
                        caption="🎙 <b>Звук с места событий (8 сек)</b>",
                        reply_markup=self._dismiss_markup(),
                        read_timeout=300,
                        write_timeout=300,
                    )
            except Exception as exc:
                self.log_message.emit(f'Failed to notify admin {admin_id} about motion: {exc}')
        await self._refresh_media_menus()

    async def _try_handle_extended_voice_command(
            self,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
            text: str,
    ) -> bool:
        cleaned = ' '.join(str(text or '').lower().replace('ё', 'е').split())

        def has_any(*phrases: str) -> bool:
            return any(phrase in cleaned for phrase in phrases)

        def tail_after(*markers: str) -> str:
            for marker in markers:
                marker_clean = ' '.join(str(marker).lower().replace('ё', 'е').split())
                if cleaned == marker_clean:
                    return ''
                if cleaned.startswith(marker_clean + ' '):
                    return cleaned[len(marker_clean):].strip(' ,.:;!?')
                index = cleaned.find(marker_clean)
                if index >= 0:
                    return cleaned[index + len(marker_clean):].strip(' ,.:;!?')
            return ''

        ocr_query = tail_after('найди на экране', 'ищи на экране', 'поиск на экране')
        if ocr_query:
            await self._command_ocr(update, self._clone_context_with_args(context, ocr_query.split()))
            return True

        if has_any('прочитай экран', 'распознай экран', 'ocr экран', 'сделай ocr', 'сделай окр', 'ocr'):
            await self._command_ocr(update, self._clone_context_with_args(context, []))
            return True

        clipboard_text = tail_after('скопируй в буфер', 'запиши в буфер', 'установи буфер', 'положи в буфер')
        if clipboard_text:
            await self._command_clip(update, self._clone_context_with_args(context, clipboard_text.split()))
            return True

        if has_any('история буфера', 'историю буфера'):
            await self._command_clip_history(update, self._clone_context_with_args(context, []))
            return True

        if has_any('буфер обмена', 'покажи буфер', 'что в буфере'):
            await self._command_clip(update, self._clone_context_with_args(context, []))
            return True

        if has_any('живые окна', 'список окон', 'покажи окна', 'активные окна'):
            await self._command_windows(update, self._clone_context_with_args(context, []))
            return True

        process_filter = ''
        if cleaned == 'процессы' or cleaned == 'тасклист':
            process_filter = ''
        elif cleaned.startswith('процессы '):
            process_filter = cleaned[len('процессы '):].strip()
        elif cleaned.startswith('тасклист '):
            process_filter = cleaned[len('тасклист '):].strip()
        elif has_any('список процессов', 'покажи процессы'):
            process_filter = tail_after('список процессов', 'покажи процессы')
        if cleaned in {'процессы', 'тасклист'} or has_any('список процессов', 'покажи процессы') or cleaned.startswith('процессы ') or cleaned.startswith('тасклист '):
            args = process_filter.split() if process_filter else []
            await self._command_tasklist(update, self._clone_context_with_args(context, args))
            return True

        if has_any('железо', 'датчики', 'температуры', 'температура'):
            await self._command_hw(update, self._clone_context_with_args(context, []))
            return True

        if has_any('аптайм', 'время работы', 'сколько работает'):
            await self._command_uptime(update, self._clone_context_with_args(context, []))
            return True

        if has_any('пинг', 'проверь связь', 'есть связь'):
            await self._command_ping(update, self._clone_context_with_args(context, []))
            return True

        if has_any('отмени выключение', 'отмена выключения', 'отмени перезагрузку', 'отмена перезагрузки'):
            await self._command_cancel_shutdown(update, self._clone_context_with_args(context, []))
            return True

        if has_any('анти афк', 'anti afk', 'antiafk'):
            if has_any('выключи', 'выруби', 'стоп', 'останови'):
                await self._command_antiafk_off(update, self._clone_context_with_args(context, []))
            else:
                await self._command_antiafk_on(update, self._clone_context_with_args(context, []))
            return True

        if has_any('задачи планировщика', 'список задач', 'покажи задачи', 'планировщик задачи'):
            await self._command_jobs(update, self._clone_context_with_args(context, []))
            return True

        return False

    async def _handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update): return
        msg = update.effective_message
        if not msg.voice: return

        status_msg = await self._send_temporary_status(update, "⏳ <b>Распознаю голос...</b>")
        try:
            import speech_recognition as sr
        except Exception as exc:
            await status_msg.edit_text(f"❌ <b>Ошибка голоса:</b> {exc}", parse_mode=ParseMode.HTML,
                                       reply_markup=self._dismiss_markup())
            return

        ogg_path = Path("temp_voice.ogg")
        wav_path = Path("temp_voice.wav")
        try:
            file = await msg.voice.get_file()
            await file.download_to_drive(ogg_path)

            import soundfile as sf
            data, samplerate = await asyncio.to_thread(sf.read, str(ogg_path))
            await asyncio.to_thread(sf.write, str(wav_path), data, samplerate)

            r = sr.Recognizer()
            with sr.AudioFile(str(wav_path)) as source:
                audio = await asyncio.to_thread(r.record, source)
            text = await asyncio.to_thread(r.recognize_google, audio, language="ru-RU")

            text = text.lower()
            # Заменяем статус-сообщение на распознанный текст (чтобы ты видел, что он услышал)
            await status_msg.edit_text(f"🗣 <b>Голос:</b> <i>{text}</i>", parse_mode=ParseMode.HTML, reply_markup=self._dismiss_markup())

            # --- Умный парсинг всех команд ---
            if await self._try_handle_extended_voice_command(update, context, text):
                return

            if "таймер" in text:
                import re
                match = re.search(r'(\d+)\s*(мин|час|сек)', text)
                if match:
                    val = int(match.group(1))
                    if 'час' in match.group(2): val *= 60
                    self._timer_counter = getattr(self, '_timer_counter', 0) + 1
                    tid = f"t_{self._timer_counter}"
                    task = asyncio.create_task(self._start_overlay_timer(val * 60, "Таймер", tid))
                    self._active_timers[tid] = (task, f"⏳ Таймер {val} мин")
                    task.add_done_callback(lambda t, timer_id=tid: self._active_timers.pop(timer_id, None))
                    await self._safe_reply(update, f"⏱ Таймер на {val} мин запущен на экране.", dismissable=True)
                else:
                    await self._safe_reply(update, "⚠️ Не понял время. Скажи: 'Таймер 5 минут'.", dismissable=True)
            elif "напомни" in text:
                parts = text.split("напомни", 1)
                reminder = parts[1].strip() if len(parts) > 1 else "Напоминание!"
                self.overlay_show_signal.emit(f"📌 Напоминание:<br>{reminder.capitalize()}", "center", True)
                await self._safe_reply(update, "📌 Напоминание выведено на экран.", dismissable=True)
            elif "убери" in text or "скрой" in text:
                self.overlay_hide_signal.emit()
                await self._safe_reply(update, "👀 Оверлей скрыт.", dismissable=True)
            elif "скриншот" in text or "снимок экрана" in text:
                await self._command_screenshot(update, context)
            elif "отчет" in text or "шпион" in text or "отчёт" in text:
                await self._command_report(update, context)
            elif ("стоп" in text or "останови" in text or "заверши" in text) and "стрим" in text:
                await self._command_stopstream(update, context)
            elif "стрим" in text or "трансляция" in text:
                await self._command_stream(update, context)
            elif "вебк" in text or "камер" in text or "фотк" in text:
                await self._command_webcam(update, context)
            elif "запиши звук" in text or "диктофон" in text or "микрофон" in text:
                await self._command_audio(update, context)
            elif "статус" in text or "состояние" in text or "как дела" in text:
                await self._command_status(update, context)
            elif "спящ" in text or "сон" in text:
                await self._command_sleep(update, context)
            elif "гибернац" in text:
                await self._command_hibernate(update, context)
            elif "заблокируй" in text or "блок" in text:
                await self._command_lock(update, context)
            elif "перезагрузи" in text or "рестарт" in text:
                cloned = self._clone_context_with_args(context, ['0'])
                await self._command_reboot(update, cloned)
            elif "выключи" in text and "комп" in text:
                cloned = self._clone_context_with_args(context, ['0'])
                await self._command_shutdown(update, cloned)
            elif "закрой окно" in text or "закрыть окно" in text:
                cloned = self._clone_context_with_args(context, ['alt', 'f4'])
                await self._command_combination(update, cloned)
            elif "сверни" in text:
                cloned = self._clone_context_with_args(context, ['win', 'd'])
                await self._command_combination(update, cloned)
            elif "напечатай" in text or "напиши" in text:
                parts = text.split(maxsplit=1)
                if len(parts) > 1 and parts[1].strip():
                    cloned = self._clone_context_with_args(context, parts[1].strip().split())
                    await self._command_printtext(update, cloned)
            elif "нажми" in text:
                parts = text.split("нажми", 1)
                if len(parts) > 1 and parts[1].strip():
                    keys_str = parts[1].strip()
                    keys_str = keys_str.replace("ентер", "enter").replace("пробел", "space").replace("эскейп", "esc")
                    keys_str = keys_str.replace("альт", "alt").replace("шифт", "shift").replace("контрол", "ctrl")
                    keys_str = keys_str.replace("таб", "tab").replace("виндовс", "win").replace("окно", "win")
                    cloned = self._clone_context_with_args(context, keys_str.split())
                    await self._command_combination(update, cloned)
            elif "клик" in text or "пкм" in text or "лкм" in text or "даблклик" in text or "дабл клик" in text:
                if "правый" in text or "пкм" in text:
                    await self._command_rightclick(update, context)
                elif "двойной" in text or "даблклик" in text or "дабл клик" in text:
                    await self._command_leftdoubleclick(update, context)
                else:
                    await self._command_leftclick(update, context)
            elif "автоприняти" in text or "автоаццепт" in text or "автоацепт" in text:
                if "выключи" in text or "стоп" in text or "останови" in text:
                    await self._command_autoaccept_off(update, context)
                else:
                    await self._command_autoaccept_on(update, context)
            elif "громче" in text or "прибавь звук" in text:
                cloned = self._clone_context_with_args(context, ['up'])
                await self._command_vol(update, cloned)
            elif "тише" in text or "убавь звук" in text:
                cloned = self._clone_context_with_args(context, ['down'])
                await self._command_vol(update, cloned)
            elif "без звука" in text or "заглуши" in text or "мут" in text:
                cloned = self._clone_context_with_args(context, ['mute'])
                await self._command_vol(update, cloned)
            elif "спотифай" in text or "музык" in text or "трек" in text or "песн" in text:
                if "следующ" in text or "дальше" in text:
                    await self._command_nexttrack(update, context)
                elif "предыдущ" in text or "прошл" in text or "назад" in text:
                    await self._command_prevtrack(update, context)
                elif "что" in text and ("играет" in text or "за" in text):
                    await self._command_music(update, context)
                else:
                    await self._command_playpause(update, context)
            elif "охрана" in text or "охран" in text:
                if "включи" in text or "вруби" in text or "активир" in text:
                    from .system_metrics import start_security
                    result = await asyncio.to_thread(start_security, self._on_security_motion)
                    await self._safe_reply(update, html.escape(result.message), dismissable=True)
                else:
                    from .system_metrics import stop_security
                    result = await asyncio.to_thread(stop_security)
                    await self._safe_reply(update, html.escape(result.message), dismissable=True)
                await self._refresh_media_menus()
            else:
                await self._safe_reply(update,
                                       "🤷‍♂️ <b>Команда не распознана.</b>\nПопробуй: <i>напечатай привет, нажми альт таб, автопринятие, гибернация, стрим...</i>",
                                       parse_mode=ParseMode.HTML, dismissable=True)

        except sr.UnknownValueError:
            await status_msg.edit_text("🤷‍♂️ <b>Речь не распознана. Повторите четче.</b>", parse_mode=ParseMode.HTML,
                                       reply_markup=self._dismiss_markup())
        except Exception as e:
            await status_msg.edit_text(f"❌ <b>Ошибка голоса:</b> {e}", parse_mode=ParseMode.HTML,
                                    reply_markup=self._dismiss_markup())
        finally:
            ogg_path.unlink(missing_ok=True)
            wav_path.unlink(missing_ok=True)

    async def _handle_panel_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None:
            return
        await query.answer()
        if not await self._ensure_admin(update):
            return

        data = str(query.data or '')
        user_id = getattr(update.effective_user, 'id', None)

        keep_media_tracking = data in {
            'panel:media',
            'panel:media:stream',
            'panel:media:report',
            'panel:media:sec_toggle',
            'panel:media:playpause',
            'panel:media:next',
            'panel:media:prev',
            'panel:media:mute',
            'panel:media:volup',
            'panel:media:voldown',
            'panel:media:webcam',
            'panel:media:webcamvid5',
            'panel:media:webcamvid15',
            'panel:media:webcamvid60',
            'panel:media:audio5',
            'panel:media:audio15',
            'panel:media:audio60',
        }
        if query.message and user_id is not None:
            tracked_media_msg_id = self._media_menu_msg_id_by_user.get(user_id)
            if data == 'panel:dismiss':
                self._clear_media_menu_tracking(user_id, query.message.message_id)
            elif tracked_media_msg_id == query.message.message_id and not keep_media_tracking:
                self._clear_media_menu_tracking(user_id, query.message.message_id)

        if data.startswith('panel:files') and not await self._ensure_admin(update, 'files'): return
        if data.startswith('panel:proc') and not await self._ensure_admin(update, 'process'): return
        if data.startswith('panel:win') and not await self._ensure_admin(update, 'process'): return
        if (data.startswith('panel:input') or data.startswith('panel:aa')) and not await self._ensure_admin(update,
                                                                                                            'input'): return
        if data.startswith('panel:cliphist') and not await self._ensure_admin(update, 'input'): return
        if data.startswith('panel:power') and not await self._ensure_admin(update, 'power'): return
        if data.startswith('panel:media') and not await self._ensure_admin(update, 'media'): return
        if (data.startswith('panel:ocr') or data.startswith('panel:sched')) and not await self._ensure_admin(update): return

        # Dismissal
        if data == 'panel:dismiss':
            try:
                await query.message.delete()
            except Exception:
                pass
            return

        # Navigation
        if data == 'panel:main':
            await self._edit_panel_message(query, self._panel_main_text(), self._panel_main_markup())
            return
        if data == 'panel:help':
            await self._edit_panel_message(query, self._panel_help_text(), self._panel_help_markup())
            return
        if data == 'panel:files':
            await self._edit_panel_message(query, self._panel_files_text(), self._panel_files_markup())
            return
        if data == 'panel:process':
            await self._edit_panel_message(query, self._panel_process_text(), self._panel_process_markup())
            return
        if data == 'panel:input':
            await self._edit_panel_message(query, self._panel_input_text(), self._panel_input_markup())
            return
        if data == 'panel:ocr':
            await self._edit_panel_message(query, self._ocr_menu_text(), self._ocr_menu_markup())
            return
        if data == 'panel:sched':
            self._menu_msg_id_by_user[update.effective_user.id] = query.message.message_id
            await self._edit_panel_message(query, self._scheduler_panel_text(), self._scheduler_panel_markup())
            return
        if data == 'panel:power':
            await self._edit_panel_message(query, self._panel_power_text(), self._panel_power_markup())
            return
        if data == 'panel:media':
            await self._restore_media_menu(update)
            return
        if data == 'panel:logs':
            await self._edit_panel_message(query, self._panel_logs_text(), self._panel_logs_markup())
            return
        if data == 'panel:aa:main':
            if self._pending_action_by_user.get(update.effective_user.id) == 'aa_timeout':
                self._pending_action_by_user.pop(update.effective_user.id, None)
            self._aa_list_msg_id_by_user.pop(update.effective_user.id, None)
            self._aa_upload_msg_id_by_user.pop(update.effective_user.id, None)
            await self._show_autoaccept_menu(query)
            return

        # Overview
        if data == 'panel:overview':
            snapshot = await asyncio.to_thread(
                collect_snapshot,
                len(self._config_provider().admins),
                self._config_provider().autostart,
                self._running,
            )
            text = (
                f"🌟 <b>Обзор системы</b> 🌟\n\n"
                f"💻 <b>Хост:</b> <code>{html.escape(snapshot.hostname)}</code> ({html.escape(snapshot.os_name)} {html.escape(snapshot.os_release)})\n"
                f"🌐 <b>Public IP:</b> <code>{html.escape(snapshot.ip_address)}</code>\n"
                f"🐍 <b>Python:</b> <code>{html.escape(snapshot.python_version)}</code>\n"
                f"🧠 <b>CPU:</b> <code>{snapshot.cpu_percent:.1f}%</code>\n"
                f"💽 <b>RAM:</b> <code>{snapshot.memory_percent:.1f}%</code>\n"
                f"💾 <b>Disk:</b> <code>{snapshot.disk_percent:.1f}%</code>\n"
                f"⏱ <b>Uptime:</b> <code>{format_uptime(snapshot.uptime_seconds)}</code>\n"
                f"👥 <b>Admins:</b> <code>{snapshot.admin_count}</code>\n"
                f"🚀 <b>Autostart:</b> {'🟢 ВКЛ' if snapshot.autostart_enabled else '🔴 ВЫКЛ'}\n"
                f"🤖 <b>Bot:</b> {'🟢 Работает' if snapshot.bot_running else '🔴 Остановлен'}"
            )
            markup = InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад', callback_data='panel:main')]])
            await self._edit_panel_message(query, text, markup)
            return

        if data == 'panel:screenshot':
            await self._command_screenshot(update, context)
            return
        if data == 'panel:ocr:screen':
            await self._run_screen_ocr(update, reply_markup=self._ocr_reply_markup())
            return
        if data == 'panel:ocr:find':
            self._pending_action_by_user[update.effective_user.id] = 'ocr_query'
            self._menu_msg_id_by_user[update.effective_user.id] = query.message.message_id
            markup = InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад', callback_data='panel:ocr')]])
            await self._edit_panel_message(query, '🔎 <b>Отправьте текст для поиска на текущем экране:</b>', markup)
            return

        if data == 'panel:sched:help':
            self._menu_msg_id_by_user[update.effective_user.id] = query.message.message_id
            await self._edit_panel_message(query, self._scheduler_help_text(), self._scheduler_help_markup())
            return
        if data == 'panel:sched:add':
            self._pending_action_by_user[update.effective_user.id] = 'schedule_create'
            self._menu_msg_id_by_user[update.effective_user.id] = query.message.message_id
            await self._edit_panel_message(query, self._scheduler_add_text(), self._scheduler_add_markup())
            return
        if data == 'panel:sched:list':
            self._menu_msg_id_by_user[update.effective_user.id] = query.message.message_id
            text, markup = self._build_scheduler_jobs_view(self._application.bot.username)
            await self._edit_panel_message(query, text, markup)
            return
        if data == 'panel:sched:clear':
            count = self._scheduler_store.clear()
            await query.answer(f'Удалено задач: {count}', show_alert=False)
            await self._edit_panel_message(query, self._scheduler_panel_text(), self._scheduler_panel_markup())
            return
        if data.startswith('panel:sched:cancel:'):
            job_id = data.split(':', 3)[-1]
            removed = self._scheduler_store.remove_job(job_id)
            await query.answer('Задача отменена.' if removed else 'Задача не найдена.', show_alert=False)
            text, markup = self._build_scheduler_jobs_view(self._application.bot.username)
            await self._edit_panel_message(query, text, markup)
            return

        # Files
        if data.startswith('panel:files:rm_yes:'):
            idx = int(data.split(':')[-1])
            user_id = update.effective_user.id
            items = self._dir_items_by_user.get(user_id, [])
            if 0 <= idx < len(items):
                try:
                    target = self._resolve_user_path(user_id, items[idx])
                    await asyncio.to_thread(self._remove_path, target, True)
                    await query.answer(f'Удалено: {items[idx]}', show_alert=False)
                except Exception as exc:
                    await query.answer(f'Ошибка: {exc}', show_alert=True)
            data = 'panel:files:ls'

        if data == 'panel:files:ls':
            user_id = update.effective_user.id
            self._menu_msg_id_by_user[user_id] = query.message.message_id
            try:
                target = self._resolve_user_path(user_id, None)
                bot_username = self._application.bot.username
                text, total_pages = await asyncio.to_thread(self._build_interactive_dir_page, user_id, target,
                                                            bot_username, 0)
                markup = self._files_list_markup(0, total_pages)
                await self._edit_panel_message(query, text, markup)
            except Exception as exc:
                await query.answer(f'Ошибка чтения: {exc}', show_alert=True)
            return

        if data.startswith('panel:files:page:'):
            page = int(data.split(':')[-1])
            user_id = update.effective_user.id
            try:
                target = self._resolve_user_path(user_id, None)
                bot_username = self._application.bot.username
                text, total_pages = await asyncio.to_thread(self._build_interactive_dir_page, user_id, target,
                                                            bot_username, page)
                markup = self._files_list_markup(page, total_pages)
                await self._edit_panel_message(query, text, markup)
            except Exception as exc:
                await query.answer(f'Ошибка: {exc}', show_alert=True)
            return

        if data == 'panel:files:pwd':
            await self._command_pwd(update, context)
            return
        if data == 'panel:files:drives':
            await self._command_drives(update, context)
            return
        if data == 'panel:files:upload':
            user_id = update.effective_user.id
            cwd = self._resolve_user_path(user_id, None)
            self._pending_upload_by_user[user_id] = cwd
            markup = InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад', callback_data='panel:files')]])
            await self._edit_panel_message(
                query,
                f'📤 <b>Режим загрузки включен для:</b>\n<code>{html.escape(str(cwd))}</code>\n\nПрикрепите документ или медиа в чат.',
                markup
            )
            return

        # AutoAccept File Management
        if data == 'panel:aa:upload':
            user_id = update.effective_user.id
            target = self._autoaccept_template_dir()
            self._pending_action_by_user.pop(user_id, None)
            self._pending_upload_by_user[user_id] = target
            self._aa_menu_messages.pop(query.message.chat_id, None)
            self._aa_list_msg_id_by_user.pop(user_id, None)
            self._aa_upload_msg_id_by_user[user_id] = query.message.message_id
            await self._edit_panel_message(query, self._aa_upload_text(), self._aa_upload_markup())
            return
        if data == 'panel:aa:cancelupload':
            user_id = update.effective_user.id
            self._pending_action_by_user.pop(user_id, None)
            self._pending_upload_by_user.pop(user_id, None)
            pending_template = self._pending_rename_by_user.pop(user_id, None)
            if pending_template and pending_template.exists():
                try:
                    pending_template.unlink()
                except Exception:
                    pass
            self._aa_upload_msg_id_by_user.pop(user_id, None)
            await self._show_autoaccept_menu(query)
            return
        if data == 'panel:aa:ls':
            try:
                user_id = update.effective_user.id
                self._pending_action_by_user.pop(user_id, None)
                self._aa_menu_messages.pop(query.message.chat_id, None)
                self._aa_upload_msg_id_by_user.pop(user_id, None)
                self._aa_list_msg_id_by_user[user_id] = query.message.message_id
                bot_username = self._application.bot.username
                text = await asyncio.to_thread(self._build_aa_listing_text, self._autoaccept_template_dir(), bot_username)
                await self._edit_panel_message(query, text, self._aa_listing_markup())
            except Exception as exc:
                await self._safe_reply(update, f'❌ Ошибка чтения: <code>{html.escape(str(exc))}</code>',
                                       parse_mode=ParseMode.HTML, dismissable=True)
            return
        if data == 'panel:aa:clear':
            target = self._autoaccept_template_dir()
            try:
                self._pending_action_by_user.pop(update.effective_user.id, None)
                for item in target.iterdir():
                    if item.is_file():
                        item.unlink()
                await self._refresh_aa_listing_message(update.effective_user.id)
                await self._safe_reply(update, '🗑 <b>Все шаблоны AutoAccept успешно очищены.</b>',
                                       parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)
            except Exception as exc:
                await self._safe_reply(update, f'❌ Ошибка очистки: <code>{html.escape(str(exc))}</code>',
                                       parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)
            return

        if data == 'panel:aa:timeout:custom':
            user_id = update.effective_user.id
            self._pending_action_by_user[user_id] = 'aa_timeout'
            self._menu_msg_id_by_user[user_id] = query.message.message_id
            self._aa_menu_messages.pop(query.message.chat_id, None)
            self._aa_list_msg_id_by_user.pop(user_id, None)
            self._aa_upload_msg_id_by_user.pop(user_id, None)
            await self._edit_panel_message(query, self._aa_timeout_text(), self._aa_timeout_markup())
            return
        if data.startswith('panel:aa:timeout:'):
            try:
                self._pending_action_by_user.pop(update.effective_user.id, None)
                timeout = self._set_autoaccept_timeout(int(data.rsplit(':', 1)[1]))
                await query.answer(f'⏱ Таймаут: {self._format_autoaccept_timeout(timeout)}', show_alert=False)
            except Exception as exc:
                await query.answer(f'❌ Ошибка: {exc}', show_alert=True)
            await self._show_autoaccept_menu(query)
            return

        # Processes & CMD
        if data == 'panel:proc:hw':
            await self._command_hw(update, context)
            return
        if data == 'panel:proc:hw:refresh':
            await self._command_hw(update, context)
            return
        if data == 'panel:proc:cmd':
            self._pending_action_by_user[update.effective_user.id] = 'cmd'
            self._menu_msg_id_by_user[update.effective_user.id] = query.message.message_id
            markup = InlineKeyboardMarkup([[InlineKeyboardButton('❌ Отменить', callback_data='panel:proc:cancel_cmd')]])
            await self._edit_panel_message(query,
                                           '💻 <b>Отправьте команду</b>, которую нужно выполнить в терминале (CMD/PowerShell):',
                                           markup)
            return
        if data == 'panel:proc:windows':
            user_id = update.effective_user.id
            self._menu_msg_id_by_user[user_id] = query.message.message_id
            bot_username = self._application.bot.username
            text, total_pages = await asyncio.to_thread(self._build_windows_page, bot_username, 0)
            markup = self._windows_list_markup(0, total_pages)
            await self._edit_panel_message(query, text, markup)
            return
        if data == 'panel:proc:cancel_cmd':
            self._pending_action_by_user.pop(update.effective_user.id, None)
            await self._edit_panel_message(query, self._panel_process_text(), self._panel_process_markup())
            return

        if data == 'panel:proc:list':
            user_id = update.effective_user.id
            self._process_filter_by_user[user_id] = ''
            self._menu_msg_id_by_user[user_id] = query.message.message_id
            try:
                bot_username = self._application.bot.username
                text, total_pages = await asyncio.to_thread(self._build_tasklist_page, '', bot_username, 0)
                markup = self._tasklist_markup(0, total_pages)
                await self._edit_panel_message(query, text, markup)
            except Exception as exc:
                await self._safe_reply(update, f'❌ Ошибка: {exc}', dismissable=True)
            return
        if data.startswith('panel:proc:page:'):
            page = int(data.split(':')[-1])
            user_id = update.effective_user.id
            self._menu_msg_id_by_user[user_id] = query.message.message_id
            filter_text = self._process_filter_by_user.get(user_id, '')
            try:
                bot_username = self._application.bot.username
                text, total_pages = await asyncio.to_thread(self._build_tasklist_page, filter_text, bot_username,
                                                            page)
                markup = self._tasklist_markup(page, total_pages)
                await self._edit_panel_message(query, text, markup)
            except Exception as exc:
                await self._safe_reply(update, f'❌ Ошибка: {exc}', dismissable=True)
            return
        if data.startswith('panel:proc:info:'):
            _, _, _, pid_str, page_str = data.split(':', 4)
            try:
                text = await asyncio.to_thread(self._process_detail_text, int(pid_str))
                markup = self._process_detail_markup(int(pid_str), int(page_str))
                await self._edit_panel_message(query, text, markup)
            except Exception as exc:
                await query.answer(str(exc), show_alert=True)
            return
        if data.startswith('panel:proc:kill:'):
            _, _, _, pid_str, page_str = data.split(':', 4)
            pid = int(pid_str)
            page = int(page_str)
            try:
                result = await asyncio.to_thread(self._terminate_pid, pid)
                await query.answer(result[:180], show_alert=False)
                user_id = update.effective_user.id
                filter_text = self._process_filter_by_user.get(user_id, '')
                bot_username = self._application.bot.username
                text, total_pages = await asyncio.to_thread(self._build_tasklist_page, filter_text, bot_username, page)
                markup = self._tasklist_markup(page, total_pages)
                await self._edit_panel_message(query, text, markup)
            except Exception as exc:
                await query.answer(str(exc), show_alert=True)
            return
        if data == 'panel:proc:search':
            self._pending_action_by_user[update.effective_user.id] = 'proc_search'
            self._menu_msg_id_by_user[update.effective_user.id] = query.message.message_id
            markup = InlineKeyboardMarkup([[InlineKeyboardButton('Отмена', callback_data='panel:proc:cancel_search')]])
            await self._edit_panel_message(query,
                                           '🔍 <b>Введите название процесса для поиска:</b>\n<i>Например: chrome или telegram</i>',
                                           markup)
            return

        if data == 'panel:proc:cancel_search':
            self._pending_action_by_user.pop(update.effective_user.id, None)
            bot_username = self._application.bot.username
            user_id = update.effective_user.id
            filter_text = self._process_filter_by_user.get(user_id, '')
            try:
                text, total_pages = await asyncio.to_thread(self._build_tasklist_page, filter_text, bot_username, 0)
                markup = self._tasklist_markup(0, total_pages)
                await self._edit_panel_message(query, text, markup)
            except Exception as exc:
                await self._safe_reply(update, f'❌ Ошибка: {exc}', dismissable=True)
            return

        # Media
        if data == 'panel:media:stream':
            cloned = self._clone_context_with_args(context, ['15'])
            await self._command_stream(update, cloned)
            return
        if data == 'panel:media:stream_stop':
            if self._request_live_stream_stop(update.effective_user.id):
                await query.answer('Останавливаю LIVE-стрим...', show_alert=False)
            else:
                await query.answer('LIVE-стрим уже завершен.', show_alert=False)
            return
        if data == 'panel:media:report':
            await self._command_report(update, context)
            return
        if data == 'panel:media:sec_toggle':
            if is_security_active():
                res = await asyncio.to_thread(stop_security)
                await query.answer(res.message, show_alert=False)
            else:
                res = await asyncio.to_thread(start_security, self._on_security_motion)
                await query.answer(res.message, show_alert=False)
            await self._restore_media_menu(update)
            await self._refresh_media_menus()
            return
        if data == 'panel:media:music':
            await self._command_music(update, context)
            return
        if data == 'panel:media:playpause':
            await self._command_playpause(update, context)
            return
        if data == 'panel:media:next':
            await self._command_nexttrack(update, context)
            return
        if data == 'panel:media:prev':
            await self._command_prevtrack(update, context)
            return
        if data == 'panel:media:mute':
            await self._command_mute(update, context)
            return
        if data == 'panel:media:volup':
            cloned = self._clone_context_with_args(context, ['up'])
            await self._command_vol(update, cloned)
            return
        if data == 'panel:media:voldown':
            cloned = self._clone_context_with_args(context, ['down'])
            await self._command_vol(update, cloned)
            return
        if data == 'panel:media:webcam':
            await self._command_webcam(update, context)
            return
        if data == 'panel:media:webcamvid5':
            cloned = self._clone_context_with_args(context, ['5'])
            await self._command_webcamvid(update, cloned)
            return
        if data == 'panel:media:webcamvid15':
            cloned = self._clone_context_with_args(context, ['15'])
            await self._command_webcamvid(update, cloned)
            return
        if data == 'panel:media:webcamvid60':
            cloned = self._clone_context_with_args(context, ['60'])
            await self._command_webcamvid(update, cloned)
            return
        if data == 'panel:media:audio5':
            cloned = self._clone_context_with_args(context, ['5'])
            await self._command_audio(update, cloned)
            return
        if data == 'panel:media:audio15':
            cloned = self._clone_context_with_args(context, ['15'])
            await self._command_audio(update, cloned)
            return
        if data == 'panel:media:audio60':
            cloned = self._clone_context_with_args(context, ['60'])
            await self._command_audio(update, cloned)
            return

        # Input & Mouse
        if data == 'panel:input:custom_text':
            self._pending_action_by_user[update.effective_user.id] = 'type'
            self._menu_msg_id_by_user[update.effective_user.id] = query.message.message_id
            markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton('❌ Отменить', callback_data='panel:input:cancel_text')]])
            await self._edit_panel_message(query, '✏️ <b>Отправь текст</b>, который нужно напечатать на ПК:', markup)
            return
        if data == 'panel:input:custom_combo':
            self._pending_action_by_user[update.effective_user.id] = 'combination'
            self._menu_msg_id_by_user[update.effective_user.id] = query.message.message_id
            markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton('❌ Отменить', callback_data='panel:input:cancel_text')]])
            await self._edit_panel_message(query, '🔠 <b>Отправь комбинацию клавиш</b> (например: win d, ctrl c):',
                                           markup)
            return
        if data == 'panel:input:msg':
            self._pending_action_by_user[update.effective_user.id] = 'message'
            self._menu_msg_id_by_user[update.effective_user.id] = query.message.message_id
            markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton('❌ Отменить', callback_data='panel:input:cancel_text')]])
            await self._edit_panel_message(query,
                                           '💬 <b>Отправьте текст</b>, который должен появиться во всплывающем окне на ПК:',
                                           markup)
            return
        if data == 'panel:input:voice':
            self._pending_action_by_user[update.effective_user.id] = 'voice'
            self._menu_msg_id_by_user[update.effective_user.id] = query.message.message_id
            markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton('❌ Отменить', callback_data='panel:input:cancel_text')]])
            await self._edit_panel_message(query, '🗣 <b>Отправьте текст</b>, который ПК должен произнести голосом:',
                                           markup)
            return
        if data == 'panel:input:clip':
            self._pending_action_by_user[update.effective_user.id] = 'clip_set'
            self._menu_msg_id_by_user[update.effective_user.id] = query.message.message_id
            text, markup = await self._build_clipboard_panel_view()
            await self._edit_panel_message(query, text, markup)
            return
        if data == 'panel:input:clip_get':
            self._pending_action_by_user[update.effective_user.id] = 'clip_set'
            self._menu_msg_id_by_user[update.effective_user.id] = query.message.message_id
            text, markup = await self._build_clipboard_panel_view()
            await self._edit_panel_message(query, text, markup)
            return
        if data == 'panel:input:clip_history':
            self._pending_action_by_user.pop(update.effective_user.id, None)
            text, markup = self._build_clipboard_history_page(0)
            await self._edit_panel_message(query, text, markup)
            return
        if data == 'panel:input:cancel_text':
            self._pending_action_by_user.pop(update.effective_user.id, None)
            await self._edit_panel_message(query, self._panel_input_text(), self._panel_input_markup())
            return
        if data == 'panel:input:showdesk':
            cloned = self._clone_context_with_args(context, ['win', 'd'])
            await self._command_combination(update, cloned)
            return
        if data == 'panel:input:alttab':
            cloned = self._clone_context_with_args(context, ['alt', 'tab'])
            await self._command_combination(update, cloned)
            return
        if data == 'panel:input:leftclick':
            await self._command_leftclick(update, context)
            return
        if data == 'panel:input:rightclick':
            await self._command_rightclick(update, context)
            return
        if data == 'panel:input:doubleclick':
            await self._command_leftdoubleclick(update, context)
            return
        if data == 'panel:input:middleclick':
            await self._command_middleclick(update, context)
            return
        if data == 'panel:input:righthold':
            await self._command_righthold(update, context)
            return

        if data == 'panel:input:antiafk:toggle':
            from .input_actions import is_anti_afk_active, start_anti_afk, stop_anti_afk
            active = is_anti_afk_active()
            if active:
                await asyncio.to_thread(stop_anti_afk)
                await query.answer("🛑 Anti-AFK выключен", show_alert=False)
            else:
                await asyncio.to_thread(start_anti_afk)
                await query.answer("🎮 Anti-AFK включен", show_alert=False)

            await self._edit_panel_message(query, self._panel_input_text(), self._panel_input_markup())
            return

        if data == 'panel:input:autoaccept:on':
            try:
                timeout = self._current_autoaccept_timeout()
                template_dir = self._autoaccept_template_dir()
                await asyncio.to_thread(
                    self._auto_accept_service.start,
                    AutoAcceptConfig(template_dir=template_dir, timeout_seconds=timeout),
                    self._handle_autoaccept_match,
                    self._handle_autoaccept_error,
                    self._handle_autoaccept_finish,
                )
                await query.answer("✅ AutoAccept запущен", show_alert=False)
            except Exception as exc:
                await query.answer(f"❌ Ошибка: {exc}", show_alert=True)
            await self._show_autoaccept_menu(query)
            return

        if data == 'panel:input:autoaccept:off':
            try:
                await asyncio.to_thread(self._auto_accept_service.stop)
                await query.answer("⏹ AutoAccept остановлен", show_alert=False)
            except Exception as exc:
                await query.answer(f"❌ Ошибка: {exc}", show_alert=True)
            await self._show_autoaccept_menu(query)
            return
        if data == 'panel:input:help':
            markup = InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад', callback_data='panel:input')]])
            await self._edit_panel_message(query, self._panel_input_help_text(), markup)
            return

        if data.startswith('panel:cliphist:page:'):
            page = int(data.split(':')[-1])
            text, markup = self._build_clipboard_history_page(page)
            await self._edit_panel_message(query, text, markup)
            return
        if data.startswith('panel:cliphist:view:'):
            _, _, _, entry_id, page_str = data.split(':', 4)
            text, markup = self._build_clipboard_entry_view(entry_id, int(page_str))
            await self._edit_panel_message(query, text, markup)
            return
        if data.startswith('panel:cliphist:restore:'):
            _, _, _, entry_id, page_str = data.split(':', 4)
            entry = self._clipboard_history.get(entry_id)
            if entry is None:
                await query.answer('Элемент истории не найден.', show_alert=False)
            else:
                result = await asyncio.to_thread(set_clipboard, entry.text)
                if result.ok:
                    self._clipboard_history.add_text(entry.text)
                await query.answer(result.message[:180], show_alert=False)
            text, markup = self._build_clipboard_entry_view(entry_id, int(page_str))
            await self._edit_panel_message(query, text, markup)
            return

        if data.startswith('panel:win:page:'):
            page = int(data.split(':')[-1])
            user_id = update.effective_user.id
            self._menu_msg_id_by_user[user_id] = query.message.message_id
            bot_username = self._application.bot.username
            text, total_pages = await asyncio.to_thread(self._build_windows_page, bot_username, page)
            markup = self._windows_list_markup(page, total_pages)
            await self._edit_panel_message(query, text, markup)
            return
        if data.startswith('panel:win:view:'):
            _, _, _, hwnd_str, page_str = data.split(':', 4)
            try:
                text = await asyncio.to_thread(self._window_detail_text, int(hwnd_str))
                markup = self._window_detail_markup(int(hwnd_str), int(page_str))
                await self._edit_panel_message(query, text, markup)
            except Exception as exc:
                await query.answer(str(exc), show_alert=True)
            return
        if data.startswith('panel:win:activate:'):
            _, _, _, hwnd_str, page_str = data.split(':', 4)
            try:
                result = await asyncio.to_thread(activate_window, int(hwnd_str))
                await query.answer(result.message[:180], show_alert=False)
                text = await asyncio.to_thread(self._window_detail_text, int(hwnd_str))
                markup = self._window_detail_markup(int(hwnd_str), int(page_str))
                await self._edit_panel_message(query, text, markup)
            except Exception as exc:
                await query.answer(str(exc), show_alert=True)
            return
        if data.startswith('panel:win:minimize:'):
            _, _, _, hwnd_str, page_str = data.split(':', 4)
            try:
                result = await asyncio.to_thread(minimize_window, int(hwnd_str))
                await query.answer(result.message[:180], show_alert=False)
                text = await asyncio.to_thread(self._window_detail_text, int(hwnd_str))
                markup = self._window_detail_markup(int(hwnd_str), int(page_str))
                await self._edit_panel_message(query, text, markup)
            except Exception as exc:
                await query.answer(str(exc), show_alert=True)
            return
        if data.startswith('panel:win:close:'):
            _, _, _, hwnd_str, page_str = data.split(':', 4)
            try:
                result = await asyncio.to_thread(close_window, int(hwnd_str))
                await query.answer(result.message[:180], show_alert=False)
                bot_username = self._application.bot.username
                text, total_pages = await asyncio.to_thread(self._build_windows_page, bot_username, int(page_str))
                markup = self._windows_list_markup(int(page_str), total_pages)
                await self._edit_panel_message(query, text, markup)
            except Exception as exc:
                await query.answer(str(exc), show_alert=True)
            return
        if data.startswith('panel:win:screenshot:'):
            _, _, _, hwnd_str, page_str = data.split(':', 4)
            hwnd = int(hwnd_str)
            page = int(page_str)
            try:
                await query.edit_message_text('⏳ <b>Делаю скрин окна...</b>', parse_mode=ParseMode.HTML)
                image_bytes, file_name = await asyncio.to_thread(capture_window_bytes_for_window, hwnd)
                await query.edit_message_text('⏳ <b>Отправка...</b>', parse_mode=ParseMode.HTML)
                if update.effective_chat:
                    await update.effective_chat.send_photo(
                        photo=InputFile(BytesIO(image_bytes), filename=file_name),
                        caption=f'🪟 <b>Скрин окна</b>\n<code>{html.escape(file_name)}</code>',
                        parse_mode=ParseMode.HTML,
                        reply_markup=self._close_markup(),
                        read_timeout=60,
                        write_timeout=60,
                    )
                self._record_runtime_activity('last_screenshot', 'окно')
                await query.answer('Скрин окна отправлен.', show_alert=False)
                text = await asyncio.to_thread(self._window_detail_text, hwnd)
                markup = self._window_detail_markup(hwnd, page)
                await self._edit_panel_message(query, text, markup)
            except Exception as exc:
                await query.answer(str(exc), show_alert=True)
                try:
                    text = await asyncio.to_thread(self._window_detail_text, hwnd)
                    markup = self._window_detail_markup(hwnd, page)
                    await self._edit_panel_message(query, text, markup)
                except Exception:
                    pass
            return
        if data.startswith('panel:win:ocr:'):
            _, _, _, hwnd_str, page_str = data.split(':', 4)
            await self._run_window_ocr(update, int(hwnd_str), int(page_str))
            return

        # Power
        if data == 'panel:power:lock':
            await self._command_lock(update, context)
            return
        if data == 'panel:power:sleep':
            await self._command_sleep(update, context)
            return
        if data == 'panel:power:hibernate':
            await self._command_hibernate(update, context)
            return
        if data == 'panel:power:hiber10':
            await self._execute_power_action(update, action='hibernate', delay=10)
            return
        if data == 'panel:power:hiber60':
            await self._execute_power_action(update, action='hibernate', delay=60)
            return
        if data == 'panel:power:hiber300':
            await self._execute_power_action(update, action='hibernate', delay=300)
            return
        if data == 'panel:power:shutdown10':
            await self._execute_power_action(update, action='shutdown', delay=10)
            return
        if data == 'panel:power:shutdown60':
            await self._execute_power_action(update, action='shutdown', delay=60)
            return
        if data == 'panel:power:shutdown300':
            await self._execute_power_action(update, action='shutdown', delay=300)
            return
        if data == 'panel:power:reboot10':
            await self._execute_power_action(update, action='reboot', delay=10)
            return
        if data == 'panel:power:reboot60':
            await self._execute_power_action(update, action='reboot', delay=60)
            return
        if data == 'panel:power:reboot300':
            await self._execute_power_action(update, action='reboot', delay=300)
            return
        if data == 'panel:power:cancel':
            await self._command_cancel_shutdown(update, context)
            return

        # Logs
        if data == 'panel:logs:tail40':
            text = await asyncio.to_thread(self._read_log_tail, 40)
            await self._safe_reply(update, f'🧾 <b>Логи:</b>\n<pre>{html.escape(text)}</pre>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
            return
        if data == 'panel:logs:tail100':
            text = await asyncio.to_thread(self._read_log_tail, 100)
            await self._safe_reply(update, f'🧾 <b>Логи:</b>\n<pre>{html.escape(text)}</pre>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
            return

        # Reminders & Timers
        if data == 'panel:input:reminders':
            await self._edit_panel_message(query, self._panel_reminders_text(), self._panel_reminders_markup())
            return

        if data == 'panel:rem:manage':
            buttons = []
            for tid, (task, desc) in self._active_timers.items():
                buttons.append([InlineKeyboardButton(f'❌ {desc}', callback_data=f'panel:rem:cancel:{tid}')])
            buttons.append([InlineKeyboardButton('⬅️ Назад', callback_data='panel:input:reminders')])
            text = "📋 <b>Активные таймеры и напоминания:</b>\nНажмите на любой для отмены." if self._active_timers else "🤷‍♂️ <b>Нет активных таймеров.</b>"
            await self._edit_panel_message(query, text, InlineKeyboardMarkup(buttons))
            return

        if data.startswith('panel:rem:cancel:'):
            tid = data.split(':')[-1]
            if tid in self._active_timers:
                task, desc = self._active_timers.pop(tid)
                task.cancel()
                self.overlay_hide_signal.emit()  # Сразу прячем зависший оверлей!
                await query.answer(f"Отменено: {desc}", show_alert=False)
            else:
                await query.answer("Уже завершен или не найден", show_alert=False)

            # Обновляем меню после удаления
            buttons = []
            for t_id, (t_task, t_desc) in self._active_timers.items():
                buttons.append([InlineKeyboardButton(f'❌ {t_desc}', callback_data=f'panel:rem:cancel:{t_id}')])
            buttons.append([InlineKeyboardButton('⬅️ Назад', callback_data='panel:input:reminders')])
            text = "📋 <b>Активные таймеры и напоминания:</b>\nНажмите на любой для отмены." if self._active_timers else "🤷‍♂️ <b>Нет активных таймеров.</b>"
            await self._edit_panel_message(query, text, InlineKeyboardMarkup(buttons))
            return

        if data == 'panel:rem:hide':
            # Убиваем таймеры
            for task, desc in list(self._active_timers.values()):
                task.cancel()
            self._active_timers.clear()
            self._timer_targets.clear()  # <- Добавляем очистку таргетов
            # Прячем окно
            self.overlay_hide_signal.emit()
            await query.answer("Оверлей скрыт, все таймеры отменены", show_alert=False)
            return

        if data == 'panel:rem:custom':
            self._pending_action_by_user[update.effective_user.id] = 'custom_remind'
            self._menu_msg_id_by_user[update.effective_user.id] = query.message.message_id
            markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton('❌ Отменить', callback_data='panel:rem:cancel_custom')]])  # Новая кнопка
            await self._edit_panel_message(query,
                                           '⏰ <b>Отправьте время и текст напоминания</b>\nФормат: <code>HH:MM Текст</code>\n<i>Пример: 15:30 Позвонить маме</i>',
                                           markup)
            return

            # Специальный обработчик отмены, который возвращает в меню Таймеров
        if data == 'panel:rem:cancel_custom':
            self._pending_action_by_user.pop(update.effective_user.id, None)
            await self._edit_panel_message(query, self._panel_reminders_text(), self._panel_reminders_markup())
            return

        if data.startswith('panel:rem:'):
            val = data.split(':')[-1]
            try:
                minutes = int(val)
                self._timer_counter = getattr(self, '_timer_counter', 0) + 1
                tid = f"t_{self._timer_counter}"
                task = asyncio.create_task(self._start_overlay_timer(minutes * 60, "Таймер", tid))
                desc = f"⏳ Таймер {minutes} мин"
                self._active_timers[tid] = (task, desc)
                task.add_done_callback(lambda t, timer_id=tid: self._active_timers.pop(timer_id, None))
                await query.answer(f"Таймер на {minutes} мин запущен", show_alert=False)
            except ValueError:
                pass
            return

        await self._safe_reply(update, '❌ Неизвестное действие панели.', dismissable=True, as_toast=True)

    async def _execute_power_action(self, update: Update, action: str, delay: int) -> None:
        try:
            if action == 'shutdown':
                result = await asyncio.to_thread(schedule_shutdown, delay)
                self.log_message.emit(result.message)
                await self._safe_reply(update, f'⏻ <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                       reply_markup=self._power_reply_markup())
            elif action == 'reboot':
                result = await asyncio.to_thread(schedule_reboot, delay)
                self.log_message.emit(result.message)
                await self._safe_reply(update, f'🔄 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                       reply_markup=self._power_reply_markup())
            elif action == 'hibernate':
                if self._hibernate_task and not self._hibernate_task.done():
                    self._hibernate_task.cancel()
                self._hibernate_task = asyncio.create_task(self._delayed_hibernate(update, delay))
                await self._safe_reply(update, f'⏳ <b>Гибернация запланирована через {delay} сек.</b>',
                                       parse_mode=ParseMode.HTML, reply_markup=self._power_reply_markup())
            else:
                raise ValueError('Unknown power action.')
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка действия: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, reply_markup=self._power_reply_markup())

    async def _delayed_hibernate(self, update: Update, delay: int) -> None:
        try:
            await asyncio.sleep(delay)
            result = await asyncio.to_thread(hibernate_system)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'❄️ <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   reply_markup=self._power_reply_markup())
        except asyncio.CancelledError:
            pass

    async def _edit_panel_message(self, query, text: str, markup: InlineKeyboardMarkup) -> None:
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        except Exception as e:
            if 'Message is not modified' in str(e):
                return  # Игнорируем ошибку, так как меню уже обновилось
            if query.message:
                await query.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)

    def _track_media_menu_message(self, user_id: int | None, message_id: int | None) -> None:
        if user_id is None or message_id is None:
            return
        self._media_menu_msg_id_by_user[user_id] = message_id

    def _clear_media_menu_tracking(self, user_id: int | None, message_id: int | None = None) -> None:
        if user_id is None:
            return
        tracked_message_id = self._media_menu_msg_id_by_user.get(user_id)
        if tracked_message_id is None:
            return
        if message_id is None or tracked_message_id == message_id:
            self._media_menu_msg_id_by_user.pop(user_id, None)

    async def _restore_media_menu(self, update: Update) -> None:
        user_id = getattr(update.effective_user, 'id', None)
        text = self._panel_media_text()
        markup = self._panel_media_markup()
        query = update.callback_query

        if query and query.message:
            try:
                message = await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
                if hasattr(message, 'message_id'):
                    self._track_media_menu_message(user_id, message.message_id)
                else:
                    self._track_media_menu_message(user_id, query.message.message_id)
                return
            except Exception as exc:
                if 'Message is not modified' in str(exc):
                    self._track_media_menu_message(user_id, query.message.message_id)
                    return

        if update.effective_chat:
            message = await update.effective_chat.send_message(text, reply_markup=markup, parse_mode=ParseMode.HTML)
            self._track_media_menu_message(user_id, getattr(message, 'message_id', None))

    async def _refresh_media_menus(self, user_ids: list[int] | None = None) -> None:
        if not self._application:
            return

        target_user_ids = user_ids or list(self._media_menu_msg_id_by_user.keys())
        text = self._panel_media_text()
        markup = self._panel_media_markup()

        for user_id in list(target_user_ids):
            msg_id = self._media_menu_msg_id_by_user.get(user_id)
            if not msg_id:
                continue
            try:
                await self._application.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=msg_id,
                    text=text,
                    reply_markup=markup,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as exc:
                if 'Message is not modified' in str(exc):
                    continue
                self._media_menu_msg_id_by_user.pop(user_id, None)

    @staticmethod
    def _is_retryable_telegram_error(exc: Exception) -> bool:
        if isinstance(exc, (TimedOut, NetworkError, RetryAfter)):
            return True
        text = str(exc).lower()
        return 'timed out' in text or 'timeout' in text

    async def _run_telegram_call_with_retry(
        self,
        operation_name: str,
        operation,
        *,
        attempts: int = 3,
        base_delay: float = 3.0,
    ):
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await operation()
            except Exception as exc:
                last_error = exc
                if attempt >= attempts or not self._is_retryable_telegram_error(exc):
                    raise
                retry_after = getattr(exc, 'retry_after', None)
                delay = float(retry_after) if retry_after else base_delay * attempt
                self.log_message.emit(
                    f'{operation_name} failed on attempt {attempt}/{attempts}: {exc}. Retry in {delay:.1f}s.'
                )
                await asyncio.sleep(delay)
        if last_error is not None:
            raise last_error

    async def _probe_telegram_api(self) -> None:
        application = self._application
        if application is None:
            raise RuntimeError('Telegram application is not initialized.')
        await application.bot.get_webhook_info(
            read_timeout=15,
            write_timeout=15,
            connect_timeout=10,
        )

    def _handle_polling_error(self, error: Exception) -> None:
        message = f'Telegram polling error: {error}'
        self._record_runtime_error(message)
        self.log_message.emit(f'⚠️ {message}')

    async def _send_live_stream_frame(
        self,
        chat,
        *,
        screenshot_bytes: bytes,
        file_name: str,
        caption_text: str,
    ):
        async def _send():
            return await chat.send_photo(
                photo=InputFile(BytesIO(screenshot_bytes), filename=file_name),
                caption=caption_text,
                parse_mode=ParseMode.HTML,
                reply_markup=self._stream_control_markup(),
                disable_notification=True,
                read_timeout=180,
                write_timeout=180,
                connect_timeout=60,
            )

        return await self._run_telegram_call_with_retry(
            'live stream frame send',
            _send,
            attempts=3,
            base_delay=2.0,
        )

    def _request_live_stream_stop(self, user_id: int | None) -> bool:
        if user_id is None:
            return False
        stop_event = self._live_stream_stop_events.get(user_id)
        if stop_event is not None and not stop_event.is_set():
            stop_event.set()
            return True

        task = self._live_stream_tasks.get(user_id)
        if task is not None and not task.done():
            task.cancel()
            return True

        return False

    @staticmethod
    def _build_voice_note(audio_bytes: bytes, file_name: str) -> BytesIO:
        import soundfile as sf

        source_stream = BytesIO(audio_bytes)
        source_stream.seek(0)
        data, sample_rate = sf.read(source_stream)

        output = BytesIO()
        last_error: Exception | None = None
        for subtype in ('OPUS', 'VORBIS'):
            try:
                output.seek(0)
                output.truncate(0)
                sf.write(output, data, sample_rate, format='OGG', subtype=subtype)
                output.seek(0)
                output.name = f'{Path(file_name).stem}.ogg'
                return output
            except Exception as exc:
                last_error = exc

        raise RuntimeError(f'Voice conversion failed: {last_error}')

    async def _send_voice_note(
        self,
        *,
        audio_bytes: bytes,
        file_name: str,
        caption: str,
        chat=None,
        bot=None,
        chat_id: int | str | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
        read_timeout: int = 300,
        write_timeout: int = 300,
    ) -> None:
        try:
            voice_stream = await asyncio.to_thread(self._build_voice_note, audio_bytes, file_name)
            voice_bytes = voice_stream.getvalue()
            voice_name = getattr(voice_stream, 'name', f'{Path(file_name).stem}.ogg')
        except Exception as exc:
            self.log_message.emit(f'Voice note conversion failed for {file_name}: {exc}')
            voice_bytes = audio_bytes
            voice_name = file_name

        def _build_payload() -> BytesIO:
            payload = BytesIO(voice_bytes)
            payload.name = voice_name
            return payload

        if chat is not None:
            async def _send_to_chat():
                return await chat.send_voice(
                    voice=_build_payload(),
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    read_timeout=read_timeout,
                    write_timeout=write_timeout,
                    connect_timeout=60,
                )

            await self._run_telegram_call_with_retry(
                f'voice note send to chat {getattr(chat, "id", "unknown")}',
                _send_to_chat,
                attempts=4,
                base_delay=4.0,
            )
            return

        if bot is None or chat_id is None:
            raise RuntimeError('Voice target is not specified.')

        async def _send_to_bot():
            return await bot.send_voice(
                chat_id=chat_id,
                voice=_build_payload(),
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                read_timeout=read_timeout,
                write_timeout=write_timeout,
                connect_timeout=60,
            )

        await self._run_telegram_call_with_retry(
            f'voice note send to chat {chat_id}',
            _send_to_bot,
            attempts=4,
            base_delay=4.0,
        )

    @staticmethod
    def _dismiss_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('👌', callback_data='panel:dismiss')]
        ])

    @staticmethod
    def _power_reply_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('⬅️ Назад', callback_data='panel:power')]
        ])

    @staticmethod
    def _stream_control_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('⏹ Завершить', callback_data='panel:media:stream_stop')]
        ])

    @staticmethod
    def _panel_main_text() -> str:
        return '🎛 <b>PC Controller Главное меню</b>\n\nВыберите нужный раздел для управления ПК:'

    @staticmethod
    def _panel_main_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('📊 Обзор', callback_data='panel:overview'),
             InlineKeyboardButton('🗂 Файлы', callback_data='panel:files')],
            [InlineKeyboardButton('⚙️ Процессы', callback_data='panel:process'),
             InlineKeyboardButton('⌨️ Ввод', callback_data='panel:input')],
            [InlineKeyboardButton('🔋 Питание', callback_data='panel:power'),
             InlineKeyboardButton('🎥 Медиа', callback_data='panel:media')],
            [InlineKeyboardButton('🔎 OCR', callback_data='panel:ocr'),
             InlineKeyboardButton('🗓 Планировщик', callback_data='panel:sched')],
            [InlineKeyboardButton('🧾 Логи', callback_data='panel:logs'),
             InlineKeyboardButton('❓ Помощь', callback_data='panel:help')],
            [InlineKeyboardButton('🖼 Скриншот', callback_data='panel:screenshot')]
        ])

    @staticmethod
    def _panel_files_text() -> str:
        return '🗂 <b>Файловая панель</b>\n\nБыстрые кнопки работают с текущей папкой внутри разрешённого каталога.'

    @staticmethod
    def _panel_files_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('📍 Текущая папка', callback_data='panel:files:pwd'),
             InlineKeyboardButton('📚 Список файлов', callback_data='panel:files:ls')],
            [InlineKeyboardButton('📤 Загрузить сюда', callback_data='panel:files:upload'),
             InlineKeyboardButton('💾 Список дисков', callback_data='panel:files:drives')],
            [InlineKeyboardButton('⬅️ Назад', callback_data='panel:main')]
        ])

    @staticmethod
    def _panel_process_text() -> str:
        return '⚙️ <b>Система и Процессы</b>\n\nУправление процессами, живыми окнами и доступ к системному терминалу.'

    @staticmethod
    def _panel_process_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('📋 Все процессы', callback_data='panel:proc:list')],
            [InlineKeyboardButton('🔎 Поиск процесса', callback_data='panel:proc:search')],
            [InlineKeyboardButton('💻 Терминал (CMD)', callback_data='panel:proc:cmd')],
            [InlineKeyboardButton('🪟 Живые окна', callback_data='panel:proc:windows')],
            [InlineKeyboardButton('🌡 Датчики и Железо', callback_data='panel:proc:hw')],
            [InlineKeyboardButton('⬅️ Назад', callback_data='panel:main')]
        ])

    @staticmethod
    def _tasklist_markup(page: int, total_pages: int) -> InlineKeyboardMarkup:
        safe_page = max(0, min(page, max(total_pages - 1, 0)))
        buttons = []
        nav_row = []
        if safe_page > 0:
            nav_row.append(InlineKeyboardButton('⬅️ Вверх', callback_data=f'panel:proc:page:{safe_page - 1}'))
        if safe_page < total_pages - 1:
            nav_row.append(InlineKeyboardButton('Вниз ➡️', callback_data=f'panel:proc:page:{safe_page + 1}'))

        if nav_row:
            buttons.append(nav_row)
        buttons.append([InlineKeyboardButton('🔎 Новый поиск', callback_data='panel:proc:search')])
        buttons.append([InlineKeyboardButton('⬅️ Назад', callback_data='panel:process')])
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def _panel_input_text() -> str:
        return '⌨️ <b>Ввод и управление</b>\n\nЭмуляция нажатий, управление мышью, буфер обмена, OCR и макросы.'

    @staticmethod
    def _panel_reminders_text() -> str:
        return '⏱ <b>Таймеры и Напоминания</b>\nВыберите готовый таймер или установите точное время.'

    @staticmethod
    def _panel_reminders_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('⏲ 1 мин', callback_data='panel:rem:1'),
             InlineKeyboardButton('⏲ 5 мин', callback_data='panel:rem:5'),
             InlineKeyboardButton('⏲ 15 мин', callback_data='panel:rem:15')],
            [InlineKeyboardButton('⏲ 30 мин', callback_data='panel:rem:30'),
             InlineKeyboardButton('⏲ 1 час', callback_data='panel:rem:60')],
            [InlineKeyboardButton('⏰ Точное напоминание', callback_data='panel:rem:custom')],
            [InlineKeyboardButton('📋 Управление активными', callback_data='panel:rem:manage')],
            [InlineKeyboardButton('❌ Отменить всё', callback_data='panel:rem:hide')],
            [InlineKeyboardButton('⬅️ Назад', callback_data='panel:input')]
        ])

    def _panel_input_markup(self) -> InlineKeyboardMarkup:
        from .input_actions import is_anti_afk_active
        is_afk = is_anti_afk_active()
        afk_btn = InlineKeyboardButton('🛑 Выкл Anti-AFK',callback_data='panel:input:antiafk:toggle') if is_afk \
            else InlineKeyboardButton('🎮 Вкл Anti-AFK', callback_data='panel:input:antiafk:toggle')

        return InlineKeyboardMarkup([
            [InlineKeyboardButton('✏️ Свой Текст', callback_data='panel:input:custom_text'),
             InlineKeyboardButton('🔠 Свои Клавиши', callback_data='panel:input:custom_combo')],
            [InlineKeyboardButton('💬 Всплывающее Сообщение', callback_data='panel:input:msg'),
             InlineKeyboardButton('🗣 Озвучить текст', callback_data='panel:input:voice')],
            [InlineKeyboardButton('⏲ Таймеры и Напоминания', callback_data='panel:input:reminders')],
            [InlineKeyboardButton('📋 Буфер обмена', callback_data='panel:input:clip')],
            [afk_btn],
            [InlineKeyboardButton('🖥 Свернуть окна', callback_data='panel:input:showdesk'),
             InlineKeyboardButton('🪟 Alt + Tab', callback_data='panel:input:alttab')],
            [InlineKeyboardButton('🖱 ЛКМ', callback_data='panel:input:leftclick'),
             InlineKeyboardButton('🖱 ПКМ', callback_data='panel:input:rightclick')],
            [InlineKeyboardButton('🖱 Двойной ЛКМ', callback_data='panel:input:doubleclick'),
             InlineKeyboardButton('🖱 СКМ', callback_data='panel:input:middleclick')],
            [InlineKeyboardButton('⏱ Удержание ПКМ', callback_data='panel:input:righthold')],
            [InlineKeyboardButton('🤖 Управление AutoAccept', callback_data='panel:aa:main')],
            [InlineKeyboardButton('❓ Команды ввода', callback_data='panel:input:help')],
            [InlineKeyboardButton('⬅️ Назад', callback_data='panel:main')]
        ])

    @staticmethod
    def _panel_media_text() -> str:
        return '🎥 <b>Медиа</b>\n\nСнимки и видео с веб-камеры, запись звука, управление музыкой.'

    @staticmethod
    def _panel_media_markup() -> InlineKeyboardMarkup:
        sec_btn = InlineKeyboardButton('🛡 Выкл Охрану',
                                       callback_data='panel:media:sec_toggle') if is_security_active() \
            else InlineKeyboardButton('🚨 Вкл Охрану', callback_data='panel:media:sec_toggle')
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('📡 LIVE Стрим', callback_data='panel:media:stream'),
             InlineKeyboardButton('🕵️‍♂️ Полный Отчет', callback_data='panel:media:report')],
            [InlineKeyboardButton('🎵 Что сейчас играет?', callback_data='panel:media:music')],
            [InlineKeyboardButton('⏮', callback_data='panel:media:prev'),
             InlineKeyboardButton('⏯', callback_data='panel:media:playpause'),
             InlineKeyboardButton('⏭', callback_data='panel:media:next')],
            [InlineKeyboardButton('🔉 Vol -', callback_data='panel:media:voldown'),
             InlineKeyboardButton('🔇 Mute', callback_data='panel:media:mute'),
             InlineKeyboardButton('🔊 Vol +', callback_data='panel:media:volup')],
            [sec_btn, InlineKeyboardButton('📸 Фото с вебки', callback_data='panel:media:webcam')],
            [InlineKeyboardButton('🎥 Видео (5с)', callback_data='panel:media:webcamvid5'),
             InlineKeyboardButton('🎥 (15с)', callback_data='panel:media:webcamvid15'),
             InlineKeyboardButton('🎥 (60с)', callback_data='panel:media:webcamvid60')],
            [InlineKeyboardButton('🎙 Аудио (5с)', callback_data='panel:media:audio5'),
             InlineKeyboardButton('🎙 (15с)', callback_data='panel:media:audio15'),
             InlineKeyboardButton('🎙 (60с)', callback_data='panel:media:audio60')],
            [InlineKeyboardButton('⬅️ Назад', callback_data='panel:main')]
        ])

    @staticmethod
    def _panel_input_help_text() -> str:
        return (
            '⌨️ <b>Команды ввода:</b>\n'
            '<code>/printtext &lt;text&gt;</code>\n'
            '<code>/combination &lt;keys...&gt;</code>\n'
            '<code>/leftclick</code> <code>/rightclick</code> <code>/leftdoubleclick</code> <code>/middleclick</code>\n'
            '<code>/righthold [sec]</code>\n'
            '<code>/movemouse &lt;x&gt; &lt;y&gt; [sec]</code>\n'
            '<code>/message &lt;text&gt;</code>\n'
            '<code>/remind HH:MM &lt;text&gt;</code>\n'
            '<code>/voice &lt;text&gt;</code>\n'
            '<code>/clip [text]</code>\n'
            '<code>/cliphistory</code>\n'
            '<code>/ocr [query]</code>\n'
            '<code>/antiafkon</code> <code>/antiafkoff</code>\n'
            '<code>/autoaccepton [600|10m|1h]</code>\n'
            '<code>/autoacceptoff</code>\n'
            '<code>/schedulein 20m webcam:15 audio:20 --if-cpu-below 12 --comment Ночная проверка</code>\n'
            '<code>/schedulein 20m ocrscreen clipboard —comment Проверить экран и буфер</code>\n'
            '<code>/schedulein 2h shutdown --if-cpu-below 10 --if-ram-below 60 --note Выключить если простаивает</code>\n'
            '<code>/scheduleat 03:00 screenshot logsave reboot --comment Ночной ребут</code>\n'
            '<code>/jobs</code> <code>/jobcancel JOB_ID</code>'
        )

    @staticmethod
    def _panel_power_text() -> str:
        return '🔋 <b>Управление питанием</b>\n\nБудьте осторожны с этими командами.'

    @staticmethod
    def _panel_power_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('🔒 Блокировка', callback_data='panel:power:lock'),
             InlineKeyboardButton('🌙 Сон', callback_data='panel:power:sleep')],
            [InlineKeyboardButton('❄️ Гибернация (сразу)', callback_data='panel:power:hibernate')],
            [InlineKeyboardButton('❄️ 10с', callback_data='panel:power:hiber10'),
             InlineKeyboardButton('❄️ 1м', callback_data='panel:power:hiber60'),
             InlineKeyboardButton('❄️ 5м', callback_data='panel:power:hiber300')],
            [InlineKeyboardButton('⏻ Выкл 10с', callback_data='panel:power:shutdown10'),
             InlineKeyboardButton('⏻ Выкл 1м', callback_data='panel:power:shutdown60'),
             InlineKeyboardButton('⏻ Выкл 5м', callback_data='panel:power:shutdown300')],
            [InlineKeyboardButton('🔄 Ребут 10с', callback_data='panel:power:reboot10'),
             InlineKeyboardButton('🔄 Ребут 1м', callback_data='panel:power:reboot60'),
             InlineKeyboardButton('🔄 Ребут 5м', callback_data='panel:power:reboot300')],
            [InlineKeyboardButton('✋ Отменить выключение/ребут/гибернацию', callback_data='panel:power:cancel')],
            [InlineKeyboardButton('⬅️ Назад', callback_data='panel:main')]
        ])

    @staticmethod
    def _panel_logs_text() -> str:
        return '🧾 <b>Логи</b>\n\nБыстрый доступ к хвосту логов приложения.'

    @staticmethod
    def _panel_logs_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('📄 40 строк', callback_data='panel:logs:tail40'),
             InlineKeyboardButton('📄 100 строк', callback_data='panel:logs:tail100')],
            [InlineKeyboardButton('⬅️ Назад', callback_data='panel:main')]
        ])

    @staticmethod
    def _panel_help_text() -> str:
        return (
            '❓ <b>Помощь по панели:</b>\n'
            '• Обзор — статус, аптайм, ping, скриншот.\n'
            '• Файлы — текущая папка, список файлов, upload.\n'
            '• Процессы — список процессов, терминал, живые окна.\n'
            '• Ввод — горячие клавиши, мышь, макросы, буфер.\n'
            '• Медиа — фото, видео, аудио.\n'
            '• Питание — lock, sleep, hibernate, выключение.\n'
            '• OCR — распознавание текста и поиск по экрану.\n'
            '• Планировщик — быстрые пресеты, список и отмена задач.\n'
            '• Логи — чтение файла логов.\n\n'
            'Полный список команд также доступен через /help'
        )

    @staticmethod
    def _panel_help_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад', callback_data='panel:main')]])

    async def _require_input_commands(self, update: Update) -> bool:
        return await self._ensure_admin(update, 'input')

    @staticmethod
    def _parse_combination_args(args: list[str]) -> list[str]:
        keys: list[str] = []
        for raw_arg in args:
            for part in raw_arg.replace(',', ' ').split():
                keys.extend(segment for segment in part.split('+') if segment.strip())
        return keys

    @staticmethod
    def _clone_context_with_args(context: ContextTypes.DEFAULT_TYPE, args: list[str]):
        context.args = args
        return context

    def _autoaccept_template_dir(self) -> Path:
        configured = self._config_provider().autoaccept_templates_dir.strip()
        target = Path(configured).expanduser() if configured else AUTOACCEPT_DIR
        target.mkdir(parents=True, exist_ok=True)
        return target.resolve(strict=False)

    def _handle_autoaccept_match(self, text: str) -> None:
        self.log_message.emit(text)
        self._notify_admins_from_thread(f'✅ {text}')

    def _handle_autoaccept_error(self, text: str) -> None:
        self.log_message.emit(text)
        self._notify_admins_from_thread(f'❌ {text}')

    def _handle_autoaccept_finish(self, text: str) -> None:
        self.log_message.emit(text)
        if "остановлен пользователем" not in text and "успешно завершен" not in text:
            self._notify_admins_from_thread(text)

        loop = self._loop
        if loop:
            loop.call_soon_threadsafe(lambda: asyncio.create_task(self._update_aa_menus()))

    def _notify_admins_from_thread(self, text: str) -> None:
        loop = self._loop
        if loop is None:
            return
        loop.call_soon_threadsafe(lambda: asyncio.create_task(self._notify_admins(text)))

    async def _notify_admins(self, text: str) -> None:
        application = self._application
        if application is None:
            return
        markup = self._dismiss_markup()
        for admin_id in self._config_provider().admins.keys():
            try:
                await application.bot.send_message(chat_id=admin_id, text=text, parse_mode=ParseMode.HTML,
                                                   reply_markup=markup)
            except Exception as exc:
                self.log_message.emit(f'Failed to notify admin {admin_id}: {exc}')

    async def _update_aa_menus(self):
        application = self._application
        if not application: return
        markup = self._autoaccept_menu_markup()
        text = self._autoaccept_menu_text()
        for chat_id, msg_id in list(self._aa_menu_messages.items()):
            try:
                await application.bot.edit_message_text(text=text, chat_id=chat_id, message_id=msg_id,
                                                        reply_markup=markup, parse_mode=ParseMode.HTML)
            except Exception:
                pass

    async def _command_unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        await self._safe_reply(update, '❌ Неизвестная команда. Введите /help для просмотра всех команд.',
                               dismissable=True, as_toast=True)

    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        self._record_runtime_error(str(context.error))
        self.log_message.emit(f'Unhandled bot error: {context.error}')
        if isinstance(update, Update):
            await self._safe_reply(update, f'❌ Внутренняя ошибка бота:\n<code>{html.escape(str(context.error))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _safe_reply(self, update: Update, text: str, reply_markup: InlineKeyboardMarkup | None = None,
                          parse_mode: str | None = None, dismissable: bool = False, as_toast: bool = False,
                          show_alert: bool = False) -> None:
        chat = update.effective_chat
        if chat is None:
            return

        query = update.callback_query

        if dismissable and reply_markup is None:
            reply_markup = self._dismiss_markup()

        clipped = text.strip()
        chunks = [clipped[i: i + 3800] for i in range(0, len(clipped), 3800)]

        is_timeout = 'timed out' in text.lower() or 'timeout' in text.lower()

        if query and query.message:
            if as_toast or is_timeout or show_alert:
                try:
                    clean_text = text.replace('<b>', '').replace('</b>', '').replace('<code>', '').replace('</code>',
                                                                                                           '').replace(
                        '❌ ', '')
                    await query.answer(clean_text[:200], show_alert=is_timeout or show_alert)
                except Exception:
                    pass
                return

            try:
                await query.message.edit_text(chunks[0], reply_markup=reply_markup if len(chunks) == 1 else None,
                                              parse_mode=parse_mode)
                for chunk in chunks[1:]:
                    await chat.send_message(chunk, reply_markup=reply_markup if chunk == chunks[-1] else None,
                                            parse_mode=parse_mode)
                return
            except Exception as e:
                if 'Message is not modified' in str(e):
                    return
                pass

        if is_timeout and query:
            return

        for index, chunk in enumerate(chunks):
            await chat.send_message(chunk, reply_markup=reply_markup if index == len(chunks) - 1 else None,
                                    parse_mode=parse_mode)

    async def _send_temporary_status(self, update: Update, text: str) -> object | None:
        query = update.callback_query
        if query:
            try:
                await query.answer(text.replace('<b>', '').replace('</b>', '').replace('⏳ ', ''))
            except Exception:
                pass
            return None
        if update.effective_chat:
            try:
                return await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML)
            except Exception:
                pass
        return None

    async def _delete_message_safe(self, message) -> None:
        if message:
            try:
                await message.delete()
            except Exception:
                pass

    async def _delete_user_message(self, update: Update) -> None:
        if update.message:
            try:
                await update.message.delete()
            except Exception:
                pass

    def _run_in_thread(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._clipboard_history.start()
        except Exception as exc:
            self.log_message.emit(f'Clipboard history disabled: {exc}')

        while not self._stop_event.is_set():
            try:
                self._loop.run_until_complete(self._runner())
                if self._stop_event.is_set():
                    break
                self.log_message.emit('🔄 Перезапуск сетевой сессии...')
            except Exception as exc:
                self._record_runtime_error(f'Ошибка сети: {exc}')
                self.log_message.emit(f'⚠️ Ошибка сети: {exc}. Повтор через 5 сек...')

            self._running = False
            self.state_changed.emit(False)

            if self._stop_event.wait(5.0):
                break

        self._running = False
        self.state_changed.emit(False)
        self._clipboard_history.stop()
        if self._loop and self._loop.is_running():
            self._loop.stop()
        if self._loop:
            self._loop.close()
        self._loop = None
        self._thread = None

    async def _runner(self) -> None:
        config = self._config_provider()
        proxy_url = str(getattr(config, 'telegram_proxy', '') or '').strip()
        builder = (
            ApplicationBuilder()
            .token(config.bot_token.strip())
            .connect_timeout(20)
            .read_timeout(30)
            .write_timeout(30)
            .pool_timeout(15)
            .connection_pool_size(16)
            .get_updates_connect_timeout(20)
            .get_updates_read_timeout(30)
            .get_updates_write_timeout(30)
            .get_updates_pool_timeout(15)
            .get_updates_connection_pool_size(8)
        )
        if proxy_url:
            if proxy_url.lower().startswith('socks'):
                import socksio  # noqa: F401
            builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)
            self.log_message.emit('Telegram proxy enabled for bot session.')
        self._application = builder.build()
        self._application.add_handler(CommandHandler('start', self._command_start))
        self._application.add_handler(CommandHandler('help', self._command_help))
        self._application.add_handler(CommandHandler('panel', self._command_panel))
        self._application.add_handler(CommandHandler('myid', self._command_myid))
        self._application.add_handler(CommandHandler('ping', self._command_ping))
        self._application.add_handler(CommandHandler('status', self._command_status))
        self._application.add_handler(CommandHandler('uptime', self._command_uptime))
        self._application.add_handler(CommandHandler('screenshot', self._command_screenshot))
        self._application.add_handler(CommandHandler('ocr', self._command_ocr))
        self._application.add_handler(CommandHandler('windows', self._command_windows))
        self._application.add_handler(CommandHandler('stream', self._command_stream))
        self._application.add_handler(CommandHandler('stopstream', self._command_stopstream))
        self._application.add_handler(CommandHandler('report', self._command_report))
        self._application.add_handler(CommandHandler('webcam', self._command_webcam))
        self._application.add_handler(CommandHandler('webcamvid', self._command_webcamvid))
        self._application.add_handler(CommandHandler('audio', self._command_audio))
        self._application.add_handler(CommandHandler('lock', self._command_lock))
        self._application.add_handler(CommandHandler('shutdown', self._command_shutdown))
        self._application.add_handler(CommandHandler('reboot', self._command_reboot))
        self._application.add_handler(CommandHandler('cancelshutdown', self._command_cancel_shutdown))
        self._application.add_handler(CommandHandler('sleep', self._command_sleep))
        self._application.add_handler(CommandHandler('hibernate', self._command_hibernate))
        self._application.add_handler(CommandHandler('openurl', self._command_open_url))
        self._application.add_handler(CommandHandler('logtail', self._command_log_tail))
        self._application.add_handler(CommandHandler('pwd', self._command_pwd))
        self._application.add_handler(CommandHandler('ls', self._command_ls))
        self._application.add_handler(CommandHandler('cd', self._command_cd))
        self._application.add_handler(CommandHandler('mkdir', self._command_mkdir))
        self._application.add_handler(CommandHandler('rm', self._command_rm))
        self._application.add_handler(CommandHandler('rmr', self._command_rmr))
        self._application.add_handler(CommandHandler('download', self._command_download))
        self._application.add_handler(CommandHandler('upload', self._command_upload))
        self._application.add_handler(CommandHandler('cancelupload', self._command_cancel_upload))
        self._application.add_handler(CommandHandler('drives', self._command_drives))
        self._application.add_handler(CommandHandler('tasklist', self._command_tasklist))
        self._application.add_handler(CommandHandler('taskkill', self._command_taskkill))
        self._application.add_handler(CommandHandler('cmd', self._command_cmd))
        self._application.add_handler(CommandHandler('hw', self._command_hw))
        self._application.add_handler(CommandHandler('music', self._command_music))
        self._application.add_handler(CommandHandler('playpause', self._command_playpause))
        self._application.add_handler(CommandHandler('nexttrack', self._command_nexttrack))
        self._application.add_handler(CommandHandler('prevtrack', self._command_prevtrack))
        self._application.add_handler(CommandHandler('vol', self._command_vol))
        self._application.add_handler(CommandHandler('mute', self._command_mute))
        self._application.add_handler(MessageHandler(filters.Regex(r'^/kill_\d+'), self._command_kill_regex))
        self._application.add_handler(MessageHandler(filters.Regex(r'^/rmaa_'), self._command_rmaa_regex))
        self._application.add_handler(CommandHandler('printtext', self._command_printtext))
        self._application.add_handler(CommandHandler('combination', self._command_combination))
        self._application.add_handler(CommandHandler('message', self._command_message))
        self._application.add_handler(CommandHandler('remind', self._command_remind))
        self._application.add_handler(CommandHandler('voice', self._command_voice))
        self._application.add_handler(CommandHandler('say', self._command_voice))
        self._application.add_handler(CommandHandler('clip', self._command_clip))
        self._application.add_handler(CommandHandler('cliphistory', self._command_clip_history))
        self._application.add_handler(CommandHandler('antiafkon', self._command_antiafk_on))
        self._application.add_handler(CommandHandler('antiafkoff', self._command_antiafk_off))
        self._application.add_handler(CommandHandler('schedulein', self._command_schedule_in))
        self._application.add_handler(CommandHandler('scheduleat', self._command_schedule_at))
        self._application.add_handler(CommandHandler('jobs', self._command_jobs))
        self._application.add_handler(CommandHandler('jobcancel', self._command_jobcancel))
        self._application.add_handler(CommandHandler('leftclick', self._command_leftclick))
        self._application.add_handler(CommandHandler('rightclick', self._command_rightclick))
        self._application.add_handler(CommandHandler('leftdoubleclick', self._command_leftdoubleclick))
        self._application.add_handler(CommandHandler('middleclick', self._command_middleclick))
        self._application.add_handler(CommandHandler('righthold', self._command_righthold))
        self._application.add_handler(CommandHandler('movemouse', self._command_movemouse))
        self._application.add_handler(CommandHandler('autoaccepton', self._command_autoaccept_on))
        self._application.add_handler(CommandHandler('autoacceptoff', self._command_autoaccept_off))
        self._application.add_handler(CallbackQueryHandler(self._handle_panel_callback, pattern=r'^panel:'))
        self._application.add_handler(
            MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO, self._handle_document_upload))
        self._application.add_handler(MessageHandler(filters.VOICE, self._handle_voice_message))
        self._application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text_message))
        self._application.add_handler(MessageHandler(filters.COMMAND, self._command_unknown))
        self._application.add_error_handler(self._error_handler)

        await self._application.initialize()
        await self._probe_telegram_api()
        await self._application.start()
        if self._application.updater is None:
            raise RuntimeError('Telegram updater is not available.')
        await self._application.updater.start_polling(
            drop_pending_updates=True,
            timeout=20,
            bootstrap_retries=0,
            error_callback=self._handle_polling_error,
        )

        self._running = True
        self.state_changed.emit(True)
        self._update_runtime_metrics(last_successful_reconnect=time.time())
        self.log_message.emit('Bot started successfully.')
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

        try:
            import socket, platform
            hostname = socket.gethostname()
            os_name = platform.system()
            boot_time = float(psutil.boot_time())
            if self._should_send_boot_notification(boot_time):
                startup_msg = (
                    f'🚀 <b>ПК Включен!</b>\n'
                    f'💻 Имя: <code>{html.escape(hostname)}</code> ({html.escape(os_name)})\n'
                    f'🤖 Бот на связи и готов к командам.'
                )
                await self._notify_admins(startup_msg)
                self._save_last_notified_boot_time(boot_time)
        except Exception as notify_exc:
            self.log_message.emit(f'Failed to send startup notification: {notify_exc}')

        try:
            last_api_check = time.time()
            api_failures = 0

            while not self._stop_event.is_set():
                if self._application and self._application.updater:
                    if not self._application.updater.running:
                        self.log_message.emit('⚠️ Внутренний пуллинг Telegram остановился!')
                        break

                await asyncio.sleep(0.5)
                now = time.time()

                if now - last_api_check > 15.0:
                    last_api_check = now
                    try:
                        await asyncio.wait_for(self._probe_telegram_api(), timeout=15.0)
                        api_failures = 0
                    except Exception as exc:
                        api_failures += 1
                        self._record_runtime_error(f'Telegram API health-check failed: {exc}')
                        self.log_message.emit(f'⚠️ Telegram API health-check failed {api_failures}/2: {exc}')
                        if api_failures >= 2:
                            self.log_message.emit('🔄 Telegram API завис или потерял маршрут. Перезапускаю сессию...')
                            break
        finally:
            self.log_message.emit('Очистка соединений...')
            if self._hibernate_task and not self._hibernate_task.done():
                self._hibernate_task.cancel()
            if self._scheduler_task and not self._scheduler_task.done():
                self._scheduler_task.cancel()
                try:
                    await self._scheduler_task
                except asyncio.CancelledError:
                    pass
                self._scheduler_task = None

            try:
                # ОЧЕНЬ ВАЖНО: Оборачиваем остановку в wait_for.
                # Иначе при мертвом VPN бот зависнет навсегда, пытаясь закрыть сокет!
                if self._application and self._application.updater:
                    await asyncio.wait_for(self._application.updater.stop(), timeout=3.0)
                if self._application:
                    await asyncio.wait_for(self._application.stop(), timeout=3.0)
                    await asyncio.wait_for(self._application.shutdown(), timeout=3.0)
            except Exception:
                self.log_message.emit('Уничтожение зависших сокетов...')

            self._application = None
            await asyncio.to_thread(self._auto_accept_service.stop)

            if hasattr(self, '_pending_upload_by_user'): self._pending_upload_by_user.clear()
            if hasattr(self, '_pending_action_by_user'): self._pending_action_by_user.clear()
            if hasattr(self, '_process_filter_by_user'): self._process_filter_by_user.clear()
            if hasattr(self, '_pending_rename_by_user'): self._pending_rename_by_user.clear()
            if hasattr(self, '_aa_upload_msg_id_by_user'): self._aa_upload_msg_id_by_user.clear()
            if hasattr(self, '_aa_list_msg_id_by_user'): self._aa_list_msg_id_by_user.clear()
            if hasattr(self, '_aa_menu_messages'): self._aa_menu_messages.clear()
            if hasattr(self, '_menu_msg_id_by_user'): self._menu_msg_id_by_user.clear()
            if hasattr(self, '_media_menu_msg_id_by_user'): self._media_menu_msg_id_by_user.clear()
            if hasattr(self, '_live_stream_stop_events'): self._live_stream_stop_events.clear()
            if hasattr(self, '_live_stream_tasks'): self._live_stream_tasks.clear()
            if hasattr(self, '_dir_items_by_user'): self._dir_items_by_user.clear()

            self.log_message.emit('Bot stopped.')

    def _base_root(self) -> Path:
        config = self._config_provider()
        root_raw = (config.files_root or '').strip()
        root = Path(root_raw).expanduser() if root_raw else Path.home()
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve(strict=False)

    def _resolve_user_path(self, user_id: int, raw_path: str | None) -> Path:
        config = self._config_provider()
        allow_all = config.allow_all_files
        root = self._base_root()

        cwd = self._cwd_by_user.get(user_id, root)
        if not allow_all and not self._is_allowed_path(cwd, root):
            cwd = root
            self._cwd_by_user[user_id] = root

        if raw_path:
            cleaned = raw_path.strip().strip('"').strip("'")
            candidate = Path(cleaned)
            target = candidate if candidate.is_absolute() else (cwd / candidate)
        else:
            target = cwd

        resolved = target.resolve(strict=False)
        if not allow_all and not self._is_allowed_path(resolved, root):
            raise ValueError(f'Path is outside allowed root: {root}')
        return resolved

    @staticmethod
    def _is_allowed_path(target: Path, root: Path) -> bool:
        try:
            target.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _files_list_markup(page: int, total_pages: int) -> InlineKeyboardMarkup:
        buttons = []
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton('⬅️ Вверх', callback_data=f'panel:files:page:{page - 1}'))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton('Вниз ➡️', callback_data=f'panel:files:page:{page + 1}'))

        if nav_row:
            buttons.append(nav_row)
        buttons.append([InlineKeyboardButton('⬅️ Назад', callback_data='panel:files')])
        return InlineKeyboardMarkup(buttons)

    def _get_fast_dir_size(self, path: Path) -> tuple[int, bool]:
        total = 0
        count = 0
        is_limited = False

        def scan(p):
            nonlocal total, count, is_limited
            try:
                for entry in os.scandir(p):
                    if count >= 300:
                        is_limited = True
                        return
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                        count += 1
                    elif entry.is_dir(follow_symlinks=False):
                        scan(entry.path)
            except Exception:
                pass

        scan(str(path))
        return total, is_limited

    def _build_interactive_dir_page(self, user_id: int, target: Path, bot_username: str, page: int = 0,
                                    page_size: int = 25) -> tuple[str, int]:
        if not target.exists():
            raise ValueError('Папка не существует.')

        entries = sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        self._dir_items_by_user[user_id] = [e.name for e in entries]

        total_pages = (len(entries) + page_size - 1) // page_size if entries else 1
        if page < 0: page = 0
        if page >= total_pages: page = total_pages - 1

        start_idx = page * page_size
        end_idx = start_idx + page_size
        page_entries = entries[start_idx:end_idx]

        lines = [f'📂 <b>Папка:</b>\n<code>{html.escape(str(target))}</code>']
        lines.append(f'📄 Стр {page + 1} из {total_pages} (Элементов: {len(entries)})\n')

        up_link = f'https://t.me/{bot_username}?start=cdup'
        lines.append(f'⬆️ <a href="{up_link}">.. (На уровень выше)</a>\n')

        for entry in page_entries:
            i = entries.index(entry)
            rm_link = f'https://t.me/{bot_username}?start=rmf_{i}'
            safe_name = html.escape(entry.name)

            if entry.is_dir():
                action_link = f'https://t.me/{bot_username}?start=cd_{i}'
                dir_size, is_limited = self._get_fast_dir_size(entry)
                size_str = f">{self._format_bytes(dir_size)}" if is_limited else self._format_bytes(dir_size)
                lines.append(
                    f'<a href="{rm_link}">❌</a> 📁 <a href="{action_link}">{safe_name}</a> <code>[{size_str}]</code>')
            else:
                action_link = f'https://t.me/{bot_username}?start=dl_{i}'
                size_str = self._format_bytes(entry.stat().st_size)
                lines.append(
                    f'<a href="{rm_link}">❌</a> 📄 <a href="{action_link}">{safe_name}</a> <code>[{size_str}]</code>')

        return '\n'.join(lines), total_pages

    def _build_aa_listing_text(self, target: Path, bot_username: str) -> str:
        if not target.exists():
            return 'Шаблонов нет.'
        entries = sorted(
            [e for e in target.iterdir() if e.is_file() and e.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp'}])
        if not entries:
            return 'Шаблонов нет.'

        lines = ['📂 <b>Шаблоны AutoAccept:</b>\n']
        for entry in entries:
            encoded = base64.urlsafe_b64encode(entry.name.encode('utf-8')).decode('utf-8').rstrip('=')
            link_show = f'https://t.me/{bot_username}?start=aa_{encoded}'
            link_del = f'https://t.me/{bot_username}?start=rmaa_{encoded}'
            lines.append(f'<a href="{link_del}">❌</a> 🖼 <a href="{link_show}">{html.escape(entry.name)}</a>')

        return '\n'.join(lines)

    def _remove_path(self, target: Path, recursive: bool) -> None:
        config = self._config_provider()
        allow_all = config.allow_all_files
        root = self._base_root()

        if not target.exists():
            raise ValueError('Path does not exist.')

        resolved = target.resolve(strict=False)
        if not allow_all and resolved == root:
            raise ValueError('Cannot remove allowed root directory.')

        if allow_all and str(resolved.parent) == str(resolved):
            raise ValueError('Cannot remove a drive root!')

        if target.is_file():
            target.unlink()
            return

        if recursive:
            shutil.rmtree(target)
            return

        target.rmdir()

    def _build_tasklist_page(self, filter_text: str, bot_username: str, page: int = 0, page_size: int = 20) -> tuple[
        str, int]:
        records: list[tuple[int, str, float]] = []
        for process in psutil.process_iter(['pid', 'name', 'memory_info']):
            try:
                info = process.info
                process_name = str(info.get('name') or 'unknown')
                if filter_text and filter_text not in process_name.lower():
                    continue
                mem_info = info.get('memory_info')
                memory_mb = float(mem_info.rss / (1024 * 1024)) if mem_info else 0.0
                records.append((int(info['pid']), process_name, memory_mb))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        if not records:
            return 'Процессы не найдены.', 0

        records.sort(key=lambda row: row[2], reverse=True)

        total_pages = (len(records) + page_size - 1) // page_size
        if page < 0: page = 0
        if page >= total_pages: page = total_pages - 1

        start_idx = page * page_size
        end_idx = start_idx + page_size
        page_records = records[start_idx:end_idx]

        filter_msg = f' (поиск: "<b>{html.escape(filter_text)}</b>")' if filter_text else ''
        lines = [f'🔝 <b>Процессы{filter_msg} | Стр {page + 1}/{total_pages}:</b>\n']

        for pid, name, memory_mb in page_records:
            link_kill = f'https://t.me/{bot_username}?start=kill_{pid}'
            link_info = f'https://t.me/{bot_username}?start=proc_{pid}_{page}'
            lines.append(
                f'<a href="{link_kill}">❌</a> | <code>{memory_mb:>6.1f} MB</code> | '
                f'<a href="{link_info}">{html.escape(name)}</a> <code>[PID {pid}]</code>')

        lines.append(f'\nВсего найдено: {len(records)}')
        return '\n'.join(lines), total_pages

    @staticmethod
    def _terminate_pid(pid: int) -> str:
        if pid <= 0:
            raise ValueError('PID should be greater than zero.')
        if pid == os.getpid():
            raise ValueError('Refusing to terminate controller process.')

        process = psutil.Process(pid)
        name = process.name()
        process.terminate()
        try:
            process.wait(timeout=4)
            return f'Process terminated: PID {pid} ({name})'
        except psutil.TimeoutExpired:
            process.kill()
            process.wait(timeout=4)
            return f'Process killed: PID {pid} ({name})'

    @staticmethod
    def _sanitize_upload_name(file_name: str | None) -> str:
        candidate = Path(file_name or '').name.strip()
        return candidate or 'uploaded_file.bin'

    @staticmethod
    def _build_unique_destination(base_path: Path) -> Path:
        if not base_path.exists():
            return base_path
        stem = base_path.stem
        suffix = base_path.suffix
        index = 1
        while True:
            candidate = base_path.with_name(f'{stem}_{index}{suffix}')
            if not candidate.exists():
                return candidate
            index += 1

    @staticmethod
    def _format_bytes(size: int) -> str:
        units = ('B', 'KB', 'MB', 'GB', 'TB')
        value = float(size)
        for unit in units:
            if value < 1024.0 or unit == units[-1]:
                return f'{value:.1f} {unit}'
            value /= 1024.0
        return f'{value:.1f} TB'

    @staticmethod
    def _read_log_tail(lines_count: int) -> str:
        log_path = Path(LOG_FILE)
        if not log_path.exists():
            return 'Log file is empty.'

        try:
            lines = log_path.read_text(encoding='utf-8', errors='replace').splitlines()
        except OSError as exc:
            return f'Failed to read log file: {exc}'
        tail = lines[-lines_count:]
        if not tail:
            return 'Log file is empty.'

        text = '\n'.join(tail)
        if len(text) > 3800:
            text = f'...\n{text[-3800:]}'
        return text
