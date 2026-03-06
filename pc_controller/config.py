from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


def _resolve_app_dir() -> Path:
    local_app_data = os.getenv('LOCALAPPDATA')
    if local_app_data:
        return Path(local_app_data) / 'PCController'
    return Path.home() / 'AppData' / 'Local' / 'PCController'


APP_DIR = _resolve_app_dir()
CONFIG_PATH = APP_DIR / 'config.json'
LOG_DIR = APP_DIR / 'logs'


@dataclass(slots=True)
class AppConfig:
    bot_token: str = ''
    admin_ids: list[int] = field(default_factory=list)
    autostart: bool = False
    start_minimized: bool = True
    auto_start_bot: bool = True
    allow_power_commands: bool = True
    allow_open_url_command: bool = True
    allow_file_commands: bool = True
    allow_process_commands: bool = True
    allow_input_commands: bool = True
    files_root: str = field(default_factory=lambda: str(Path.home()))
    autoaccept_templates_dir: str = field(default_factory=lambda: str(APP_DIR / 'autoaccept_templates'))
    show_notifications: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> 'AppConfig':
        return cls(
            bot_token=str(data.get('bot_token', '') or '').strip(),
            admin_ids=ConfigManager.parse_admins(data.get('admin_ids', [])),
            autostart=bool(data.get('autostart', False)),
            start_minimized=bool(data.get('start_minimized', True)),
            auto_start_bot=bool(data.get('auto_start_bot', True)),
            allow_power_commands=bool(data.get('allow_power_commands', True)),
            allow_open_url_command=bool(data.get('allow_open_url_command', True)),
            allow_file_commands=bool(data.get('allow_file_commands', True)),
            allow_process_commands=bool(data.get('allow_process_commands', True)),
            allow_input_commands=bool(data.get('allow_input_commands', True)),
            files_root=str(data.get('files_root', '') or str(Path.home())).strip(),
            autoaccept_templates_dir=str(data.get('autoaccept_templates_dir', '') or str(APP_DIR / 'autoaccept_templates')).strip(),
            show_notifications=bool(data.get('show_notifications', True)),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def masked_token(self) -> str:
        if not self.bot_token:
            return ''
        if len(self.bot_token) <= 10:
            return '***'
        return f'{self.bot_token[:6]}...{self.bot_token[-4:]}'


class ConfigManager:
    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self._config = self.load()

    def load(self) -> AppConfig:
        if not self.path.exists():
            config = AppConfig()
            self.save(config)
            return config

        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            self._config = AppConfig.from_dict(data)
        except (json.JSONDecodeError, OSError):
            self._config = AppConfig()
            self.save(self._config)
        return self._config

    def save(self, config: AppConfig) -> AppConfig:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        self._config = config
        return config

    def current(self) -> AppConfig:
        return self._config

    @staticmethod
    def parse_admins(raw_text: str | Iterable[str | int]) -> list[int]:
        if isinstance(raw_text, str):
            parts = re.split(r'[\s,;]+', raw_text.strip())
        else:
            parts = [str(item).strip() for item in raw_text]

        result: set[int] = set()
        for part in parts:
            if not part:
                continue
            value = int(part)
            if value <= 0:
                raise ValueError('Admin ID should be a positive integer.')
            result.add(value)
        return sorted(result)
