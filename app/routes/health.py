import shutil
import subprocess
from fastapi import APIRouter
from app import __version__
from app.database import get_db
from app.models import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])

def check_binary(binary_name: str) -> str:
    path = shutil.which(binary_name)
    if not path:
        return "missing"
    try:
        res = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=5)
        return "available" if res.returncode == 0 else "error"
    except Exception:
        return "error"

def check_db() -> str:
    try:
        with get_db() as conn:
            row = conn.execute("SELECT 1 AS ok;").fetchone()
            return "connected" if row and row["ok"] == 1 else "error"
    except Exception:
        return "error"

@router.get("/health", response_model=HealthResponse)
def get_health():
    db_status = check_db()
    ffmpeg_status = check_binary("ffmpeg")
    ffprobe_status = check_binary("ffprobe")

    is_healthy = (
        db_status == "connected"
        and ffmpeg_status == "available"
        and ffprobe_status == "available"
    )

    return HealthResponse(
        status="healthy" if is_healthy else "degraded",
        database=db_status,
        ffmpeg=ffmpeg_status,
        ffprobe=ffprobe_status,
        version=__version__,
    )
