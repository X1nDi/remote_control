from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .config import APP_DIR


@dataclass(slots=True)
class ScheduledJob:
    job_id: str
    run_at: float
    actions: list[str]
    created_by: int
    created_at: float
    cpu_below: float | None = None
    cpu_above: float | None = None
    ram_below: float | None = None
    ram_above: float | None = None
    note: str = ''

    @classmethod
    def from_dict(cls, payload: dict) -> 'ScheduledJob':
        actions = payload.get('actions', [])
        return cls(
            job_id=str(payload.get('job_id', '')).strip(),
            run_at=float(payload.get('run_at', time.time())),
            actions=[str(item).strip() for item in actions if str(item).strip()],
            created_by=int(payload.get('created_by', 0) or 0),
            created_at=float(payload.get('created_at', time.time())),
            cpu_below=float(payload['cpu_below']) if payload.get('cpu_below') is not None else None,
            cpu_above=float(payload['cpu_above']) if payload.get('cpu_above') is not None else None,
            ram_below=float(payload['ram_below']) if payload.get('ram_below') is not None else None,
            ram_above=float(payload['ram_above']) if payload.get('ram_above') is not None else None,
            note=str(payload.get('note', '') or ''),
        )

    def to_dict(self) -> dict:
        return {
            'job_id': self.job_id,
            'run_at': self.run_at,
            'actions': self.actions,
            'created_by': self.created_by,
            'created_at': self.created_at,
            'cpu_below': self.cpu_below,
            'cpu_above': self.cpu_above,
            'ram_below': self.ram_below,
            'ram_above': self.ram_above,
            'note': self.note,
        }


class SchedulerStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (APP_DIR / 'scheduled_jobs.json')
        self._lock = threading.Lock()
        self._jobs = self._load()

    def list_jobs(self) -> list[ScheduledJob]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda item: item.run_at)

    def add_job(
            self,
            run_at: float,
            actions: list[str],
            created_by: int,
            cpu_below: float | None = None,
            cpu_above: float | None = None,
            ram_below: float | None = None,
            ram_above: float | None = None,
            note: str = '',
    ) -> ScheduledJob:
        job = ScheduledJob(
            job_id=f'j{int(time.time() * 1000)}',
            run_at=float(run_at),
            actions=[str(item).strip() for item in actions if str(item).strip()],
            created_by=int(created_by),
            created_at=time.time(),
            cpu_below=float(cpu_below) if cpu_below is not None else None,
            cpu_above=float(cpu_above) if cpu_above is not None else None,
            ram_below=float(ram_below) if ram_below is not None else None,
            ram_above=float(ram_above) if ram_above is not None else None,
            note=str(note or ''),
        )
        with self._lock:
            self._jobs[job.job_id] = job
            self._save_locked()
        return job

    def remove_job(self, job_id: str) -> ScheduledJob | None:
        with self._lock:
            removed = self._jobs.pop(job_id, None)
            if removed is not None:
                self._save_locked()
            return removed

    def clear(self) -> int:
        with self._lock:
            count = len(self._jobs)
            self._jobs.clear()
            self._save_locked()
            return count

    def pop_due(self, now_ts: float | None = None) -> list[ScheduledJob]:
        now_value = time.time() if now_ts is None else float(now_ts)
        with self._lock:
            due_ids = [job_id for job_id, job in self._jobs.items() if job.run_at <= now_value]
            due_jobs = [self._jobs.pop(job_id) for job_id in due_ids]
            if due_ids:
                self._save_locked()
        return sorted(due_jobs, key=lambda item: item.run_at)

    def get(self, job_id: str) -> ScheduledJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _load(self) -> dict[str, ScheduledJob]:
        try:
            if not self._path.exists():
                return {}
            payload = json.loads(self._path.read_text(encoding='utf-8'))
            jobs = payload.get('jobs', [])
            items = {}
            for raw_job in jobs:
                if not isinstance(raw_job, dict):
                    continue
                job = ScheduledJob.from_dict(raw_job)
                if job.job_id:
                    items[job.job_id] = job
            return items
        except Exception:
            return {}

    def _save_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'jobs': [job.to_dict() for job in sorted(self._jobs.values(), key=lambda item: item.run_at)]
        }
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
