from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import QSharedMemory
from PySide6.QtWidgets import QApplication, QMessageBox

from pc_controller.bot_service import TelegramBotService
from pc_controller.config import ConfigManager
from pc_controller.logging_setup import setup_logging
from pc_controller.ui import MainWindow, APP_STYLE, check_first_run_and_install


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--minimized', action='store_true', help='Start hidden in system tray.')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = QApplication(sys.argv)

    # 1. ЗАЩИТА ОТ ДВОЙНОГО ЗАПУСКА
    shared_mem = QSharedMemory("PCController_App_Shared_Memory_Lock_1")
    if not shared_mem.create(1):
        QMessageBox.warning(None, "PC Controller", "Программа уже запущена! Проверьте системный трей (возле часов).")
        return 0

    app.setQuitOnLastWindowClosed(False)

    # 2. ПРИМЕНЕНИЕ СТИЛЕЙ
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)

    # 3. ПРОВЕРКА ПЕРВОГО ЗАПУСКА (УСТАНОВЩИК)
    check_first_run_and_install()

    logger = setup_logging()
    config_manager = ConfigManager()
    bot_service = TelegramBotService(
        config_provider=config_manager.current,
        config_saver=config_manager.save,
    )

    # Сворачиваем в трей ТОЛЬКО если программа запущена Windows с флагом --minimized
    start_minimized = args.minimized

    window = MainWindow(
        config_manager=config_manager,
        bot_service=bot_service,
        logger=logger,
        start_minimized=start_minimized,
    )

    if not start_minimized:
        window.show()

    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
