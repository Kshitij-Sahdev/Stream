import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from app.config import RESOLUTION_LADDER, HLS_SEGMENT_DURATION

logger = logging.getLogger("stream.media")

class MediaProcessingError(Exception):
    """Custom exception for media probing or transcoding failures."""
    pass

def get_binary_path(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise MediaProcessingError(f"Required binary '{name}' not found on system PATH.")
    return path

def probe_video(file_path: Path) -> Dict[str, Any]:
    """Inspects media file using FFprobe and returns duration, dimensions, and codec info."""
    ffprobe_bin = get_binary_path("ffprobe")
    if not file_path.exists():
        raise MediaProcessingError(f"File not found: {file_path}")

    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise MediaProcessingError("FFprobe timed out while inspecting file.")
    except Exception as e:
        raise MediaProcessingError(f"Failed to execute FFprobe: {str(e)}")

    if result.returncode != 0:
        raise MediaProcessingError(f"FFprobe failed: {result.stderr.strip()[:300]}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise MediaProcessingError("Invalid JSON output from FFprobe.")

    video_stream = None
    audio_stream = None

    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type")
        if codec_type == "video" and not video_stream:
            video_stream = stream
        elif codec_type == "audio" and not audio_stream:
            audio_stream = stream

    if not video_stream:
        raise MediaProcessingError("File contains no valid video stream.")

    try:
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))
    except (ValueError, TypeError):
        width, height = 0, 0

    format_info = data.get("format", {})
    try:
        duration = float(format_info.get("duration", 0.0))
        if duration == 0.0 and "duration" in video_stream:
            duration = float(video_stream.get("duration", 0.0))
    except (ValueError, TypeError):
        duration = 0.0

    return {
        "width": width,
        "height": height,
        "duration": duration,
        "video_codec": video_stream.get("codec_name", "unknown"),
        "audio_codec": audio_stream.get("codec_name", None) if audio_stream else None,
        "has_audio": audio_stream is not None,
    }

def select_renditions(source_width: int, source_height: int) -> List[Dict[str, Any]]:
    """Selects ladder renditions that do not upscale the source video."""
    selected = []
    # If source dimensions are 0 or unknown, default to 360p minimum
    if source_height <= 0 or source_width <= 0:
        return [RESOLUTION_LADDER[0]]

    for r in RESOLUTION_LADDER:
        # Include rendition only if source is at least 85% of target height to avoid significant upscaling
        # Always include 360p as minimum base rendition if it's the first
        if r["max_height"] <= source_height or not selected:
            selected.append(r)

    # Ensure at least one rendition is selected
    if not selected:
        selected.append(RESOLUTION_LADDER[0])
    return selected

