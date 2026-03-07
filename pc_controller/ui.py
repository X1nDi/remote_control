from __future__ import annotations

import logging
import subprocess
import sys
from os import startfile
from pathlib import Path

from PySide6.QtCore import Property, QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QRect, QSize, Qt, \
    QTimer, QPoint
from PySide6.QtGui import QAction, QPainter, QColor, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
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
QLabel#MiniStatValue {
    font-size: 22px;
    font-weight: bold;
    color: #ffffff;
}
QLabel#MiniStatCaption {
    color: #64748b;
    font-size: 12px;
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
        self.setFixedSize(560, 240)
        self.setStyleSheet(APP_STYLE)

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
        layout.addStretch()
        layout.addLayout(btn_layout)

    def _browse(self):
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Выберите куда сохранить программу",
            str(self.chosen_path),
            "Executable (*.exe)" if getattr(sys, 'frozen', False) else "Python Script (*.py)"
        )
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

        if not self._config.installed:
            QTimer.singleShot(100, self._show_install_prompt)

        if self._config.auto_start_bot:
            QTimer.singleShot(600, lambda: self.start_bot(save_before_start=False))

        if self._start_minimized:
            QTimer.singleShot(0, self.hide)
            self._notify('Приложение запущено в трее.')

    def show_toast(self, message: str):
        ToastWidget(self, message)

    def _show_install_prompt(self):
        if self._config.installed:
            return

        dialog = InstallDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.action == "install":
                target_path = dialog.chosen_path
                try:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    if getattr(sys, 'frozen', False):
                        import shutil
                        shutil.copy2(sys.executable, target_path)
                    else:
                        import shutil
                        shutil.copy2(sys.argv[0], target_path)

                    self._config.installed = True
                    self.config_manager.save(self._config)

                    subprocess.Popen([str(target_path)])
                    QApplication.instance().quit()
                    return
                except Exception as e:
                    QMessageBox.warning(self, "Ошибка", f"Не удалось скопировать файл:\n{e}")

            self._config.installed = True
            self.config_manager.save(self._config)

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
        self.tabs.addTab(self._build_settings_tab(), 'Настройки')
        self.tabs.addTab(self._build_permissions_card(), 'Администраторы')
        self.tabs.addTab(self._build_commands_tab(), 'Telegram')
        self.tabs.addTab(self._build_logs_tab(), 'Логи')
        self.tabs.addTab(self._build_about_tab(), 'О программе')

        self._tabs_effect = QGraphicsOpacityEffect(self.tabs)
        self._tabs_effect.setOpacity(0.0)
        self.tabs.setGraphicsEffect(self._tabs_effect)

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

        self.perms_widget = QWidget()
        perms_layout = QVBoxLayout(self.perms_widget)
        perms_layout.setSpacing(16)

        self.perm_power = AnimatedToggle('🔋 Питание (выключение, ребут, сон, лок)')
        self.perm_open_url = AnimatedToggle('🌐 Открытие ссылок (/openurl)')
        self.perm_files = AnimatedToggle('🗂 Файлы (перемещение, загрузка, скачивание)')
        self.perm_process = AnimatedToggle('⚙️ Процессы (просмотр и завершение taskkill)')
        self.perm_input = AnimatedToggle('⌨️ Ввод (мышь, текст, клавиши, AutoAccept)')
        self.perm_media = AnimatedToggle('🎥 Медиа (камера, аудио, скриншоты)')

        self.perm_power.toggled.connect(lambda: self._update_current_admin_perm('power'))
        self.perm_open_url.toggled.connect(lambda: self._update_current_admin_perm('open_url'))
        self.perm_files.toggled.connect(lambda: self._update_current_admin_perm('files'))
        self.perm_process.toggled.connect(lambda: self._update_current_admin_perm('process'))
        self.perm_input.toggled.connect(lambda: self._update_current_admin_perm('input'))
        self.perm_media.toggled.connect(lambda: self._update_current_admin_perm('media'))

        perms_layout.addWidget(QLabel('<b>Индивидуальные права для выбранного админа:</b>'))
        perms_layout.addWidget(self.perm_power)
        perms_layout.addWidget(self.perm_open_url)
        perms_layout.addWidget(self.perm_files)
        perms_layout.addWidget(self.perm_process)
        perms_layout.addWidget(self.perm_input)
        perms_layout.addWidget(self.perm_media)
        perms_layout.addStretch()

        self.perms_widget.setEnabled(False)

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
        buttons.addWidget(self.open_logs_button)
        buttons.addWidget(self.show_config_button)
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
        self.clear_log_view_button.clicked.connect(self.log_output.clear)
        self.refresh_log_view_button.clicked.connect(self.load_last_log_lines)
        self.quit_button.clicked.connect(self.quit_app)
        self.tabs.currentChanged.connect(self._animate_current_tab)

        self.bot_service.log_message.connect(self.append_log)
        self.bot_service.state_changed.connect(self.on_bot_state_changed)

    def _add_admin(self):
        text, ok = QInputDialog.getText(self, 'Добавить админа', 'Введите Telegram ID администратора:')
        if ok and text.strip().isdigit():
            admin_id = text.strip()
            if admin_id not in self._current_admins_data:
                self._current_admins_data[admin_id] = AdminPerms()
                self.admins_list.addItem(admin_id)
                self.admins_list.setCurrentRow(self.admins_list.count() - 1)
                self._schedule_save()

    def _remove_admin(self):
        row = self.admins_list.currentRow()
        if row >= 0:
            admin_id = self.admins_list.item(row).text()
            del self._current_admins_data[admin_id]
            self.admins_list.takeItem(row)
            self._schedule_save()

    def _on_admin_selected(self):
        items = self.admins_list.selectedItems()
        if not items:
            self.perms_widget.setEnabled(False)
            return

        self.perms_widget.setEnabled(True)
        admin_id = items[0].text()
        perms = self._current_admins_data[admin_id]

        self.perm_power.set_checked_silent(perms.power)
        self.perm_open_url.set_checked_silent(perms.open_url)
        self.perm_files.set_checked_silent(perms.files)
        self.perm_process.set_checked_silent(perms.process)
        self.perm_input.set_checked_silent(perms.input)
        self.perm_media.set_checked_silent(perms.media)

    def _update_current_admin_perm(self, field_name: str):
        items = self.admins_list.selectedItems()
        if not items:
            return
        admin_id = items[0].text()
        perms = self._current_admins_data[admin_id]
        val = getattr(self, f"perm_{field_name}").isChecked()
        setattr(perms, field_name, val)
        self._schedule_save()

    def _load_config_into_form(self) -> None:
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
        for admin_id, perms in self._config.admins.items():
            self._current_admins_data[admin_id] = deepcopy(perms)
            self.admins_list.addItem(admin_id)

        if self.admins_list.count() > 0:
            self.admins_list.setCurrentRow(0)

        self._refresh_state_cards()
        self.sync_autostart_ui(silent=True)
        self.load_last_log_lines()
        self.append_log(f'Config loaded from {self.config_manager.path}')

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
        self.admin_count_value.setText(str(len(self._config.admins)))
        self.mode_value.setText('Трей' if self._config.start_minimized else 'Окно')

    def _schedule_save(self, *_):
        """Сохранение конфига с задержкой (Debounce), чтобы не было фризов UI при быстром клике"""
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
        self.config_manager.save(self._config)
        self._refresh_state_cards()

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


