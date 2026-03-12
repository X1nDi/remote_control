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
class AdminPerms:
    power: bool = True
    open_url: bool = True
    files: bool = True
    process: bool = True
    input: bool = True
    media: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> 'AdminPerms':
        return cls(
            power=bool(data.get('power', True)),
            open_url=bool(data.get('open_url', True)),
            files=bool(data.get('files', True)),
            process=bool(data.get('process', True)),
            input=bool(data.get('input', True)),
            media=bool(data.get('media', True)),
        )


@dataclass(slots=True)
class AppConfig:
    bot_token: str = ''
    telegram_proxy: str = ''
    admins: dict[str, AdminPerms] = field(default_factory=dict)
    autostart: bool = False
    start_minimized: bool = True
    auto_start_bot: bool = True
    allow_all_files: bool = False
    files_root: str = field(default_factory=lambda: str(Path.home()))
    autoaccept_templates_dir: str = field(default_factory=lambda: str(APP_DIR / 'autoaccept_templates'))
    show_notifications: bool = True
    installed: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> 'AppConfig':
        # Миграция старого формата (список ID) в новый (словарь с правами)
        old_admin_ids = data.get('admin_ids', [])
        admins_data = data.get('admins', {})

        parsed_admins = {}
        for admin_id_str, perms_dict in admins_data.items():
            parsed_admins[str(admin_id_str)] = AdminPerms.from_dict(perms_dict)

        if isinstance(old_admin_ids, list):
            for a_id in old_admin_ids:
                if str(a_id) not in parsed_admins:
                    parsed_admins[str(a_id)] = AdminPerms()

        return cls(
            bot_token=str(data.get('bot_token', '') or '').strip(),
            telegram_proxy=str(data.get('telegram_proxy', '') or '').strip(),
            admins=parsed_admins,
            autostart=bool(data.get('autostart', False)),
            start_minimized=bool(data.get('start_minimized', True)),
            auto_start_bot=bool(data.get('auto_start_bot', True)),
            allow_all_files=bool(data.get('allow_all_files', False)),
            files_root=str(data.get('files_root', str(Path.home()))),
            autoaccept_templates_dir=str(
                data.get('autoaccept_templates_dir', '') or str(APP_DIR / 'autoaccept_templates')).strip(),
            show_notifications=bool(data.get('show_notifications', True)),
            installed=bool(data.get('installed', False)),
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d['admins'] = {k: asdict(v) for k, v in self.admins.items()}
        return d


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
    def parse_admins(raw_text: str, existing_admins: dict[str, AdminPerms]) -> dict[str, AdminPerms]:
        parts = re.split(r'[\s,;]+', raw_text.strip())
        new_admins = {}
        for part in parts:
            if part.strip():
                new_admins[part] = existing_admins.get(part, AdminPerms())
        return new_admins
