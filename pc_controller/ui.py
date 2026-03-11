from __future__ import annotations

import logging
import re
import subprocess
import sys
import time
from datetime import datetime
from os import startfile
from pathlib import Path

from PySide6.QtCore import Property, QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QRect, QSize, Qt, \
    QTimer, QPoint
from PySide6.QtGui import QAction, QPainter, QColor, QPainterPath, QPen, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
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
from .config import APP_DIR, AppConfig, AdminPerms, ConfigManager
from .logging_setup import LOG_FILE

APP_STYLE = """
QWidget {
    font-family: "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 13px;
    color: #e2e8f0;
}
QMainWindow, QDialog {
    background: #0f172a;
}
QLabel {
    background: transparent;
}
QScrollArea, QScrollArea > QWidget > QWidget {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    background: rgba(30, 41, 59, 0.5);
    width: 10px;
    margin: 2px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: rgba(71, 85, 105, 0.8);
    min-height: 30px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(100, 116, 139, 1);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
    height: 0px;
}
QGroupBox {
    background: rgba(30, 41, 59, 0.4);
    border: 1px solid rgba(51, 65, 85, 0.6);
    border-radius: 12px;
    margin-top: 24px;
    padding: 20px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 16px;
    top: 4px;
    color: #93c5fd;
    font-size: 14px;
    font-weight: bold;
    background: transparent;
}
QFrame#HeroCard, QFrame#GlassCard {
    background: rgba(30, 41, 59, 0.5);
    border: 1px solid rgba(51, 65, 85, 0.6);
    border-radius: 16px;
}
QLabel#HeroTitle {
    font-size: 28px;
    font-weight: 800;
    color: #ffffff;
}
QLabel#HeroSubtitle, QLabel#Muted {
    color: #94a3b8;
    font-size: 13px;
}
QLabel#SectionTitle {
    font-size: 18px;
    font-weight: bold;
    color: #ffffff;
}
QFrame#MiniStatCard {
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(51, 65, 85, 0.4);
    border-radius: 12px;
}
QFrame#StatusStripCard {
    background: rgba(15, 23, 42, 0.45);
    border: 1px solid rgba(51, 65, 85, 0.35);
    border-radius: 14px;
}
QLabel#MiniStatValue {
    font-size: 22px;
    font-weight: bold;
    color: #ffffff;
}
QLabel#MiniStatCaption {
    color: #64748b;
    font-size: 12px;
}
QLabel#StatusKey {
    color: #93c5fd;
    font-size: 12px;
    font-weight: bold;
}
QLabel#StatusValue {
    color: #ffffff;
    font-size: 14px;
}
QLabel#StepDone {
    color: #bbf7d0;
    font-weight: bold;
}
QLabel#StepTodo {
    color: #fcd34d;
    font-weight: bold;
}
QLineEdit, QPlainTextEdit {
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(71, 85, 105, 0.5);
    border-radius: 8px;
    padding: 10px;
    color: #ffffff;
    selection-background-color: #3b82f6;
}
QLineEdit:disabled {
    background: rgba(15, 23, 42, 0.3);
    color: #64748b;
    border: 1px solid rgba(71, 85, 105, 0.3);
}
QLineEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #60a5fa;
    background: rgba(30, 41, 59, 0.9);
}
QTabWidget::pane {
    border: none;
    background: transparent;
}
QTabBar::tab {
    background: transparent;
    color: #94a3b8;
    font-size: 14px;
    font-weight: bold;
    padding: 12px 20px;
    border-bottom: 2px solid transparent;
    margin-right: 4px;
}
QTabBar::tab:selected {
    color: #ffffff;
    border-bottom: 2px solid #3b82f6;
}
QTabBar::tab:hover:!selected {
    color: #cbd5e1;
    border-bottom: 2px solid rgba(59, 130, 246, 0.5);
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2563eb, stop:1 #4f46e5);
    border: none;
    border-radius: 8px;
    color: white;
    font-weight: bold;
    font-size: 13px;
    padding: 10px 20px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3b82f6, stop:1 #6366f1);
}
QPushButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1d4ed8, stop:1 #4338ca);
}
QPushButton[secondary="true"] {
    background: rgba(30, 41, 59, 0.8);
    border: 1px solid rgba(71, 85, 105, 0.5);
}
QPushButton[secondary="true"]:hover {
    background: rgba(51, 65, 85, 0.9);
}
QPushButton[danger="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #e11d48, stop:1 #be123c);
}
QPushButton[danger="true"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f43f5e, stop:1 #e11d48);
}
QToolButton {
    background: rgba(30, 41, 59, 0.8);
    border: 1px solid rgba(71, 85, 105, 0.5);
    border-radius: 8px;
    color: #ffffff;
    padding: 8px 12px;
}
QToolButton:hover {
    background: rgba(51, 65, 85, 0.9);
}
QLabel[badge="true"] {
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: bold;
    font-size: 12px;
}
QLabel[badgeState="on"] {
    color: #bbf7d0;
    background: rgba(22, 101, 52, 0.6);
    border: 1px solid rgba(34, 197, 94, 0.4);
}
QLabel[badgeState="off"] {
    color: #fecdd3;
    background: rgba(159, 18, 57, 0.6);
    border: 1px solid rgba(225, 29, 72, 0.4);
}
QLabel[badgeState="idle"] {
    color: #dbeafe;
    background: rgba(30, 64, 175, 0.6);
    border: 1px solid rgba(59, 130, 246, 0.4);
}
QListWidget {
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(71, 85, 105, 0.5);
    border-radius: 8px;
    padding: 4px;
    color: #ffffff;
}
QListWidget::item {
    padding: 10px;
    border-radius: 4px;
}
QListWidget::item:selected {
    background: #3b82f6;
    font-weight: bold;
}
QListWidget::item:hover:!selected {
    background: rgba(59, 130, 246, 0.3);
}
"""

PERMISSION_FIELDS: list[tuple[str, str]] = [
    ('power', 'Питание'),
    ('open_url', 'Ссылки'),
    ('files', 'Файлы'),
    ('process', 'Процессы'),
    ('input', 'Ввод'),
    ('media', 'Медиа'),
]


def _asset_base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        bundle_root = getattr(sys, '_MEIPASS', '')
        if bundle_root:
            bundled_dir = Path(bundle_root) / 'pc_controller'
            if bundled_dir.exists():
                return bundled_dir
    return Path(__file__).resolve().parent


def _load_app_icon() -> QIcon:
    icon_path = _asset_base_dir() / 'icon.png'
    if icon_path.exists():
        return QIcon(str(icon_path))
    return QIcon()


