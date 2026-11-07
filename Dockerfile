# PRD//SUITE — imagem de produção compatível com x86-64 baseline.
# A base Chainguard/Wolfi exige SSE4.2 e não roda em CPUs Llano antigas.
FROM python:3.13-alpine

USER root

# Bibliotecas nativas do WeasyPrint, fontes e dados de fuso.
RUN apk add --no-cache \
        pango cairo harfbuzz fontconfig ttf-dejavu libjpeg-turbo libffi \
        shared-mime-info tzdata \
    && rm -rf /var/cache/apk/*

# Mantém o UID/GID histórico do volume (10001).
RUN addgroup -g 10001 app && adduser -S -D -H -u 10001 -G app app

WORKDIR /app
COPY requirements.txt ./
RUN python -m venv /app/.venv \
    && /app/.venv/bin/pip install --no-cache-dir --no-compile -r requirements.txt \
    && /app/.venv/bin/pip uninstall -y pip setuptools wheel >/dev/null 2>&1 || true
# Remove o pip do Python do sistema; não é necessário em runtime.
RUN rm -rf /usr/local/lib/python3.13/site-packages/pip* \
           /usr/local/lib/python3.13/site-packages/setuptools* \
           /usr/local/lib/python3.13/site-packages/wheel* \
           /usr/local/lib/python3.13/ensurepip

COPY --chown=app:app . .
RUN mkdir -p /data /app/instance && chown -R app:app /data /app

USER app
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MALLOC_ARENA_MAX=2 \
    FLASK_ENV=production \
    XDG_CACHE_HOME=/tmp \
    DATABASE_URL=sqlite:////data/prodsuite.db \
    PORT=5000 \
    WEB_CONCURRENCY=2 \
    GUNICORN_THREADS=2

EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; r = urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=3); sys.exit(0 if r.status == 200 else 1)"]

ENTRYPOINT []
CMD ["sh", "-c", "flask --app app init-db && exec gunicorn --config gunicorn.conf.py app:app"]
