#!/usr/bin/env bash
# Gera certificado local para HTTPS. mkcert é preferível (CA confiável).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="$ROOT/certs"
mkdir -p "$CERT_DIR"

HOSTS=(localhost 127.0.0.1 ::1)
if [[ -n "${EXTRA_HOST:-}" ]]; then
  HOSTS+=("$EXTRA_HOST")
fi

if command -v mkcert >/dev/null 2>&1; then
  mkcert -install >/dev/null 2>&1 || true
  mkcert -cert-file "$CERT_DIR/local.pem" -key-file "$CERT_DIR/local-key.pem" "${HOSTS[@]}"
  echo "Certificado mkcert gerado em certs/."
else
  openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
    -keyout "$CERT_DIR/local-key.pem" \
    -out "$CERT_DIR/local.pem" \
    -subj "/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" >/dev/null 2>&1
  echo "mkcert não encontrado; certificado autoassinado gerado em certs/."
  echo "O navegador exibirá aviso de CA. Instale mkcert para evitar o aviso."
fi

chmod 600 "$CERT_DIR/local-key.pem"
