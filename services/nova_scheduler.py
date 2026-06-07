from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


def _load_apscheduler_backend() -> dict[str, Any] | None:
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except Exception:
        return None

    backend: dict[str, Any] = {"BackgroundScheduler": BackgroundScheduler}
    try:
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
    except Exception:
        SQLAlchemyJobStore = None
    backend["SQLAlchemyJobStore"] = SQLAlchemyJobStore
    return backend


@dataclass
class NovaSchedulerService:
    """Thin APScheduler wrapper with lazy import and graceful fallback."""

    jobstore_url: str | None = None
    timezone: str = "UTC"
    backend_factory: Callable[[], dict[str, Any] | None] = _load_apscheduler_backend
    _scheduler: Any = field(default=None, init=False, repr=False)
    backend_name: str = field(default="apscheduler", init=False)
    available: bool = field(default=False, init=False)

    def _build_scheduler(self) -> Any:
        backend = self.backend_factory()
        if not backend:
            self.available = False
            self.backend_name = "apscheduler-unavailable"
            self._scheduler = None
            return None

        BackgroundScheduler = backend["BackgroundScheduler"]
        SQLAlchemyJobStore = backend.get("SQLAlchemyJobStore")
        kwargs: dict[str, Any] = {"timezone": self.timezone}
        if self.jobstore_url and SQLAlchemyJobStore is not None:
            kwargs["jobstores"] = {"default": SQLAlchemyJobStore(url=self.jobstore_url)}
        self._scheduler = BackgroundScheduler(**kwargs)
        self.available = True
        self.backend_name = "apscheduler"
        return self._scheduler

    def scheduler(self) -> Any:
        if self._scheduler is None:
            return self._build_scheduler()
        return self._scheduler

    def start(self) -> bool:
        scheduler = self.scheduler()
        if scheduler is None:
            return False
        scheduler.start()
        return True

    def shutdown(self, wait: bool = True) -> bool:
        if self._scheduler is None:
            return False
        self._scheduler.shutdown(wait=wait)
        return True

    def add_job(self, func: Callable[..., Any], trigger: str, **kwargs: Any) -> Any:
        scheduler = self.scheduler()
        if scheduler is None:
            raise RuntimeError("APScheduler is not available")
        return scheduler.add_job(func, trigger, **kwargs)

    def job_ids(self) -> list[str]:
        scheduler = self.scheduler()
        if scheduler is None:
            return []
        return [str(job.id) for job in scheduler.get_jobs()]

