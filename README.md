# ProdSuite

### Seu dia, mais leve.

**Tarefas, foco, notas e cuidado pessoal em um só lugar.**
O app pessoal e auto-hospedado para quem quer sair do modo automático e voltar a fazer o que importa.

**Menos abas abertas. Menos ruído. Mais intenção.**

**Sua produtividade não precisa de mais uma assinatura. Precisa de um lugar para começar.**

<p align="center">
  <strong>Comece em poucos minutos. Seus dados ficam com você.</strong><br>
  <a href="#instalação">Instalar agora</a> · <a href="#conheça-as-funções">Conhecer os recursos</a>
</p>

![Python](https://img.shields.io/badge/Python-3.13-7c6aa3)
![Flask](https://img.shields.io/badge/Flask-3.0-9e8ab8)
![Docker](https://img.shields.io/badge/Docker-ready-8eb7c6)
![Testes](https://img.shields.io/badge/testes-177%20passando-b98aa4)
![Trivy](https://img.shields.io/badge/Trivy-0%20HIGH%2FCRITICAL-a7d1b0)

![Meu dia no ProdSuite](docs/images/readme-dashboard.webp)

<p align="center"><em>Meu dia: prioridades, foco e próximos passos sem excesso de informação.</em></p>

---

## Índice

- [Por que ProdSuite](#por-que-prodsuite)
- [Conheça as funções](#conheça-as-funções)
- [Primeiros passos](#primeiros-passos)
- [No celular](#no-celular)
- [Instalação](#instalação)
- [Notificações](#notificações)
- [Segurança e operação](#segurança-e-operação)
- [Desenvolvimento](#desenvolvimento)
- [Documentação](#documentação)

---

## Por que ProdSuite

Porque produtividade não deveria significar viver dentro de uma ferramenta.

O ProdSuite reúne o essencial em uma rotina curta e possível:

1. **Escolher** o que importa hoje.
2. **Focar** em uma coisa por vez.
3. **Guardar** o que não pode ser esquecido.
4. **Cuidar** do corpo e do humor.
5. **Revisar** o que funcionou.

Sem feed infinito, sem ranking, sem cobrança e sem transformar sua vida em uma planilha.

**Você não precisa organizar tudo. Só precisa começar pelo próximo passo.**

Se você tem cinco minutos, use o Pomodoro. Se tem uma ideia, capture. Se tem uma semana, revise. O restante o app guarda para você.

[Quero começar agora](#instalação)

---

## Conheça as funções

### Meu dia

A tela inicial mostra o que precisa da sua atenção agora:

- próximas tarefas e prioridades do dia;
- andamento do foco na semana;
- captura rápida para não perder uma ideia;
- notas recentes;
- prazos próximos.

![Meu dia](docs/images/readme-dashboard.webp)

### Tarefas

Um quadro com as colunas que fizerem sentido para você.

- crie quantos projetos quiser;
- organize tarefas em colunas personalizadas;
- arraste cartões para mudar o estágio;
- defina prazo e estimativa só quando fizer sentido; o prazo pode ficar em branco;
- anexe arquivos ou cole/arraste um print diretamente na tarefa;
- marque uma coluna como conclusão para fechar o ciclo.

![Tarefas em um quadro personalizado](docs/images/readme-tasks.webp)

### Planejar

Planeje um dia possível, não um dia ideal.

- escolha até três prioridades;
- distribua tarefas por esforço;
- use a matriz de urgência e importância;
- veja os blocos planejados para hoje;
- identifique tarefas rápidas.

![Planejamento do dia](docs/images/readme-planner.webp)

### Pomodoro

Foco com começo, pausa e fim.

- ciclos de foco, pausa curta e pausa longa;
- escolha a tarefa antes de começar;
- o timer continua enquanto você navega;
- som e notificação ao terminar;
- as pausas fazem parte do método;

![Pomodoro](docs/images/readme-focus.webp)

### Caixa de entrada

O lugar para o que ainda não precisa virar tarefa, nota ou obrigação.

- capture em segundos, sem projeto, prazo ou prioridade;
- decida depois: **virar tarefa**, **virar nota**, **Talvez**, **Feito** ou **soltar**;
- use **Decidir um por um** para esvaziar a cabeça no modo foco;
- itens de **Talvez** descansam fora da fila de decisão;
- o que foi resolvido continua consultável em **Resolvidas**.

![Caixa de entrada](docs/images/readme-scratchpad.webp)

![Modo foco da caixa de entrada](docs/images/readme-inbox-focus.webp)

### Notas

Um espaço para ideias que merecem continuar.

- escrita em Markdown e prévia renderizada no mesmo espaço;
- listas e links;
- links entre notas com `[[outra nota]]`, abertos em nova aba;
- busca no conteúdo;
- tags na lateral para filtrar notas e seguir uma linha de pensamento;
- compartilhe a nota com formatação para Teams ou outro chat;
- copie blocos de código sem as cercas de Markdown.

![Notas](docs/images/readme-notes.webp)

### Hidratação

Registre água e outras bebidas sem tratar tudo como água.

- água, café coado, espresso, chá, cerveja, vinho, destilado e outras bebidas;
- meta de hidratação calculada pelo peso;
- barra líquida com a participação de cada bebida;
- compensação alcoólica estimada;
- histórico recente e visão semanal.

O resultado é uma **estimativa**, não uma prescrição médica.

![Hidratação](docs/images/readme-hydration.webp)

### Humor

Um check-in curto para perceber padrões.

- humor, energia e tensão em escalas de 1 a 5;
- contextos como sono, trabalho, estudos, relações, corpo e família;
- radar de frequência e contexto;
- comparação com a semana anterior;
- análise de impacto com médias de humor, energia e tensão por contexto.

![Check-in de humor](docs/images/readme-mood.webp)

![Análise de impacto dos contextos](docs/images/readme-mood-impact.webp)

### Revisão

No fim da semana, o app vira uma conversa curta com você mesmo. A revisão pode ser completada ou ajustada mesmo depois que a semana foi encerrada; o relatório e o arquivamento continuam como registro; tarefas concluídas são arquivadas automaticamente quando a semana vira.

Três perguntas:

- O que funcionou?
- O que foi difícil?
- Qual é o foco da próxima semana?

![Revisão semanal](docs/images/readme-review.webp)

### Relatório

Uma leitura dos seus dados, sem transformar a semana em uma nota.

- foco e tarefas por dia;
- água e outras bebidas;
- humor e contextos;
- comparação com a semana anterior;
- download em PDF.

![Relatório semanal](docs/images/readme-report.webp)

### TUI beta

Existe uma versão local em terminal, separada do app web e sem Docker:

```bash
curl -fsSL https://raw.githubusercontent.com/leobarros/prodsuite/main/tui/install.py -o /tmp/prodsuite-tui-install.py
python3 /tmp/prodsuite-tui-install.py
prodsuite-tui
```

O instalador detecta Linux/Debian, macOS e Windows, cria um ambiente isolado e
usa um banco SQLite local. Veja [tui/README.md](tui/README.md).

## Notificações

Lembretes discretos para a rotina:

- check-in de humor antes do fim do expediente;
- revisão semanal;
- prazos de tarefas;
- horário silencioso configurável;
- central interna e histórico.

O sino ao lado do perfil mostra as notificações das últimas 2 horas.

![Central de notificações](docs/images/readme-notifications.webp)

### Perfil e preferências

Cada pessoa configura o próprio ritmo:

- fuso horário;
- semana e horário de trabalho;
- notificações;
- tema;
- segurança da conta;
- exportação dos próprios dados.

![Perfil](docs/images/readme-profile.webp)

---

## Primeiros passos

### 1. Crie sua conta

Abra o app, informe como quer ser chamado e crie seu acesso. O nome de perfil aparece nas boas-vindas; o usuário de acesso serve para entrar.

### 2. Crie um projeto e suas colunas

Abra **Tarefas** e crie o primeiro projeto. Depois crie as colunas que representam seu fluxo: ideias, esta semana, em andamento, concluídas — ou qualquer nome que funcione para você.

### 3. Coloque uma tarefa no lugar

Adicione uma tarefa com título claro. Prazo, categoria, prioridade e estimativa são opcionais.

### 4. Escolha o essencial

Abra **Planejar** e marque até três prioridades do dia. O resto pode esperar.

### 5. Faça um bloco de foco

Abra **Pomodoro**, escolha uma tarefa e comece. Quando o ciclo terminar, faça a pausa de verdade.

### 6. Registre o dia

Use **Hidratação** e **Humor** para registrar o que o corpo e a cabeça pedirem. Não precisa preencher tudo.

### 7. Feche a semana

Abra **Revisão**, responda às três perguntas e consulte o **Relatório** para enxergar o que mudou.

---

## No celular

O ProdSuite é instalável como PWA:

- abra o endereço HTTPS no navegador do celular;
- use **Adicionar à Tela de Início**;
- o app abre sem a barra do navegador;
- a navegação inferior mantém o essencial por perto.

Para instalar e usar Web Push, o endereço precisa ser **HTTPS**. Veja [docs/HTTPS.md](docs/HTTPS.md).

---

## Instalação

### Comece em minutos, só com a imagem

Você não precisa baixar o projeto, instalar Python ou montar um ambiente de
desenvolvimento. Só precisa de Docker ou Podman e um lugar para chamar de seu.

Pré-requisitos: Docker 24+ **ou** Podman 4+, com pelo menos 512 MB de memória
disponível para o container. A imagem é `nickolback/prodsuite:latest`.

Crie uma vez o arquivo de segredo local, fora do projeto:

```bash
mkdir -p "$HOME/.config/prodsuite"
umask 077
printf 'SECRET_KEY=%s\nAPP_TIMEZONE=America/Sao_Paulo\n' \
  "$(openssl rand -hex 32)" > "$HOME/.config/prodsuite/prodsuite.env"
chmod 600 "$HOME/.config/prodsuite/prodsuite.env"
```

Se `openssl` não estiver disponível, gere a chave com:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

e grave o valor em `SECRET_KEY=` no arquivo acima.

#### Docker

```bash
docker volume create prodsuite_data

docker run -d --name prodsuite --init --restart unless-stopped \
  --memory=512m --memory-swap=512m \
  --publish 127.0.0.1:8090:5000 \
  --env-file "$HOME/.config/prodsuite/prodsuite.env" \
  --volume prodsuite_data:/data \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --security-opt no-new-privileges --cap-drop ALL \
  nickolback/prodsuite:latest
```

#### Podman

```bash
podman volume create prodsuite_data

podman run -d --name prodsuite --init --restart unless-stopped \
  --memory=512m --memory-swap=512m \
  --publish 127.0.0.1:8090:5000 \
  --env-file "$HOME/.config/prodsuite/prodsuite.env" \
  --volume prodsuite_data:/data \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --security-opt no-new-privileges --cap-drop ALL \
  docker.io/nickolback/prodsuite:latest
```

Abra **http://127.0.0.1:8090** e crie o primeiro usuário:

> **Usa proxy?** Se a sua rede exige proxy, inclua `localhost`, `127.0.0.1` e
> `::1` nas exceções — ou defina `NO_PROXY`/`no_proxy` no seu usuário:
>
> ```powershell
> [Environment]::SetEnvironmentVariable(
>   "NO_PROXY", "localhost,127.0.0.1,::1", "User"
> )
> [Environment]::SetEnvironmentVariable(
>   "no_proxy", "localhost,127.0.0.1,::1", "User"
> )
> ```
>
> Reinicie o navegador ou o app depois de alterar a variável.


```bash
# Docker
docker exec -it prodsuite flask --app app create-user

# Podman
podman exec -it prodsuite flask --app app create-user
```

O limite de memória pode ser conferido com:

```bash
# Docker — deve mostrar 536870912 bytes
docker inspect -f '{{.HostConfig.Memory}}' prodsuite

# Podman — deve mostrar 536870912 bytes
podman inspect -f '{{.HostConfig.Memory}}' prodsuite
```

Para atualizar, baixe a nova imagem e recrie somente o container. O volume
`prodsuite_data` e o arquivo de segredo são preservados:

```bash
# Docker
docker pull nickolback/prodsuite:latest
docker rm -f prodsuite
# repita o comando docker run acima

# Podman
podman pull docker.io/nickolback/prodsuite:latest
podman rm -f prodsuite
# repita o comando podman run acima
```

Não é necessário instalar Python, criar ambiente virtual, rodar `pip` ou
baixar este repositório. A aplicação, o banco SQLite e os uploads ficam no
volume persistente; a porta 8090 é exposta apenas em `127.0.0.1`.

### Com Docker

Requisitos: Docker 24+ com Compose v2 e cerca de 512 MB de memória.

```bash
git clone https://github.com/leobarros/prodsuite.git
cd prodsuite
cp .env.example .env
make secret
docker compose pull
docker compose up -d --wait
docker compose ps
```

Abra:

```text
http://localhost:8090
```

Para criar a primeira conta pelo terminal:

```bash
docker compose exec app flask --app app create-user
```

Depois de criar sua conta, feche o registro:

```env
ALLOW_REGISTRATION=false
```

```bash
docker compose up -d --force-recreate
```

Verificação rápida:

```bash
curl http://127.0.0.1:8090/healthz
# {"status":"ok"}
```

### Build local

```bash
docker build -t nickolback/prodsuite:latest .
docker compose up -d --force-recreate --pull never
```

### Desenvolvimento

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
flask --app app init-db
flask --app app run --debug
```

Testes:

```bash
pytest -q
# 177 testes
```

O banco local fica em `instance/prodsuite.db` e não é apagado ao sair da conta.

---

## Notificações

As notificações são configuradas em **Perfil → Notificações**.

O check-in de humor é calculado **30 minutos antes do fim do expediente**. A semana de trabalho é configurável, incluindo sábado e domingo para quem trabalha nesses dias.

Para Web Push com o app fechado:

1. configure `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` e `VAPID_SUBJECT`;
2. acesse por HTTPS;
3. ative o push no dispositivo;
4. execute o agendador periodicamente:

```bash
docker compose exec -T app flask --app app notifications-run
```

O agendador respeita o fuso de cada usuário, o horário silencioso e evita duplicidades.

---

## Privacidade por padrão

O ProdSuite é um app **pessoal** de desenvolvimento, foco e metas — não uma
ferramenta de colaboração. Cada conta tem seu próprio board, tarefas, notas,
caixa de entrada, revisão, Pomodoro e métricas.

- não há quadro compartilhado, convite de equipe ou comentário público;
- não há link público de tarefa ou nota;
- compartilhar uma nota copia o conteúdo para o chat escolhido, sem criar
  acesso ao app para outras pessoas;
- multiusuário significa contas isoladas no mesmo servidor, não um workspace
  compartilhado.

## Segurança e operação

- Imagem Docker compatível com x86-64 baseline.
- Runtime sem `pip`, `setuptools` ou `wheel`.
- WeasyPrint atualizado para geração segura do PDF.
- Trivy sem achados **HIGH/CRITICAL** na verificação atual:

```bash
make scan
```

- Dados ficam no volume Docker `prodsuite_data`.
- O relatório e o PDF são privados.
- Notas íntimas não entram no relatório.
- Backup frio:

```bash
make backup
```

- Backup do banco local:

```bash
make backup-local
```

Mais detalhes:

- [Runbook de operação](docs/RUNBOOK.md)
- [Segurança da imagem](docs/SECURITY.md)
- [Compatibilidade de CPU](docs/CPU_COMPATIBILITY.md)
- [HTTPS local e Docker](docs/HTTPS.md)

### Stack

- Python 3.13 + Flask 3
- SQLAlchemy + SQLite em WAL
- Gunicorn `gthread`
- Bootstrap local + CSS/JS próprios
- PWA com Service Worker
- WeasyPrint para PDF
- Web Push para notificações

---

## Documentação

| Documento | Conteúdo |
|---|---|
| [RUNBOOK](docs/RUNBOOK.md) | Instalação, atualização, backup, HTTPS, Tailscale, diagnóstico |
| [HTTPS](docs/HTTPS.md) | mkcert, Caddy local e Tailscale Serve |
| [SECURITY](docs/SECURITY.md) | Imagem, scan Trivy e política de atualização |
| [CPU_COMPATIBILITY](docs/CPU_COMPATIBILITY.md) | Requisitos para homelabs com CPUs antigas |
| [DESIGN_SYSTEM](docs/DESIGN_SYSTEM.md) | Tokens, componentes e regras visuais |

---

## O próximo passo é seu

Você não precisa de uma vida perfeita. Precisa de um lugar para começar, um foco por vez e a liberdade de parar quando for hora.

O ProdSuite não tenta preencher cada minuto do dia. Ele deixa espaço para o que importa.

**Sem assinatura. Sem feed. Sem ruído. Seus dados ficam com você.**

<p align="center"><a href="#instalação"><strong>Instalar o ProdSuite agora</strong></a></p>

**ProdSuite v1.0**
Feito para o seu dia a dia e o seu ritmo.