def transcode_to_hls(
    video_id: str,
    input_path: Path,
    output_dir: Path,
    probe_info: Dict[str, Any],
) -> Dict[str, Any]:
    """Transcodes the source video to multi-bitrate HLS using FFmpeg."""
    ffmpeg_bin = get_binary_path("ffmpeg")
    output_dir.mkdir(parents=True, exist_ok=True)

    has_audio = probe_info.get("has_audio", False)
    source_width = probe_info.get("width", 0)
    source_height = probe_info.get("height", 0)
    renditions = select_renditions(source_width, source_height)

    start_time = time.time()
    generated_renditions = []

    # Transcode each rendition separately to ensure clean playlist generation and predictable execution
    for r in renditions:
        rendition_name = r["name"]
        target_height = r["max_height"]
        r_dir = output_dir / rendition_name
        r_dir.mkdir(parents=True, exist_ok=True)
        playlist_path = r_dir / "index.m3u8"
        segment_pattern = r_dir / "seg_%03d.ts"

        # Scale filter maintaining aspect ratio and ensuring even dimensions
        vf_filter = (
            f"scale='min({r['max_width']},iw)':min'({target_height},ih)':force_original_aspect_ratio=decrease,"
            f"scale=trunc(iw/2)*2:trunc(ih/2)*2"
        )

        cmd = [
            ffmpeg_bin,
            "-y",
            "-i", str(input_path),
            "-vf", vf_filter,
            "-c:v", "libx264",
            "-profile:v", "main",
            "-crf", "22",
            "-maxrate", r["video_bitrate"],
            "-bufsize", str(int(r["bandwidth"] * 1.5)),
            "-pix_fmt", "yuv420p",
            "-g", "96",
            "-keyint_min", "96",
            "-sc_threshold", "0",
        ]

        if has_audio:
            cmd.extend([
                "-c:a", "aac",
                "-b:a", r["audio_bitrate"],
                "-ac", "2",
                "-ar", "44100",
            ])
        else:
            cmd.extend(["-an"])

        cmd.extend([
            "-f", "hls",
            "-hls_time", str(HLS_SEGMENT_DURATION),
            "-hls_playlist_type", "vod",
            "-hls_segment_filename", str(segment_pattern),
            str(playlist_path),
        ])

        logger.info("Transcoding %s rendition for video %s", rendition_name, video_id)
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if res.returncode != 0:
            error_msg = res.stderr[-500:] if res.stderr else "Unknown FFmpeg error"
            raise MediaProcessingError(f"Transcoding failed for {rendition_name}: {error_msg}")

        # Count segments and size
        segments = list(r_dir.glob("seg_*.ts"))
        total_r_size = sum(f.stat().st_size for f in segments if f.is_file())
        if playlist_path.is_file():
            total_r_size += playlist_path.stat().st_size

        # Probe the generated rendition dimensions
        try:
            r_probe = probe_video(playlist_path)
            actual_w = r_probe["width"] or r["max_width"]
            actual_h = r_probe["height"] or r["max_height"]
        except Exception:
            actual_w, actual_h = r["max_width"], r["max_height"]

        generated_renditions.append({
            "name": rendition_name,
            "width": actual_w,
            "height": actual_h,
            "bitrate": r["bandwidth"],
            "playlist_rel_path": f"{rendition_name}/index.m3u8",
            "segment_count": len(segments),
            "size_bytes": total_r_size,
        })

    # Generate master.m3u8
    master_playlist_path = output_dir / "master.m3u8"
    master_lines = ["#EXTM3U", "#EXT-X-VERSION:3"]

    for r in generated_renditions:
        codecs = 'avc1.4d401f,mp4a.40.2' if has_audio else 'avc1.4d401f'
        master_lines.append(
            f'#EXT-X-STREAM-INF:BANDWIDTH={r["bitrate"]},RESOLUTION={r["width"]}x{r["height"]},CODECS="{codecs}"'
        )
        master_lines.append(r["playlist_rel_path"])

    with open(master_playlist_path, "w", encoding="utf-8") as f:
        f.write("\n".join(master_lines) + "\n")

    encoding_duration = time.time() - start_time
    total_output_size = sum(f.stat().st_size for f in output_dir.rglob("*") if f.is_file())

    # Validate output
    validate_hls_output(output_dir, generated_renditions)

    return {
        "encoding_duration_seconds": round(encoding_duration, 2),
        "total_output_size": total_output_size,
        "renditions": generated_renditions,
    }

def validate_hls_output(output_dir: Path, renditions: List[Dict[str, Any]]) -> None:
    """Validates that master playlist, variant playlists, and all referenced segments exist on disk."""
    master = output_dir / "master.m3u8"
    if not master.is_file() or master.stat().st_size == 0:
        raise MediaProcessingError("Master playlist is missing or empty.")

    for r in renditions:
        r_playlist = output_dir / r["playlist_rel_path"]
        if not r_playlist.is_file() or r_playlist.stat().st_size == 0:
            raise MediaProcessingError(f"Rendition playlist missing: {r['playlist_rel_path']}")

        # Read playlist and verify every .ts file listed exists and is non-empty
        with open(r_playlist, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

        if not lines:
            raise MediaProcessingError(f"Rendition playlist {r['name']} contains no media segments.")

        r_dir = r_playlist.parent
        for seg_name in lines:
            seg_file = r_dir / seg_name
            if not seg_file.is_file() or seg_file.stat().st_size == 0:
                raise MediaProcessingError(f"Referenced segment {seg_name} is missing or empty on disk.")
