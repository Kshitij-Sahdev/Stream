import asyncio
import logging
import traceback
from datetime import datetime
from pathlib import Path
from app.config import ORIGINALS_DIR, HLS_DIR
from app.database import get_db
from app.media import probe_video, transcode_to_hls, MediaProcessingError

logger = logging.getLogger("stream.worker")

class BackgroundWorker:
    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task = None
        self._running: bool = False
        self._current_job_id: str = None

    def start(self):
        if not self._running:
            self._running = True
            self.recover_stale_jobs()
            self._task = asyncio.create_task(self._worker_loop())
            logger.info("STREAM in-process background worker started.")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("STREAM in-process background worker stopped.")

    def enqueue(self, job_id: str, video_id: str):
        self._queue.put_nowait({"job_id": job_id, "video_id": video_id})
        logger.info("Enqueued job %s for video %s", job_id, video_id)

    def recover_stale_jobs(self):
        """Startup recovery: marks any jobs left in PROCESSING as FAILED due to shutdown."""
        try:
            with get_db() as conn:
                stale_jobs = conn.execute(
                    "SELECT id, video_id FROM jobs WHERE status = 'PROCESSING';"
                ).fetchall()
                if stale_jobs:
                    logger.warning("Found %d stale PROCESSING jobs on startup. Marking as FAILED.", len(stale_jobs))
                    for job in stale_jobs:
                        conn.execute(
                            """
                            UPDATE jobs
                            SET status = 'FAILED',
                                stage = 'failed',
                                error_summary = 'Processing interrupted by application restart/shutdown',
                                completed_at = CURRENT_TIMESTAMP
                            WHERE id = ?;
                            """,
                            (job["id"],),
                        )
                        conn.execute(
                            "UPDATE videos SET status = 'FAILED' WHERE id = ?;",
                            (job["video_id"],),
                        )
        except Exception as e:
            logger.error("Failed to recover stale jobs: %s", e)

    async def _worker_loop(self):
        while self._running:
            try:
                item = await self._queue.get()
                job_id = item["job_id"]
                video_id = item["video_id"]
                self._current_job_id = job_id
                logger.info("Processing job %s for video %s", job_id, video_id)
                # Run the blocking media pipeline in an executor thread so event loop remains responsive
                await asyncio.to_thread(self._process_job, job_id, video_id)
                self._queue.task_done()
                self._current_job_id = None
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Unexpected worker loop error: %s", e)
                await asyncio.sleep(1)

    def _process_job(self, job_id: str, video_id: str):
        now_str = datetime.utcnow().isoformat()
        with get_db() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'PROCESSING', stage = 'probing', progress = 10, started_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (job_id,),
            )
            conn.execute("UPDATE videos SET status = 'PROCESSING' WHERE id = ?;", (video_id,))

            video_row = conn.execute("SELECT * FROM videos WHERE id = ?;", (video_id,)).fetchone()
            if not video_row:
                logger.error("Video %s not found for job %s", video_id, job_id)
                return

        storage_filename = video_row["storage_filename"]
        input_path = ORIGINALS_DIR / storage_filename
        output_dir = HLS_DIR / video_id

        try:
            # Step 1: Probe video
            probe_info = probe_video(input_path)
            with get_db() as conn:
                conn.execute(
                    """
                    UPDATE videos
                    SET duration_seconds = ?, width = ?, height = ?, video_codec = ?, audio_codec = ?
                    WHERE id = ?;
                    """,
                    (
                        probe_info["duration"],
                        probe_info["width"],
                        probe_info["height"],
                        probe_info["video_codec"],
                        probe_info["audio_codec"],
                        video_id,
                    ),
                )
                conn.execute(
                    "UPDATE jobs SET stage = 'transcoding', progress = 30 WHERE id = ?;",
                    (job_id,),
                )

            # Step 2: Transcode to HLS
            result = transcode_to_hls(video_id, input_path, output_dir, probe_info)

            # Step 3: Record renditions and mark READY
            with get_db() as conn:
                for r in result["renditions"]:
                    conn.execute(
                        """
                        INSERT INTO renditions (video_id, name, width, height, bitrate, playlist_path, segment_count, size_bytes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            video_id,
                            r["name"],
                            r["width"],
                            r["height"],
                            r["bitrate"],
                            r["playlist_rel_path"],
                            r["segment_count"],
                            r["size_bytes"],
                        ),
                    )

                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'READY',
                        stage = 'completed',
                        progress = 100,
                        encoding_duration_seconds = ?,
                        total_output_size = ?,
                        completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?;
                    """,
                    (result["encoding_duration_seconds"], result["total_output_size"], job_id),
                )
                conn.execute("UPDATE videos SET status = 'READY' WHERE id = ?;", (video_id,))

            logger.info("Job %s completed successfully in %.2fs", job_id, result["encoding_duration_seconds"])

        except Exception as e:
            logger.error("Job %s failed: %s", job_id, e)
            safe_error = str(e)
            diag_log = traceback.format_exc()

            # Clean up incomplete HLS output to prevent broken streams
            if output_dir.exists():
                try:
                    import shutil
                    shutil.rmtree(output_dir)
                except Exception as cleanup_err:
                    logger.warning("Failed to clean up output dir %s: %s", output_dir, cleanup_err)

            with get_db() as conn:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'FAILED',
                        stage = 'failed',
                        error_summary = ?,
                        diagnostic_log = ?,
                        completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?;
                    """,
                    (safe_error, diag_log, job_id),
                )
                conn.execute("UPDATE videos SET status = 'FAILED' WHERE id = ?;", (video_id,))

# Singleton worker instance
worker = BackgroundWorker()
