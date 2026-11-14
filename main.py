import os
import re
import uuid
import shutil
import tempfile
import subprocess
import threading
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader, PdfWriter

APP_DIR = Path(__file__).resolve().parent
WORK_DIR = Path(os.getenv("WORK_DIR", "/tmp/ocr_jobs"))
WORK_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Unlimited Page Searchable PDF OCR")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

# Job status is held in memory for this starter deployment. Keep the server running
# while jobs are processing; use a database/queue for a multi-server production setup.
jobs: Dict[str, Dict[str, Any]] = {}
jobs_lock = threading.Lock()

LANGUAGES = {"eng", "tam", "eng+tam", "hin", "eng+hin", "fra", "deu", "spa"}


def update_job(job_id: str, **values):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(values)


def run_ocr(job_id: str, input_path: Path, output_path: Path, language: str, chunk_size: int):
    job_dir = input_path.parent
    try:
        reader = PdfReader(str(input_path), strict=False)
        if reader.is_encrypted:
            raise ValueError("This PDF is password-protected. Remove the password and upload it again.")
        total_pages = len(reader.pages)
        if total_pages == 0:
            raise ValueError("The uploaded PDF has no pages.")

        update_job(job_id, status="processing", total_pages=total_pages,
                   completed_pages=0, progress=0, message=f"Preparing {total_pages:,} pages…")

        merged = PdfWriter()
        chunk_count = (total_pages + chunk_size - 1) // chunk_size

        for chunk_index, start in enumerate(range(0, total_pages, chunk_size)):
            end = min(start + chunk_size, total_pages)
            chunk_input = job_dir / f"chunk_{chunk_index:05d}_input.pdf"
            chunk_output = job_dir / f"chunk_{chunk_index:05d}_searchable.pdf"

            writer = PdfWriter()
            for page_num in range(start, end):
                writer.add_page(reader.pages[page_num])
            with chunk_input.open("wb") as f:
                writer.write(f)

            update_job(job_id, message=f"OCR processing pages {start + 1:,}–{end:,} of {total_pages:,}",
                       completed_pages=start, progress=round(start / total_pages * 100, 1))

            command = [
                "ocrmypdf",
                "--skip-text",
                "--rotate-pages",
                "--deskew",
                "--jobs", str(max(1, min(4, os.cpu_count() or 2))),
                "--language", language,
                "--output-type", "pdf",
                str(chunk_input),
                str(chunk_output),
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "OCR engine failed")[-2500:]
                raise RuntimeError(f"Failed while processing pages {start + 1}–{end}.\n{detail}")

            chunk_reader = PdfReader(str(chunk_output), strict=False)
            for page in chunk_reader.pages:
                merged.add_page(page)

            update_job(job_id, completed_pages=end, progress=round(end / total_pages * 100, 1),
                       message=f"Completed {end:,} of {total_pages:,} pages")

            chunk_input.unlink(missing_ok=True)
            chunk_output.unlink(missing_ok=True)

        with output_path.open("wb") as f:
            merged.write(f)

        update_job(job_id, status="completed", progress=100, completed_pages=total_pages,
                   message="OCR completed. Your searchable PDF is ready.",
                   output_path=str(output_path), output_name="searchable_" + input_path.name)
    except Exception as exc:
        update_job(job_id, status="failed", message=str(exc), error=str(exc))
    finally:
        input_path.unlink(missing_ok=True)


@app.get("/")
def home():
    return FileResponse(APP_DIR / "static" / "index.html")


@app.post("/api/ocr")
async def create_ocr_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str = Form("eng"),
    chunk_size: int = Form(50),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")
    if language not in LANGUAGES:
        raise HTTPException(status_code=400, detail="Unsupported OCR language selection.")
    if chunk_size < 10 or chunk_size > 200:
        raise HTTPException(status_code=400, detail="Chunk size must be between 10 and 200 pages.")

    job_id = uuid.uuid4().hex
    job_dir = WORK_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file.filename).name)
    input_path = job_dir / safe_name
    output_path = job_dir / ("searchable_" + safe_name)

    try:
        with input_path.open("wb") as destination:
            while True:
                data = await file.read(1024 * 1024)
                if not data:
                    break
                destination.write(data)
    finally:
        await file.close()

    with jobs_lock:
        jobs[job_id] = {
            "status": "queued", "progress": 0, "completed_pages": 0,
            "total_pages": None, "message": "Upload received. Waiting for OCR…",
            "output_path": None, "output_name": None,
        }

    background_tasks.add_task(run_ocr, job_id, input_path, output_path, language, chunk_size)
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        return {k: v for k, v in job.items() if k != "output_path"}


@app.get("/api/download/{job_id}")
def download_result(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job.get("status") != "completed" or not job.get("output_path"):
        raise HTTPException(status_code=404, detail="The searchable PDF is not ready.")
    path = Path(job["output_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="The output file is no longer available.")
    return FileResponse(path, media_type="application/pdf", filename=job["output_name"])
