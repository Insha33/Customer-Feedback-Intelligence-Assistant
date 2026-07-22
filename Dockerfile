FROM node:22-bookworm-slim AS web-builder

WORKDIR /app

COPY web/package.json web/package-lock.json ./web/
RUN npm --prefix web ci

COPY web ./web
RUN npm --prefix web run build


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-deploy.txt ./
RUN pip install --no-cache-dir -r requirements-deploy.txt

COPY backend ./backend
COPY data/instagram_reviews_rag.csv data/backlog_recommendations.json ./data/
COPY frontend ./frontend
COPY prompts.py ./
COPY --from=web-builder /app/web/out ./web/out

EXPOSE 8080

CMD ["python", "-m", "backend.reviewlens_server"]
