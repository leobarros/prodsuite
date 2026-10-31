# Runbook do ProdSuite

Este documento é para quem instala, mantém e diagnostica o ProdSuite. Ele é intencionalmente técnico e direto: cada procedimento tem um objetivo, os comandos e uma forma de confirmar que deu certo.

Para a apresentação do app, o tour visual e o guia de uso, volte ao **[README](../README.md)**.

---

## Ficha rápida

| Item | Valor |
| --- | --- |
| Stack | Python 3.11, Flask 3, SQLAlchemy, SQLite |
| Servidor | Gunicorn `gthread`, 2 workers × 2 threads |
| Imagem | `nickolback/prodsuite:latest` (Docker Hub) |
| Porta no container | `5000` |
| Porta publicada padrão | `8090` (livre da stack Grafana/Prometheus; não use `5060`) |
| Volume | `prodsuite_data` → `/data` |
| Banco | `/data/prodsuite.db` |
| Limite de memória | 512 MB |
| Healthcheck | `GET /healthz` |
| Testes | 104 Pytest |
| Dados no Git | nenhum (banco, `.env` e backups são ignorados) |

---

## 1. Antes de instalar

Você precisa de:

- Docker 24+ e Docker Compose v2;
- um host Linux, macOS ou Windows com Docker Desktop;
- 512 MB de memória disponível para o container;
- um endereço de acesso: `localhost`, IP da LAN, IP Tailscale ou um domínio com proxy HTTPS.

Confirme as versões:

```bash
docker --version
docker compose version
```

---

## 2. Instalação com Docker

### 2.1 Baixar o projeto

```bash
git clone https://github.com/leobarros/prodsuite.git
cd prodsuite
```

### 2.2 Criar o `.env`

```bash
cp .env.example .env
make secret
```

O alvo `make secret` gera um `SECRET_KEY` aleatório e ajusta o `.env`. O arquivo é ignorado pelo Git.

Confira se a chave foi criada:

```bash
grep '^SECRET_KEY=' .env
```

Nunca use o valor de exemplo em produção.

### 2.3 Subir o container

```bash
docker compose pull
docker compose up -d
docker compose ps
```

O `make up` usa `docker compose up -d --wait`: ele espera o serviço ficar `healthy` antes de testar o `/healthz`. Se o healthcheck não ficar pronto em 90 segundos, o comando falha e não tenta acessar uma porta ainda fechada.

Se você usa `docker compose up` diretamente, aguarde o status `healthy` em `docker compose ps` antes de testar a aplicação.

### 2.4 Verificar a saúde

```bash
curl http://127.0.0.1:8090/healthz
# {"status":"ok"}
```

### 2.5 Ver os logs

```bash
docker compose logs -f app
```

O log deve mostrar `startup app=ProdSuite ... db_backend=sqlite`, o Gunicorn escutando em `0.0.0.0:5000` e os workers iniciando. `Ctrl+C` sai do acompanhamento sem parar o container.

As requisições dinâmicas aparecem em uma linha com contexto útil e sem corpo, query string ou credenciais:

```text
2026-10-31 15:50:57 INFO  app [99d93fc5b0308dac] GET /tarefas user=1 ip=127.0.0.1 | request_complete status=200 duration_ms=100.6 endpoint=tasks.index bytes=32637
```

Use o código entre colchetes para correlacionar um erro mostrado ao usuário com o stack trace. O access log duplicado do Werkzeug, o `/healthz` bem-sucedido e assets estáticos não poluem o log; healthcheck com falha e respostas 4xx/5xx aparecem.

---

## 3. Primeiro acesso

1. Abra `http://localhost:8090`.
2. Crie a conta em **Criar conta**.
3. Faça o tour de boas-vindas.
4. Confirme que o dashboard mostra seu nome de perfil.

### Fechar o registro

Depois de criar a conta principal, edite o `.env`:

```env
ALLOW_REGISTRATION=false
```

Recrie o container para aplicar:

```bash
docker compose up -d --force-recreate
```

Tente abrir `/registrar`: deve retornar **403**.

### Criar usuário pela CLI

Se o registro já estiver fechado e você precisar de outra conta:

```bash
docker compose exec app flask --app app create-user
```

