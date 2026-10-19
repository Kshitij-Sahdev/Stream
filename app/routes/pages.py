from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.config import BASE_DIR
from app.database import get_db

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@router.get("/", response_class=HTMLResponse)
def page_library(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@router.get("/upload", response_class=HTMLResponse)
def page_upload(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})

@router.get("/watch/{video_id}", response_class=HTMLResponse)
def page_watch(request: Request, video_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM videos WHERE id = ?;", (video_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Video not found")
        video = dict(row)
    return templates.TemplateResponse("watch.html", {"request": request, "video": video})

@router.get("/jobs", response_class=HTMLResponse)
def page_jobs(request: Request):
    return templates.TemplateResponse("jobs.html", {"request": request})
