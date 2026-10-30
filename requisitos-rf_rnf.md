# Requisitos não funcionais e funcionais

---

## 1. Requisitos Funcionais (RF)

### RF01 — Autenticação e Gestão de Usuários

* **RF01.1 — Login e Cadastro:** Registro e autenticação de usuários com nome de usuário, e-mail e senha.
* **RF01.2 — Expiração de Sessão:** A sessão do usuário expira após **30 minutos de inatividade** (configurado via `PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)` no Flask).
* **RF01.3 — Gestão de Perfil:** Troca de senha e encerramento manual de sessões ativas (logout).

### RF02 — Módulo de Foco (Timer / Pomodoro Integrado)

* **RF02.1 — Timer Configurável:** Temporizador de Foco (Pomodoro), Pausa Curtas e Pausa Longas.
* **RF02.2 — Vinculação de Tarefa:** Permitir iniciar um Pomodoro diretamente atrelado a uma tarefa específica.
* **RF02.3 — Histórico e Métricas:** Registrar automaticamente ciclos concluídos com tempo total dedicado a cada projeto/tag.

### RF03 — Módulo de Captura Rápida (Scratchpad / Quick Notes)

* **RF03.1 — Captura Instantânea:** Modal ou painel com atalho global para rascunhar ideias sem mudar de página.
* **RF03.2 — Conversão em Tarefa:** Botão direto para transformar um rascunho de nota em uma tarefa no Kanban/Lista.

### RF04 — Módulo de Tarefas (Kanban & To-Do)

* **RF04.1 — Gestão de Status:** Organização por estados (*A Fazer*, *Em Progresso*, *Concluído*).
* **RF04.2 — Metadados de Tarefa:** Suporte a prioridades, estimativa de Pomodoros, data de entrega e tags.

### RF05 — Módulo PKM (Gestão de Conhecimento e Documentos)

* **RF05.1 — Editor Markdown:** Criação de notas longas com visualização em tempo real e suporte a links internos.
* **RF05.2 — Busca Global:** Campo de busca rápida indexando notas, rascunhos e tarefas.

---

## 2. Requisitos Não Funcionais (RNF)

### RNF01 — Performance e Uso de Memória

* **RNF01.1 — Pegada de Memória (≤ 512 MB RAM):**
* Backend leve rodando Flask em produção via **Gunicorn** com *gevent* ou múltiplos workers otimizados (ex: 2 workers consomem ~80-120 MB RAM).
* Banco de dados leve baseado em **SQLite**, garantindo I/O direto em disco com baixíssimo consumo de memória.

* **RNF01.2 — Tempo de Resposta:** Páginas renderizadas e rotas de API devem responder em menos de 100ms.

### RNF02 — Segurança

* **RNF02.1 — Armazenamento de Senhas:** Criptografia e hashing seguro de senhas via `pbkdf2:sha256` ou `bcrypt` (`Werkzeug.security`).
* **RNF02.2 — Proteção CSRF & XSS:**
* Proteção CSRF ativada em todos os formulários (`Flask-WTF` / `WTForms`).
* Higienização de inputs e auto-escape nativo do Jinja2 para prevenir XSS.

* **RNF02.3 — Prevenção a SQL Injection:** Consultas parametrizadas obrigatórias utilizando ORM (SQLAlchemy / Peewee) ou rotas parametrizadas em SQLite.
* **RNF02.4 — Headers de Segurança:** Configuração de diretivas HTTPS (caso atrás de proxy reverso) e cookies seguros (`SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE='Lax'`).

### RNF03 — Testabilidade & Qualidade de Código (TDD)

* **RNF03.1 — Suíte de Testes Automatizada:** **Nenhuma alteração ou nova funcionalidade é implantada sem testes prévios**.
* **RNF03.2 — Cobertura (Pytest / Unittest):** Cobertura obrigatória para rotas de autenticação, expiração de sessão, operações de banco de dados e regras de negócio dos Pomodoros/Tarefas.

### RNF04 — Frontend, Arquitetura Visual e Ativos Locais

* **RNF04.1 — Dependências Locais sem CDN:**
* Bootstrap 5 e Bootstrap Icons armazenados e servidos estaticamente via repositório local (`/static/vendor/bootstrap/` e `/static/vendor/bootstrap-icons/`).
* Sem requisições a serviços/CDNs externos.

* **RNF04.2 — Identidade Visual Distinta & Disruptiva:**
* **Conceito Visual ("Cyber-Minimalist Command Dashboard"):** Fugir do padrão "painel branco corporativo". Uso de paleta *Dark Mode* profunda com contrastes neons sutis (âmbar, ciano ou esmeralda), tipografia monospace para dados do timer e cantos levemente facetados.
* **Widgets Flutuantes e HUD:** O Timer Pomodoro deve funcionar como um componente fixo no estilo HUD (*Heads-Up Display*), visível em qualquer seção da aplicação.
* **Layout Bento Grid:** Organização dos módulos na tela principal no formato *Bento Grid* assimétrico, garantindo apelo estético sem poluição visual.

---

### Visão Geral do Consumo de Recursos (Inbound/Memory Baseline)

```shell
+--------------------------------------------------------+
|                      512 MB RAM                        |
+--------------------------+-----------------------------+
| Gunicorn / Flask App     | ~90 MB - 130 MB             |
| SQLite In-Memory Cache   | ~20 MB                      |
| Sistema Operacional/OS   | ~120 MB - 180 MB            |
| Folga / Peak Overhead    | ~180 MB (Segurança)         |
+--------------------------+-----------------------------+

```