O comando pede nome de acesso, nome de perfil, e-mail e senha.

---

## 4. Variáveis de ambiente

| Variável | Padrão | Para que serve |
| --- | --- | --- |
| `SECRET_KEY` | — | Assinatura de sessão e CSRF. Obrigatória; use 32+ bytes. |
| `BIND_ADDR` | `0.0.0.0` | Interface do host onde a porta é publicada. |
| `APP_PORT` | `8090` | Porta publicada no host. |
| `APP_TIMEZONE` | `America/Sao_Paulo` | Fuso de “hoje”, prazos e métricas. |
| `COOKIE_SECURE` | `false` | Use `true` atrás de HTTPS. |
| `SESSION_LIFETIME_MINUTES` | `30` | Inatividade até a sessão expirar. |
| `WEB_CONCURRENCY` | `2` | Workers do Gunicorn. |
| `GUNICORN_THREADS` | `2` | Threads por worker. |
| `ALLOW_REGISTRATION` | `true` | Desligue após criar a conta principal. |
| `PASSWORD_MIN_LENGTH` | `4` | Mínimo de senha. Aumente em instalações expostas. |
| `LOGIN_ATTEMPT_LIMIT` | `5` | Tentativas antes do bloqueio temporário. |

Depois de alterar qualquer variável:

```bash
docker compose up -d --force-recreate
```

---

## 5. Acesso pelo celular com Tailscale

Há dois modos. O modo B é o recomendado porque permite HTTPS, PWA instalável e cache offline.

### 5.1 Preparar o servidor

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale ip -4
tailscale status
```

No painel do Tailscale, habilite **MagicDNS** e **HTTPS certificates**.

### 5.2 Modo A — HTTP direto pela tailnet

Bom para testar rápido. Não terá service worker/offline, porque HTTP não é um contexto seguro.

```env
BIND_ADDR=100.101.102.103
APP_PORT=8090
COOKIE_SECURE=false
```

```bash
docker compose pull
docker compose up -d
```

Abra no celular:

```text
http://100.101.102.103:8090
```

### 5.3 Modo B — HTTPS com `tailscale serve` (recomendado)

Mantenha o container fechado em localhost e deixe o Tailscale terminar o TLS.

```env
BIND_ADDR=127.0.0.1
APP_PORT=8090
COOKIE_SECURE=true
```

```bash
docker compose pull
docker compose up -d
sudo tailscale serve --bg 8090
sudo tailscale serve status
```

O status deve mostrar algo como:

```text
https://seu-host.sua-tailnet.ts.net -> http://127.0.0.1:8090
```

Abra a URL HTTPS no celular. Para desfazer:

```bash
sudo tailscale serve reset
```

> **Não use Tailscale Funnel.** Ele publica o app na internet aberta. O `serve` fica restrito à sua tailnet.

### 5.4 Instalar na tela inicial

1. Abra a URL HTTPS no navegador do celular.
2. Use **Compartilhar → Adicionar à Tela de Início**.
3. Abra pelo ícone.
4. Confirme que o app abre em tela cheia.

### 5.5 Verificar o offline

1. Abra o app online e aguarde o service worker instalar.
2. Ative o modo avião ou desligue a VPN.
3. Recarregue: deve aparecer a tela **Sem conexão**.
4. Volte à rede e recarregue.

O shell fica em cache; os dados continuam no servidor.

---

## 6. Operação do dia a dia

### Status e saúde

```bash
docker compose ps
curl http://127.0.0.1:8090/healthz
```

### Logs

```bash
docker compose logs -f --tail=100 app
```

Eventos de autenticação, CSRF, rate limit e expiração de sessão têm prefixos como `auth.login.success`, `auth.login.failure`, `security.csrf_failure` e `security.session_revoked`. Senhas, tokens CSRF, corpo de requisição, query string e e-mail não são registrados.

### Memória e CPU

```bash
docker stats --no-stream prodsuite
```

Baseline esperado: **100–160 MB** de RSS para a aplicação. O limite do Compose é **512 MB**.

### Parar e subir

```bash
docker compose stop
docker compose start
```

### Atualizar

A imagem vem do Docker Hub e o Compose usa `pull_policy: always`.

```bash
docker compose pull
docker compose up -d
docker compose ps
```

Se a imagem for privada, faça login antes:

```bash
docker login
```

O `latest` só é aplicado quando o container é recriado. Para atualização automática em segundo plano, agende o comando acima no cron/Watchtower; o Compose sozinho não fica monitorando o Docker Hub.

### Limpar imagens antigas

```bash
docker image prune -f
```

---

## 7. Backup e restauração

### Pela interface

Abra **Meus dados** e baixe:

- **Cópia organizada** — um arquivo leve com perfil, tarefas, colunas, notas, rascunhos, sessões e revisões.
- **Cópia completa** — uma cópia fiel para guardar, sem a senha.

### Backup frio do volume

O `make backup` para o container, compacta o volume em `./backups` e sobe de novo:

```bash
make backup
ls -lh backups/
```

Procedimento equivalente manual:

```bash
mkdir -p backups
docker compose stop
docker run --rm \
  -v prodsuite_data:/data:ro \
  -v "$PWD/backups:/backup" \
  alpine tar czf /backup/prodsuite-$(date +%F-%H%M).tgz -C /data .
