import os
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from app.config import HLS_DIR
from app.database import get_db

router = APIRouter(prefix="/stream", tags=["stream"])

# Safe video_id pattern (hex alphanumeric uuid)
ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

@router.get("/{video_id}/{file_path:path}")
def serve_stream_file(video_id: str, file_path: str):
    # 1. Validate video_id format
    if not ID_PATTERN.match(video_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid video ID format")

    # 2. Check video exists and is in READY state
    with get_db() as conn:
        row = conn.execute("SELECT status FROM videos WHERE id = ?;", (video_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
        if row["status"] != "READY":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Video stream not ready. Current status: {row['status']}",
            )

    # 3. Path traversal protection: resolve against video HLS directory
    base_dir = (HLS_DIR / video_id).resolve()
    target_file = (base_dir / file_path).resolve()

    # Ensure resolved path is strictly within base_dir
    try:
        target_file.relative_to(base_dir)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Path traversal detected.",
        )

    if not target_file.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requested stream file not found")

    # 4. Set accurate MIME type and cache-control headers
    ext = target_file.suffix.lower()
    if ext == ".m3u8":
        media_type = "application/vnd.apple.mpegurl"
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Access-Control-Allow-Origin": "*",
        }
    elif ext == ".ts":
        media_type = "video/MP2T"
        headers = {
            "Cache-Control": "public, max-age=86400, immutable",
            "Access-Control-Allow-Origin": "*",
        }
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unsupported stream file type")

    return FileResponse(
        path=str(target_file),
        media_type=media_type,
        headers=headers,
    )
