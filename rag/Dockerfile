FROM python:3.11-slim

# WORKDIR is one level above the package so `python -m rag.server` resolves.
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install deps first (layer cache friendly — code changes don't bust the deps layer).
COPY requirements.txt /app/rag/requirements.txt
RUN pip install --no-cache-dir -r /app/rag/requirements.txt

# Copy the rest of the rag/ package.
COPY . /app/rag

EXPOSE 8002

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

CMD ["uvicorn", "rag.server:app", "--host", "0.0.0.0", "--port", "8002"]
