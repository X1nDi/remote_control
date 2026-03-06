from __future__ import annotations

import asyncio
import html
import os
import shutil
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Callable

import psutil
from PySide6.QtCore import QObject, Signal
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
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
    show_message,
    speak_text,
    type_text,
)
from .logging_setup import LOG_FILE
from .system_actions import (
    cancel_scheduled_power_action,
    hibernate_system,
    lock_workstation,
    open_url,
    parse_delay,
    schedule_reboot,
    schedule_shutdown,
    sleep_system,
)
from .system_metrics import capture_screenshot_bytes, collect_snapshot, format_uptime

MAX_DOWNLOAD_FILE_SIZE = 45 * 1024 * 1024
MAX_LIST_ITEMS = 120

HELP_TEXT = """✨ <b>PC Controller — Список команд</b> ✨

📌 <b>Основное:</b>
🔸 /panel - Открыть красивую панель управления
🔸 /help - Показать все команды
🔸 /myid - Твой Telegram ID
🔸 /ping - Проверка связи
🔸 /status - Статус приложения и ПК
🔸 /uptime - Время работы системы
🔸 /screenshot - Скриншот рабочего стола

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
🔸 /cancelshutdown - Отменить действия питания

🗂 <b>Файлы:</b>
🔸 /pwd, /ls, /cd, /mkdir, /rm, /rmr
🔸 /download, /upload, /cancelupload

⚙️ <b>Процессы:</b>
🔸 /tasklist [filter] - Список
🔸 /taskkill &lt;pid&gt; - Завершить

⌨️ <b>Ввод и управление:</b>
🔸 /printtext &lt;text&gt; - Напечатать текст
🔸 /combination &lt;keys...&gt; - Горячие клавиши
🔸 /movemouse &lt;x&gt; &lt;y&gt; [sec]
🔸 /message, /voice
🔸 /autoaccepton, /autoacceptoff

🌐 <b>Прочее:</b>
🔸 /openurl &lt;link&gt;, /logtail [n]"""


