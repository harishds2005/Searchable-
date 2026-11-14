FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-tam tesseract-ocr-hin \
    tesseract-ocr-fra tesseract-ocr-deu tesseract-ocr-spa \
    ghostscript qpdf unpaper pngquant jbig2enc \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir ocrmypdf==16.10.4
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ENV WORK_DIR=/data/ocr_jobs
RUN mkdir -p /data/ocr_jobs
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
