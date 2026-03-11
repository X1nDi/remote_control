from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .config import APP_DIR

try:
    import pyperclip
except ImportError:  # pragma: no cover - dependency is optional at import time
    pyperclip = None


def _ensure_pyperclip() -> None:
    if pyperclip is None:
        raise RuntimeError('pyperclip is not installed.')


@dataclass(slots=True)
class ClipboardEntry:
    entry_id: str
    text: str
    created_at: float

    @classmethod
    def from_dict(cls, payload: dict) -> 'ClipboardEntry':
        return cls(
            entry_id=str(payload.get('entry_id', '')).strip(),
            text=str(payload.get('text', '')),
            created_at=float(payload.get('created_at', time.time())),
        )

    def to_dict(self) -> dict:
        return {
            'entry_id': self.entry_id,
            'text': self.text,
            'created_at': self.created_at,
        }


class ClipboardHistoryService:
    def __init__(
            self,
            path: Path | None = None,
            max_entries: int = 20,
            poll_interval: float = 1.0,
    ) -> None:
        self._path = path or (APP_DIR / 'clipboard_history.json')
        self._max_entries = max(5, min(max_entries, 100))
        self._poll_interval = max(0.3, min(poll_interval, 10.0))
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._entries = self._load()
        self._last_seen = self._entries[0].text if self._entries else None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        _ensure_pyperclip()
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name='clipboard-history', daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def snapshot(self, limit: int | None = None) -> list[ClipboardEntry]:
        with self._lock:
            items = list(self._entries)
        if limit is None:
            return items
        return items[:max(0, limit)]

    def get(self, entry_id: str) -> ClipboardEntry | None:
        normalized = str(entry_id or '').strip()
        if not normalized:
            return None
        with self._lock:
            for entry in self._entries:
                if entry.entry_id == normalized:
                    return entry
        return None

    def add_text(self, text: str) -> ClipboardEntry | None:
        cleaned = self._normalize_text(text)
        if cleaned is None:
            return None
        with self._lock:
            entry = self._record_locked(cleaned)
            self._save_locked()
        self._last_seen = cleaned
        return entry

    @staticmethod
    def preview(text: str, max_len: int = 60) -> str:
        compact = ' '.join((text or '').split())
        if not compact:
            return '(пусто)'
        if len(compact) <= max_len:
            return compact
        return compact[:max_len - 1] + '…'

    def _run(self) -> None:
        while not self._stop_event.wait(self._poll_interval):
            try:
                current = pyperclip.paste()
            except Exception:
                continue

            cleaned = self._normalize_text(current)
            if cleaned is None or cleaned == self._last_seen:
                continue

            with self._lock:
                self._record_locked(cleaned)
                self._save_locked()
            self._last_seen = cleaned

    def _record_locked(self, text: str) -> ClipboardEntry:
        self._entries = [item for item in self._entries if item.text != text]
        entry = ClipboardEntry(
            entry_id=f'c{int(time.time() * 1000)}',
            text=text,
            created_at=time.time(),
        )
        self._entries.insert(0, entry)
        del self._entries[self._max_entries:]
        return entry

    def _load(self) -> list[ClipboardEntry]:
        try:
            if not self._path.exists():
                return []
            payload = json.loads(self._path.read_text(encoding='utf-8'))
            items = payload.get('entries', [])
            return [ClipboardEntry.from_dict(item) for item in items if isinstance(item, dict)]
        except Exception:
            return []

    def _save_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {'entries': [entry.to_dict() for entry in self._entries]}
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    @staticmethod
    def _normalize_text(text: str | None) -> str | None:
        if text is None:
            return None
        cleaned = str(text).replace('\x00', '').strip()
        if not cleaned:
            return None
        if len(cleaned) > 20_000:
            cleaned = cleaned[:20_000]
        return cleaned
