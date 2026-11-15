"""Database-backed job queue with an in-process worker thread.

WHY: processing a document (preprocessing, YOLO, OCR) or training a model takes seconds
to hours. The API therefore only *enqueues* a job row and returns at once; a worker
thread claims queued jobs, runs the registered handler, and persists stage, progress,
per-stage timings and a short log. The frontend follows a job via polling or SSE.

Because state lives in the database, a restart never loses jobs: queued jobs are picked
up again, and jobs that were mid-run when the process died are marked FAILED with an
"interrupted" message rather than left hanging.

A single worker thread is used deliberately: the target laptop has 7 GB RAM and one 4 GB
GPU, so running two heavy CV jobs at once would be slower, not faster.
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, update

from app.core.config import get_settings
from app.database.session import session_scope
from app.models import ProcessingJob
from app.models.base import utcnow
from app.models.enums import ACTIVE_JOB_STATUSES, JobStatus

log = logging.getLogger(__name__)

_LOG_LIMIT = 200  # keep the persisted job log small


class JobCancelled(Exception):
    pass


@dataclass
class JobContext:
    """Passed to handlers so they can report progress without touching the DB directly."""

    job_id: int
    job_type: str
    params: dict[str, Any]
    document_id: int | None
    _stage: str | None = None
    _stage_started: float = field(default_factory=time.perf_counter)
    _timings: dict[str, float] = field(default_factory=dict)

    def stage(self, status: JobStatus, message: str | None = None, progress: float | None = None) -> None:
        """Enter a new stage; the previous stage's wall time is recorded."""
        self._close_stage()
        self._stage = status.value
        self._stage_started = time.perf_counter()
        self._write(status=status, message=message, progress=progress, log_msg=message or status.value)

    def progress(self, value: float, message: str | None = None) -> None:
        self._write(progress=max(0.0, min(1.0, value)), message=message, log_msg=message)

    def log(self, message: str) -> None:
        self._write(log_msg=message)

    def _close_stage(self) -> None:
        if self._stage is not None:
            self._timings[self._stage] = round(
                self._timings.get(self._stage, 0.0) + time.perf_counter() - self._stage_started, 4
            )
            self._stage = None  # closing twice must not double-count

    def _write(
        self,
        *,
        status: JobStatus | None = None,
        message: str | None = None,
        progress: float | None = None,
        log_msg: str | None = None,
    ) -> None:
        with session_scope() as db:
            job = db.get(ProcessingJob, self.job_id)
            if job is None:
                raise JobCancelled("job deleted")
            if job.status is JobStatus.CANCELLED:
                raise JobCancelled("cancelled by user")
            if status is not None:
                job.status = status
            if message is not None:
                job.message = message[:512]
            if progress is not None:
                job.progress = progress
            job.stage_timings = dict(self._timings)
            job.heartbeat_at = utcnow()
            if log_msg:
                entries = list(job.log or [])
                entries.append({"ts": utcnow().isoformat(timespec="seconds"), "msg": log_msg[:500]})
                job.log = entries[-_LOG_LIMIT:]


Handler = Callable[[JobContext], dict[str, Any] | None]
_HANDLERS: dict[str, Handler] = {}


def register(job_type: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _HANDLERS[job_type] = fn
        return fn

    return deco


def registered_job_types() -> list[str]:
    return sorted(_HANDLERS)


def enqueue(
    job_type: str,
    params: dict[str, Any] | None = None,
    *,
    document_id: int | None = None,
    created_by: int | None = None,
) -> int:
    if job_type not in _HANDLERS:
        raise ValueError(f"unknown job type: {job_type}")
    with session_scope() as db:
        job = ProcessingJob(
            job_type=job_type,
            params=params or {},
            document_id=document_id,
            created_by=created_by,
            status=JobStatus.QUEUED,
            log=[{"ts": utcnow().isoformat(timespec="seconds"), "msg": "queued"}],
        )
        db.add(job)
        db.flush()
        return job.id


def cancel(job_id: int) -> bool:
    """Cancel a queued or running job. A running handler stops at its next progress call."""
    with session_scope() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None or job.status.is_terminal:
            return False
        job.status = JobStatus.CANCELLED
        job.finished_at = utcnow()
        job.message = "Cancelled"
        return True


def recover_interrupted_jobs() -> int:
    """Mark jobs that were running when the process stopped as FAILED."""
    with session_scope() as db:
        res = db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.status.in_(ACTIVE_JOB_STATUSES))
            .values(status=JobStatus.FAILED, error="Interrupted: the server stopped while this job was running.",
                    finished_at=utcnow())
        )
        return res.rowcount or 0


