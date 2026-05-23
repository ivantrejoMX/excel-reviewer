from __future__ import annotations
import asyncio
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from backend.config import TEMP_DIR, JOB_TTL_SECONDS
from backend.models.job import JobStatus, Issue


class Job:
    def __init__(self, job_id: str, filename: str, api_key: str = ""):
        self.job_id = job_id
        self.filename = filename
        self.api_key = api_key          # user-supplied key, held in memory only
        self.status = JobStatus.UPLOADED
        self.progress_message = "Uploaded"
        self.auto_fixes: list[Issue] = []
        self.validation_queue: list[Issue] = []
        self.summary = ""
        self.error: str | None = None
        self.partial_analysis = False
        self.created_at = time.time()

    @property
    def dir(self) -> Path:
        return TEMP_DIR / self.job_id

    @property
    def original_path(self) -> Path:
        return self.dir / f"original_{self.filename}"

    @property
    def output_path(self) -> Path:
        return self.dir / f"reviewed_{self.filename}"


_jobs: dict[str, Job] = {}
_lock = asyncio.Lock()


async def create_job(filename: str, api_key: str = "") -> Job:
    job_id = str(uuid.uuid4())
    job = Job(job_id, filename, api_key=api_key)
    job.dir.mkdir(parents=True, exist_ok=True)
    async with _lock:
        _jobs[job_id] = job
    return job


async def get_job(job_id: str) -> Job | None:
    async with _lock:
        return _jobs.get(job_id)


async def update_job(job_id: str, **kwargs: Any) -> None:
    async with _lock:
        job = _jobs.get(job_id)
        if job:
            for k, v in kwargs.items():
                setattr(job, k, v)


async def delete_job(job_id: str) -> bool:
    async with _lock:
        job = _jobs.pop(job_id, None)
    if job and job.dir.exists():
        shutil.rmtree(job.dir, ignore_errors=True)
    return job is not None


def cleanup_old_jobs() -> int:
    cutoff = time.time() - JOB_TTL_SECONDS
    expired = [jid for jid, j in list(_jobs.items()) if j.created_at < cutoff]
    for jid in expired:
        job = _jobs.pop(jid, None)
        if job and job.dir.exists():
            shutil.rmtree(job.dir, ignore_errors=True)
    return len(expired)