docker compose start
```

### Restaurar o volume

```bash
docker compose stop
docker run --rm \
  -v prodsuite_data:/data \
  -v "$PWD/backups:/backup" \
  alpine sh -c "tar xzf /backup/SEU_ARQUIVO.tgz -C /data && chown -R 10001:10001 /data"
docker compose start
```

### Restaurar uma cópia completa

```bash
docker compose stop
docker run --rm \
  -v prodsuite_data:/data \
  -v "$PWD/backups:/backup" \
  alpine sh -c "cp /backup/arquivo.db /data/prodsuite.db && rm -f /data/prodsuite.db-wal /data/prodsuite.db-shm && chown 10001:10001 /data/prodsuite.db"
docker compose start
```

> Faça backup antes de atualizar. Restaurar dados de versões diferentes pode exigir migração de schema.

### Banco local (fora do Docker)

Quando você roda o app com `flask --app app run`, o banco fica em `instance/prodsuite.db`. **Sair da conta não apaga esse arquivo**; ele só é removido se alguém apagar a pasta `instance/` ou o arquivo manualmente.

Cuidados:

- não rode `rm -rf instance` para “limpar” o projeto;
- não use `git clean -fdx` sem conferir se `instance/` contém dados;
- faça cópias periódicas com `make backup-local`;
- para restaurar, pare o servidor, copie a cópia para `instance/prodsuite.db` e remova `prodsuite.db-wal`/`prodsuite.db-shm` antes de subir de novo.

```bash
make backup-local
ls -lh backups/prodsuite-local-*.db
```

Se a pasta `instance/` já foi apagada, não há como recuperar pelo app; resta criar a conta novamente ou restaurar uma cópia que você tenha guardado.

---

## 8. Teste de fumaça pós-instalação

Execute na ordem. É um runbook de aceitação, não uma prova de carga.

### 8.1 Infraestrutura

- [ ] `docker compose ps` mostra `healthy`.
- [ ] `curl /healthz` retorna `{"status":"ok"}`.
- [ ] `docker stats --no-stream prodsuite` mostra memória abaixo de 512 MB.
- [ ] Os logs não mostram traceback.

### 8.2 Conta e onboarding

- [ ] Criar uma conta nova.
- [ ] O tutorial abre em pop-up por cima do **Meu dia**.
- [ ] O nome exibido é o **nome de perfil**, não o nome de acesso.
- [ ] Fechar pelo **X** ou por **Começar a usar** não repete o tutorial.
- [ ] Sair e entrar novamente não repete o tutorial.

### 8.3 Tarefas e colunas

- [ ] Abrir **Tarefas**; a conta nova deve mostrar **Crie seu primeiro projeto**.
- [ ] Criar um projeto em **Novo projeto**.
- [ ] Confirmar que o projeto novo está vazio, sem colunas prontas.
- [ ] Criar a primeira coluna pelo botão **+ Nova coluna**.
- [ ] Confirmar que o projeto novo não mostra tarefas de outro projeto.
- [ ] Criar uma coluna personalizada em **Colunas → Nova coluna**.
- [ ] Renomear a coluna.
- [ ] Criar uma categoria em **Categorias → Nova categoria**, escolher um ícone e usar a categoria em uma tarefa.
- [ ] Renomear e remover uma categoria, confirmando que as tarefas foram realocadas.
- [ ] Mover a coluna para a esquerda/direita.
- [ ] Criar uma tarefa já dentro da coluna.
- [ ] Arrastar a tarefa para outra coluna no desktop.
- [ ] Trocar a coluna pelo seletor no celular.
- [ ] Marcar uma coluna como **coluna de conclusão** e mover a tarefa para ela; confirmar que ela passa a contar como concluída e que o tempo por coluna aparece nos detalhes.
- [ ] Excluir uma coluna e confirmar que as tarefas foram realocadas.

### 8.4 Planejamento e foco

- [ ] Abrir **Planejar** e marcar três prioridades.
- [ ] Confirmar que uma quarta prioridade é recusada.
- [ ] Abrir **Pomodoro** e escolher uma tarefa.
- [ ] Iniciar o cronômetro e navegar para outra página; ele deve continuar.
- [ ] Tocar em **Testar som** e ouvir o alerta exclusivo do app.
- [ ] Ao final de um ciclo, conferir o som, a faixa de conclusão e o título da aba.

### 8.5 Revisão e dados

- [ ] Salvar uma revisão em **Revisão**.
- [ ] Abrir **Meus dados** e baixar a **Cópia organizada**.
- [ ] Baixar a **Cópia completa**.
- [ ] Alternar tema claro/escuro e recarregar; a preferência deve permanecer.
- [ ] Instalar o PWA no celular por HTTPS e abrir em tela cheia.

### 8.6 Persistência

- [ ] `docker compose restart`.
- [ ] Recarregar o app.
- [ ] Confirmar que tarefas, colunas e revisão continuam lá.

---

## 9. Testes automatizados

```bash
make test
```

Equivalente:

```bash
source .venv/bin/activate
pytest -q
```

Resultado esperado: **104 testes passando**.

Cobertura:

```bash
make coverage
```

A suíte cobre modelos, autenticação, sessões, CSRF, headers, isolamento entre usuários, tarefas, colunas personalizadas, rascunhos, notas/XSS, busca, Pomodoro, planejamento, revisão, onboarding, ajuda, exportação e PWA.

Os testes usam bancos temporários em `tmp_path` e não tocam no banco de produção.

---

## 10. Segurança e privacidade

- Senhas com hash `pbkdf2:sha256`; nunca são exportadas.
- Cookie de sessão `HttpOnly` e `SameSite=Lax`; `Secure` quando `COOKIE_SECURE=true`.
- Expiração de sessão no servidor por inatividade.
- CSRF em formulários e chamadas JSON.
- CSP sem script inline; Bootstrap e ícones são locais.
- Markdown sanitizado antes de renderizar.
- SQLAlchemy/ORM e consultas parametrizadas.
- Rate limit de login por processo.
- Snapshot do banco filtrado por usuário e sem hash de senha.
- Nenhum dado de produção no Git.

**Senha mínima:** o projeto usa 4 caracteres por padrão. Em uma instalação exposta, eleve `PASSWORD_MIN_LENGTH` para 12 ou mais e use um gerenciador de senhas.

**Exposição:** prefira `BIND_ADDR=127.0.0.1` + `tailscale serve`. Não use Funnel sem uma camada de autenticação na frente.

---

## 11. Diagnóstico de problemas

| Sintoma | Verifique | Ação |
| --- | --- | --- |
| Compose reclama de `SECRET_KEY` | `.env` existe? | `cp .env.example .env && make secret` |
| Container `unhealthy` | Logs | `docker compose logs --tail=200 app` |
| Login não persiste em HTTPS | `COOKIE_SECURE` | Coloque `true` e recrie |
| Login não persiste em HTTP | `COOKIE_SECURE` | Coloque `false` no modo HTTP direto |
| PWA não instala | URL | Use HTTPS via `tailscale serve` |
| Offline só mostra “Sem conexão” | Comportamento | Dados exigem o servidor; o shell é offline |
| Porta ocupada | `ss -ltnp \| grep 8090` | Mude `APP_PORT` ou `BIND_ADDR` |
| `APP_PORT=5060` no `.env` | `grep APP_PORT .env` | Use `APP_PORT=8090`; 5060 é bloqueada pelo Firefox |
| `make up` falhou no healthcheck | `docker compose ps` | O comando espera até 90s; veja `docker compose logs app` |
| Registro retorna 403 | `ALLOW_REGISTRATION` | Abra temporariamente ou crie via CLI |
| Tailscale sem HTTPS | Admin console | Habilite MagicDNS e HTTPS certificates |
| Timer estranho após suspensão | iOS/background | O estado se reconcilia por timestamp; recarregue |
| Nota grande retorna 413 | Limite de request | Reduza o conteúdo; limite de 40k caracteres |
| Muitas tentativas de login | Rate limit | Aguarde a janela ou reinicie o processo |

---

## 12. Auditoria antes de publicar

```bash
git status --ignored
git ls-files | grep -Ei '(^|/)(instance|backups)/|(^|/)\.env$|\.(db|sqlite|sqlite3)(-wal|-shm)?$' \
  && echo "REVISE: dados rastreados" \
  || echo "OK: nenhum dado rastreado"
