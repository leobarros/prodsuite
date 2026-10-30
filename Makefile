# PRD//SUITE — atalhos de desenvolvimento e operação
SHELL := /bin/bash
PYTHON ?= python3
VENV := .venv
COMPOSE := docker compose

.PHONY: help install test coverage run init-db icons secret pull up down logs ps backup backup-local

help:
	@echo "PRD//SUITE"
	@echo "  make install   cria .venv e instala dependências de dev"
	@echo "  make test      roda a suíte Pytest"
	@echo "  make coverage  testes com cobertura"
	@echo "  make run       servidor de desenvolvimento em :5000"
	@echo "  make init-db   cria as tabelas SQLite locais"
	@echo "  make icons     regenera os ícones PWA (requer Pillow)"
	@echo "  make secret    gera um SECRET_KEY e atualiza .env"
	@echo "  make pull      baixa a imagem latest do Docker Hub"
	@echo "  make up        pull + sobe o Compose"
	@echo "  make down      para o Compose"
	@echo "  make logs      acompanha logs"
	@echo "  make ps        status + healthcheck"
	@echo "  make backup    backup frio do volume em ./backups"
	@echo "  make backup-local  copia o banco local de instance/ para ./backups"

install:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements-dev.txt

test:
	$(VENV)/bin/python -m pytest -q

coverage:
	$(VENV)/bin/python -m pytest --cov=. --cov-report=term-missing

run:
	$(VENV)/bin/flask --app app run --debug

init-db:
	$(VENV)/bin/flask --app app init-db

icons:
	$(VENV)/bin/python scripts/generate_icons.py

secret:
	@test -f .env || cp .env.example .env
	@chmod 600 .env
	@$(PYTHON) -c "import pathlib,re,secrets; p=pathlib.Path('.env'); p.write_text(re.sub(r'^SECRET_KEY=.*$$', 'SECRET_KEY='+secrets.token_hex(32), p.read_text(), flags=re.M)); print('SECRET_KEY atualizado em .env')"

pull:
	$(COMPOSE) pull

up:
	@test -f .env || (echo "Crie o .env: cp .env.example .env && make secret"; exit 1)
	@if grep -Eq '^APP_PORT=(5060|5061)([[:space:]]|$$)' .env; then 		echo "APP_PORT=5060/5061 é bloqueada pelo Firefox (portas SIP)."; 		echo "Corrija: sed -i 's/^APP_PORT=.*/APP_PORT=8090/' .env"; 		exit 1; 	fi
	$(COMPOSE) pull
	$(COMPOSE) up -d --wait --wait-timeout 90
	$(COMPOSE) ps
	@echo "Healthcheck OK."
	@$(COMPOSE) exec -T app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:5000/healthz').read().decode())"

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f app

ps:
	$(COMPOSE) ps
	@$(COMPOSE) exec -T app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:5000/healthz').read().decode())" || true

backup:
	@mkdir -p backups
	$(COMPOSE) stop
	docker run --rm -v prodsuite_data:/data:ro -v "$(PWD)/backups:/backup" \
		alpine tar czf /backup/prodsuite-$$(date +%F-%H%M).tgz -C /data .
	$(COMPOSE) start

backup-local:
	$(PYTHON) scripts/backup_local.py
