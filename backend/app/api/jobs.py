"""Job status endpoints: list, detail, cancel, and a Server-Sent Events stream.

The frontend prefers the SSE stream for live progress and falls back to polling
GET /jobs/{id} when SSE is unavailable.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, select
from sse_starlette.sse import EventSourceResponse

from app.api.deps import DB, CurrentUser
from app.database.session import SessionLocal
from app.models import ProcessingJob
from app.models.enums import JobStatus
from app.schemas.common import JobOut, Page
from app.workers import jobs as job_queue

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=Page[JobOut])
def list_jobs(
    _: CurrentUser,
    db: DB,
    status: list[JobStatus] | None = Query(default=None),
    job_type: str | None = None,
    active_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[JobOut]:
    q = select(ProcessingJob)
    if status:
        q = q.where(ProcessingJob.status.in_(status))
    if active_only:
        q = q.where(ProcessingJob.status.not_in([JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]))
    if job_type:
        q = q.where(ProcessingJob.job_type == job_type)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(
        q.order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).scalars()
    return Page(items=[JobOut.model_validate(r) for r in rows], total=total, page=page, page_size=page_size)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, _: CurrentUser, db: DB) -> ProcessingJob:
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: int, _: CurrentUser, db: DB) -> ProcessingJob:
    if not job_queue.cancel(job_id):
        job = db.get(ProcessingJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        raise HTTPException(status_code=409, detail="Job already finished")
    db.expire_all()
    job = db.get(ProcessingJob, job_id)
    assert job is not None
    return job


@router.get("/{job_id}/events")
async def job_events(job_id: int, request: Request, _: CurrentUser, interval: float = Query(1.0, ge=0.2, le=10)):
    """SSE stream: emits the job as JSON whenever it changes, and closes when it ends."""

    def snapshot() -> dict | None:
        with SessionLocal() as db:
            job = db.get(ProcessingJob, job_id)
            return None if job is None else JobOut.model_validate(job).model_dump(mode="json")

    if snapshot() is None:
        raise HTTPException(status_code=404, detail="Job not found")

    async def stream():
        last = None
        while True:
            if await request.is_disconnected():
                break
            data = await asyncio.to_thread(snapshot)
            if data is None:
                yield {"event": "error", "data": json.dumps({"detail": "Job not found"})}
                break
            encoded = json.dumps(data, sort_keys=True)
            if encoded != last:
                yield {"event": "job", "data": encoded}
                last = encoded
            if JobStatus(data["status"]).is_terminal:
                yield {"event": "end", "data": encoded}
                break
            await asyncio.sleep(interval)

    return EventSourceResponse(stream())