```

Também confirme:

- [ ] `.env` não está no commit.
- [ ] `instance/`, `backups/` e arquivos `*.db` estão ignorados.
- [ ] Nenhum screenshot contém dados reais.
- [ ] `ALLOW_REGISTRATION=false` em produção.
- [ ] `COOKIE_SECURE` corresponde ao modo de acesso.
- [ ] Existe um backup recente do volume.

---

## 13. Mapa técnico

```text
prodsuite/
├── app.py                  # app factory, migração leve, CSP, CLI
├── config.py               # configuração por ambiente
├── extensions.py           # db, login, CSRF
├── models.py               # User, Project, BoardColumn, Category, Task, Note, cycles, review
├── forms.py                # WTForms
├── security.py             # sessão, rate limit, headers, erros
├── routes/
│   ├── auth.py             # entrar, sair, perfil, nome
│   ├── onboarding.py       # tour de contas novas
│   ├── help.py             # ajuda
│   ├── planner.py          # prioridades, matriz, meta
│   ├── review.py           # revisão semanal
│   ├── tasks.py            # tarefas e colunas personalizadas
│   ├── pomodoro.py         # timer e ciclos
│   ├── scratchpad.py       # captura rápida
│   ├── notes.py            # notas e busca
│   ├── dashboard.py        # Meu dia, PWA, healthcheck
│   └── export.py           # cópias dos dados
├── services/
│   ├── boards.py           # projetos, colunas e migração de dados antigos
│   ├── pomodoro.py
│   ├── planning.py
│   ├── notes.py
│   ├── search.py
│   ├── export.py
│   └── timeutils.py
├── templates/              # Jinja
├── static/                 # CSS, JS, ícones, áudio, Bootstrap local
├── docs/images/            # imagens do README
├── tests/test_app.py       # 104 testes
├── Dockerfile
├── docker-compose.yml
├── gunicorn.conf.py
└── .env.example
```

Rotas principais:

| Rota | Função |
| --- | --- |
| `/` | Meu dia |
| `/planejar` | Planejamento diário |
| `/tarefas` | Quadro e colunas |
| `/foco` | Pomodoro |
| `/revisao` | Revisão semanal |
| `/ajuda` | Ajuda |
| `/bem-vindo` | Tour |
| `/perfil` | Conta e aparência |
| `/exportar` | Meus dados |
| `/healthz` | Saúde do container |

---

## 14. Limitações conhecidas

- O Safari suspende JavaScript em segundo plano; o timer se reconcilia ao voltar, mas não dispara som com o app fechado.
- O shell funciona offline; tarefas e notas exigem o servidor acessível.
- O rate limit é por processo, não distribuído.
- Não há 2FA/OIDC nativo; use um proxy autenticado se precisar.
- A migração de schema é leve e idempotente; mudanças grandes merecem Alembic.
- A senha mínima padrão é 4; aumente em produção.

---

**ProdSuite v1.0** — operação simples, decisões explícitas e o seu ritmo.
