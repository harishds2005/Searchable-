# Searchable PDF OCR Website

A self-hostable website that converts scanned/image-only PDFs into searchable PDFs using OCRmyPDF and Tesseract. It processes documents in batches and does **not** impose a fixed page-count limit. 1,500+ pages are supported, subject to server capacity and available disk space.

## Run with Docker (recommended)

1. Install Docker Desktop (Windows/macOS) or Docker Engine (Linux).
2. Extract this project folder.
3. Open a terminal in this folder.
4. Run:

   ```bash
   docker compose up --build
   ```

5. Open `http://localhost:8000` in your browser.
6. Upload a scanned PDF, choose its OCR language, and start processing.
7. Download the searchable PDF when processing reaches 100%.

The first build downloads the OCR engine and may take several minutes.

## Languages

Included in the Docker image: English (`eng`), Tamil (`tam`), Hindi (`hin`), French (`fra`), German (`deu`) and Spanish (`spa`). English + Tamil is available as `eng+tam`.

To add another language, install its Tesseract language package in the Dockerfile and add its language code to `LANGUAGES` in `app/main.py`.

## Large PDFs (1,500+ pages)

- The server splits the source into batches (25–200 pages), OCRs each batch, and merges the searchable pages in their original order.
- There is no hard-coded total-page limit.
- Large scans can take a long time and need enough disk space and CPU/RAM. Use a machine with adequate resources and keep the server running during processing.
- The default deployment stores job status in memory. It is suitable for a single-server prototype. For a public production service, add persistent job storage/queue, authentication, per-user storage quotas, upload limits appropriate to your infrastructure, automatic file expiry, HTTPS, and monitoring.
- The uploaded file and temporary batch files are stored on the server. Do not upload confidential documents to a server you do not control.

## Run locally without Docker

This is more involved: install Python 3.11+, Tesseract with the selected language data, Ghostscript, and qpdf, then install OCRmyPDF. Install Python dependencies with `pip install -r requirements.txt`, then run `uvicorn app.main:app --reload`. Docker is the easier setup because it installs the system OCR dependencies consistently.

## API

- `POST /api/ocr` — multipart fields: `file`, `language`, `chunk_size`
- `GET /api/status/{job_id}` — processing status and progress
- `GET /api/download/{job_id}` — download completed searchable PDF
