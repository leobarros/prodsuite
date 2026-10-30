# PRD//SUITE — imagem de produção
# Gunicorn (gthread) + SQLite em volume. Sem dependências de sistema pesadas.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MALLOC_ARENA_MAX=2 \
    FLASK_ENV=production

WORKDIR /app

# Usuário sem privilégios e diretórios preparados para o volume.
# UID/GID determinísticos (10001) simplificam backup/restore do volume.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --home-dir /app \
        --shell /usr/sbin/nologin app \
    && mkdir -p /data /app/instance \
    && chown -R 10001:10001 /data /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --no-compile -r requirements.txt

COPY --chown=app:app . .

USER app

ENV DATABASE_URL=sqlite:////data/prodsuite.db \
    PORT=5000 \
    WEB_CONCURRENCY=2 \
    GUNICORN_THREADS=2

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; r = urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=3); sys.exit(0 if r.status == 200 else 1)"]

# init-db é idempotente e roda antes de subir os workers.
CMD ["sh", "-c", "flask --app app init-db && exec gunicorn --config gunicorn.conf.py app:app"]
