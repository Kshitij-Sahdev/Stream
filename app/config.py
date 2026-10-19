import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
ORIGINALS_DIR = DATA_DIR / "originals"
HLS_DIR = DATA_DIR / "hls"
DB_PATH = DATA_DIR / "stream.db"

# Limits & Validation
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 500 * 1024 * 1024))  # 500 MB
ALLOWED_EXTENSIONS = {"mp4", "mov", "mkv", "avi", "webm", "m4v"}

# HLS Transcoding Settings
HLS_SEGMENT_DURATION = int(os.getenv("HLS_SEGMENT_DURATION", 4))  # 4 seconds

# Resolution ladder: (target_width, target_height, video_bitrate_bps, audio_bitrate_str)
# Standard 16:9 target ladder
RESOLUTION_LADDER = [
    {
        "name": "360p",
        "max_height": 360,
        "max_width": 640,
        "video_bitrate": "800k",
        "audio_bitrate": "96k",
        "bandwidth": 896000,
    },
    {
        "name": "480p",
        "max_height": 480,
        "max_width": 854,
        "video_bitrate": "1400k",
        "audio_bitrate": "128k",
        "bandwidth": 1528000,
    },
    {
        "name": "720p",
        "max_height": 720,
        "max_width": 1280,
        "video_bitrate": "2800k",
        "audio_bitrate": "128k",
        "bandwidth": 2928000,
    },
]

# Ensure critical directories exist
def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
    HLS_DIR.mkdir(parents=True, exist_ok=True)
