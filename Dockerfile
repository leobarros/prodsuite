# PRD//SUITE — imagem de produção Chainguard/Wolfi.
# Base fixada por digest; atualize junto com a revisão de segurança.
FROM cgr.dev/chainguard/wolfi-base@sha256:24f549a7fcace88e69b9557941168c74645688ecc4acf7fb6d734a6b74e9019d

USER root

# Python + bibliotecas nativas do WeasyPrint, fontes e dados de fuso.
RUN apk update && apk add --no-cache \
        python-3.13 py3.13-pip \
        pango cairo harfbuzz fontconfig ttf-dejavu libjpeg-turbo \
        libffi shared-mime-info tzdata \
    && rm -rf /var/cache/apk/*

# Mantém o UID/GID histórico do volume (10001) para atualização sem quebra.
RUN addgroup --gid 10001 app \
    && adduser -u 10001 -G app -S -D -H -g "ProdSuite" app

WORKDIR /app
COPY requirements.txt ./
RUN python3.13 -m venv /app/.venv \
    && /app/.venv/bin/pip install --no-cache-dir --no-compile -r requirements.txt \
    && /app/.venv/bin/pip uninstall -y pip setuptools wheel >/dev/null 2>&1 || true
RUN apk del py3.13-pip py3.13-setuptools py3-pip-wheel >/dev/null 2>&1 || true

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
