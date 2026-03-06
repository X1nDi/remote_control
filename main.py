from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from pc_controller.bot_service import TelegramBotService
from pc_controller.config import ConfigManager
from pc_controller.logging_setup import setup_logging
from pc_controller.ui import MainWindow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--minimized', action='store_true', help='Start hidden in system tray.')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    logger = setup_logging()
    config_manager = ConfigManager()
    bot_service = TelegramBotService(config_provider=config_manager.current)
    window = MainWindow(
        config_manager=config_manager,
        bot_service=bot_service,
        logger=logger,
        start_minimized=args.minimized,
    )
    if not args.minimized:
        window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
