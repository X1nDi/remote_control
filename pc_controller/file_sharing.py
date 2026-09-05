"""Bounded-memory guest uploads using https://gofile.io/api."""
from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx  # Already required by python-telegram-bot.

TELEGRAM_FILE_LIMIT = 45 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024
UPLOAD_URL = 'https://upload.gofile.io/uploadfile'
_UPLOAD_LOCK = threading.Lock()


@dataclass(frozen=True)
class SharedFile:
    url: str
    size: int
    sha256: str


class UploadStream:
    """Keep multipart reads bounded and enforce a monotonic operation budget."""
    def __init__(self, stream):
        self.stream = stream
        self.started = time.monotonic()

    def read(self, size=-1):
        if time.monotonic() - self.started > 3600:
            raise ValueError('Превышено время загрузки (1 час).')
        return self.stream.read(min(size, CHUNK_SIZE) if size >= 0 else CHUNK_SIZE)

    def seek(self, offset, whence=0):
        return self.stream.seek(offset, whence)

    def tell(self):
        return self.stream.tell()

    def fileno(self):
        return self.stream.fileno()


def upload_large_file(path: Path, *, client=None) -> SharedFile:
    if not _UPLOAD_LOCK.acquire(blocking=False):
        raise ValueError('Уже загружается большой файл. Дождитесь завершения.')
    try:
        if client is not None:
            return _upload(path, client)
        with httpx.Client(timeout=httpx.Timeout(180, connect=30), follow_redirects=False) as session:
            return _upload(path, session)
    except (httpx.HTTPError, KeyError, TypeError):
        raise ValueError('Gofile не завершил загрузку. Повторите позже.') from None
    finally:
        _UPLOAD_LOCK.release()


def _upload(path: Path, client) -> SharedFile:
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        if not before.st_size:
            raise ValueError('Пустой файл не загружается на файлообменник.')
        sha256 = hashlib.sha256()
        md5 = hashlib.md5()  # Integrity comparison with service, not authentication.
        for part in iter(lambda: stream.read(CHUNK_SIZE), b''):
            sha256.update(part)
            md5.update(part)
        stream.seek(0)
        response = client.post(UPLOAD_URL,
                              files={'file': (path.name, UploadStream(stream), 'application/octet-stream')})
        response.raise_for_status()
        try:
            result = response.json()
        except ValueError:
            raise ValueError('Gofile вернул некорректное подтверждение загрузки.') from None
        if not isinstance(result, dict) or result.get('status') != 'ok':
            raise ValueError('Gofile отклонил загрузку. Повторите позже.')
        data = result['data']
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('Файл изменился во время загрузки; ссылка не опубликована.')
        url = data.get('downloadPage')
        # Gofile sanitizes names (e.g. strips a leading dot); verify file bytes.
        if data.get('size') != before.st_size or data.get('md5') != md5.hexdigest():
            raise ValueError('Gofile не подтвердил целостность файла.')
        if not isinstance(url, str) or not re.fullmatch(r'https://gofile\.io/d/[A-Za-z0-9]+', url):
            raise ValueError('Gofile не вернул корректную ссылку.')
        # Never persist or log guest account tokens returned by the provider.
        return SharedFile(url, before.st_size, sha256.hexdigest())
