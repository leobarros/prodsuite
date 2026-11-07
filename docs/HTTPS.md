# HTTPS local e no Docker

## 1. Certificado local

O projeto usa `mkcert` quando disponível. Ele cria uma CA local confiável no
navegador:

```bash
# Ubuntu/Debian (exemplo)
sudo apt install mkcert
make certs
```

Para incluir o IP da sua máquina na LAN:

```bash
EXTRA_HOST=192.168.1.20 make certs
```

Sem `mkcert`, o script gera um certificado autoassinado e o navegador exibirá
um aviso. Não use esse fallback para PWA em produção.

## 2. Flask local em HTTPS

```bash
make run-https
```

Abra `https://localhost:5001`. O alvo ativa `COOKIE_SECURE=true` e usa os
certificados de `certs/`.

## 3. Docker com Caddy

O `docker-compose.https.yml` adiciona um Caddy na frente do app:

```bash
make certs
docker compose -f docker-compose.yml -f docker-compose.https.yml up -d --wait
```

Abra `https://localhost:8443`.

O app continua recebendo HTTP somente na rede interna; o Caddy termina TLS e
envia `X-Forwarded-Proto`. `COOKIE_SECURE` e `PREFERRED_URL_SCHEME` são
ativados no override.

Para outro host/IP:

```bash
EXTRA_HOST=192.168.1.20 make certs
docker compose -f docker-compose.yml -f docker-compose.https.yml up -d --wait
```

## 4. Celular

Para instalar o PWA no celular com HTTPS:

1. gere o certificado incluindo o IP da máquina;
2. instale a CA do mkcert no celular;
3. acesse `https://IP:8443`.

Sem a CA instalada no celular, o navegador mostrará aviso de certificado.

## 5. Produção

Para acesso externo, prefira um proxy com certificado público ou Tailscale
HTTPS. Não exponha o Caddy local diretamente na Internet sem uma camada de
autenticação e firewall.
