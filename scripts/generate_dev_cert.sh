#!/usr/bin/env bash
# Gera certificado local confiável. Requer mkcert e certutil (NSS).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="$ROOT/certs"
mkdir -p "$CERT_DIR"

if ! command -v mkcert >/dev/null 2>&1; then
  cat >&2 <<'MSG'
mkcert não encontrado.

Para evitar o aviso de certificado não confiável no Firefox:
  sudo apt install mkcert libnss3-tools
  mkcert -install
  make certs

O fallback autoassinado foi removido de propósito: ele sempre exibe aviso
de segurança no navegador e não serve para PWA/Web Push confiável.
MSG
  exit 1
fi

HOSTS=(localhost 127.0.0.1 ::1)
if [[ -n "${EXTRA_HOST:-}" ]]; then
  HOSTS+=("$EXTRA_HOST")
fi

mkcert -install >/dev/null 2>&1 || true
mkcert -cert-file "$CERT_DIR/local.pem" -key-file "$CERT_DIR/local-key.pem" "${HOSTS[@]}"
chmod 600 "$CERT_DIR/local-key.pem"

echo "Certificado confiável gerado em certs/."
echo "CA local: $(mkcert -CAROOT)/rootCA.pem"