class TelegramBotService(QObject):
    log_message = Signal(str)
    state_changed = Signal(bool)

    def __init__(self, config_provider: Callable[[], AppConfig]) -> None:
        super().__init__()
        self._config_provider = config_provider
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._application: Application | None = None
        self._stop_event = threading.Event()
        self._running = False
        self._cwd_by_user: dict[int, Path] = {}
        self._pending_upload_by_user: dict[int, Path] = {}
        self._pending_action_by_user: dict[int, str] = {}
        self._hibernate_task: asyncio.Task | None = None
        self._auto_accept_service = AutoAcceptService()

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            self.log_message.emit('Bot is already running.')
            return

        config = self._config_provider()
        if not config.bot_token.strip():
            self.log_message.emit('Bot token is empty. Set it in settings first.')
            return
        if not config.admin_ids:
            self.log_message.emit('Admin IDs list is empty. Add at least one admin ID.')
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

    async def _command_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
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
        await self._safe_reply(update, f'🪪 Твой Telegram ID: <code>{user.id}</code>', parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        await self._safe_reply(update, '🟢 <b>Pong!</b> Связь с ПК установлена.', parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return

        config = self._config_provider()
        snapshot = await asyncio.to_thread(
            collect_snapshot,
            len(config.admin_ids),
            config.autostart,
            self._running,
        )

        text = (
            f"🌟 <b>Статус системы</b> 🌟\n\n"
            f"💻 <b>Хост:</b> <code>{html.escape(snapshot.hostname)}</code> ({html.escape(snapshot.os_name)} {html.escape(snapshot.os_release)})\n"
            f"🌐 <b>IP:</b> <code>{html.escape(snapshot.ip_address)}</code>\n"
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
            len(config.admin_ids),
            config.autostart,
            self._running,
        )
        await self._safe_reply(update, f'⏱ <b>Uptime:</b> <code>{format_uptime(snapshot.uptime_seconds)}</code>',
                               parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_screenshot(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return

        temp_msg = await self._send_temporary_status(update, '⏳ <b>Делаю скриншот...</b>')
        try:
            screenshot_bytes, file_name = await asyncio.to_thread(capture_screenshot_bytes)
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
            self.log_message.emit(f'Screenshot sent to admin {update.effective_user.id}.')
        except Exception as exc:
            self.log_message.emit(f'Failed to capture screenshot: {exc}')
            await self._safe_reply(update, f'❌ Ошибка создания скриншота: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
        finally:
            await self._delete_message_safe(temp_msg)

    async def _command_webcam(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return

        temp_msg = await self._send_temporary_status(update, '⏳ <b>Делаю фото с веб-камеры...</b>')
        try:
            from .system_metrics import capture_webcam_photo
            photo_bytes, file_name = await asyncio.to_thread(capture_webcam_photo)
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
            self.log_message.emit(f'Webcam photo sent to admin {update.effective_user.id}.')
        except Exception as exc:
            self.log_message.emit(f'Failed to capture webcam: {exc}')
            await self._safe_reply(update, f'❌ Ошибка камеры: <code>{html.escape(str(exc))}</code>', parse_mode=ParseMode.HTML, dismissable=True)
        finally:
            await self._delete_message_safe(temp_msg)

    async def _command_webcamvid(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return

        duration = 5
        if context.args:
            try:
                duration = max(1, min(60, int(context.args[0])))
            except ValueError:
                pass
                
        temp_msg = await self._send_temporary_status(update, f'⏳ <b>Записываю видео с веб-камеры ({duration}с)...</b>')
        try:
            from .system_metrics import capture_webcam_video
            video_bytes, file_name = await asyncio.to_thread(capture_webcam_video, duration)
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
            self.log_message.emit(f'Webcam video sent to admin {update.effective_user.id}.')
        except Exception as exc:
            self.log_message.emit(f'Failed to capture webcam video: {exc}')
            await self._safe_reply(update, f'❌ Ошибка камеры: <code>{html.escape(str(exc))}</code>', parse_mode=ParseMode.HTML, dismissable=True)
        finally:
            await self._delete_message_safe(temp_msg)

    async def _command_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return

        duration = 5
        if context.args:
            try:
                duration = max(1, min(60, int(context.args[0])))
            except ValueError:
                pass
                
        temp_msg = await self._send_temporary_status(update, f'⏳ <b>Записываю аудио ({duration}с)...</b>')
        try:
            from .system_metrics import record_audio
            audio_bytes, file_name = await asyncio.to_thread(record_audio, duration)
            stream = BytesIO(audio_bytes)
            stream.name = file_name
            if update.effective_chat:
                await update.effective_chat.send_voice(
                    voice=stream, 
                    caption=f'🎙 <b>Аудиозапись ({duration}с)</b>', 
                    parse_mode=ParseMode.HTML, 
                    reply_markup=self._dismiss_markup(),
                    read_timeout=120, 
                    write_timeout=120
                )
            self.log_message.emit(f'Audio sent to admin {update.effective_user.id}.')
        except Exception as exc:
            self.log_message.emit(f'Failed to record audio: {exc}')
            await self._safe_reply(update, f'❌ Ошибка записи аудио: <code>{html.escape(str(exc))}</code>', parse_mode=ParseMode.HTML, dismissable=True)
        finally:
            await self._delete_message_safe(temp_msg)

    async def _command_lock(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return

        try:
            result = await asyncio.to_thread(lock_workstation)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🔒 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            self.log_message.emit(f'Lock command failed: {exc}')
            await self._safe_reply(update, f'❌ Ошибка блокировки: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_shutdown(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        if not self._config_provider().allow_power_commands:
            await self._safe_reply(update, '❌ Управление питанием отключено в настройках.', dismissable=True)
            return

        try:
            delay = parse_delay(context.args[0] if context.args else None)
            result = await asyncio.to_thread(schedule_shutdown, delay)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'⏻ <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
        except ValueError as exc:
            await self._safe_reply(update,
                                   f'Использование: <code>/shutdown [seconds]</code>\nОшибка: {html.escape(str(exc))}',
                                   parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            self.log_message.emit(f'Shutdown command failed: {exc}')
            await self._safe_reply(update, f'❌ Ошибка выключения: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_reboot(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        if not self._config_provider().allow_power_commands:
            await self._safe_reply(update, '❌ Управление питанием отключено в настройках.', dismissable=True)
            return

        try:
            delay = parse_delay(context.args[0] if context.args else None)
            result = await asyncio.to_thread(schedule_reboot, delay)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🔄 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
        except ValueError as exc:
            await self._safe_reply(update,
                                   f'Использование: <code>/reboot [seconds]</code>\nОшибка: {html.escape(str(exc))}',
                                   parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            self.log_message.emit(f'Reboot command failed: {exc}')
            await self._safe_reply(update, f'❌ Ошибка перезагрузки: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_cancel_shutdown(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        if not self._config_provider().allow_power_commands:
            await self._safe_reply(update, '❌ Управление питанием отключено в настройках.', dismissable=True)
            return

        try:
            if self._hibernate_task and not self._hibernate_task.done():
                self._hibernate_task.cancel()
                self._hibernate_task = None

            result = await asyncio.to_thread(cancel_scheduled_power_action)
            self.log_message.emit(result.message)
            await self._safe_reply(update,
                                   f'✋ <b>{html.escape(result.message)}</b> (Включая отмену таймера гибернации)',
                                   parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            self.log_message.emit(f'Cancel shutdown command failed: {exc}')
            await self._safe_reply(update, f'❌ Ошибка отмены: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_sleep(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        if not self._config_provider().allow_power_commands:
            await self._safe_reply(update, '❌ Управление питанием отключено в настройках.', dismissable=True)
            return

        try:
            result = await asyncio.to_thread(sleep_system)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🌙 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            self.log_message.emit(f'Sleep command failed: {exc}')
            await self._safe_reply(update, f'❌ Ошибка перехода в сон: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_open_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        if not self._config_provider().allow_open_url_command:
            await self._safe_reply(update, '❌ Команда открытия ссылок отключена в настройках.', dismissable=True)
            return

        if not context.args:
            await self._safe_reply(update, 'Использование: <code>/openurl &lt;https://example.com&gt;</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
            return

        url = context.args[0].strip()
        try:
            result = await asyncio.to_thread(open_url, url)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🌐 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
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
        await self._safe_reply(update, f'🧾 <b>Логи:</b>\n<pre>{html.escape(text)}</pre>', parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_pwd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        if not self._config_provider().allow_file_commands:
            await self._safe_reply(update, '❌ Управление файлами отключено в настройках.', dismissable=True)
            return

        user_id = update.effective_user.id
        root = self._base_root()
        cwd = self._cwd_by_user.get(user_id, root)
        if not self._is_allowed_path(cwd, root):
            cwd = root
            self._cwd_by_user[user_id] = root
        await self._safe_reply(update,
                               f'📂 <b>Корень:</b> <code>{html.escape(str(root))}</code>\n📍 <b>Текущая папка:</b> <code>{html.escape(str(cwd))}</code>',
                               parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_ls(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        if not self._config_provider().allow_file_commands:
            await self._safe_reply(update, '❌ Управление файлами отключено в настройках.', dismissable=True)
            return

        user_id = update.effective_user.id
        raw_path = ' '.join(context.args).strip() if context.args else ''
        try:
            target = self._resolve_user_path(user_id, raw_path)
            text = await asyncio.to_thread(self._build_dir_listing_text, target)
            await self._safe_reply(update, f'<pre>{html.escape(text)}</pre>', parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /ls: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_cd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        if not self._config_provider().allow_file_commands:
            await self._safe_reply(update, '❌ Управление файлами отключено в настройках.', dismissable=True)
            return

        if not context.args:
            await self._safe_reply(update, 'Использование: <code>/cd &lt;path&gt;</code>', parse_mode=ParseMode.HTML, dismissable=True)
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
        if not await self._ensure_admin(update):
            return
        if not self._config_provider().allow_file_commands:
            await self._safe_reply(update, '❌ Управление файлами отключено в настройках.', dismissable=True)
            return

        if not context.args:
            await self._safe_reply(update, 'Использование: <code>/mkdir &lt;path&gt;</code>', parse_mode=ParseMode.HTML, dismissable=True)
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
        if not await self._ensure_admin(update):
            return
        if not self._config_provider().allow_file_commands:
            await self._safe_reply(update, '❌ Управление файлами отключено в настройках.', dismissable=True)
            return

        if not context.args:
            await self._safe_reply(update, 'Использование: <code>/rm &lt;path&gt;</code>', parse_mode=ParseMode.HTML, dismissable=True)
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
        if not await self._ensure_admin(update):
            return
        if not self._config_provider().allow_file_commands:
            await self._safe_reply(update, '❌ Управление файлами отключено в настройках.', dismissable=True)
            return

        if not context.args:
            await self._safe_reply(update, 'Использование: <code>/rmr &lt;path&gt;</code>', parse_mode=ParseMode.HTML, dismissable=True)
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
        if not await self._ensure_admin(update):
            return
        if not self._config_provider().allow_file_commands:
            await self._safe_reply(update, '❌ Управление файлами отключено в настройках.', dismissable=True)
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
                
            temp_msg = await self._send_temporary_status(update, f'⏳ <b>Подготовка файла {html.escape(target.name)}...</b>')
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
        if not await self._ensure_admin(update):
            return
        if not self._config_provider().allow_file_commands:
            await self._safe_reply(update, '❌ Управление файлами отключено в настройках.', dismissable=True)
            return

        user_id = update.effective_user.id
        raw_path = ' '.join(context.args).strip() if context.args else ''
        try:
            target_dir = self._resolve_user_path(user_id, raw_path)
            if not target_dir.exists() or not target_dir.is_dir():
                raise ValueError('Target directory does not exist.')
            self._pending_upload_by_user[user_id] = target_dir
            await self._safe_reply(
                update,
                f'📤 <b>Режим загрузки включен для:</b>\n<code>{html.escape(str(target_dir))}</code>\n\nПрикрепите файл или фото в чат прямо сейчас.\nИспользуйте /cancelupload для отмены.',
                parse_mode=ParseMode.HTML, dismissable=True
            )
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /upload: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_cancel_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return

        user_id = update.effective_user.id
        if user_id in self._pending_upload_by_user:
            self._pending_upload_by_user.pop(user_id, None)
            await self._safe_reply(update, '✋ <b>Режим загрузки файла отменен.</b>', parse_mode=ParseMode.HTML, dismissable=True)
            return
        await self._safe_reply(update, 'ℹ️ Режим загрузки файла сейчас не активен.', dismissable=True)

    async def _handle_document_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        if not self._config_provider().allow_file_commands:
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

            # Check if target is inside autoaccept dir to bypass root restriction
            is_aa_dir = False
            try:
                target_dir.relative_to(aa_dir)
                is_aa_dir = True
            except ValueError:
                pass

            if not is_aa_dir and not self._is_allowed_path(target_dir, root):
                raise ValueError('Upload target is outside allowed root.')

            target_dir.mkdir(parents=True, exist_ok=True)
            destination = self._build_unique_destination(target_dir / file_name)

            await file_obj.download_to_drive(custom_path=str(destination))
            size = destination.stat().st_size
            self.log_message.emit(f'File uploaded by admin {user_id}: {destination}')
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
        action = self._pending_action_by_user.pop(user_id, None)

        if not action:
            return

        message = update.effective_message
        if not message or not message.text:
            return

        text = message.text

        if action == 'printtext':
            try:
                result = await asyncio.to_thread(type_text, text)
                self.log_message.emit(result.message)
                await self._safe_reply(update, f'⌨️ <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
            except Exception as exc:
                await self._safe_reply(update, f'❌ Ошибка печати текста: <code>{html.escape(str(exc))}</code>',
                                       parse_mode=ParseMode.HTML, dismissable=True)

        elif action == 'combination':
            keys = self._parse_combination_args(text.split())
            if not keys:
                await self._safe_reply(update, '❌ Клавиши не распознаны.', dismissable=True)
                return
            try:
                result = await asyncio.to_thread(press_combination, keys)
                self.log_message.emit(result.message)
                await self._safe_reply(update, f'🪟 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
            except Exception as exc:
                await self._safe_reply(update, f'❌ Ошибка нажатия комбинации: <code>{html.escape(str(exc))}</code>',
                                       parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_tasklist(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        if not self._config_provider().allow_process_commands:
            await self._safe_reply(update, '❌ Управление процессами отключено в настройках.', dismissable=True)
            return

        filter_text = ' '.join(context.args).strip().lower() if context.args else ''
        text = await asyncio.to_thread(self._build_tasklist_text, filter_text)
        await self._safe_reply(update, f'<pre>{html.escape(text)}</pre>', parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_taskkill(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        if not self._config_provider().allow_process_commands:
            await self._safe_reply(update, '❌ Управление процессами отключено в настройках.', dismissable=True)
            return

        if not context.args:
            await self._safe_reply(update, 'Использование: <code>/taskkill &lt;pid&gt;</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
            return

        try:
            pid = int(context.args[0])
            message = await asyncio.to_thread(self._terminate_pid, pid)
            await self._safe_reply(update, f'☠️ <b>{html.escape(message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
        except ValueError:
            await self._safe_reply(update, '❌ PID должен быть целым числом.', dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /taskkill: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_printtext(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update):
            return

        text = ' '.join(context.args).strip()
        if not text:
            await self._safe_reply(update, 'Использование: <code>/printtext &lt;text&gt;</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
            return

        try:
            result = await asyncio.to_thread(type_text, text)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'⌨️ <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
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
                                   'Использование: <code>/combination &lt;keys...&gt;</code>\nПример: <code>/combination win d</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
            return

        try:
            result = await asyncio.to_thread(press_combination, keys)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🪟 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /combination: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update):
            return

        text = ' '.join(context.args).strip()
        if not text:
            await self._safe_reply(update, 'Использование: <code>/message &lt;text&gt;</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
            return

        try:
            result = await asyncio.to_thread(show_message, text)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'💬 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /message: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update):
            return

        text = ' '.join(context.args).strip()
        if not text:
            await self._safe_reply(update, 'Использование: <code>/voice &lt;text&gt;</code>', parse_mode=ParseMode.HTML, dismissable=True)
            return

        try:
            result = await asyncio.to_thread(speak_text, text)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🗣 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /voice: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_leftclick(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update):
            return
        try:
            result = await asyncio.to_thread(left_click)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🖱 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
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
            await self._safe_reply(update, f'🖱 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
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
            await self._safe_reply(update, f'🖱 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
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
            await self._safe_reply(update, f'🖱 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
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
            await self._safe_reply(update, f'🖱 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
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
            await self._safe_reply(update, 'Использование: <code>/movemouse &lt;x&gt; &lt;y&gt; [seconds]</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
            return

        try:
            x = int(context.args[0])
            y = int(context.args[1])
            duration = float(context.args[2]) if len(context.args) > 2 else 0.15
            result = await asyncio.to_thread(move_mouse, x, y, duration)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🖱 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
        except ValueError:
            await self._safe_reply(update, 'Использование: <code>/movemouse &lt;x&gt; &lt;y&gt; [seconds]</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка мыши: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_autoaccept_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update):
            return

        try:
            timeout = int(context.args[0]) if context.args else 300
            timeout = max(10, min(timeout, 3600))
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
                parse_mode=ParseMode.HTML, dismissable=True
            )
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /autoaccepton: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_autoaccept_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._require_input_commands(update):
            return

        try:
            result = await asyncio.to_thread(self._auto_accept_service.stop)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🤖 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /autoacceptoff: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_hibernate(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        if not self._config_provider().allow_power_commands:
            await self._safe_reply(update, '❌ Управление питанием отключено в настройках.', dismissable=True)
            return

        try:
            result = await asyncio.to_thread(hibernate_system)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'❄️ <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка гибернации: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _handle_panel_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None:
            return
        await query.answer()
        if not await self._ensure_admin(update):
            return

        data = str(query.data or '')

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
        if data == 'panel:overview':
            await self._edit_panel_message(query, self._panel_overview_text(), self._panel_overview_markup())
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
        if data == 'panel:power':
            await self._edit_panel_message(query, self._panel_power_text(), self._panel_power_markup())
            return
        if data == 'panel:media':
            await self._edit_panel_message(query, self._panel_media_text(), self._panel_media_markup())
            return
        if data == 'panel:logs':
            await self._edit_panel_message(query, self._panel_logs_text(), self._panel_logs_markup())
            return
        if data == 'panel:aa:main':
            await self._edit_panel_message(query, self._panel_autoaccept_text(), self._panel_autoaccept_markup())
            return

        # Overview
        if data == 'panel:status':
            await self._command_status(update, context)
            return
        if data == 'panel:screenshot':
            await self._command_screenshot(update, context)
            return
        if data == 'panel:uptime':
            await self._command_uptime(update, context)
            return
        if data == 'panel:ping':
            await self._command_ping(update, context)
            return
        if data == 'panel:myid':
            await self._command_myid(update, context)
            return

        # Files
        if data == 'panel:files:pwd':
            await self._command_pwd(update, context)
            return
        if data == 'panel:files:ls':
            await self._command_ls(update, context)
            return
        if data == 'panel:files:upload':
            user_id = update.effective_user.id
            cwd = self._resolve_user_path(user_id, None)
            self._pending_upload_by_user[user_id] = cwd
            await self._safe_reply(
                update,
                f'📤 <b>Режим загрузки включен для:</b>\n<code>{html.escape(str(cwd))}</code>\n\nПрикрепите документ в чат. /cancelupload для отмены.',
                parse_mode=ParseMode.HTML, dismissable=True
            )
            return
        if data == 'panel:files:cancelupload':
            await self._command_cancel_upload(update, context)
            return

        # AutoAccept File Management
        if data == 'panel:aa:upload':
            user_id = update.effective_user.id
            target = self._autoaccept_template_dir()
            self._pending_upload_by_user[user_id] = target
            await self._safe_reply(
                update,
                f'📸 <b>Отправь скриншот/шаблон как фото или файл.</b>\nОн будет сохранен для AutoAccept.\n\nИспользуйте /cancelupload для отмены.',
                parse_mode=ParseMode.HTML, dismissable=True
            )
            return
        if data == 'panel:aa:ls':
            target = self._autoaccept_template_dir()
            try:
                text = await asyncio.to_thread(self._build_dir_listing_text, target)
                await self._safe_reply(update, f'<pre>{html.escape(text)}</pre>', parse_mode=ParseMode.HTML, dismissable=True)
            except Exception as exc:
                await self._safe_reply(update, f'❌ Ошибка чтения: <code>{html.escape(str(exc))}</code>',
                                       parse_mode=ParseMode.HTML, dismissable=True)
            return
        if data == 'panel:aa:clear':
            target = self._autoaccept_template_dir()
            try:
                for item in target.iterdir():
                    if item.is_file():
                        item.unlink()
                await self._safe_reply(update, '🗑 <b>Все шаблоны AutoAccept успешно очищены.</b>',
                                       parse_mode=ParseMode.HTML, dismissable=True)
            except Exception as exc:
                await self._safe_reply(update, f'❌ Ошибка очистки: <code>{html.escape(str(exc))}</code>',
                                       parse_mode=ParseMode.HTML, dismissable=True)
            return

        # Processes
        if data == 'panel:proc:list':
            await self._command_tasklist(update, context)
            return

        # Media
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
        if data == 'panel:media:audio5':
            cloned = self._clone_context_with_args(context, ['5'])
            await self._command_audio(update, cloned)
            return
        if data == 'panel:media:audio15':
            cloned = self._clone_context_with_args(context, ['15'])
            await self._command_audio(update, cloned)
            return

        # Input & Mouse
        if data == 'panel:input:custom_text':
            self._pending_action_by_user[update.effective_user.id] = 'printtext'
            await self._safe_reply(update, '✏️ <b>Отправь текст</b>, который нужно напечатать на ПК:',
                                   parse_mode=ParseMode.HTML, dismissable=True)
            return
        if data == 'panel:input:custom_combo':
            self._pending_action_by_user[update.effective_user.id] = 'combination'
            await self._safe_reply(update, '🔠 <b>Отправь комбинацию клавиш</b> (например: win d, ctrl c):',
                                   parse_mode=ParseMode.HTML, dismissable=True)
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
        if data == 'panel:input:autoaccept:on':
            cloned = self._clone_context_with_args(context, ['300'])
            await self._command_autoaccept_on(update, cloned)
            return
        if data == 'panel:input:autoaccept:off':
            await self._command_autoaccept_off(update, context)
            return
        if data == 'panel:input:help':
            await self._safe_reply(update, self._panel_input_help_text(), parse_mode=ParseMode.HTML, dismissable=True)
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
            await self._safe_reply(update, f'🧾 <b>Логи:</b>\n<pre>{html.escape(text)}</pre>', parse_mode=ParseMode.HTML, dismissable=True)
            return
        if data == 'panel:logs:tail100':
            text = await asyncio.to_thread(self._read_log_tail, 100)
            await self._safe_reply(update, f'🧾 <b>Логи:</b>\n<pre>{html.escape(text)}</pre>', parse_mode=ParseMode.HTML, dismissable=True)
            return

        await self._safe_reply(update, '❌ Неизвестное действие панели.', dismissable=True)

    async def _execute_power_action(self, update: Update, action: str, delay: int) -> None:
        if not self._config_provider().allow_power_commands:
            await self._safe_reply(update, '❌ Управление питанием отключено в настройках.', dismissable=True)
            return

        try:
            if action == 'shutdown':
                result = await asyncio.to_thread(schedule_shutdown, delay)
                self.log_message.emit(result.message)
                await self._safe_reply(update, f'⚡️ <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
            elif action == 'reboot':
                result = await asyncio.to_thread(schedule_reboot, delay)
                self.log_message.emit(result.message)
                await self._safe_reply(update, f'🔄 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
            elif action == 'hibernate':
                if self._hibernate_task and not self._hibernate_task.done():
                    self._hibernate_task.cancel()
                self._hibernate_task = asyncio.create_task(self._delayed_hibernate(update, delay))
                await self._safe_reply(update, f'⏳ <b>Гибернация запланирована через {delay} сек.</b>',
                                       parse_mode=ParseMode.HTML, dismissable=True)
            else:
                raise ValueError('Unknown power action.')
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка действия: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _delayed_hibernate(self, update: Update, delay: int) -> None:
        try:
            await asyncio.sleep(delay)
            result = await asyncio.to_thread(hibernate_system)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'❄️ <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML, dismissable=True)
        except asyncio.CancelledError:
            pass

    async def _edit_panel_message(self, query, text: str, markup: InlineKeyboardMarkup) -> None:
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        except Exception:
            if query.message:
                await query.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)

    @staticmethod
    def _dismiss_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('👌', callback_data='panel:dismiss'),
             InlineKeyboardButton('⬅️ В меню', callback_data='panel:main')]
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
            [InlineKeyboardButton('🧾 Логи', callback_data='panel:logs'),
             InlineKeyboardButton('❓ Помощь', callback_data='panel:help')]
        ])

    @staticmethod
    def _panel_overview_text() -> str:
        return '📊 <b>Обзор системы</b>\n\nЧастые действия и статус ПК.'

    @staticmethod
    def _panel_overview_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('📈 Статус', callback_data='panel:status'),
             InlineKeyboardButton('⏱ Аптайм', callback_data='panel:uptime')],
            [InlineKeyboardButton('🖼 Скриншот', callback_data='panel:screenshot'),
             InlineKeyboardButton('🟢 Ping', callback_data='panel:ping')],
            [InlineKeyboardButton('🪪 Мой ID', callback_data='panel:myid')],
            [InlineKeyboardButton('⬅️ В главное меню', callback_data='panel:main')]
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
             InlineKeyboardButton('✋ Отмена загрузки', callback_data='panel:files:cancelupload')],
            [InlineKeyboardButton('⬅️ В главное меню', callback_data='panel:main')]
        ])

    @staticmethod
    def _panel_process_text() -> str:
        return '⚙️ <b>Процессы</b>\n\nСписок активных процессов. Для точечного завершения используй <code>/taskkill &lt;pid&gt;</code>.'

    @staticmethod
    def _panel_process_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('📋 Список процессов', callback_data='panel:proc:list')],
            [InlineKeyboardButton('⬅️ В главное меню', callback_data='panel:main')]
        ])

    @staticmethod
    def _panel_input_text() -> str:
        return '⌨️ <b>Ввод и мышь</b>\n\nЭмуляция нажатий, управление курсором и автоматизация.'

    @staticmethod
    def _panel_input_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('✏️ Свой Текст', callback_data='panel:input:custom_text'),
             InlineKeyboardButton('🔠 Свои Клавиши', callback_data='panel:input:custom_combo')],
            [InlineKeyboardButton('🖥 Свернуть окна', callback_data='panel:input:showdesk'),
             InlineKeyboardButton('🪟 Alt + Tab', callback_data='panel:input:alttab')],
            [InlineKeyboardButton('🖱 ЛКМ', callback_data='panel:input:leftclick'),
             InlineKeyboardButton('🖱 ПКМ', callback_data='panel:input:rightclick')],
            [InlineKeyboardButton('🖱 Двойной ЛКМ', callback_data='panel:input:doubleclick'),
             InlineKeyboardButton('🖱 СКМ', callback_data='panel:input:middleclick')],
            [InlineKeyboardButton('⏱ Удержание ПКМ', callback_data='panel:input:righthold')],
            [InlineKeyboardButton('🤖 Управление AutoAccept', callback_data='panel:aa:main')],
            [InlineKeyboardButton('❓ Команды ввода', callback_data='panel:input:help')],
            [InlineKeyboardButton('⬅️ В главное меню', callback_data='panel:main')]
        ])

    @staticmethod
    def _panel_media_text() -> str:
        return '🎥 <b>Медиа</b>\n\nСнимки и видео с веб-камеры, запись звука.'

    @staticmethod
    def _panel_media_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('📸 Фото с вебки', callback_data='panel:media:webcam')],
            [InlineKeyboardButton('🎥 Видео (5с)', callback_data='panel:media:webcamvid5'),
             InlineKeyboardButton('🎥 Видео (15с)', callback_data='panel:media:webcamvid15')],
            [InlineKeyboardButton('🎙 Аудио (5с)', callback_data='panel:media:audio5'),
             InlineKeyboardButton('🎙 Аудио (15с)', callback_data='panel:media:audio15')],
            [InlineKeyboardButton('⬅️ В главное меню', callback_data='panel:main')]
        ])

    @staticmethod
    def _panel_autoaccept_text() -> str:
        return '🤖 <b>Управление AutoAccept</b>\n\nЗагрузите скриншоты шаблонов для автоматического поиска и клика на экране.'

    @staticmethod
    def _panel_autoaccept_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('📸 Загрузить скриншот', callback_data='panel:aa:upload')],
            [InlineKeyboardButton('📂 Список шаблонов', callback_data='panel:aa:ls'),
             InlineKeyboardButton('🗑 Очистить всё', callback_data='panel:aa:clear')],
            [InlineKeyboardButton('▶️ Запустить бота', callback_data='panel:input:autoaccept:on')],
            [InlineKeyboardButton('⏹ Остановить', callback_data='panel:input:autoaccept:off')],
            [InlineKeyboardButton('⬅️ Назад к вводу', callback_data='panel:input')]
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
            '<code>/voice &lt;text&gt;</code>\n'
            '<code>/autoaccepton [timeout]</code>\n'
            '<code>/autoacceptoff</code>'
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
            [InlineKeyboardButton('⬅️ В главное меню', callback_data='panel:main')]
        ])

    @staticmethod
    def _panel_logs_text() -> str:
        return '🧾 <b>Логи</b>\n\nБыстрый доступ к хвосту логов приложения.'

    @staticmethod
    def _panel_logs_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('📄 40 строк', callback_data='panel:logs:tail40'),
             InlineKeyboardButton('📄 100 строк', callback_data='panel:logs:tail100')],
            [InlineKeyboardButton('⬅️ В главное меню', callback_data='panel:main')]
        ])

    @staticmethod
    def _panel_help_text() -> str:
        return (
            '❓ <b>Помощь по панели:</b>\n'
            '• Обзор — статус, аптайм, ping, скриншот.\n'
            '• Файлы — текущая папка, список файлов, upload.\n'
            '• Процессы — список процессов.\n'
            '• Ввод — горячие клавиши, мышь, автоакцепт.\n'
            '• Медиа — фото, видео, аудио.\n'
            '• Питание — lock, sleep, hibernate, выключение.\n'
            '• Логи — чтение файла логов.\n\n'
            'Полный список команд также доступен через <code>/help</code>.'
        )

    @staticmethod
    def _panel_help_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ В главное меню', callback_data='panel:main')]])

    async def _require_input_commands(self, update: Update) -> bool:
        if not await self._ensure_admin(update):
            return False
        if not self._config_provider().allow_input_commands:
            await self._safe_reply(update, '❌ Управление вводом отключено в настройках.', parse_mode=ParseMode.HTML, dismissable=True)
            return False
        return True

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
        self._notify_admins_from_thread(f'ℹ️ {text}')

    def _notify_admins_from_thread(self, text: str) -> None:
        loop = self._loop
        if loop is None:
            return
        loop.call_soon_threadsafe(lambda: asyncio.create_task(self._notify_admins(text)))

    async def _notify_admins(self, text: str) -> None:
        application = self._application
        if application is None:
            return
        for admin_id in self._config_provider().admin_ids:
            try:
                await application.bot.send_message(chat_id=admin_id, text=text)
            except Exception as exc:
                self.log_message.emit(f'Failed to notify admin {admin_id}: {exc}')

    async def _command_unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update):
            return
        await self._safe_reply(update, '❌ Неизвестная команда. Введите /help для просмотра всех команд.', dismissable=True)

    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.log_message.emit(f'Unhandled bot error: {context.error}')
        if isinstance(update, Update):
            await self._safe_reply(update, '❌ Внутренняя ошибка бота. Проверьте логи приложения.', dismissable=True)

    async def _ensure_admin(self, update: Update) -> bool:
        user = update.effective_user
        user_id = getattr(user, 'id', None)
        if user_id is None:
            return False

        if user_id not in self._config_provider().admin_ids:
            self.log_message.emit(f'Access denied for user_id={user_id}')
            await self._safe_reply(update, '❌ Доступ запрещен. Ваш Telegram ID не найден в списке администраторов.', dismissable=True)
            return False
        return True

    async def _safe_reply(self, update: Update, text: str, reply_markup: InlineKeyboardMarkup | None = None,
                          parse_mode: str | None = None, dismissable: bool = False) -> None:
        chat = update.effective_chat
        if chat is None:
            return

        query = update.callback_query

        if dismissable and reply_markup is None:
            reply_markup = self._dismiss_markup()

        clipped = text.strip()
        chunks = [clipped[i: i + 3800] for i in range(0, len(clipped), 3800)]
        
        if query and query.message:
            try:
                await query.message.edit_text(chunks[0], reply_markup=reply_markup if len(chunks) == 1 else None, parse_mode=parse_mode)
                for chunk in chunks[1:]:
                    await chat.send_message(chunk, reply_markup=reply_markup if chunk == chunks[-1] else None, parse_mode=parse_mode)
                return
            except Exception:
                pass

        for index, chunk in enumerate(chunks):
            await chat.send_message(chunk, reply_markup=reply_markup if index == len(chunks)-1 else None, parse_mode=parse_mode)

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
            self._loop.run_until_complete(self._runner())
        except Exception as exc:
            self.log_message.emit(f'Bot startup failed: {exc}')
        finally:
            self._running = False
            self.state_changed.emit(False)
            if self._loop and self._loop.is_running():
                self._loop.stop()
            if self._loop:
                self._loop.close()
            self._loop = None
            self._thread = None

    async def _runner(self) -> None:
        config = self._config_provider()
        self._application = ApplicationBuilder().token(config.bot_token.strip()).build()
        self._application.add_handler(CommandHandler('start', self._command_start))
        self._application.add_handler(CommandHandler('help', self._command_help))
        self._application.add_handler(CommandHandler('panel', self._command_panel))
        self._application.add_handler(CommandHandler('myid', self._command_myid))
        self._application.add_handler(CommandHandler('ping', self._command_ping))
        self._application.add_handler(CommandHandler('status', self._command_status))
        self._application.add_handler(CommandHandler('uptime', self._command_uptime))
        self._application.add_handler(CommandHandler('screenshot', self._command_screenshot))
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
        self._application.add_handler(CommandHandler('tasklist', self._command_tasklist))
        self._application.add_handler(CommandHandler('taskkill', self._command_taskkill))
        self._application.add_handler(CommandHandler('printtext', self._command_printtext))
        self._application.add_handler(CommandHandler('combination', self._command_combination))
        self._application.add_handler(CommandHandler('message', self._command_message))
        self._application.add_handler(CommandHandler('voice', self._command_voice))
        self._application.add_handler(CommandHandler('say', self._command_voice))
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
            MessageHandler(filters.Document.ALL | filters.PHOTO, self._handle_document_upload))
        self._application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text_message))
        self._application.add_handler(MessageHandler(filters.COMMAND, self._command_unknown))
        self._application.add_error_handler(self._error_handler)

        await self._application.initialize()
        await self._application.start()
        if self._application.updater is None:
            raise RuntimeError('Telegram updater is not available.')
        await self._application.updater.start_polling(drop_pending_updates=True)

        self._running = True
        self.state_changed.emit(True)
        self.log_message.emit('Bot started successfully.')

        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(0.3)
        finally:
            self.log_message.emit('Stopping bot...')
            if self._hibernate_task and not self._hibernate_task.done():
                self._hibernate_task.cancel()
            if self._application and self._application.updater:
                await self._application.updater.stop()
            if self._application:
                await self._application.stop()
                await self._application.shutdown()
            self._application = None
            await asyncio.to_thread(self._auto_accept_service.stop)
            self._pending_upload_by_user.clear()
            self._pending_action_by_user.clear()
            self.log_message.emit('Bot stopped.')

    def _base_root(self) -> Path:
        config = self._config_provider()
        root_raw = (config.files_root or '').strip()
        root = Path(root_raw).expanduser() if root_raw else Path.home()
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve(strict=False)

    def _resolve_user_path(self, user_id: int, raw_path: str | None) -> Path:
        root = self._base_root()
        cwd = self._cwd_by_user.get(user_id, root)
        if not self._is_allowed_path(cwd, root):
            cwd = root
            self._cwd_by_user[user_id] = root

        if raw_path:
            cleaned = raw_path.strip().strip('"').strip("'")
            candidate = Path(cleaned)
            target = candidate if candidate.is_absolute() else (cwd / candidate)
        else:
            target = cwd

        resolved = target.resolve(strict=False)
        if not self._is_allowed_path(resolved, root):
            raise ValueError(f'Path is outside allowed root: {root}')
        return resolved

    @staticmethod
    def _is_allowed_path(target: Path, root: Path) -> bool:
        try:
            target.relative_to(root)
            return True
        except ValueError:
            return False

    def _build_dir_listing_text(self, target: Path) -> str:
        if not target.exists():
            raise ValueError('Path does not exist.')

        if target.is_file():
            size = target.stat().st_size
            return f'📄 File:\n{target}\nSize: {self._format_bytes(size)}'

        entries = sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        lines = [f'📂 Directory: {target}', f'📊 Items: {len(entries)}']
        limit = min(len(entries), MAX_LIST_ITEMS)
        for entry in entries[:limit]:
            icon = '📁' if entry.is_dir() else '📄'
            if entry.is_dir():
                details = '<DIR>'
            else:
                details = self._format_bytes(entry.stat().st_size)
            lines.append(f'{icon} {entry.name}  ({details})')
        if len(entries) > limit:
            lines.append(f'... and {len(entries) - limit} more items.')
        return '\n'.join(lines)

    def _remove_path(self, target: Path, recursive: bool) -> None:
        root = self._base_root()
        if not target.exists():
            raise ValueError('Path does not exist.')
        if target.resolve(strict=False) == root:
            raise ValueError('Cannot remove allowed root directory.')

        if target.is_file():
            target.unlink()
            return

        if recursive:
            shutil.rmtree(target)
            return

        target.rmdir()

    def _build_tasklist_text(self, filter_text: str) -> str:
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
            return 'No processes matched your filter.'

        records.sort(key=lambda row: row[2], reverse=True)
        top = records[:60]
        lines = ['🔝 Top processes by RAM usage:']
        for pid, name, memory_mb in top:
            lines.append(f'PID {pid:>6} | {memory_mb:>8.1f} MB | {name}')
        if len(records) > len(top):
            lines.append(f'... and {len(records) - len(top)} more.')
        return '\n'.join(lines)

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