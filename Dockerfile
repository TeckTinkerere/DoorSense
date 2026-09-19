# Stage 1: build the static Next.js frontend (same origin as the API, so no API base).
FROM node:22-slim AS web
WORKDIR /web
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN corepack prepare pnpm@11.19.0 --activate && pnpm install --frozen-lockfile
COPY frontend/ ./
ENV NEXT_PUBLIC_API_BASE=""
RUN pnpm run build

# Stage 2: FastAPI serving the API plus the exported frontend on $PORT (Cloud Run sets it).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY --from=web /web/out ./frontend/out
ENV PYTHONPATH=/app/backend
# Analyses live in process memory, so run ONE instance (see scripts/deploy_gcp.ps1).
CMD exec uvicorn doorlens.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1
