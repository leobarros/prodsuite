# PRD//SUITE — atalhos de desenvolvimento e operação
SHELL := /bin/bash
PYTHON ?= python3
VENV := .venv
COMPOSE := docker compose
REGISTRY_IMAGE ?= nickolback/prodsuite
TRIVY_IMAGE ?= aquasec/trivy:latest
SCAN_IMAGE ?= prodsuite:1.0
PUSH_TARGET := $(word 2,$(MAKECMDGOALS))

.PHONY: help install test coverage run run-https init-db icons secret certs pull up up-https down logs ps backup backup-local push push-tag scan FORCE

help:
	@echo "PRD//SUITE"
	@echo "  make install   cria .venv e instala dependências de dev"
	@echo "  make test      roda a suíte Pytest"
	@echo "  make coverage  testes com cobertura"
	@echo "  make run       servidor de desenvolvimento em :5000"
	@echo "  make certs     gera certificado local para HTTPS"
	@echo "  make run-https servidor de desenvolvimento HTTPS em :5001"
	@echo "  make init-db   cria as tabelas SQLite locais"
	@echo "  make icons     regenera os ícones PWA (requer Pillow)"
	@echo "  make secret    gera um SECRET_KEY e atualiza .env"
	@echo "  make pull      baixa a imagem latest do Docker Hub"
	@echo "  make push      build + push da imagem latest"
	@echo "  make push TAG  build + push da tag informada (ex.: v1)"
	@echo "  make scan      Trivy HIGH/CRITICAL na imagem local"
	@echo "  make up        pull + sobe o Compose"
	@echo "  make up-https  sobe app + Caddy em https://localhost:8443"
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

run-https: certs
	COOKIE_SECURE=true PREFERRED_URL_SCHEME=https $(VENV)/bin/flask --app app run --debug --port 5001 --cert certs/local.pem --key certs/local-key.pem

certs:
	./scripts/generate_dev_cert.sh

run:
	@test -x "$(VENV)/bin/flask" || { 		echo "Flask não encontrado em $(VENV)/bin/flask."; 		echo "O ambiente existe, mas as dependências não foram instaladas."; 		echo "Rode: make install"; 		exit 1; 	}
	$(VENV)/bin/flask --app app run --debug

init-db:
	@test -x "$(VENV)/bin/flask" || { echo "Dependências ausentes. Rode: make install"; exit 1; }
	$(VENV)/bin/flask --app app init-db

icons:
	$(VENV)/bin/python scripts/generate_icons.py

secret:
	@test -f .env || cp .env.example .env
	@chmod 600 .env
	@$(PYTHON) -c "import pathlib,re,secrets; p=pathlib.Path('.env'); p.write_text(re.sub(r'^SECRET_KEY=.*$$', 'SECRET_KEY='+secrets.token_hex(32), p.read_text(), flags=re.M)); print('SECRET_KEY atualizado em .env')"

# make push        -> nickolback/prodsuite:latest
# make push TAG    -> nickolback/prodsuite:TAG (ex.: make push v1)
ifeq ($(PUSH_TARGET),)
push:
	@$(MAKE) --no-print-directory push-tag TAG=latest
else
push:
	@:
endif

# O segundo argumento é uma tag de imagem, não um alvo convencional.
ifneq ($(PUSH_TARGET),)
.PHONY: $(PUSH_TARGET)
$(PUSH_TARGET): FORCE
	@$(MAKE) --no-print-directory push-tag TAG=$(PUSH_TARGET)
endif

push-tag:
	@test -n "$(TAG)" || { echo "Informe a tag: make push v1"; exit 1; }
	docker build -t $(REGISTRY_IMAGE):$(TAG) .
	docker push $(REGISTRY_IMAGE):$(TAG)

scan:
	docker run --rm \
		-v /var/run/docker.sock:/var/run/docker.sock \
		-v "$(PWD)/.trivy-cache:/root/.cache/trivy" \
		$(TRIVY_IMAGE) image \
		--scanners vuln \
		--severity HIGH,CRITICAL \
		--exit-code 1 \
		$(SCAN_IMAGE)

FORCE:

pull:
	$(COMPOSE) pull

up-https: certs
	docker compose -f docker-compose.yml -f docker-compose.https.yml up -d --wait

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
