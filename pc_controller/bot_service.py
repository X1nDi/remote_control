from __future__ import annotations

import asyncio
import base64
import html
import os
import re
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
    get_clipboard,
    set_clipboard,
    start_anti_afk,
    stop_anti_afk,
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
    run_cmd,
)
from .system_metrics import (
    capture_screenshot_bytes,
    collect_snapshot,
    format_uptime,
    get_hardware_info,
    get_now_playing
)

MAX_DOWNLOAD_FILE_SIZE = 45 * 1024 * 1024
MAX_LIST_ITEMS = 120

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

⌨️ <b>Ввод и управление:</b>
🔸 /printtext &lt;text&gt;
🔸 /combination &lt;keys...&gt;
🔸 /movemouse &lt;x&gt; &lt;y&gt; [sec]
🔸 /message, /voice
🔸 /clip [text] - Буфер обмена
🔸 /antiafkon, /antiafkoff - Anti-AFK
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
        self._process_filter_by_user: dict[int, str] = {}
        self._pending_rename_by_user: dict[int, Path] = {}
        self._aa_menu_messages: dict[int, int] = {}
        self._menu_msg_id_by_user: dict[int, int] = {}
        self._dir_items_by_user: dict[int, list[str]] = {}
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
        if not config.admins:
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
            if query:
                try:
                    await query.message.delete()
                except:
                    pass
            if temp_msg:
                await self._delete_message_safe(temp_msg)

            if thumb_bytes:
                stream = BytesIO(thumb_bytes)
                stream.name = 'cover.jpg'
                if update.effective_chat:
                    await update.effective_chat.send_photo(photo=stream, caption=text, parse_mode=ParseMode.HTML,
                                                           reply_markup=self._dismiss_markup())
            else:
                if update.effective_chat:
                    await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML,
                                                             reply_markup=self._dismiss_markup())
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
                for _ in range(3): await asyncio.to_thread(press_media_key, 0xAF)
                await self._safe_reply(update, '🔊 <b>Громкость +</b>', parse_mode=ParseMode.HTML, dismissable=True,
                                       as_toast=True)
            elif direction == 'down':
                for _ in range(3): await asyncio.to_thread(press_media_key, 0xAE)
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
            self.log_message.emit(f'Screenshot sent to admin {update.effective_user.id}.')
        except Exception as exc:
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
            self.log_message.emit(f'Webcam photo sent to admin {update.effective_user.id}.')
        except Exception as exc:
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
            self.log_message.emit(f'Webcam video sent to admin {update.effective_user.id}.')
        except Exception as exc:
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
            await self._safe_reply(update, f'❌ Ошибка записи аудио: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)
        finally:
            if query:
                await query.edit_message_text(self._panel_media_text(), reply_markup=self._panel_media_markup(),
                                              parse_mode=ParseMode.HTML)
            elif temp_msg:
                await self._delete_message_safe(temp_msg)

    async def _command_lock(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'power'):
            return

        try:
            result = await asyncio.to_thread(lock_workstation)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🔒 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
        except Exception as exc:
            self.log_message.emit(f'Lock command failed: {exc}')
            await self._safe_reply(update, f'❌ Ошибка блокировки: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_shutdown(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'power'):
            return

        try:
            delay = parse_delay(context.args[0] if context.args else None)
            result = await asyncio.to_thread(schedule_shutdown, delay)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'⏻ <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
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
        if not await self._ensure_admin(update, 'power'):
            return

        try:
            delay = parse_delay(context.args[0] if context.args else None)
            result = await asyncio.to_thread(schedule_reboot, delay)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🔄 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
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
        if not await self._ensure_admin(update, 'power'):
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
        if not await self._ensure_admin(update, 'power'):
            return

        try:
            result = await asyncio.to_thread(sleep_system)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'🌙 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
        except Exception as exc:
            self.log_message.emit(f'Sleep command failed: {exc}')
            await self._safe_reply(update, f'❌ Ошибка перехода в сон: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

    async def _command_hibernate(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._delete_user_message(update)
        if not await self._ensure_admin(update, 'power'):
            return

        try:
            result = await asyncio.to_thread(hibernate_system)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'❄️ <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка гибернации: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

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
        if user_id in self._pending_upload_by_user:
            self._pending_upload_by_user.pop(user_id, None)
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
                await self._safe_reply(update,
                                       f'📸 Фото загружено.\n✏️ <b>Отправьте ответным сообщением название для шаблона</b> (например, <code>accept_btn</code>):',
                                       parse_mode=ParseMode.HTML)
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

            await self._safe_reply(update, f'✅ Шаблон сохранен как <b>{html.escape(new_path.name)}</b>',
                                   parse_mode=ParseMode.HTML, dismissable=True)
            return

        action = self._pending_action_by_user.pop(user_id, None)
        if not action:
            return

        if action in ('type', 'printtext', 'combination', 'message', 'voice', 'cmd', 'clip_set'):
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
                    result = await asyncio.to_thread(show_message, text)
                elif action == 'voice':
                    result = await asyncio.to_thread(speak_text, text)
                elif action == 'clip_set':
                    result = await asyncio.to_thread(set_clipboard, text)
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
            result = await asyncio.to_thread(show_message, text)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'💬 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка /message: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True)

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
                await self._safe_reply(update, f'📋 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                       dismissable=True, as_toast=True)
            else:
                result = await asyncio.to_thread(get_clipboard)
                if result.ok:
                    await self._safe_reply(update,
                                           f'📋 <b>Текст из буфера обмена ПК:</b>\n\n<code>{html.escape(result.message)}</code>',
                                           parse_mode=ParseMode.HTML, dismissable=True)
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

    async def _show_autoaccept_menu(self, query) -> None:
        text = '🤖 <b>Управление AutoAccept</b>\n\nЗагрузите скриншоты шаблонов для автоматического поиска и клика на экране.'
        is_active = self._auto_accept_service.active

        toggle_btn = InlineKeyboardButton('⏹ Выключить AutoAccept',
                                          callback_data='panel:input:autoaccept:off') if is_active else InlineKeyboardButton(
            '▶️ Включить AutoAccept', callback_data='panel:input:autoaccept:on')

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton('📸 Загрузить скриншот', callback_data='panel:aa:upload')],
            [InlineKeyboardButton('📂 Список шаблонов', callback_data='panel:aa:ls'),
             InlineKeyboardButton('🗑 Очистить всё', callback_data='panel:aa:clear')],
            [toggle_btn],
            [InlineKeyboardButton('⬅️ Назад', callback_data='panel:input')]
        ])
        await self._edit_panel_message(query, text, markup)
        self._aa_menu_messages[query.message.chat_id] = query.message.message_id

    async def _handle_panel_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None:
            return
        await query.answer()
        if not await self._ensure_admin(update):
            return

        data = str(query.data or '')

        if data.startswith('panel:files') and not await self._ensure_admin(update, 'files'): return
        if data.startswith('panel:proc') and not await self._ensure_admin(update, 'process'): return
        if (data.startswith('panel:input') or data.startswith('panel:aa')) and not await self._ensure_admin(update,
                                                                                                            'input'): return
        if data.startswith('panel:power') and not await self._ensure_admin(update, 'power'): return
        if data.startswith('panel:media') and not await self._ensure_admin(update, 'media'): return

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
                bot_username = self._application.bot.username
                text = await asyncio.to_thread(self._build_aa_listing_text, target, bot_username)
                markup = InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад', callback_data='panel:aa:main')]])
                await self._safe_reply(update, text, reply_markup=markup, parse_mode=ParseMode.HTML)
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
                                       parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)
            except Exception as exc:
                await self._safe_reply(update, f'❌ Ошибка очистки: <code>{html.escape(str(exc))}</code>',
                                       parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)
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
        if data == 'panel:proc:cancel_cmd':
            self._pending_action_by_user.pop(update.effective_user.id, None)
            await self._edit_panel_message(query, self._panel_process_text(), self._panel_process_markup())
            return

        if data == 'panel:proc:list':
            user_id = update.effective_user.id
            self._process_filter_by_user[user_id] = ''
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
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton('📥 Получить текущий буфер', callback_data='panel:input:clip_get')],
                [InlineKeyboardButton('❌ Отменить', callback_data='panel:input:cancel_text')]
            ])
            await self._edit_panel_message(query,
                                           '📋 <b>Отправьте текст</b>, чтобы скопировать его в буфер обмена ПК, или нажмите кнопку ниже для получения текущего текста:',
                                           markup)
            return
        if data == 'panel:input:clip_get':
            await self._command_clip(update, context)
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
                timeout = 300
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

        await self._safe_reply(update, '❌ Неизвестное действие панели.', dismissable=True, as_toast=True)

    async def _execute_power_action(self, update: Update, action: str, delay: int) -> None:
        if not self._config_provider().allow_power_commands:
            await self._safe_reply(update, '❌ Управление питанием отключено в настройках.', dismissable=True,
                                   as_toast=True)
            return

        try:
            if action == 'shutdown':
                result = await asyncio.to_thread(schedule_shutdown, delay)
                self.log_message.emit(result.message)
                await self._safe_reply(update, f'⚡️ <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                       dismissable=True, as_toast=True)
            elif action == 'reboot':
                result = await asyncio.to_thread(schedule_reboot, delay)
                self.log_message.emit(result.message)
                await self._safe_reply(update, f'🔄 <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                       dismissable=True, as_toast=True)
            elif action == 'hibernate':
                if self._hibernate_task and not self._hibernate_task.done():
                    self._hibernate_task.cancel()
                self._hibernate_task = asyncio.create_task(self._delayed_hibernate(update, delay))
                await self._safe_reply(update, f'⏳ <b>Гибернация запланирована через {delay} сек.</b>',
                                       parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)
            else:
                raise ValueError('Unknown power action.')
        except Exception as exc:
            await self._safe_reply(update, f'❌ Ошибка действия: <code>{html.escape(str(exc))}</code>',
                                   parse_mode=ParseMode.HTML, dismissable=True, as_toast=True)

    async def _delayed_hibernate(self, update: Update, delay: int) -> None:
        try:
            await asyncio.sleep(delay)
            result = await asyncio.to_thread(hibernate_system)
            self.log_message.emit(result.message)
            await self._safe_reply(update, f'❄️ <b>{html.escape(result.message)}</b>', parse_mode=ParseMode.HTML,
                                   dismissable=True)
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

    @staticmethod
    def _dismiss_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('👌', callback_data='panel:dismiss')]
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
        return '⚙️ <b>Система и Процессы</b>\n\nУправление процессами и доступ к системному терминалу.'

    @staticmethod
    def _panel_process_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('📋 Все процессы', callback_data='panel:proc:list')],
            [InlineKeyboardButton('🔎 Поиск процесса', callback_data='panel:proc:search')],
            [InlineKeyboardButton('💻 Терминал (CMD)', callback_data='panel:proc:cmd')],
            [InlineKeyboardButton('🌡 Датчики и Железо', callback_data='panel:proc:hw')],
            [InlineKeyboardButton('⬅️ Назад', callback_data='panel:main')]
        ])

    @staticmethod
    def _tasklist_markup(page: int, total_pages: int) -> InlineKeyboardMarkup:
        buttons = []
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton('⬅️ Вверх', callback_data=f'panel:proc:page:{page - 1}'))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton('Вниз ➡️', callback_data=f'panel:proc:page:{page + 1}'))

        if nav_row:
            buttons.append(nav_row)
        buttons.append([InlineKeyboardButton('🔎 Новый поиск', callback_data='panel:proc:search')])
        buttons.append([InlineKeyboardButton('⬅️ Назад', callback_data='panel:process')])
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def _panel_input_text() -> str:
        return '⌨️ <b>Ввод и управление</b>\n\nЭмуляция нажатий, управление мышью, буфер обмена и макросы.'

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
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('🎵 Что сейчас играет?', callback_data='panel:media:music')],
            [InlineKeyboardButton('⏮', callback_data='panel:media:prev'),
             InlineKeyboardButton('⏯', callback_data='panel:media:playpause'),
             InlineKeyboardButton('⏭', callback_data='panel:media:next')],
            [InlineKeyboardButton('🔉 Vol -', callback_data='panel:media:voldown'),
             InlineKeyboardButton('🔇 Mute', callback_data='panel:media:mute'),
             InlineKeyboardButton('🔊 Vol +', callback_data='panel:media:volup')],
            [InlineKeyboardButton('📸 Фото с вебки', callback_data='panel:media:webcam')],
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
            '<code>/voice &lt;text&gt;</code>\n'
            '<code>/clip [text]</code>\n'
            '<code>/antiafkon</code> <code>/antiafkoff</code>\n'
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
            '• Процессы — список процессов, терминал.\n'
            '• Ввод — горячие клавиши, мышь, макросы.\n'
            '• Медиа — фото, видео, аудио.\n'
            '• Питание — lock, sleep, hibernate, выключение.\n'
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
        is_active = self._auto_accept_service.active
        toggle_btn = InlineKeyboardButton('⏹ Выключить AutoAccept',
                                          callback_data='panel:input:autoaccept:off') if is_active else InlineKeyboardButton(
            '▶️ Включить AutoAccept', callback_data='panel:input:autoaccept:on')
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton('📸 Загрузить скриншот', callback_data='panel:aa:upload')],
            [InlineKeyboardButton('📂 Список шаблонов', callback_data='panel:aa:ls'),
             InlineKeyboardButton('🗑 Очистить всё', callback_data='panel:aa:clear')],
            [toggle_btn], [InlineKeyboardButton('⬅️ Назад', callback_data='panel:input')]
        ])
        text = '🤖 <b>Управление AutoAccept</b>\n\nЗагрузите скриншоты шаблонов для автоматического поиска и клика на экране.'
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

        while not self._stop_event.is_set():
            try:
                self._loop.run_until_complete(self._runner())
                if self._stop_event.is_set():
                    break
                self.log_message.emit('🔄 Бот завис. Идет автоматический перезапуск...')
            except Exception as exc:
                self.log_message.emit(f'Нет сети или ошибка старта: {exc}. Повтор через 10 сек...')

            self._running = False
            self.state_changed.emit(False)

            if self._stop_event.wait(10.0):
                break

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
        self._application.add_handler(CommandHandler('voice', self._command_voice))
        self._application.add_handler(CommandHandler('say', self._command_voice))
        self._application.add_handler(CommandHandler('clip', self._command_clip))
        self._application.add_handler(CommandHandler('antiafkon', self._command_antiafk_on))
        self._application.add_handler(CommandHandler('antiafkoff', self._command_antiafk_off))
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
            import socket, platform
            hostname = socket.gethostname()
            os_name = platform.system()
            startup_msg = f'🚀 <b>ПК Включен!</b>\n💻 Имя: <code>{html.escape(hostname)}</code> ({html.escape(os_name)})\n🤖 Бот на связи и готов к командам.'
            await self._notify_admins(startup_msg)
        except Exception as notify_exc:
            self.log_message.emit(f'Failed to send startup notification: {notify_exc}')

        try:
            while not self._stop_event.is_set():
                if self._application and self._application.updater:
                    if not self._application.updater.running:
                        self.log_message.emit('⚠️ Соединение с Telegram потеряно!')
                        break
                await asyncio.sleep(0.5)
        finally:
            self.log_message.emit('Stopping bot...')
            if self._hibernate_task and not self._hibernate_task.done():
                self._hibernate_task.cancel()

            try:
                if self._application and self._application.updater:
                    await self._application.updater.stop()
                if self._application:
                    await self._application.stop()
                    await self._application.shutdown()
            except Exception as cleanup_exc:
                self.log_message.emit(f'Cleanup warning: {cleanup_exc}')

            self._application = None
            await asyncio.to_thread(self._auto_accept_service.stop)

            if hasattr(self, '_pending_upload_by_user'): self._pending_upload_by_user.clear()
            if hasattr(self, '_pending_action_by_user'): self._pending_action_by_user.clear()
            if hasattr(self, '_process_filter_by_user'): self._process_filter_by_user.clear()
            if hasattr(self, '_pending_rename_by_user'): self._pending_rename_by_user.clear()
            if hasattr(self, '_aa_menu_messages'): self._aa_menu_messages.clear()
            if hasattr(self, '_menu_msg_id_by_user'): self._menu_msg_id_by_user.clear()
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
            lines.append(
                f'<a href="{link_kill}">❌</a> | <code>{memory_mb:>6.1f} MB</code> | <code>{html.escape(name)}</code>')

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