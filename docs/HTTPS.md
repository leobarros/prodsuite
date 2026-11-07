# HTTPS local e no Docker

## 1. Certificado local

O projeto exige `mkcert` para criar uma CA local confiável. O fallback
autoassinado foi removido de propósito, porque o Firefox sempre exibirá aviso
de segurança nesse caso.

```bash
# Ubuntu/Debian
sudo apt install mkcert libnss3-tools
mkcert -install
make certs
```

Para incluir o IP da sua máquina na LAN:

```bash
EXTRA_HOST=192.168.1.20 make certs
```

Se você gerou um certificado autoassinado anteriormente, remova-o antes:

```bash
rm -rf certs
make certs
```

Depois de gerar, reinicie o Firefox. A CA fica em:

```bash
mkcert -CAROOT
```

Se o `mkcert -install` não alcançar o perfil do Firefox, importe
`$(mkcert -CAROOT)/rootCA.pem` manualmente em **Configurações → Privacidade e
segurança → Certificados → Autoridades**.

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
