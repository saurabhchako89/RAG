# Multi-stage Dockerfile for RAG Application
# Stage 1: Backend (FastAPI)
FROM python:3.11-slim AS backend

WORKDIR /app

# System deps for ChromaDB
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

RUN mkdir -p uploads data/chromadb data/repos data/

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# Stage 2: Frontend (Nginx serving static HTML)
FROM nginx:alpine AS frontend

COPY frontend/index.html /usr/share/nginx/html/index.html
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
