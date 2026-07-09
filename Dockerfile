# PE-RAG — FastAPI service image.
# Serves src/api/main.py (POST /query, GET /health). The built index (data/) and the
# corpus are mounted at runtime (not baked in); API keys come from the environment.
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Install deps first for better layer caching. (sentence-transformers is optional and
# stays commented in requirements.txt, so the image is lean; reranking falls back to identity.)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code + the tracked manifest (the corpus/index are mounted at runtime).
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY edgar_corpus/manifest.json ./edgar_corpus/manifest.json

EXPOSE 8000

# Container health = the API's own readiness endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
