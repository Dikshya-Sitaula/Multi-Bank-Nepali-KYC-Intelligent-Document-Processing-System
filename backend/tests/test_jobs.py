"""Job queue lifecycle: enqueue, run, stage timings, failure, cancel, recovery, API, SSE."""
import json
import time

import pytest

from app.database.session import session_scope
from app.models import ProcessingJob, Role
from app.models.enums import JobStatus
from app.workers import jobs as q


@q.register("test.stages")
def _stages(ctx: q.JobContext):
    ctx.stage(JobStatus.PREPROCESSING, "pre", 0.2)
    ctx.stage(JobStatus.OCR, "ocr", 0.6)
    ctx.progress(0.9, "almost")
    return {"echo": ctx.params.get("value")}


@q.register("test.fail")
def _fail(ctx: q.JobContext):
    ctx.stage(JobStatus.DETECTING)
    raise RuntimeError("boom")


def _job(job_id: int) -> ProcessingJob:
    with session_scope() as db:
        job = db.get(ProcessingJob, job_id)
        assert job is not None
        db.expunge(job)
        return job


def test_unknown_job_type_rejected(app_env, client):
    with pytest.raises(ValueError):
        q.enqueue("does.not.exist")


def test_job_completes_with_stage_timings(client):
    jid = q.enqueue("test.stages", {"value": 42})
    assert _job(jid).status is JobStatus.QUEUED
    assert q.run_one() is True
    job = _job(jid)
    assert job.status is JobStatus.COMPLETED
    assert job.progress == 1.0
    assert job.result == {"echo": 42}
    assert set(job.stage_timings) == {"PREPROCESSING", "OCR", "total"}
    assert all(v >= 0 for v in job.stage_timings.values())
    assert [e["msg"] for e in job.log][:2] == ["queued", "pre"]
    assert q.run_one() is False  # queue drained


def test_job_failure_recorded(client):
    jid = q.enqueue("test.fail")
    q.run_one()
    job = _job(jid)
    assert job.status is JobStatus.FAILED
    assert "RuntimeError: boom" in job.error
    assert "DETECTING" in job.stage_timings


def test_cancel_queued_job(client):
    jid = q.enqueue("test.stages")
    assert q.cancel(jid) is True
    assert _job(jid).status is JobStatus.CANCELLED
    assert q.run_one() is False
    assert q.cancel(jid) is False


def test_interrupted_jobs_recovered(client):
    jid = q.enqueue("test.stages")
    with session_scope() as db:
        db.get(ProcessingJob, jid).status = JobStatus.OCR
    assert q.recover_interrupted_jobs() == 1
    job = _job(jid)
    assert job.status is JobStatus.FAILED and "Interrupted" in job.error


def test_worker_thread_processes_queue(client):
    jid = q.enqueue("test.stages", {"value": "w"})
    worker = q.Worker(poll_interval=0.05)
    worker.start()
    try:
        deadline = time.time() + 10
        while time.time() < deadline and _job(jid).status is not JobStatus.COMPLETED:
            time.sleep(0.05)
    finally:
        worker.stop()
    assert _job(jid).status is JobStatus.COMPLETED


def test_jobs_api_and_sse(client, make_user):
    _, headers = make_user("asha", Role.employee)
    jid = q.enqueue("test.stages", {"value": 1})
    q.run_one()
    r = client.get(f"/api/v1/jobs/{jid}", headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "COMPLETED"
    page = client.get("/api/v1/jobs", headers=headers).json()
    assert page["total"] == 1 and page["items"][0]["id"] == jid
    assert client.get("/api/v1/jobs/9999", headers=headers).status_code == 404
    assert client.get(f"/api/v1/jobs/{jid}").status_code == 401

    token = headers["Authorization"].split()[1]
    with client.stream("GET", f"/api/v1/jobs/{jid}/events?access_token={token}") as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    events = [line.split(":", 1)[1].strip() for line in body.splitlines() if line.startswith("event:")]
    assert events == ["job", "end"]
    data_line = next(line for line in body.splitlines() if line.startswith("data:"))
    assert json.loads(data_line[5:])["status"] == "COMPLETED"


def test_cancel_api(client, make_user):
    _, headers = make_user()
    jid = q.enqueue("test.stages")
    r = client.post(f"/api/v1/jobs/{jid}/cancel", headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    assert client.post(f"/api/v1/jobs/{jid}/cancel", headers=headers).status_code == 409
