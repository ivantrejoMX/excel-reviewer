import asyncio
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from backend.services.job_manager import get_job, update_job, delete_job
from backend.models.job import JobStatus, JobStatusResponse, ApplyRequest

router = APIRouter()


@router.get("/api/jobs/{job_id}/status", response_model=JobStatusResponse)
async def get_status(job_id: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        filename=job.filename,
        progress_message=job.progress_message,
        auto_fixes=job.auto_fixes,
        validation_queue=job.validation_queue,
        summary=job.summary,
        error=job.error,
        partial_analysis=job.partial_analysis,
    )


@router.post("/api/jobs/{job_id}/apply")
async def apply_fixes(job_id: str, body: ApplyRequest, background_tasks: BackgroundTasks):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.READY:
        raise HTTPException(409, f"Job is not ready (status: {job.status})")

    await update_job(job_id, status=JobStatus.APPLYING, progress_message="Applying fixes...")

    async def _apply(jid: str, req: ApplyRequest) -> None:
        from backend.services.fix_applier import apply_fixes as do_apply
        try:
            j = await get_job(jid)
            approved = [i for i in j.auto_fixes + j.validation_queue if i.issue_id in req.approved_fix_ids]
            await asyncio.to_thread(
                do_apply,
                str(j.original_path),
                str(j.output_path),
                approved,
                req.named_range_choices,
            )
            await update_job(jid, status=JobStatus.DONE, progress_message="Done")
        except Exception as exc:
            await update_job(jid, status=JobStatus.ERROR, error=str(exc))

    background_tasks.add_task(_apply, job_id, body)
    return {"status": JobStatus.APPLYING}


@router.get("/api/jobs/{job_id}/download")
async def download(job_id: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.DONE:
        raise HTTPException(409, f"File not ready (status: {job.status})")
    if not job.output_path.exists():
        raise HTTPException(500, "Output file missing")
    return FileResponse(
        path=str(job.output_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"reviewed_{job.filename}",
    )


@router.delete("/api/jobs/{job_id}")
async def remove_job(job_id: str):
    deleted = await delete_job(job_id)
    if not deleted:
        raise HTTPException(404, "Job not found")
    return {"deleted": True}
