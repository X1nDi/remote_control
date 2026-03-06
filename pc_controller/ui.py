from __future__ import annotations

import logging
import sys
from os import startfile
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QRect, Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFormLayout,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QSystemTrayIcon,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import autostart
from .bot_service import HELP_TEXT, TelegramBotService
from .config import AppConfig, ConfigManager
from .logging_setup import LOG_FILE

APP_STYLE = """
QWidget {
    background: #07111f;
    color: #e8eefc;
    font-size: 13px;
}
QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #07111f, stop:0.42 #0b1730, stop:1 #091526);
}
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: rgba(11, 23, 48, 0.95);
    width: 12px;
    margin: 4px 0 4px 0;
    border-radius: 6px;
}
QScrollBar::handle:vertical {
    background: rgba(72, 105, 166, 0.90);
    min-height: 32px;
    border-radius: 6px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    height: 0;
    background: none;
}
QFrame#HeroCard,
QFrame#GlassCard,
QGroupBox {
    background: rgba(16, 27, 49, 0.92);
    border: 1px solid rgba(95, 126, 180, 0.32);
    border-radius: 24px;
}
QGroupBox {
    margin-top: 14px;
    padding: 18px 16px 16px 16px;
}
QGroupBox::title {
    left: 16px;
    padding: 0 8px;
    color: #8eb7ff;
    font-size: 14px;
    font-weight: 700;
}
QLabel#HeroTitle {
    font-size: 30px;
    font-weight: 900;
    color: #f3f7ff;
}
QLabel#HeroSubtitle, QLabel#Muted {
    color: #93a6c9;
}
QLabel#SectionTitle {
    font-size: 16px;
    font-weight: 800;
    color: #dce7ff;
}
QLabel#MiniStatValue {
    font-size: 20px;
    font-weight: 900;
    color: #ffffff;
}
QLabel#MiniStatCaption {
    color: #8ea4cb;
    font-size: 12px;
}
QFrame#MiniStatCard {
    background: rgba(10, 20, 38, 0.95);
    border: 1px solid rgba(87, 118, 177, 0.35);
    border-radius: 18px;
}
QLineEdit, QPlainTextEdit {
    background: rgba(7, 16, 31, 0.96);
    border: 1px solid #2b426d;
    border-radius: 14px;
    padding: 10px 12px;
    selection-background-color: #4c86ff;
}
QLineEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #6ea4ff;
}
QTabWidget::pane {
    border: none;
    background: transparent;
    top: -4px;
}
QTabBar::tab {
    background: rgba(19, 32, 56, 0.96);
    border: 1px solid rgba(89, 119, 178, 0.30);
    border-radius: 14px;
    padding: 11px 18px;
    margin-right: 8px;
    color: #9fb4db;
    font-weight: 700;
}
QTabBar::tab:selected {
    color: #ffffff;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #2b6dff, stop:1 #6b7dff);
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #3177ff, stop:1 #6c7bff);
    border: none;
    border-radius: 14px;
    color: white;
    font-weight: 800;
    padding: 11px 16px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #4d8cff, stop:1 #8591ff);
}
QPushButton:pressed {
    padding-top: 12px;
    padding-bottom: 10px;
}
QPushButton[secondary="true"] {
    background: rgba(24, 39, 68, 0.98);
    border: 1px solid rgba(83, 112, 170, 0.40);
}
QPushButton[secondary="true"]:hover {
    background: rgba(35, 57, 96, 0.98);
}
QPushButton[danger="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #b62d4a, stop:1 #df4a67);
}
QPushButton[danger="true"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #d94160, stop:1 #ff6583);
}
QToolButton {
    background: rgba(19, 32, 56, 0.96);
    border: 1px solid rgba(89, 119, 178, 0.30);
    border-radius: 12px;
    padding: 8px 12px;
    color: #d8e4fb;
    font-weight: 700;
}
QToolButton:hover {
    background: rgba(34, 53, 89, 0.98);
}
QCheckBox {
    spacing: 10px;
    color: #dce7ff;
    min-height: 24px;
    padding: 4px 0;
}
QCheckBox::indicator {
    width: 20px;
    height: 20px;
    border-radius: 10px;
    border: 1px solid #45639c;
    background: #0b1730;
}
QCheckBox::indicator:checked {
    background: #4d86ff;
    border: 1px solid #76a6ff;
}
QLabel[badge="true"] {
    border-radius: 999px;
    padding: 7px 12px;
    font-weight: 900;
}
QLabel[badgeState="on"] {
    color: #d7ffe4;
    background: rgba(28, 90, 55, 0.95);
    border: 1px solid rgba(71, 180, 111, 0.42);
}
QLabel[badgeState="off"] {
    color: #ffdce3;
    background: rgba(92, 31, 45, 0.95);
    border: 1px solid rgba(213, 83, 110, 0.34);
}
QLabel[badgeState="idle"] {
    color: #d5e5ff;
    background: rgba(36, 57, 95, 0.95);
    border: 1px solid rgba(102, 136, 204, 0.32);
}
QLabel#PathValue {
    color: #9cb0d8;
}
"""


