# Backend do Simulador de Investimentos (FastAPI + workers APScheduler no mesmo processo).
# Rode UMA instância só: os workers (stop loss, proventos, renda fixa, snapshots) vivem dentro do app.
# 1) gera o site (React) ...
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 2) ... e o backend FastAPI serve o site e a API juntos
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ENVIRONMENT=production

WORKDIR /app
COPY backend/requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY --from=web /web/dist frontend/dist
COPY alembic.ini .
COPY backend backend
# só o manifesto das videoaulas (durações e caminhos); os vídeos ficam no MEDIA_BASE_URL (bucket/CDN)
COPY media/manifest.json media/manifest.json

# a maioria dos hosts define $PORT; as migrations rodam antes de abrir a porta
CMD ["sh", "-c", "python -c \"from backend.config import get_settings; get_settings().check_production()\" && alembic upgrade head && exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