def _claim_next() -> tuple[int, str, dict[str, Any], int | None] | None:
    """Atomically move the oldest QUEUED job to RUNNING and return it."""
    with session_scope() as db:
        job_id = db.execute(
            select(ProcessingJob.id)
            .where(ProcessingJob.status == JobStatus.QUEUED)
            .order_by(ProcessingJob.created_at, ProcessingJob.id)
            .limit(1)
        ).scalar_one_or_none()
        if job_id is None:
            return None
        claimed = db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == job_id, ProcessingJob.status == JobStatus.QUEUED)
            .values(status=JobStatus.RUNNING, started_at=utcnow(), heartbeat_at=utcnow())
        ).rowcount
        if not claimed:  # another worker took it first
            return None
        job = db.get(ProcessingJob, job_id)
        assert job is not None
        return job.id, job.job_type, dict(job.params or {}), job.document_id


def run_one() -> bool:
    """Claim and run a single job. Returns False when the queue is empty."""
    claimed = _claim_next()
    if claimed is None:
        return False
    job_id, job_type, params, document_id = claimed
    ctx = JobContext(job_id, job_type, params, document_id)
    handler = _HANDLERS.get(job_type)
    started = time.perf_counter()
    try:
        if handler is None:
            raise RuntimeError(f"no handler registered for job type '{job_type}'")
        result = handler(ctx) or {}
        ctx._close_stage()
        _finish(job_id, JobStatus.COMPLETED, ctx, result=result, elapsed=time.perf_counter() - started)
    except JobCancelled:
        ctx._close_stage()
        log.info("job cancelled", extra={"ctx": {"job_id": job_id}})
    except Exception as exc:  # noqa: BLE001 - any handler failure becomes a FAILED job
        ctx._close_stage()
        log.exception("job failed", extra={"ctx": {"job_id": job_id, "job_type": job_type}})
        _finish(job_id, JobStatus.FAILED, ctx, error=f"{type(exc).__name__}: {exc}",
                trace=traceback.format_exc(limit=5), elapsed=time.perf_counter() - started)
    return True


def _finish(job_id: int, status: JobStatus, ctx: JobContext, *, result: dict | None = None,
            error: str | None = None, trace: str | None = None, elapsed: float) -> None:
    with session_scope() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None or job.status is JobStatus.CANCELLED:
            return
        job.status = status
        job.finished_at = utcnow()
        job.stage_timings = {**ctx._timings, "total": round(elapsed, 4)}
        if status is JobStatus.COMPLETED:
            job.progress = 1.0
            job.result = result
            job.message = job.message or "Completed"
        else:
            job.error = (error or "") + ("\n" + trace if trace else "")
            job.message = (error or "Failed")[:512]
        entries = list(job.log or [])
        entries.append({"ts": utcnow().isoformat(timespec="seconds"), "msg": status.value.lower()})
        job.log = entries[-_LOG_LIMIT:]


class Worker:
    """Background thread that drains the queue."""

    def __init__(self, poll_interval: float | None = None) -> None:
        self.poll_interval = poll_interval or get_settings().worker_poll_interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="kyc-job-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    @property
    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if not run_one():
                    self._stop.wait(self.poll_interval)
            except Exception:  # noqa: BLE001 - the worker must never die silently
                log.exception("worker loop error")
                self._stop.wait(self.poll_interval)