class QtLogHandler(logging.Handler):
    def __init__(self, sink) -> None:
        super().__init__()
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self._sink(self.format(record))


class MainWindow(QMainWindow):
    def __init__(
        self,
        config_manager: ConfigManager,
        bot_service: TelegramBotService,
        logger: logging.Logger,
        start_minimized: bool = False,
    ) -> None:
        super().__init__()
        self.config_manager = config_manager
        self.bot_service = bot_service
        self.logger = logger
        self._quitting = False
        self._start_minimized = start_minimized
        self._token_visible = False
        self._hero_effect: QGraphicsOpacityEffect | None = None
        self._tabs_effect: QGraphicsOpacityEffect | None = None
        self._state_effect: QGraphicsOpacityEffect | None = None
        self._intro_group: QParallelAnimationGroup | None = None
        self._tab_fade_animation: QPropertyAnimation | None = None
        self._state_pulse_animation: QPropertyAnimation | None = None

        self.setWindowTitle('PC Controller')
        self.resize(1240, 860)
        self.setMinimumSize(980, 720)
        QApplication.instance().setStyleSheet(APP_STYLE)

        self._build_ui()
        self._setup_tray()
        self._connect_signals()

        self.log_handler = QtLogHandler(self.append_log)
        self.log_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
        self.logger.addHandler(self.log_handler)

        self._load_config_into_form()

        if self.config_manager.current().auto_start_bot:
            QTimer.singleShot(600, lambda: self.start_bot(save_before_start=False))

        if self._start_minimized:
            QTimer.singleShot(0, self.hide)
            self._notify('Приложение запущено в трее.')

    def _build_ui(self) -> None:
        root = QWidget(self)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        self.hero = QFrame()
        self.hero.setObjectName('HeroCard')
        hero_layout = QHBoxLayout(self.hero)
        hero_layout.setContentsMargins(24, 22, 24, 22)
        hero_layout.setSpacing(18)

        hero_left = QVBoxLayout()
        hero_left.setSpacing(10)

        hero_title = QLabel('PC Controller')
        hero_title.setObjectName('HeroTitle')
        hero_subtitle = QLabel('Современный центр управления ботом, автозагрузкой и треем — с нормальной прокруткой и живыми анимациями.')
        hero_subtitle.setObjectName('HeroSubtitle')
        hero_subtitle.setWordWrap(True)
        hero_left.addWidget(hero_title)
        hero_left.addWidget(hero_subtitle)

        hero_buttons = QHBoxLayout()
        hero_buttons.setSpacing(10)
        self.save_button = QPushButton('💾 Сохранить')
        self.start_button = QPushButton('▶ Запустить бота')
        self.stop_button = QPushButton('■ Остановить')
        self.stop_button.setProperty('secondary', 'true')
        self.hide_button = QPushButton('🗕 В трей')
        self.hide_button.setProperty('secondary', 'true')
        hero_buttons.addWidget(self.save_button)
        hero_buttons.addWidget(self.start_button)
        hero_buttons.addWidget(self.stop_button)
        hero_buttons.addWidget(self.hide_button)
        hero_buttons.addStretch(1)
        hero_left.addLayout(hero_buttons)

        hero_layout.addLayout(hero_left, stretch=3)

        hero_right = QGridLayout()
        hero_right.setHorizontalSpacing(12)
        hero_right.setVerticalSpacing(12)
        self.bot_state_card, self.bot_state_value = self._create_stat_card('Бот', 'OFF')
        self.autostart_state_card, self.autostart_state_value = self._create_stat_card('Автозагрузка', 'OFF')
        self.admin_count_card, self.admin_count_value = self._create_stat_card('Админов', '0')
        self.mode_card, self.mode_value = self._create_stat_card('Режим', 'Окно')
        hero_right.addWidget(self.bot_state_card, 0, 0)
        hero_right.addWidget(self.autostart_state_card, 0, 1)
        hero_right.addWidget(self.admin_count_card, 1, 0)
        hero_right.addWidget(self.mode_card, 1, 1)
        hero_layout.addLayout(hero_right, stretch=2)

        self.state_badge = QLabel('Бот остановлен')
        self.state_badge.setProperty('badge', 'true')
        self._apply_badge_state(self.state_badge, 'off', 'Бот остановлен')
        hero_layout.addWidget(self.state_badge, alignment=Qt.AlignmentFlag.AlignTop)

        self._hero_effect = QGraphicsOpacityEffect(self.hero)
        self._hero_effect.setOpacity(0.0)
        self.hero.setGraphicsEffect(self._hero_effect)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_settings_tab(), 'Настройки')
        self.tabs.addTab(self._build_commands_tab(), 'Telegram')
        self.tabs.addTab(self._build_logs_tab(), 'Логи')
        self.tabs.addTab(self._build_about_tab(), 'О программе')

        self._tabs_effect = QGraphicsOpacityEffect(self.tabs)
        self._tabs_effect.setOpacity(0.0)
        self.tabs.setGraphicsEffect(self._tabs_effect)

        self._state_effect = QGraphicsOpacityEffect(self.state_badge)
        self._state_effect.setOpacity(1.0)
        self.state_badge.setGraphicsEffect(self._state_effect)

        main_layout.addWidget(self.hero)
        main_layout.addWidget(self.tabs, stretch=1)
        self.setCentralWidget(root)

    def _build_settings_tab(self) -> QWidget:
        wrapper = QWidget()
        outer = QVBoxLayout(wrapper)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(2, 2, 2, 2)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        grid.addWidget(self._build_bot_card(), 0, 0)
        grid.addWidget(self._build_autostart_card(), 0, 1)
        grid.addWidget(self._build_permissions_card(), 1, 0)
        grid.addWidget(self._build_paths_card(), 1, 1)

        scroll.setWidget(content)
        outer.addWidget(scroll)
        return wrapper

    def _build_bot_card(self) -> QWidget:
        card = QGroupBox('Подключение бота')
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        note = QLabel('Укажи токен BotFather и Telegram ID администраторов. Всё сохраняется в config.json.')
        note.setObjectName('Muted')
        note.setWordWrap(True)
        layout.addWidget(note)

        token_row = QHBoxLayout()
        token_row.setSpacing(10)
        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setPlaceholderText('Токен Telegram-бота')
        self.token_toggle_button = QToolButton()
        self.token_toggle_button.setText('👁 Показать')
        token_row.addWidget(self.token_edit, stretch=1)
        token_row.addWidget(self.token_toggle_button)
        layout.addWidget(QLabel('Bot token'))
        layout.addLayout(token_row)

        self.admins_edit = QPlainTextEdit()
        self.admins_edit.setPlaceholderText('Один Telegram user_id на строку или список через запятую')
        self.admins_edit.setMinimumHeight(145)
        layout.addWidget(QLabel('Admin IDs'))
        layout.addWidget(self.admins_edit)

        actions = QHBoxLayout()
        self.copy_commands_button = QPushButton('📋 Скопировать команды')
        self.copy_commands_button.setProperty('secondary', 'true')
        self.bot_panel_hint_button = QPushButton('🎛 Скопировать /panel')
        self.bot_panel_hint_button.setProperty('secondary', 'true')
        actions.addWidget(self.copy_commands_button)
        actions.addWidget(self.bot_panel_hint_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        return card

    def _build_autostart_card(self) -> QWidget:
        card = QGroupBox('Автозагрузка и запуск')
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.autostart_badge = QLabel('Проверка...')
        self.autostart_badge.setProperty('badge', 'true')
        self._apply_badge_state(self.autostart_badge, 'idle', 'Проверка...')
        top.addWidget(self.autostart_badge)
        top.addStretch(1)
        self.enable_autostart_button = QPushButton('✅ Включить')
        self.enable_autostart_button.setProperty('secondary', 'true')
        self.disable_autostart_button = QPushButton('🗑 Выключить')
        self.disable_autostart_button.setProperty('secondary', 'true')
        self.sync_autostart_button = QPushButton('🔄 Обновить')
        self.sync_autostart_button.setProperty('secondary', 'true')
        top.addWidget(self.enable_autostart_button)
        top.addWidget(self.disable_autostart_button)
        top.addWidget(self.sync_autostart_button)
        layout.addLayout(top)

        hint = QLabel('Автозагрузка управляется отдельно и сразу пишет или удаляет ключ Windows Run.')
        hint.setObjectName('Muted')
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.autostart_checkbox = QCheckBox('Добавлять приложение в автозагрузку Windows')
        self.start_minimized_checkbox = QCheckBox('При автозапуске сразу прятать приложение в трей')
        self.auto_start_bot_checkbox = QCheckBox('Автоматически запускать Telegram-бота при старте приложения')
        self.show_notifications_checkbox = QCheckBox('Показывать уведомления из трея')

        layout.addWidget(self.autostart_checkbox)
        layout.addWidget(self.start_minimized_checkbox)
        layout.addWidget(self.auto_start_bot_checkbox)
        layout.addWidget(self.show_notifications_checkbox)
        layout.addStretch(1)
        return card

    def _build_permissions_card(self) -> QWidget:
        card = QGroupBox('Разрешения и команды')
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        note = QLabel('Включай только нужные категории команд. Это влияет на доступные действия и команды.')
        note.setObjectName('Muted')
        note.setWordWrap(True)
        layout.addWidget(note)

        self.allow_power_commands_checkbox = QCheckBox('Разрешить питание: shutdown / reboot / sleep / lock')
        self.allow_open_url_checkbox = QCheckBox('Разрешить открытие ссылок через /openurl')
        self.allow_file_commands_checkbox = QCheckBox('Разрешить файловые команды и файловую панель')
        self.allow_process_commands_checkbox = QCheckBox('Разрешить просмотр процессов и taskkill')

        layout.addWidget(self.allow_power_commands_checkbox)
        layout.addWidget(self.allow_open_url_checkbox)
        layout.addWidget(self.allow_file_commands_checkbox)
        layout.addWidget(self.allow_process_commands_checkbox)

        files_form = QFormLayout()
        files_form.setHorizontalSpacing(16)
        files_form.setVerticalSpacing(12)
        self.files_root_edit = QLineEdit()
        self.files_root_edit.setPlaceholderText(r'Корневая папка для файловых команд, например C:\Users\Arseniy')
        files_form.addRow('Root folder', self.files_root_edit)
        layout.addLayout(files_form)
        layout.addStretch(1)
        return card

    def _build_paths_card(self) -> QWidget:
        card = QGroupBox('Пути и сервисная информация')
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        self.config_path_label = self._make_path_label()
        self.log_path_label = self._make_path_label()
        self.executable_path_label = self._make_path_label()
        self.autostart_command_label = self._make_path_label()
        self.autostart_command_label.setWordWrap(True)

        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        form.addRow('Config', self.config_path_label)
        form.addRow('Логи', self.log_path_label)
        form.addRow('Исполняемый файл', self.executable_path_label)
        form.addRow('Команда автозагрузки', self.autostart_command_label)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.open_logs_button = QPushButton('📂 Папка логов')
        self.open_logs_button.setProperty('secondary', 'true')
        self.show_config_button = QPushButton('🧩 Папка конфигурации')
        self.show_config_button.setProperty('secondary', 'true')
        buttons.addWidget(self.open_logs_button)
        buttons.addWidget(self.show_config_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addStretch(1)
        return card

    def _build_commands_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        info_card = QFrame()
        info_card.setObjectName('GlassCard')
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(18, 16, 18, 16)
        info_layout.setSpacing(8)

        title = QLabel('Команды Telegram')
        title.setObjectName('SectionTitle')
        text = QLabel('Здесь можно быстро посмотреть и скопировать доступные текстовые команды бота.')
        text.setObjectName('Muted')
        text.setWordWrap(True)
        info_layout.addWidget(title)
        info_layout.addWidget(text)

        self.commands_text = QPlainTextEdit()
        self.commands_text.setReadOnly(True)
        self.commands_text.setPlainText(HELP_TEXT)

        layout.addWidget(info_card)
        layout.addWidget(self.commands_text, stretch=1)
        return tab

    def _build_logs_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)

        controls = QHBoxLayout()
        self.clear_log_view_button = QPushButton('🧹 Очистить вид')
        self.clear_log_view_button.setProperty('secondary', 'true')
        self.refresh_log_view_button = QPushButton('🔁 Загрузить последние 200 строк')
        self.refresh_log_view_button.setProperty('secondary', 'true')
        controls.addWidget(self.clear_log_view_button)
        controls.addWidget(self.refresh_log_view_button)
        controls.addStretch(1)

        layout.addWidget(self.log_output, stretch=1)
        layout.addLayout(controls)
        return tab

    def _build_about_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        card = QGroupBox('О приложении')
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(QLabel('• Desktop app: PySide6'))
        card_layout.addWidget(QLabel('• Telegram bot: python-telegram-bot'))
        card_layout.addWidget(QLabel('• Build target: single-file EXE via PyInstaller'))
        card_layout.addWidget(QLabel('• Autostart: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run'))

        warning = QLabel('Используй приватный bot token и держи admin IDs только у доверенных аккаунтов.')
        warning.setWordWrap(True)
        warning.setObjectName('Muted')

        self.quit_button = QPushButton('⏻ Выйти из приложения')
        self.quit_button.setProperty('danger', 'true')

        layout.addWidget(card)
        layout.addWidget(warning)
        layout.addStretch(1)
        layout.addWidget(self.quit_button)
        return tab

    def _create_stat_card(self, caption: str, value: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName('MiniStatCard')
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        value_label = QLabel(value)
        value_label.setObjectName('MiniStatValue')
        caption_label = QLabel(caption)
        caption_label.setObjectName('MiniStatCaption')
        layout.addWidget(value_label)
        layout.addWidget(caption_label)
        return card, value_label

    def _make_path_label(self) -> QLabel:
        label = QLabel('')
        label.setObjectName('PathValue')
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _setup_tray(self) -> None:
        app = QApplication.instance()
        icon = app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(icon)
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip('PC Controller')

        tray_menu = QMenu(self)
        action_show = QAction('Показать окно', self)
        action_hide = QAction('Свернуть в трей', self)
        action_start = QAction('Запустить бота', self)
        action_stop = QAction('Остановить бота', self)
        action_save = QAction('Сохранить настройки', self)
        action_quit = QAction('Выход', self)

        action_show.triggered.connect(self.show_window)
        action_hide.triggered.connect(self.hide)
        action_start.triggered.connect(lambda: self.start_bot(save_before_start=True))
        action_stop.triggered.connect(self.stop_bot)
        action_save.triggered.connect(self.save_settings)
        action_quit.triggered.connect(self.quit_app)

        tray_menu.addAction(action_show)
        tray_menu.addAction(action_hide)
        tray_menu.addSeparator()
        tray_menu.addAction(action_start)
        tray_menu.addAction(action_stop)
        tray_menu.addAction(action_save)
        tray_menu.addSeparator()
        tray_menu.addAction(action_quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _connect_signals(self) -> None:
        self.save_button.clicked.connect(self.save_settings)
        self.start_button.clicked.connect(lambda: self.start_bot(save_before_start=True))
        self.stop_button.clicked.connect(self.stop_bot)
        self.hide_button.clicked.connect(self.hide)
        self.enable_autostart_button.clicked.connect(self.enable_autostart_now)
        self.disable_autostart_button.clicked.connect(self.disable_autostart_now)
        self.sync_autostart_button.clicked.connect(lambda: self.sync_autostart_ui(silent=False))
        self.token_toggle_button.clicked.connect(self.toggle_token_visibility)
        self.copy_commands_button.clicked.connect(self.copy_commands_to_clipboard)
        self.bot_panel_hint_button.clicked.connect(lambda: QApplication.clipboard().setText('/panel'))
        self.open_logs_button.clicked.connect(self.open_logs_folder)
        self.show_config_button.clicked.connect(self.open_config_folder)
        self.clear_log_view_button.clicked.connect(self.log_output.clear)
        self.refresh_log_view_button.clicked.connect(self.load_last_log_lines)
        self.quit_button.clicked.connect(self.quit_app)
        self.tabs.currentChanged.connect(self._animate_current_tab)

        self.bot_service.log_message.connect(self.append_log)
        self.bot_service.state_changed.connect(self.on_bot_state_changed)

    def _load_config_into_form(self) -> None:
        config = self.config_manager.current()
        self.token_edit.setText(config.bot_token)
        self.admins_edit.setPlainText('\n'.join(str(value) for value in config.admin_ids))
        self.autostart_checkbox.setChecked(autostart.is_enabled() or config.autostart)
        self.start_minimized_checkbox.setChecked(config.start_minimized)
        self.auto_start_bot_checkbox.setChecked(config.auto_start_bot)
        self.allow_power_commands_checkbox.setChecked(config.allow_power_commands)
        self.allow_open_url_checkbox.setChecked(config.allow_open_url_command)
        self.allow_file_commands_checkbox.setChecked(config.allow_file_commands)
        self.allow_process_commands_checkbox.setChecked(config.allow_process_commands)
        self.files_root_edit.setText(config.files_root)
        self.show_notifications_checkbox.setChecked(config.show_notifications)
        self._refresh_state_cards(config)
        self.sync_autostart_ui(silent=True)
        self.load_last_log_lines()
        self.append_log(f'Config loaded from {self.config_manager.path}')

    def _refresh_path_labels(self) -> None:
        self.config_path_label.setText(str(self.config_manager.path))
        self.log_path_label.setText(str(LOG_FILE))
        self.executable_path_label.setText(sys.executable)
        command = autostart.current_command() if autostart.is_enabled() else '(disabled)'
        self.autostart_command_label.setText(command)

    def _refresh_state_cards(self, config: AppConfig | None = None) -> None:
        current = config or self.config_manager.current()
        self.bot_state_value.setText('ON' if self.bot_service.running else 'OFF')
        self.admin_count_value.setText(str(len(current.admin_ids)))
        self.mode_value.setText('Трей' if current.start_minimized else 'Окно')

    def collect_form(self) -> AppConfig:
        return AppConfig(
            bot_token=self.token_edit.text().strip(),
            admin_ids=ConfigManager.parse_admins(self.admins_edit.toPlainText()),
            autostart=self.autostart_checkbox.isChecked(),
            start_minimized=self.start_minimized_checkbox.isChecked(),
            auto_start_bot=self.auto_start_bot_checkbox.isChecked(),
            allow_power_commands=self.allow_power_commands_checkbox.isChecked(),
            allow_open_url_command=self.allow_open_url_checkbox.isChecked(),
            allow_file_commands=self.allow_file_commands_checkbox.isChecked(),
            allow_process_commands=self.allow_process_commands_checkbox.isChecked(),
            files_root=self.files_root_edit.text().strip(),
            show_notifications=self.show_notifications_checkbox.isChecked(),
        )

    def save_settings(self) -> bool:
        try:
            config = self.collect_form()
        except ValueError:
            QMessageBox.warning(
                self,
                'Некорректные Admin IDs',
                'Каждый admin ID должен быть положительным целым числом. Можно разделять ID запятыми, пробелами или переносами строк.',
            )
            return False

        self.config_manager.save(config)

        try:
            if config.autostart:
                autostart.enable(start_minimized=config.start_minimized)
            else:
                autostart.disable()
        except Exception as exc:
            self.logger.warning('Autostart update failed: %s', exc)
            QMessageBox.warning(self, 'Автозагрузка', f'Не удалось обновить автозагрузку:\n{exc}')
            return False

        self._refresh_path_labels()
        self._refresh_state_cards(config)
        self.sync_autostart_ui(silent=True)
        self.logger.info(
            'Settings saved. admins=%s, autostart=%s, auto_start_bot=%s',
            config.admin_ids,
            config.autostart,
            config.auto_start_bot,
        )
        self._notify('Настройки сохранены.')
        return True

    def start_bot(self, save_before_start: bool = True) -> None:
        if save_before_start and not self.save_settings():
            return
        self.bot_service.start()

    def stop_bot(self) -> None:
        self.bot_service.stop()

    def on_bot_state_changed(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self._apply_badge_state(self.state_badge, 'on' if running else 'off', 'Бот запущен' if running else 'Бот остановлен')
        self.bot_state_value.setText('ON' if running else 'OFF')
        self._pulse_state_badge()
        if running:
            self._notify('Telegram-бот запущен.')
        else:
            self._notify('Telegram-бот остановлен.')

    def append_log(self, message: str) -> None:
        self.log_output.appendPlainText(message)
        scroll = self.log_output.verticalScrollBar()
        scroll.setValue(scroll.maximum())

    def load_last_log_lines(self) -> None:
        log_path = Path(LOG_FILE)
        if not log_path.exists():
            self.log_output.setPlainText('Лог-файл ещё не создан.')
            return

        lines = log_path.read_text(encoding='utf-8', errors='replace').splitlines()
        tail = '\n'.join(lines[-200:])
        self.log_output.setPlainText(tail)

    def open_logs_folder(self) -> None:
        Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        startfile(str(Path(LOG_FILE).parent))

    def open_config_folder(self) -> None:
        self.config_manager.path.parent.mkdir(parents=True, exist_ok=True)
        startfile(str(self.config_manager.path.parent))

    def sync_autostart_ui(self, silent: bool = False) -> None:
        enabled = autostart.is_enabled()
        self.autostart_checkbox.setChecked(enabled)
        self.autostart_state_value.setText('ON' if enabled else 'OFF')
        self._apply_badge_state(
            self.autostart_badge,
            'on' if enabled else 'off',
            'Автозагрузка включена' if enabled else 'Автозагрузка выключена',
        )
        self._refresh_path_labels()
        if not silent:
            self.append_log(f'Autostart registry value is currently: {"enabled" if enabled else "disabled"}')

    def enable_autostart_now(self) -> None:
        try:
            autostart.enable(start_minimized=self.start_minimized_checkbox.isChecked())
            self.autostart_checkbox.setChecked(True)
            self.sync_autostart_ui(silent=True)
            self.append_log('Autostart enabled from UI.')
            self._notify('Автозагрузка включена.')
        except Exception as exc:
            QMessageBox.warning(self, 'Автозагрузка', f'Не удалось включить автозагрузку:\n{exc}')

    def disable_autostart_now(self) -> None:
        try:
            autostart.disable()
            self.autostart_checkbox.setChecked(False)
            self.sync_autostart_ui(silent=True)
            self.append_log('Autostart disabled from UI.')
            self._notify('Автозагрузка выключена.')
        except Exception as exc:
            QMessageBox.warning(self, 'Автозагрузка', f'Не удалось выключить автозагрузку:\n{exc}')

    def copy_commands_to_clipboard(self) -> None:
        QApplication.clipboard().setText(HELP_TEXT)
        self._notify('Список команд скопирован.')

    def toggle_token_visibility(self) -> None:
        self._token_visible = not self._token_visible
        self.token_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if self._token_visible else QLineEdit.EchoMode.Password
        )
        self.token_toggle_button.setText('🙈 Скрыть' if self._token_visible else '👁 Показать')

    def show_window(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()
        self._play_intro_animation()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            if self.isVisible():
                self.hide()
            else:
                self.show_window()

    def _notify(self, text: str) -> None:
        if not self.config_manager.current().show_notifications:
            return
        self.tray_icon.showMessage('PC Controller', text)

    def _play_intro_animation(self) -> None:
        hero_effect = self._hero_effect
        tabs_effect = self._tabs_effect
        if hero_effect is None or tabs_effect is None:
            return

        hero_end = self.hero.geometry()
        tabs_end = self.tabs.geometry()
        hero_start = QRect(hero_end.x(), hero_end.y() + 18, hero_end.width(), hero_end.height())
        tabs_start = QRect(tabs_end.x(), tabs_end.y() + 28, tabs_end.width(), tabs_end.height())

        self.hero.setGeometry(hero_start)
        self.tabs.setGeometry(tabs_start)
        hero_effect.setOpacity(0.0)
        tabs_effect.setOpacity(0.0)

        hero_opacity = QPropertyAnimation(hero_effect, b'opacity', self)
        hero_opacity.setDuration(320)
        hero_opacity.setStartValue(0.0)
        hero_opacity.setEndValue(1.0)
        hero_opacity.setEasingCurve(QEasingCurve.Type.OutCubic)

        hero_slide = QPropertyAnimation(self.hero, b'geometry', self)
        hero_slide.setDuration(420)
        hero_slide.setStartValue(hero_start)
        hero_slide.setEndValue(hero_end)
        hero_slide.setEasingCurve(QEasingCurve.Type.OutCubic)

        tabs_opacity = QPropertyAnimation(tabs_effect, b'opacity', self)
        tabs_opacity.setDuration(380)
        tabs_opacity.setStartValue(0.0)
        tabs_opacity.setEndValue(1.0)
        tabs_opacity.setEasingCurve(QEasingCurve.Type.OutCubic)

        tabs_slide = QPropertyAnimation(self.tabs, b'geometry', self)
        tabs_slide.setDuration(480)
        tabs_slide.setStartValue(tabs_start)
        tabs_slide.setEndValue(tabs_end)
        tabs_slide.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._intro_group = QParallelAnimationGroup(self)
        self._intro_group.addAnimation(hero_opacity)
        self._intro_group.addAnimation(hero_slide)
        self._intro_group.addAnimation(tabs_opacity)
        self._intro_group.addAnimation(tabs_slide)
        self._intro_group.start()

    def _animate_current_tab(self) -> None:
        current = self.tabs.currentWidget()
        if current is None:
            return
        effect = QGraphicsOpacityEffect(current)
        current.setGraphicsEffect(effect)
        effect.setOpacity(0.35)
        self._tab_fade_animation = QPropertyAnimation(effect, b'opacity', self)
        self._tab_fade_animation.setDuration(220)
        self._tab_fade_animation.setStartValue(0.35)
        self._tab_fade_animation.setEndValue(1.0)
        self._tab_fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._tab_fade_animation.finished.connect(lambda: current.setGraphicsEffect(None))
        self._tab_fade_animation.start()

    def _pulse_state_badge(self) -> None:
        if self._state_effect is None:
            return
        self._state_pulse_animation = QPropertyAnimation(self._state_effect, b'opacity', self)
        self._state_pulse_animation.setDuration(320)
        self._state_pulse_animation.setStartValue(0.45)
        self._state_pulse_animation.setEndValue(1.0)
        self._state_pulse_animation.setEasingCurve(QEasingCurve.Type.OutBack)
        self._state_pulse_animation.start()

    def _apply_badge_state(self, label: QLabel, state: str, text: str) -> None:
        label.setText(text)
        label.setProperty('badgeState', state)
        style = label.style()
        style.unpolish(label)
        style.polish(label)
        label.update()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._quitting:
            super().closeEvent(event)
            return

        event.ignore()
        self.hide()
        self._notify('Окно скрыто в трей. Приложение продолжает работать.')

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._play_intro_animation)

    def quit_app(self) -> None:
        self._quitting = True
        self.bot_service.shutdown()
        self.tray_icon.hide()
        self.close()
        QApplication.instance().quit()
