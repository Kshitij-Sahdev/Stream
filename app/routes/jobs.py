from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from app.database import get_db
from app.models import JobResponse

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

@router.get("", response_model=List[JobResponse])
def list_jobs(limit: int = 50):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, video_id, status, stage, progress, error_summary, diagnostic_log,
                   encoding_duration_seconds, total_output_size, created_at, started_at, completed_at
            FROM jobs
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            (limit,),
        ).fetchall()
        return [
            JobResponse(
                id=r["id"],
                video_id=r["video_id"],
                status=r["status"],
                stage=r["stage"],
                progress=r["progress"] or 0,
                error_summary=r["error_summary"],
                diagnostic_log=r["diagnostic_log"],
                encoding_duration_seconds=r["encoding_duration_seconds"],
                total_output_size=r["total_output_size"],
                created_at=str(r["created_at"]),
                started_at=str(r["started_at"]) if r["started_at"] else None,
                completed_at=str(r["completed_at"]) if r["completed_at"] else None,
            )
            for r in rows
        ]

@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str):
    with get_db() as conn:
        r = conn.execute("SELECT * FROM jobs WHERE id = ?;", (job_id,)).fetchone()
        if not r:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        return JobResponse(
            id=r["id"],
            video_id=r["video_id"],
            status=r["status"],
            stage=r["stage"],
            progress=r["progress"] or 0,
            error_summary=r["error_summary"],
            diagnostic_log=r["diagnostic_log"],
            encoding_duration_seconds=r["encoding_duration_seconds"],
            total_output_size=r["total_output_size"],
            created_at=str(r["created_at"]),
            started_at=str(r["started_at"]) if r["started_at"] else None,
            completed_at=str(r["completed_at"]) if r["completed_at"] else None,
        )
