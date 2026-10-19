from typing import Optional, List
from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    status: str = Field(..., description="Overall health status: healthy or degraded")
    database: str = Field(..., description="Database status: connected or error")
    ffmpeg: str = Field(..., description="FFmpeg binary status: available or missing")
    ffprobe: str = Field(..., description="FFprobe binary status: available or missing")
    version: str = Field(..., description="Application version")

class RenditionResponse(BaseModel):
    name: str
    width: int
    height: int
    bitrate: int
    playlist_path: str
    segment_count: int
    size_bytes: int

class VideoListItem(BaseModel):
    id: str
    title: str
    original_filename: str
    file_size: int
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    status: str
    created_at: str

class VideoDetailResponse(BaseModel):
    id: str
    title: str
    original_filename: str
    file_size: int
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    status: str
    created_at: str
    updated_at: str
    renditions: List[RenditionResponse] = []
    job_id: Optional[str] = None
    error_summary: Optional[str] = None

class JobResponse(BaseModel):
    id: str
    video_id: str
    status: str
    stage: Optional[str] = None
    progress: int = 0
    error_summary: Optional[str] = None
    diagnostic_log: Optional[str] = None
    encoding_duration_seconds: Optional[float] = None
    total_output_size: Optional[int] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
