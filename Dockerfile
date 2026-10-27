FROM node:22-alpine AS frontend
WORKDIR /build
RUN corepack enable && corepack prepare pnpm@11.25.0 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --create-home --uid 10001 inspector
COPY backend ./backend
COPY scripts ./scripts
COPY models ./models
COPY alembic.ini ./
COPY --from=frontend /build/dist ./frontend/dist
RUN mkdir -p /app/data/private && chown -R inspector:inspector /app/data
USER inspector
EXPOSE 8000
CMD ["sh", "-c", "python scripts/manage.py migrate && python scripts/manage.py register-model && uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]
