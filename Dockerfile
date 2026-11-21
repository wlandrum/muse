# Muse web UI (Streamlit). All artist data lives under /data (a volume).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY muse/ muse/
COPY ui/ ui/

ENV DB_PATH=/data/muse.db \
    CHROMADB_PATH=/data/chroma_db \
    INVOICE_OUTPUT_DIR=/data/invoices \
    GOOGLE_TOKEN_PATH=/data/token.json \
    GOOGLE_CREDENTIALS_PATH=/data/credentials.json

RUN useradd --create-home --uid 1000 muse && mkdir -p /data && chown muse /data
USER muse
VOLUME ["/data"]
EXPOSE 8501

CMD ["streamlit", "run", "ui/app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