class ToastWidget(QWidget):
    """Красивое всплывающее уведомление (Toast) внутри окна"""

    def __init__(self, parent, text):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel(text)
        self.label.setStyleSheet("""
            QLabel {
                background: rgba(15, 23, 42, 0.95);
                border: 1px solid #3b82f6;
                border-radius: 10px;
                color: white;
                font-weight: bold;
                padding: 12px 24px;
                font-size: 14px;
            }
        """)
        layout.addWidget(self.label)
        self.adjustSize()

        # Центрируем внизу окна
        self.move(parent.width() // 2 - self.width() // 2, parent.height() - 100)

        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)

        self.anim = QPropertyAnimation(self.effect, b"opacity")
        self.anim.setDuration(250)
        self.anim.setStartValue(0)
        self.anim.setEndValue(1)
        self.anim.start()

        QTimer.singleShot(2500, self.fade_out)
        self.show()

    def fade_out(self):
        self.anim.setStartValue(1)
        self.anim.setEndValue(0)
        self.anim.finished.connect(self.deleteLater)
        self.anim.start()


class AnimatedToggle(QCheckBox):
    """Красивый анимированный переключатель в стиле iOS"""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._position = 4
        self.animation = QPropertyAnimation(self, b"position")
        self.animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.animation.setDuration(120)
        self.toggled.connect(self.setup_animation)

    @Property(float)
    def position(self):
        return self._position

    @position.setter
    def position(self, pos):
        self._position = pos
        self.update()

    def setup_animation(self, checked):
        self.animation.stop()
        self.animation.setEndValue(24 if checked else 4)
        self.animation.start()

    def set_checked_silent(self, checked: bool):
        """Переключает статус мгновенно, без задержек и анимаций при загрузке"""
        self.blockSignals(True)
        self.setChecked(checked)
        self.position = 24.0 if checked else 4.0
        self.blockSignals(False)

    def sizeHint(self):
        size = super().sizeHint()
        return QSize(size.width() + 50, max(size.height(), 24))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)

        bg_color = QColor("#3b82f6") if self.isChecked() else QColor("#334155")
        p.setBrush(bg_color)
        p.drawRoundedRect(0, 0, 44, 24, 12, 12)

        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(int(self._position), 4, 16, 16)

        p.setPen(QColor("#f8fafc"))
        p.drawText(54, 0, self.width() - 54, self.height(),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text())
        p.end()

    def hitButton(self, pos: QPoint):
        return self.contentsRect().contains(pos)


class InstallDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Первый запуск PC Controller")
        self.setModal(True)
        self.setFixedSize(560, 270)
        self.setStyleSheet(APP_STYLE)
        app_icon = _load_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

        self.action = "leave"
        self.chosen_path = APP_DIR / ("PCController.exe" if getattr(sys, 'frozen', False) else "PCController.py")

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        title = QLabel("🚀 <b>Привет! Это первый запуск программы.</b>")
        title.setStyleSheet("font-size: 18px;")

        desc = QLabel(
            "Для правильной работы автозагрузки рекомендуется установить программу в надёжное место (чтобы файл случайно не удалился).")
        desc.setWordWrap(True)

        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit(str(self.chosen_path))
        self.path_edit.setReadOnly(True)
        self.browse_btn = QPushButton("📂 Выбрать")
        self.browse_btn.setProperty("secondary", "true")
        self.browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(self.path_edit, stretch=1)
        path_layout.addWidget(self.browse_btn)

        self.chk_desktop = QCheckBox("Добавить ярлык на рабочий стол")
        self.chk_desktop.setChecked(True)
        self.chk_start_menu = QCheckBox("Добавить ярлык в меню Пуск")
        self.chk_start_menu.setChecked(True)

        options_layout = QVBoxLayout()
        options_layout.addWidget(self.chk_desktop)
        options_layout.addWidget(self.chk_start_menu)

        btn_layout = QHBoxLayout()
        self.install_btn = QPushButton("Установить сюда")
        self.leave_btn = QPushButton("Оставить где есть")
        self.leave_btn.setProperty("secondary", "true")

        self.install_btn.clicked.connect(self._install)
        self.leave_btn.clicked.connect(self._leave)

        btn_layout.addStretch()
        btn_layout.addWidget(self.leave_btn)
        btn_layout.addWidget(self.install_btn)

        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addLayout(path_layout)
        layout.addLayout(options_layout)
        layout.addStretch()
        layout.addLayout(btn_layout)

    def _browse(self):
        file_name, _ = QFileDialog.getSaveFileName(self, "Выберите куда сохранить программу", str(self.chosen_path),
                                                   "Executable (*.exe)" if getattr(sys, 'frozen',
                                                                                   False) else "Python Script (*.py)")
        if file_name:
            self.chosen_path = Path(file_name)
            self.path_edit.setText(str(self.chosen_path))

    def _install(self):
        self.action = "install"
        self.accept()

    def _leave(self):
        self.action = "leave"
        self.accept()


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
        self._config = config_manager.current()
        self.bot_service = bot_service
        self.logger = logger
        self._quitting = False
        self._start_minimized = start_minimized
        self._token_visible = False

        self._hero_effect: QGraphicsOpacityEffect | None = None
        self._tabs_effect: QGraphicsOpacityEffect | None = None
        self._intro_group: QParallelAnimationGroup | None = None
        self._tab_fade_animation: QPropertyAnimation | None = None
        self._current_admins_data: dict[str, AdminPerms] = {}
        self._matrix_checkboxes: dict[tuple[str, str], QCheckBox] = {}
        self._log_records: list[dict[str, object]] = []
        self._last_logged_error_time: float | None = None
        self._last_logged_error_message: str | None = None
        self._loading_config = False
        self._config_dirty = False
        self._last_saved_at = self.config_manager.path.stat().st_mtime if self.config_manager.path.exists() else None

        self.setWindowTitle('PC Controller')
        self.resize(1240, 860)
        self.setMinimumSize(980, 720)
        QApplication.instance().setStyleSheet(APP_STYLE)

        self._build_ui()
        self._setup_status_bar()
        self._setup_tray()
        self._connect_signals()

        self.log_handler = QtLogHandler(self.append_log)
        self.log_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
        self.logger.addHandler(self.log_handler)

        self._load_config_into_form()
        self._start_live_ui_updates()

        if self._config.auto_start_bot:
            QTimer.singleShot(600, lambda: self.start_bot(save_before_start=False))

        if self._start_minimized:
            QTimer.singleShot(0, self.hide)
            self._notify('Приложение запущено в трее.')

    def show_toast(self, message: str):
        ToastWidget(self, message)

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
        hero_subtitle = QLabel('Современный центр управления ПК через Telegram.')
        hero_subtitle.setObjectName('HeroSubtitle')
        hero_subtitle.setWordWrap(True)
        hero_left.addWidget(hero_title)
        hero_left.addWidget(hero_subtitle)

        hero_buttons = QHBoxLayout()
        hero_buttons.setSpacing(10)
        self.save_button = QPushButton('💾 Сохранить')
        self.toggle_bot_button = QPushButton('▶ Запустить бота')
        self.hide_button = QPushButton('🗕 В трей')
        self.hide_button.setProperty('secondary', 'true')
        hero_buttons.addWidget(self.save_button)
        hero_buttons.addWidget(self.toggle_bot_button)
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
        self.dashboard_tab = self._build_dashboard_tab()
        self.settings_tab = self._build_settings_tab()
        self.permissions_tab = self._build_permissions_card()
        self.telegram_tab = self._build_commands_tab()
        self.logs_tab = self._build_logs_tab()
        self.about_tab = self._build_about_tab()

        self.tabs.addTab(self.dashboard_tab, 'Дашборд')
        self.tabs.addTab(self.settings_tab, 'Настройки')
        self.tabs.addTab(self.permissions_tab, 'Администраторы')
        self.tabs.addTab(self.telegram_tab, 'Telegram')
        self.tabs.addTab(self.logs_tab, 'Логи')
        self.tabs.addTab(self.about_tab, 'О программе')

        self._tabs_effect = QGraphicsOpacityEffect(self.tabs)
        self._tabs_effect.setOpacity(0.0)
        self.tabs.setGraphicsEffect(self._tabs_effect)

        main_layout.addWidget(self.hero)
        main_layout.addWidget(self.tabs, stretch=1)
        self.setCentralWidget(root)

    def _build_dashboard_tab(self) -> QWidget:
        wrapper = QWidget()
        outer = QVBoxLayout(wrapper)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(16)

        self.onboarding_card = QGroupBox('Быстрый старт')
        onboarding_layout = QVBoxLayout(self.onboarding_card)
        onboarding_layout.setSpacing(10)
        self.onboarding_summary_label = QLabel()
        self.onboarding_summary_label.setWordWrap(True)
        self.onboarding_summary_label.setObjectName('Muted')
        onboarding_layout.addWidget(self.onboarding_summary_label)

        self.onboarding_step_labels: list[QLabel] = []
        for _ in range(4):
            label = QLabel()
            label.setWordWrap(True)
            onboarding_layout.addWidget(label)
            self.onboarding_step_labels.append(label)

        onboarding_buttons = QHBoxLayout()
        self.onboarding_settings_button = QPushButton('⚙ Настройки')
        self.onboarding_settings_button.setProperty('secondary', 'true')
        self.onboarding_admins_button = QPushButton('👥 Админы')
        self.onboarding_admins_button.setProperty('secondary', 'true')
        self.onboarding_start_button = QPushButton('▶ Запустить бота')
        self.onboarding_panel_button = QPushButton('🎛 Скопировать /panel')
        self.onboarding_panel_button.setProperty('secondary', 'true')
        onboarding_buttons.addWidget(self.onboarding_settings_button)
        onboarding_buttons.addWidget(self.onboarding_admins_button)
        onboarding_buttons.addWidget(self.onboarding_start_button)
        onboarding_buttons.addWidget(self.onboarding_panel_button)
        onboarding_buttons.addStretch(1)
        onboarding_layout.addLayout(onboarding_buttons)
        layout.addWidget(self.onboarding_card)

        overview_card = QGroupBox('Сводка')
        overview_layout = QVBoxLayout(overview_card)
        overview_layout.setSpacing(14)

        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(12)
        stats_grid.setVerticalSpacing(12)
        self.dashboard_bot_card, self.dashboard_bot_value = self._create_stat_card('Бот', 'OFF')
        self.dashboard_scheduler_card, self.dashboard_scheduler_value = self._create_stat_card('Задач', '0')
        self.dashboard_admins_card, self.dashboard_admins_value = self._create_stat_card('Админов', '0')
        self.dashboard_ping_card, self.dashboard_ping_value = self._create_stat_card('Последний ping', '—')
        stats_grid.addWidget(self.dashboard_bot_card, 0, 0)
        stats_grid.addWidget(self.dashboard_scheduler_card, 0, 1)
        stats_grid.addWidget(self.dashboard_admins_card, 1, 0)
        stats_grid.addWidget(self.dashboard_ping_card, 1, 1)
        overview_layout.addLayout(stats_grid)

        activity_card = QFrame()
        activity_card.setObjectName('StatusStripCard')
        activity_layout = QGridLayout(activity_card)
        activity_layout.setContentsMargins(16, 16, 16, 16)
        activity_layout.setHorizontalSpacing(24)
        activity_layout.setVerticalSpacing(10)
        self.dashboard_last_reconnect_value = self._create_status_value()
        self.dashboard_last_screenshot_value = self._create_status_value()
        self.dashboard_last_webcam_value = self._create_status_value()
        self.dashboard_last_ocr_value = self._create_status_value()
        self.dashboard_last_error_value = self._create_status_value()
        self.dashboard_last_error_value.setWordWrap(True)
        self._add_status_row(activity_layout, 0, 0, 'Последний reconnect', self.dashboard_last_reconnect_value)
        self._add_status_row(activity_layout, 1, 0, 'Последний скрин', self.dashboard_last_screenshot_value)
        self._add_status_row(activity_layout, 2, 0, 'Последняя вебка', self.dashboard_last_webcam_value)
        self._add_status_row(activity_layout, 0, 2, 'Последний OCR', self.dashboard_last_ocr_value)
        self._add_status_row(activity_layout, 1, 2, 'Последняя ошибка', self.dashboard_last_error_value)
        overview_layout.addWidget(activity_card)

        quick_actions = QHBoxLayout()
        self.dashboard_refresh_button = QPushButton('🔄 Обновить')
        self.dashboard_refresh_button.setProperty('secondary', 'true')
        self.dashboard_logs_button = QPushButton('🧾 Открыть логи')
        self.dashboard_logs_button.setProperty('secondary', 'true')
        self.dashboard_copy_panel_button = QPushButton('🎛 Скопировать /panel')
        self.dashboard_copy_panel_button.setProperty('secondary', 'true')
        quick_actions.addWidget(self.dashboard_refresh_button)
        quick_actions.addWidget(self.dashboard_logs_button)
        quick_actions.addWidget(self.dashboard_copy_panel_button)
        quick_actions.addStretch(1)
        overview_layout.addLayout(quick_actions)
        layout.addWidget(overview_card)

        scroll.setWidget(content)
        outer.addWidget(scroll)
        return wrapper

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
        grid.addWidget(self._build_paths_card(), 1, 0, 1, 2)

        scroll.setWidget(content)
        outer.addWidget(scroll)
        return wrapper

    def _build_bot_card(self) -> QWidget:
        card = QGroupBox('Подключение бота')
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        token_row = QHBoxLayout()
        token_row.setSpacing(10)
        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setPlaceholderText('Токен Telegram-бота')
        self.token_edit.textChanged.connect(self._schedule_save)
        self.token_toggle_button = QToolButton()
        self.token_toggle_button.setText('👁 Показать')
        token_row.addWidget(self.token_edit, stretch=1)
        token_row.addWidget(self.token_toggle_button)
        layout.addWidget(QLabel('Bot token'))
        layout.addLayout(token_row)

        files_form = QFormLayout()
        files_form.setHorizontalSpacing(16)
        files_form.setVerticalSpacing(12)

        self.chk_allow_all_files = AnimatedToggle('Полный доступ ко всем дискам (Опасно)')
        self.chk_allow_all_files.toggled.connect(self._on_allow_all_files_toggled)
        files_form.addRow(self.chk_allow_all_files)

        self.files_root_edit = QLineEdit()
        self.files_root_edit.setPlaceholderText(r'Папка для команд файлов: C:\ ')
        self.files_root_edit.textChanged.connect(self._schedule_save)
        files_form.addRow('Корень файлов', self.files_root_edit)

        self.edit_aa_dir = QLineEdit()
        self.edit_aa_dir.setPlaceholderText('Папка шаблонов AutoAccept')
        self.edit_aa_dir.textChanged.connect(self._schedule_save)
        files_form.addRow('Шаблоны AutoAccept', self.edit_aa_dir)

        layout.addLayout(files_form)

        actions = QHBoxLayout()
        self.copy_commands_button = QPushButton('📋 Скопировать команды')
        self.copy_commands_button.setProperty('secondary', 'true')
        self.bot_panel_hint_button = QPushButton('🎛 Скопировать /panel')
        self.bot_panel_hint_button.setProperty('secondary', 'true')
        actions.addWidget(self.copy_commands_button)
        actions.addWidget(self.bot_panel_hint_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch(1)
        return card

    def _build_autostart_card(self) -> QWidget:
        card = QGroupBox('Автозагрузка и поведение')
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.autostart_badge = QLabel('Проверка...')
        self.autostart_badge.setProperty('badge', 'true')
        self._apply_badge_state(self.autostart_badge, 'idle', 'Проверка...')
        top.addWidget(self.autostart_badge)
        top.addStretch(1)
        self.sync_autostart_button = QPushButton('🔄 Обновить статус')
        self.sync_autostart_button.setProperty('secondary', 'true')
        top.addWidget(self.sync_autostart_button)
        layout.addLayout(top)

        self.autostart_checkbox = AnimatedToggle('Добавлять в автозагрузку Windows')
        self.autostart_checkbox.toggled.connect(self._on_autostart_toggled)
        self.start_minimized_checkbox = AnimatedToggle('Сразу прятать в трей при автозапуске')
        self.start_minimized_checkbox.toggled.connect(self._schedule_save)
        self.auto_start_bot_checkbox = AnimatedToggle('Запускать бота автоматически')
        self.auto_start_bot_checkbox.toggled.connect(self._schedule_save)
        self.show_notifications_checkbox = AnimatedToggle('Показывать уведомления (трей)')
        self.show_notifications_checkbox.toggled.connect(self._schedule_save)

        layout.addWidget(self.autostart_checkbox)
        layout.addWidget(self.start_minimized_checkbox)
        layout.addWidget(self.auto_start_bot_checkbox)
        layout.addWidget(self.show_notifications_checkbox)
        layout.addStretch(1)
        return card

    def _build_permissions_card(self) -> QWidget:
        card = QGroupBox('Администраторы и права доступа')
        layout = QHBoxLayout(card)
        layout.setSpacing(24)

        left_layout = QVBoxLayout()
        left_layout.setSpacing(12)
        left_layout.addWidget(QLabel('<b>Telegram IDs:</b>'))

        self.admins_list = QListWidget()
        self.admins_list.setFixedWidth(240)
        self.admins_list.itemSelectionChanged.connect(self._on_admin_selected)

        btn_layout = QHBoxLayout()
        self.add_admin_btn = QPushButton('➕ Добавить')
        self.add_admin_btn.setProperty('secondary', 'true')
        self.remove_admin_btn = QPushButton('➖ Удалить')
        self.remove_admin_btn.setProperty('secondary', 'true')
        self.add_admin_btn.clicked.connect(self._add_admin)
        self.remove_admin_btn.clicked.connect(self._remove_admin)
        btn_layout.addWidget(self.add_admin_btn)
        btn_layout.addWidget(self.remove_admin_btn)

        left_layout.addWidget(self.admins_list)
        left_layout.addLayout(btn_layout)

        self.perms_widget = QGroupBox('Матрица прав')
        perms_layout = QVBoxLayout(self.perms_widget)
        perms_layout.setSpacing(12)
        perms_layout.addWidget(QLabel('Все права видны сразу. Можно быстро включать и выключать доступ по колонкам админов.'))

        self.perms_matrix_scroll = QScrollArea()
        self.perms_matrix_scroll.setWidgetResizable(True)
        self.perms_matrix_content = QWidget()
        self.perms_matrix_layout = QGridLayout(self.perms_matrix_content)
        self.perms_matrix_layout.setContentsMargins(4, 4, 4, 4)
        self.perms_matrix_layout.setHorizontalSpacing(12)
        self.perms_matrix_layout.setVerticalSpacing(10)
        self.perms_matrix_scroll.setWidget(self.perms_matrix_content)
        perms_layout.addWidget(self.perms_matrix_scroll, stretch=1)

        layout.addLayout(left_layout)
        layout.addWidget(self.perms_widget, stretch=1)

        return card

    def _build_paths_card(self) -> QWidget:
        card = QGroupBox('Пути и сервисная информация')
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        self.config_path_label = self._make_path_label()
        self.log_path_label = self._make_path_label()
        self.executable_path_label = self._make_path_label()
        self.autostart_command_label = self._make_path_label()

        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        form.addRow('Config:', self.config_path_label)
        form.addRow('Логи:', self.log_path_label)
        form.addRow('Исполняемый файл:', self.executable_path_label)
        form.addRow('Ключ автозагрузки:', self.autostart_command_label)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.open_logs_button = QPushButton('📂 Открыть папку логов')
        self.open_logs_button.setProperty('secondary', 'true')
        self.show_config_button = QPushButton('🧩 Открыть папку конфига')
        self.show_config_button.setProperty('secondary', 'true')
        self.install_app_button = QPushButton('📦 Установить приложение...')
        self.install_app_button.setProperty('secondary', 'true')
        buttons.addWidget(self.open_logs_button)
        buttons.addWidget(self.show_config_button)
        buttons.addWidget(self.install_app_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
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

        filters = QHBoxLayout()
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(['Все', 'INFO', 'WARNING', 'ERROR'])
        self.log_search_edit = QLineEdit()
        self.log_search_edit.setPlaceholderText('Поиск по строкам логов...')
        self.log_errors_today_button = QPushButton('⛔ Только ошибки за сегодня')
        self.log_errors_today_button.setProperty('secondary', 'true')
        self.log_errors_today_button.setCheckable(True)
        self.log_pause_autoscroll_checkbox = QCheckBox('Пауза автоскролла')
        filters.addWidget(QLabel('Уровень'))
        filters.addWidget(self.log_level_combo)
        filters.addWidget(self.log_search_edit, stretch=1)
        filters.addWidget(self.log_errors_today_button)
        filters.addWidget(self.log_pause_autoscroll_checkbox)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)

        controls = QHBoxLayout()
        self.clear_log_view_button = QPushButton('🧹 Очистить вид')
        self.clear_log_view_button.setProperty('secondary', 'true')
        self.refresh_log_view_button = QPushButton('🔁 Загрузить последние 200 строк')
        self.refresh_log_view_button.setProperty('secondary', 'true')
        self.copy_log_selection_button = QPushButton('📋 Копировать выделенное')
        self.copy_log_selection_button.setProperty('secondary', 'true')
        controls.addWidget(self.clear_log_view_button)
        controls.addWidget(self.refresh_log_view_button)
        controls.addWidget(self.copy_log_selection_button)
        controls.addStretch(1)

        layout.addLayout(filters)
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

        warning = QLabel('Берегите свой Bot Token. Добавляйте в список администраторов только свои Telegram ID.')
        warning.setWordWrap(True)
        warning.setObjectName('Muted')

        self.quit_button = QPushButton('⏻ Полностью закрыть приложение')
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

    @staticmethod
    def _create_status_value() -> QLabel:
        label = QLabel('—')
        label.setObjectName('StatusValue')
        label.setWordWrap(True)
        return label

    def _add_status_row(self, layout: QGridLayout, row: int, column: int, title: str, value_label: QLabel) -> None:
        key = QLabel(title)
        key.setObjectName('StatusKey')
        layout.addWidget(key, row, column)
        layout.addWidget(value_label, row, column + 1)

    def _make_path_label(self) -> QLabel:
        label = QLabel('')
        label.setObjectName('PathValue')
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _setup_tray(self) -> None:
        app = QApplication.instance()
        icon = _load_app_icon()
        if icon.isNull():
            icon = app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        app.setWindowIcon(icon)
        self.setWindowIcon(icon)
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip('PC Controller')

        tray_menu = QMenu(self)
        action_show = QAction('Показать окно', self)
        action_hide = QAction('Свернуть в трей', self)
        action_toggle_bot = QAction('Вкл / Выкл Бота', self)
        action_quit = QAction('Выход', self)

        action_show.triggered.connect(self.show_window)
        action_hide.triggered.connect(self.hide)
        action_toggle_bot.triggered.connect(self._on_toggle_bot_clicked)
        action_quit.triggered.connect(self.quit_app)

        tray_menu.addAction(action_show)
        tray_menu.addAction(action_hide)
        tray_menu.addSeparator()
        tray_menu.addAction(action_toggle_bot)
        tray_menu.addSeparator()
        tray_menu.addAction(action_quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _setup_status_bar(self) -> None:
        status = self.statusBar()
        status.setSizeGripEnabled(False)

        self.status_bot_label = QLabel()
        self.status_autostart_label = QLabel()
        self.status_config_label = QLabel()
        self.status_last_save_label = QLabel()
        self.status_log_lines_label = QLabel()
        self.status_scheduler_label = QLabel()

        for label in (
            self.status_bot_label,
            self.status_autostart_label,
            self.status_config_label,
            self.status_last_save_label,
            self.status_log_lines_label,
            self.status_scheduler_label,
        ):
            label.setObjectName('Muted')
            status.addPermanentWidget(label)

        self._refresh_status_bar()

    def _start_live_ui_updates(self) -> None:
        self._live_ui_timer = QTimer(self)
        self._live_ui_timer.setInterval(1000)
        self._live_ui_timer.timeout.connect(self._refresh_live_panels)
        self._live_ui_timer.start()
        self._refresh_live_panels()

    def _connect_signals(self) -> None:
        self.save_button.clicked.connect(self.save_settings)
        self.toggle_bot_button.clicked.connect(self._on_toggle_bot_clicked)
        self.hide_button.clicked.connect(self.hide)
        self.sync_autostart_button.clicked.connect(lambda: self.sync_autostart_ui(silent=False))
        self.token_toggle_button.clicked.connect(self.toggle_token_visibility)
        self.copy_commands_button.clicked.connect(self.copy_commands_to_clipboard)
        self.bot_panel_hint_button.clicked.connect(self.copy_panel_to_clipboard)
        self.open_logs_button.clicked.connect(self.open_logs_folder)
        self.show_config_button.clicked.connect(self.open_config_folder)
        self.install_app_button.clicked.connect(self.open_install_dialog)
        self.clear_log_view_button.clicked.connect(self._clear_log_view)
        self.refresh_log_view_button.clicked.connect(self.load_last_log_lines)
        self.copy_log_selection_button.clicked.connect(self._copy_selected_logs)
        self.quit_button.clicked.connect(self.quit_app)
        self.tabs.currentChanged.connect(self._animate_current_tab)
        self.log_level_combo.currentTextChanged.connect(self._render_logs)
        self.log_search_edit.textChanged.connect(self._render_logs)
        self.log_errors_today_button.toggled.connect(self._render_logs)
        self.dashboard_refresh_button.clicked.connect(self._refresh_live_panels)
        self.dashboard_logs_button.clicked.connect(lambda: self.tabs.setCurrentWidget(self.logs_tab))
        self.dashboard_copy_panel_button.clicked.connect(self.copy_panel_to_clipboard)
        self.onboarding_settings_button.clicked.connect(lambda: self.tabs.setCurrentWidget(self.settings_tab))
        self.onboarding_admins_button.clicked.connect(lambda: self.tabs.setCurrentWidget(self.permissions_tab))
        self.onboarding_start_button.clicked.connect(self._on_toggle_bot_clicked)
        self.onboarding_panel_button.clicked.connect(self.copy_panel_to_clipboard)

        self.bot_service.log_message.connect(self.append_log)
        self.bot_service.state_changed.connect(self.on_bot_state_changed)

    def _refresh_live_panels(self, *_args) -> None:
        self._refresh_dashboard()
        self._refresh_status_bar()

    def _refresh_status_bar(self) -> None:
        runtime = self.bot_service.get_runtime_snapshot()
        bot_text = 'Bot ON' if runtime.get('running') else 'Bot OFF'
        autostart_text = 'Autostart ON' if self.autostart_checkbox.isChecked() else 'Autostart OFF' if hasattr(self, 'autostart_checkbox') else 'Autostart ?'
        config_text = 'Config saved' if not self._config_dirty else 'Config pending'
        last_save_text = f'Last save {self._format_timestamp(self._last_saved_at)}' if self._last_saved_at else 'Last save —'
        self.status_bot_label.setText(bot_text)
        self.status_autostart_label.setText(autostart_text)
        self.status_config_label.setText(config_text)
        self.status_last_save_label.setText(last_save_text)
        self.status_log_lines_label.setText(f'Log lines {len(self._log_records)}')
        self.status_scheduler_label.setText(f'Scheduler {runtime.get("scheduler_jobs", 0)} jobs')

    def _refresh_dashboard(self) -> None:
        runtime = self.bot_service.get_runtime_snapshot()
        self.dashboard_bot_value.setText('ON' if runtime.get('running') else 'OFF')
        self.dashboard_scheduler_value.setText(str(runtime.get('scheduler_jobs', 0)))
        self.dashboard_admins_value.setText(str(len(self._current_admins_data)))
        self.dashboard_ping_value.setText(self._format_timestamp(runtime.get('last_ping')))
        self.dashboard_last_reconnect_value.setText(self._format_timestamp(runtime.get('last_successful_reconnect')))
        self.dashboard_last_screenshot_value.setText(
            self._format_event(runtime.get('last_screenshot'), runtime.get('last_screenshot_detail'))
        )
        self.dashboard_last_webcam_value.setText(
            self._format_event(runtime.get('last_webcam'), runtime.get('last_webcam_detail'))
        )
        self.dashboard_last_ocr_value.setText(
            self._format_event(runtime.get('last_ocr'), runtime.get('last_ocr_detail'))
        )

        runtime_error_ts = runtime.get('last_error_time')
        runtime_error_msg = runtime.get('last_error_message')
        if self._last_logged_error_time and (
            runtime_error_ts is None or self._last_logged_error_time > float(runtime_error_ts)
        ):
            self.dashboard_last_error_value.setText(self._format_event(self._last_logged_error_time, self._last_logged_error_message))
        else:
            self.dashboard_last_error_value.setText(self._format_event(runtime_error_ts, runtime_error_msg))

        self._update_onboarding_card()

    def _update_onboarding_card(self) -> None:
        token_ready = bool(self.token_edit.text().strip()) if hasattr(self, 'token_edit') else False
        admins_ready = bool(self._current_admins_data)
        bot_ready = self.bot_service.running
        panel_ready = bot_ready
        steps = [
            (token_ready, '1. Вставьте токен бота в Настройках.'),
            (admins_ready, '2. Добавьте свой Telegram ID в Администраторы.'),
            (bot_ready, '3. Запустите бота из приложения.'),
            (panel_ready, '4. Отправьте в Telegram команду /panel.'),
        ]
        pending_count = sum(0 if done else 1 for done, _ in steps)
        if pending_count == 0:
            self.onboarding_summary_label.setText('Базовая настройка завершена. Панель готова к работе.')
        else:
            self.onboarding_summary_label.setText(f'Осталось шагов: {pending_count}. Идите сверху вниз, без лишней возни.')

        for label, (done, text) in zip(self.onboarding_step_labels, steps):
            label.setObjectName('StepDone' if done else 'StepTodo')
            prefix = '✓' if done else '•'
            label.setText(f'{prefix} {text}')
            label.style().unpolish(label)
            label.style().polish(label)
        self.onboarding_card.setVisible(pending_count > 0)

    @staticmethod
    def _format_timestamp(raw_ts: object) -> str:
        if raw_ts in (None, '', 0):
            return '—'
        try:
            value = float(raw_ts)
        except (TypeError, ValueError):
            return str(raw_ts)
        stamp = datetime.fromtimestamp(value)
        now = datetime.now()
        if stamp.date() == now.date():
            return stamp.strftime('%H:%M:%S')
        return stamp.strftime('%d.%m %H:%M')

    def _format_event(self, raw_ts: object, detail: object) -> str:
        base = self._format_timestamp(raw_ts)
        if base == '—':
            return base
        detail_text = str(detail).strip() if detail else ''
        return f'{base} ({detail_text})' if detail_text else base

    def _set_config_dirty(self, dirty: bool) -> None:
        self._config_dirty = dirty
        self._refresh_status_bar()

    @staticmethod
    def _detect_log_level(line: str) -> str:
        upper_line = line.upper()
        lower_line = line.lower()
        if '| ERROR |' in upper_line or '❌' in line or 'ошиб' in lower_line or 'failed' in lower_line:
            return 'ERROR'
        if '| WARNING |' in upper_line or '⚠' in line or 'warning' in lower_line or 'warn' in lower_line:
            return 'WARNING'
        return 'INFO'

    def _make_log_record(self, line: str) -> dict[str, object]:
        text = str(line or '').rstrip()
        ts = time.time()
        rendered_text = text
        match = re.match(r'^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d+)?) \| (?P<level>[A-Z]+) \| (?P<msg>.*)$', text)
        if match:
            raw_ts = match.group('ts')
            level = match.group('level').upper()
            try:
                ts = datetime.strptime(raw_ts, '%Y-%m-%d %H:%M:%S,%f').timestamp()
            except ValueError:
                try:
                    ts = datetime.strptime(raw_ts, '%Y-%m-%d %H:%M:%S').timestamp()
                except ValueError:
                    ts = time.time()
        else:
            level = self._detect_log_level(text)
            rendered_text = f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | {level} | {text}'
        return {
            'ts': ts,
            'dt': datetime.fromtimestamp(ts),
            'level': level,
            'text': rendered_text,
            'raw': text,
        }

    def _filtered_log_records(self) -> list[dict[str, object]]:
        search = self.log_search_edit.text().strip().lower() if hasattr(self, 'log_search_edit') else ''
        selected_level = self.log_level_combo.currentText() if hasattr(self, 'log_level_combo') else 'Все'
        only_errors_today = self.log_errors_today_button.isChecked() if hasattr(self, 'log_errors_today_button') else False
        today = datetime.now().date()

        result: list[dict[str, object]] = []
        for record in self._log_records:
            level = str(record['level'])
            text = str(record['text'])
            dt = record['dt']
            if selected_level != 'Все' and level != selected_level:
                continue
            if only_errors_today and (level != 'ERROR' or getattr(dt, 'date', lambda: None)() != today):
                continue
            if search and search not in text.lower():
                continue
            result.append(record)
        return result

    def _render_logs(self, *_args) -> None:
        if not hasattr(self, 'log_output'):
            return
        filtered = self._filtered_log_records()
        text = '\n'.join(str(record['text']) for record in filtered).strip()
        self.log_output.setPlainText(text or 'Нет записей для текущего фильтра.')
        if not self.log_pause_autoscroll_checkbox.isChecked():
            scroll = self.log_output.verticalScrollBar()
            scroll.setValue(scroll.maximum())
        self._refresh_status_bar()

    def _clear_log_view(self, *_args) -> None:
        self._log_records.clear()
        self.log_output.clear()
        self._refresh_status_bar()

    def _copy_selected_logs(self, *_args) -> None:
        cursor = self.log_output.textCursor()
        selected = cursor.selectedText().replace('\u2029', '\n').strip()
        if not selected:
            selected = self.log_output.toPlainText().strip()
        if selected:
            QApplication.clipboard().setText(selected)
            self.show_toast('📋 Логи скопированы')

    def _rebuild_permissions_matrix(self) -> None:
        if not hasattr(self, 'perms_matrix_layout'):
            return

        self._matrix_checkboxes.clear()
        while self.perms_matrix_layout.count():
            item = self.perms_matrix_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        admins = list(self._current_admins_data.keys())
        if not admins:
            empty = QLabel('Сначала добавьте хотя бы один Telegram ID. Потом матрица прав заполнится автоматически.')
            empty.setObjectName('Muted')
            empty.setWordWrap(True)
            self.perms_matrix_layout.addWidget(empty, 0, 0)
            return

        header = QLabel('Право')
        header.setObjectName('SectionTitle')
        self.perms_matrix_layout.addWidget(header, 0, 0)
        for col, admin_id in enumerate(admins, start=1):
            label = QLabel(admin_id)
            label.setObjectName('SectionTitle')
            label.setWordWrap(True)
            self.perms_matrix_layout.addWidget(label, 0, col)

        for row, (field_name, title) in enumerate(PERMISSION_FIELDS, start=1):
            label = QLabel(title)
            self.perms_matrix_layout.addWidget(label, row, 0)
            for col, admin_id in enumerate(admins, start=1):
                checkbox = QCheckBox()
                checkbox.setChecked(getattr(self._current_admins_data[admin_id], field_name))
                checkbox.stateChanged.connect(
                    lambda _state, a=admin_id, f=field_name, box=checkbox: self._on_matrix_perm_changed(a, f, box.isChecked())
                )
                self._matrix_checkboxes[(admin_id, field_name)] = checkbox
                self.perms_matrix_layout.addWidget(checkbox, row, col, alignment=Qt.AlignmentFlag.AlignCenter)

        self.perms_matrix_layout.setColumnStretch(len(admins) + 1, 1)

    def _on_matrix_perm_changed(self, admin_id: str, field_name: str, checked: bool) -> None:
        perms = self._current_admins_data.get(admin_id)
        if perms is None:
            return
        setattr(perms, field_name, checked)
        self._schedule_save()

    def _add_admin(self):
        text, ok = QInputDialog.getText(self, 'Добавить админа', 'Введите Telegram ID администратора:')
        if ok and text.strip().isdigit():
            admin_id = text.strip()
            if admin_id not in self._current_admins_data:
                self._current_admins_data[admin_id] = AdminPerms()
                self.admins_list.addItem(admin_id)
                self.admins_list.setCurrentRow(self.admins_list.count() - 1)
                self._rebuild_permissions_matrix()
                self._refresh_state_cards()
                self._schedule_save()

    def _remove_admin(self):
        row = self.admins_list.currentRow()
        if row >= 0:
            admin_id = self.admins_list.item(row).text()
            del self._current_admins_data[admin_id]
            self.admins_list.takeItem(row)
            self._rebuild_permissions_matrix()
            self._refresh_state_cards()
            self._schedule_save()

    def _on_admin_selected(self):
        self._rebuild_permissions_matrix()

    def _update_current_admin_perm(self, field_name: str):
        self._rebuild_permissions_matrix()

    def _load_config_into_form(self) -> None:
        self._loading_config = True
        try:
            self.token_edit.setText(self._config.bot_token)

            self.autostart_checkbox.set_checked_silent(self._config.autostart)
            self.start_minimized_checkbox.set_checked_silent(self._config.start_minimized)
            self.auto_start_bot_checkbox.set_checked_silent(self._config.auto_start_bot)
            self.show_notifications_checkbox.set_checked_silent(self._config.show_notifications)

            self.chk_allow_all_files.set_checked_silent(self._config.allow_all_files)
            self.files_root_edit.setEnabled(not self._config.allow_all_files)

            self.files_root_edit.setText(self._config.files_root)
            self.edit_aa_dir.setText(self._config.autoaccept_templates_dir)

            from copy import deepcopy
            self._current_admins_data = {}
            self.admins_list.clear()
            for admin_id, perms in self._config.admins.items():
                self._current_admins_data[admin_id] = deepcopy(perms)
                self.admins_list.addItem(admin_id)

            if self.admins_list.count() > 0:
                self.admins_list.setCurrentRow(0)
        finally:
            self._loading_config = False

        self._rebuild_permissions_matrix()
        self._refresh_state_cards()
        self.sync_autostart_ui(silent=True)
        self.load_last_log_lines()
        self.append_log(f'Config loaded from {self.config_manager.path}')
        self._set_config_dirty(False)
        self._refresh_live_panels()

    def _on_allow_all_files_toggled(self, checked: bool) -> None:
        self.files_root_edit.setEnabled(not checked)
        self._schedule_save()

    def _refresh_path_labels(self) -> None:
        self.config_path_label.setText(str(self.config_manager.path))
        self.log_path_label.setText(str(LOG_FILE))
        self.executable_path_label.setText(sys.executable)
        command = autostart.current_command() if autostart.is_enabled() else '(disabled)'
        self.autostart_command_label.setText(command)

    def _refresh_state_cards(self) -> None:
        self.bot_state_value.setText('ON' if self.bot_service.running else 'OFF')
        self.admin_count_value.setText(str(len(self._current_admins_data)))
        start_minimized = self.start_minimized_checkbox.isChecked() if hasattr(self, 'start_minimized_checkbox') else self._config.start_minimized
        self.mode_value.setText('Трей' if start_minimized else 'Окно')
        if hasattr(self, 'dashboard_admins_value'):
            self.dashboard_admins_value.setText(str(len(self._current_admins_data)))

    def _schedule_save(self, *_):
        """Сохранение конфига с задержкой (Debounce), чтобы не было фризов UI при быстром клике"""
        if self._loading_config:
            return
        self._set_config_dirty(True)
        self._refresh_state_cards()
        if hasattr(self, '_save_timer'):
            self._save_timer.stop()
        else:
            self._save_timer = QTimer(self)
            self._save_timer.setSingleShot(True)
            self._save_timer.setInterval(300)
            self._save_timer.timeout.connect(self._save_settings_immediate)
        self._save_timer.start()

    def _save_settings_immediate(self) -> None:
        self._config.bot_token = self.token_edit.text().strip()
        self._config.admins = self._current_admins_data
        self._config.autostart = self.autostart_checkbox.isChecked()
        self._config.start_minimized = self.start_minimized_checkbox.isChecked()
        self._config.auto_start_bot = self.auto_start_bot_checkbox.isChecked()
        self._config.show_notifications = self.show_notifications_checkbox.isChecked()
        self._config.allow_all_files = self.chk_allow_all_files.isChecked()
        self._config.files_root = self.files_root_edit.text().strip()
        self._config.autoaccept_templates_dir = self.edit_aa_dir.text().strip()
        self._config = self.config_manager.save(self._config)
        self._last_saved_at = time.time()
        self._set_config_dirty(False)
        self._refresh_state_cards()
        self._refresh_live_panels()

    def save_settings(self) -> bool:
        self._save_settings_immediate()
        self._refresh_path_labels()
        self.show_toast('💾 Настройки сохранены')
        return True

    def _on_autostart_toggled(self, checked: bool):
        try:
            if checked:
                autostart.enable(self.start_minimized_checkbox.isChecked())
            else:
                if hasattr(autostart, 'disable'):
                    autostart.disable()
        except Exception as e:
            self.logger.error(f"Ошибка настройки автозагрузки: {e}")
        self.sync_autostart_ui(silent=True)
        self._schedule_save()

    def _on_toggle_bot_clicked(self) -> None:
        if self.bot_service.running:
            self.stop_bot()
        else:
            self.start_bot(save_before_start=True)

    def start_bot(self, save_before_start: bool = True) -> None:
        if save_before_start and not self.save_settings():
            return
        self.bot_service.start()

    def stop_bot(self) -> None:
        self.bot_service.stop()

    def on_bot_state_changed(self, running: bool) -> None:
        if running:
            self.toggle_bot_button.setText('■ Остановить бота')
            self.toggle_bot_button.setProperty('danger', 'true')
            self._apply_badge_state(self.state_badge, 'on', 'Бот запущен')
            self._notify('Telegram-бот запущен.')
        else:
            self.toggle_bot_button.setText('▶ Запустить бота')
            self.toggle_bot_button.setProperty('danger', 'false')
            self._apply_badge_state(self.state_badge, 'off', 'Бот остановлен')
            self._notify('Telegram-бот остановлен.')

        self.toggle_bot_button.style().unpolish(self.toggle_bot_button)
        self.toggle_bot_button.style().polish(self.toggle_bot_button)
        self.bot_state_value.setText('ON' if running else 'OFF')
        self._refresh_live_panels()

    def append_log(self, message: str) -> None:
        record = self._make_log_record(message)
        self._log_records.append(record)
        if len(self._log_records) > 2000:
            self._log_records = self._log_records[-2000:]
        if str(record['level']) == 'ERROR':
            self._last_logged_error_time = float(record['ts'])
            self._last_logged_error_message = str(record['raw'])
        self._render_logs()
        self._refresh_dashboard()

    def load_last_log_lines(self) -> None:
        log_path = Path(LOG_FILE)
        if not log_path.exists():
            self._log_records = []
            self.log_output.setPlainText('Лог-файл ещё не создан.')
            self._refresh_status_bar()
            return

        lines = log_path.read_text(encoding='utf-8', errors='replace').splitlines()
        self._log_records = [self._make_log_record(line) for line in lines[-200:]]
        self._last_logged_error_time = None
        self._last_logged_error_message = None
        for record in self._log_records:
            if str(record['level']) == 'ERROR':
                self._last_logged_error_time = float(record['ts'])
                self._last_logged_error_message = str(record['raw'])
        self._render_logs()

    def open_logs_folder(self) -> None:
        Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        startfile(str(Path(LOG_FILE).parent))

    def open_config_folder(self) -> None:
        self.config_manager.path.parent.mkdir(parents=True, exist_ok=True)
        startfile(str(self.config_manager.path.parent))

    def open_install_dialog(self) -> None:
        run_install_dialog(parent=self, force=True)

    def sync_autostart_ui(self, silent: bool = False) -> None:
        enabled = autostart.is_enabled()
        self.autostart_checkbox.set_checked_silent(enabled)

        self.autostart_state_value.setText('ON' if enabled else 'OFF')
        self._apply_badge_state(
            self.autostart_badge,
            'on' if enabled else 'off',
            'Автозагрузка включена' if enabled else 'Автозагрузка выключена',
        )
        self._refresh_path_labels()
        if not silent:
            self.show_toast('🔄 Статус автозагрузки обновлен')
            self.append_log(f'Autostart registry value is currently: {"enabled" if enabled else "disabled"}')
        self._refresh_live_panels()

    def copy_commands_to_clipboard(self) -> None:
        QApplication.clipboard().setText(HELP_TEXT)
        self.show_toast('📋 Команды скопированы')

    def copy_panel_to_clipboard(self) -> None:
        QApplication.clipboard().setText('/panel')
        self.show_toast('📋 Скопировано: /panel')

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
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.isVisible() and self.isActiveWindow():
                self.hide()
            else:
                self.show_window()

    def _notify(self, text: str) -> None:
        if not self._config.show_notifications:
            return
        self.tray_icon.showMessage('PC Controller', text, QSystemTrayIcon.MessageIcon.Information, 2000)

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
        effect.setOpacity(0.0)

        self._tab_fade_animation = QPropertyAnimation(effect, b'opacity', self)
        self._tab_fade_animation.setDuration(300)
        self._tab_fade_animation.setStartValue(0.0)
        self._tab_fade_animation.setEndValue(1.0)
        self._tab_fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._tab_fade_animation.finished.connect(lambda: current.setGraphicsEffect(None))

        self._tab_fade_animation.start()

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


def _current_install_source_path() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve()
    return Path(__file__).resolve().parent


def _default_install_dir() -> Path:
    return Path.home() / 'AppData' / 'Local' / 'PCController'


def _is_inside_install_dir(current_path: Path, install_dir: Path) -> bool:
    return current_path == install_dir or install_dir in current_path.parents or current_path.parent == install_dir


def run_install_dialog(parent=None, force: bool = False) -> None:
    """Показывает диалог установки и при необходимости копирует программу в целевую папку."""
    current_path = _current_install_source_path()
    default_install_dir = _default_install_dir()
    config_manager = ConfigManager()
    config = config_manager.current()

    if not force:
        if not getattr(sys, 'frozen', False):
            return
        if _is_inside_install_dir(current_path, default_install_dir):
            if not config.installed:
                config.installed = True
                config_manager.save(config)
            return
        if config.installed:
            return

    dialog = InstallDialog(parent)
    dialog.exec()

    if dialog.action != "install":
        if not force:
            config.installed = True
            config_manager.save(config)
        return

    target_dir = dialog.chosen_path.parent
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        if getattr(sys, 'frozen', False):
            target_exe = dialog.chosen_path
            if target_exe.resolve() == current_path:
                QMessageBox.information(parent, "Установка", "Программа уже запущена из этой папки.")
                return
            import shutil
            shutil.copy2(current_path, target_exe)
            installed_path = target_exe
        else:
            import shutil
            shutil.copytree(current_path, target_dir, dirs_exist_ok=True)
            installed_path = target_dir / current_path.name if current_path.is_file() else target_dir / 'main.py'

        if dialog.chk_desktop.isChecked() or dialog.chk_start_menu.isChecked():
            try:
                from win32com.client import Dispatch
                shell = Dispatch('WScript.Shell')

                if dialog.chk_desktop.isChecked():
                    desktop = Path(shell.SpecialFolders("Desktop"))
                    shortcut = shell.CreateShortCut(str(desktop / "PC Controller.lnk"))
                    shortcut.Targetpath = str(installed_path)
                    shortcut.WorkingDirectory = str(installed_path.parent)
                    shortcut.IconLocation = str(installed_path)
                    shortcut.save()

                if dialog.chk_start_menu.isChecked():
                    programs = Path(shell.SpecialFolders("Programs"))
                    shortcut = shell.CreateShortCut(str(programs / "PC Controller.lnk"))
                    shortcut.Targetpath = str(installed_path)
                    shortcut.WorkingDirectory = str(installed_path.parent)
                    shortcut.IconLocation = str(installed_path)
                    shortcut.save()
            except Exception as e:
                print(f"Не удалось создать ярлыки: {e}")

        config.installed = True
        config_manager.save(config)

        if getattr(sys, 'frozen', False):
            subprocess.Popen([str(installed_path)])
        else:
            subprocess.Popen([sys.executable, str(installed_path)])
        sys.exit(0)
    except Exception as e:
        QMessageBox.critical(parent, "Ошибка", f"Не удалось скопировать файлы:\n{e}")


def check_first_run_and_install():
    """Диалог установки при первом запуске."""
    run_install_dialog(force=False)
