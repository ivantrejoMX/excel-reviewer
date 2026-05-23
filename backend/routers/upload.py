import asyncio
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile, BackgroundTasks

from backend.config import MAX_FILE_SIZE_BYTES, ALLOWED_EXTENSIONS, ANTHROPIC_API_KEY as _SERVER_KEY
from backend.services.job_manager import create_job, update_job
from backend.models.job import JobStatus

router = APIRouter()


async def _run_analysis(job_id: str) -> None:
    from backend.services.workbook_analyzer import scan_workbook
    from backend.services.claude_agent import run_agent_loop
    from backend.services.job_manager import get_job

    try:
        job = await get_job(job_id)
        if not job:
            return

        await update_job(job_id, status=JobStatus.ANALYZING, progress_message="Scanning workbook formulas...")
        analysis = await asyncio.to_thread(scan_workbook, str(job.original_path))

        await update_job(job_id, progress_message="Running AI analysis...")
        auto_fixes, validation_queue, summary, partial = await run_agent_loop(
            job_id, analysis, api_key=job.api_key
        )

        await update_job(
            job_id,
            status=JobStatus.READY,
            progress_message="Analysis complete",
            auto_fixes=auto_fixes,
            validation_queue=validation_queue,
            summary=summary,
            partial_analysis=partial,
        )
    except Exception as exc:
        await update_job(job_id, status=JobStatus.ERROR, error=str(exc))


@router.post("/api/upload")
async def upload_file(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    anthropic_api_key: str = Form(default=""),
):
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Upload an .xlsx or .xlsm file.")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(413, "File exceeds 10 MB limit")

    # Prefer user-supplied key; fall back to server .env key (for local dev)
    effective_key = anthropic_api_key.strip() or _SERVER_KEY
    if not effective_key:
        raise HTTPException(400, "No Anthropic API key provided. Enter your key in the form.")

    job = await create_job(file.filename, api_key=effective_key)
    job.original_path.write_bytes(contents)

    background_tasks.add_task(_run_analysis, job.job_id)

    return {"job_id": job.job_id, "status": JobStatus.ANALYZING, "filename": file.filename}
