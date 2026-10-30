"""Configuração do Gunicorn.

Objetivo: 2 workers × 2 threads (gthread) para uma aplicação pessoal, com
~120–180 MB de RSS total — folga confortável dentro do limite de 512 MB.
``preload_app`` fica desligado para não herdar conexões SQLite/pool no fork.
"""

from __future__ import annotations

import os

bind = f"0.0.0.0:{int(os.environ.get('PORT', '5000'))}"
workers = max(1, int(os.environ.get("WEB_CONCURRENCY", "2")))
threads = max(1, int(os.environ.get("GUNICORN_THREADS", "2")))
worker_class = "gthread"

timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))
graceful_timeout = 30
keepalive = 5

# Recicla workers periodicamente para conter eventuais vazamentos de memória.
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "2000"))
max_requests_jitter = 200

preload_app = False
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")
capture_output = True

# O app já envia headers de segurança; não adicionar proxies não confiáveis.
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")