def check_first_run_and_install():
    """Диалог установки при первом запуске"""
    if getattr(sys, 'frozen', False):
        current_path = Path(sys.executable).resolve()
    else:
        current_path = Path(__file__).resolve().parent

    default_install_dir = Path.home() / 'AppData' / 'Local' / 'PCController'

    if default_install_dir in current_path.parents or current_path.parent == default_install_dir:
        return

    from .config import CONFIG_PATH
    if CONFIG_PATH.exists():
        return

    msg = QMessageBox()
    msg.setWindowTitle("Первый запуск PC Controller")
    msg.setText("Похоже, вы запускаете программу впервые.\nХотите установить её в систему?")
    msg.setInformativeText(
        f"Рекомендуется скопировать файлы в:\n{default_install_dir}\n\nЕсли нажать 'Оставить здесь', программа будет работать портативно.")
    msg.setStyleSheet(APP_STYLE)

    btn_install = msg.addButton("Установить (Рекомендуется)", QMessageBox.ButtonRole.AcceptRole)
    btn_portable = msg.addButton("Оставить здесь", QMessageBox.ButtonRole.RejectRole)

    msg.exec()

    if msg.clickedButton() == btn_install:
        target_dir = default_install_dir
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            if getattr(sys, 'frozen', False):
                target_exe = target_dir / current_path.name
                import shutil
                shutil.copy2(current_path, target_exe)
                subprocess.Popen([str(target_exe)])
            else:
                import shutil
                shutil.copytree(current_path, target_dir, dirs_exist_ok=True)
                run_file = target_dir / current_path.name if current_path.is_file() else target_dir / 'ui.py'
                subprocess.Popen([sys.executable, str(run_file)])
            sys.exit(0)
        except Exception as e:
            QMessageBox.critical(None, "Ошибка", f"Не удалось скопировать файлы:\n{e}")
