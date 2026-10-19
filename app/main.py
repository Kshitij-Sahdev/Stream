import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app import __version__
from app.config import BASE_DIR, ensure_directories
from app.database import init_db
from app.worker import worker
from app.routes import health, videos, jobs, stream, pages

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("stream.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Starting STREAM v%s", __version__)
    ensure_directories()
    init_db()
    worker.start()
    yield
    # Shutdown actions
    logger.info("Shutting down STREAM")
    await worker.stop()

app = FastAPI(
    title="STREAM",
    description="Lightweight, self-hosted HLS video streaming platform",
    version=__version__,
    lifespan=lifespan,
)

# Mount static files
static_dir = BASE_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include Routers
app.include_router(health.router)
app.include_router(videos.router)
app.include_router(jobs.router)
app.include_router(stream.router)
app.include_router(pages.router)
