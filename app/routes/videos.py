import os
import shutil
import uuid
from typing import List, Optional
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from app.config import ORIGINALS_DIR, HLS_DIR, ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE, ensure_directories
from app.database import get_db
from app.models import VideoListItem, VideoDetailResponse, RenditionResponse
from app.worker import worker

router = APIRouter(prefix="/api/videos", tags=["videos"])

@router.get("", response_model=List[VideoListItem])
def list_videos():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, title, original_filename, file_size, duration_seconds, width, height, status, created_at
            FROM videos
            ORDER BY created_at DESC;
            """
        ).fetchall()
        return [
            VideoListItem(
                id=r["id"],
                title=r["title"],
                original_filename=r["original_filename"],
                file_size=r["file_size"],
                duration_seconds=r["duration_seconds"],
                width=r["width"],
                height=r["height"],
                status=r["status"],
                created_at=str(r["created_at"]),
            )
            for r in rows
        ]

@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_video(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
):
    ensure_directories()

    # 1. Validate filename and extension
    original_filename = file.filename or "upload.mp4"
    ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '.{ext}'. Supported formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # 2. Generate secure internal IDs
    video_id = uuid.uuid4().hex
    job_id = uuid.uuid4().hex
    storage_filename = f"{video_id}.{ext}"
    target_path = ORIGINALS_DIR / storage_filename

    display_title = title.strip() if title and title.strip() else original_filename.rsplit(".", 1)[0]

    # 3. Stream file to disk while enforcing max upload size
    bytes_written = 0
    chunk_size = 1024 * 1024  # 1MB chunks

    try:
        with open(target_path, "wb") as buffer:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_SIZE:
                    # Clean up partial upload immediately
                    buffer.close()
                    if target_path.exists():
                        target_path.unlink()
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Upload exceeds maximum allowable size of {MAX_UPLOAD_SIZE // (1024 * 1024)}MB",
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        if target_path.exists():
            target_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save upload: {str(e)}",
        )

    if bytes_written == 0:
        if target_path.exists():
            target_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes).",
        )

    # 4. Record video and job in database
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO videos (id, title, original_filename, storage_filename, file_size, status)
            VALUES (?, ?, ?, ?, ?, 'QUEUED');
            """,
            (video_id, display_title, original_filename, storage_filename, bytes_written),
        )
        conn.execute(
            """
            INSERT INTO jobs (id, video_id, status, stage, progress)
            VALUES (?, ?, 'QUEUED', 'queued', 0);
            """,
            (job_id, video_id),
        )

    # 5. Enqueue background processing job
    worker.enqueue(job_id, video_id)

    return {
        "video_id": video_id,
        "job_id": job_id,
        "title": display_title,
        "status": "QUEUED",
        "file_size": bytes_written,
    }

@router.get("/{video_id}", response_model=VideoDetailResponse)
def get_video_detail(video_id: str):
    with get_db() as conn:
        v_row = conn.execute("SELECT * FROM videos WHERE id = ?;", (video_id,)).fetchone()
        if not v_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

        r_rows = conn.execute(
            "SELECT * FROM renditions WHERE video_id = ? ORDER BY bitrate ASC;", (video_id,)
        ).fetchall()

        j_row = conn.execute(
            "SELECT id, error_summary FROM jobs WHERE video_id = ? ORDER BY created_at DESC LIMIT 1;",
            (video_id,),
        ).fetchone()

        renditions = [
            RenditionResponse(
                name=r["name"],
                width=r["width"],
                height=r["height"],
                bitrate=r["bitrate"],
                playlist_path=r["playlist_path"],
                segment_count=r["segment_count"],
                size_bytes=r["size_bytes"],
            )
            for r in r_rows
        ]

        return VideoDetailResponse(
            id=v_row["id"],
            title=v_row["title"],
            original_filename=v_row["original_filename"],
            file_size=v_row["file_size"],
            duration_seconds=v_row["duration_seconds"],
            width=v_row["width"],
            height=v_row["height"],
            video_codec=v_row["video_codec"],
            audio_codec=v_row["audio_codec"],
            status=v_row["status"],
            created_at=str(v_row["created_at"]),
            updated_at=str(v_row["updated_at"]),
            renditions=renditions,
            job_id=j_row["id"] if j_row else None,
            error_summary=j_row["error_summary"] if j_row else None,
        )

@router.delete("/{video_id}", status_code=status.HTTP_200_OK)
def delete_video(video_id: str):
    with get_db() as conn:
        v_row = conn.execute("SELECT * FROM videos WHERE id = ?;", (video_id,)).fetchone()
        if not v_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

        # Reject deletion if an active job is processing
        j_row = conn.execute(
            "SELECT id FROM jobs WHERE video_id = ? AND status = 'PROCESSING';", (video_id,)
        ).fetchone()
        if j_row:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete video while transcoding job is actively running.",
            )

        storage_filename = v_row["storage_filename"]

        # Delete from database (foreign keys cascade to jobs & renditions)
        conn.execute("DELETE FROM videos WHERE id = ?;", (video_id,))

    # Safely delete stored files on host
    original_path = ORIGINALS_DIR / storage_filename
    if original_path.exists():
        try:
            original_path.unlink()
        except Exception as e:
            pass

    hls_video_dir = HLS_DIR / video_id
    if hls_video_dir.exists():
        try:
            shutil.rmtree(hls_video_dir)
        except Exception as e:
            pass

    return {"message": "Video and associated streaming files deleted successfully", "video_id": video_id}
