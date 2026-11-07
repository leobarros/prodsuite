# Segurança da imagem

## Base

A imagem de produção usa **Chainguard Wolfi, Python 3.13**, fixada por digest no
`Dockerfile`. O runtime não usa `apt` e não mantém `pip`, `setuptools` ou
`wheel`.

## Dependências nativas

O WeasyPrint usa Pango, Cairo, HarfBuzz, Fontconfig, DejaVu, libjpeg e tzdata.
Essas bibliotecas são instaladas pelo `apk` no estágio de build e permanecem
somente quando necessárias ao runtime.

## Scan

```bash
docker build -t prodsuite:1.0 .
make scan
```

O alvo executa Trivy com `HIGH,CRITICAL` e falha se encontrar achados. O cache
fica em `.trivy-cache/` e não é versionado.

## Política de atualização

- Revisar o digest da base Chainguard e as versões Python periodicamente.
- Atualizar dependências Python com teste de PDF e suíte completa.
- Não ignorar achados sem uma justificativa registrada.
- Push, Web Push e notificações continuam exigindo HTTPS em produção.

## Estado verificado

Na verificação de implementação, a imagem anterior baseada em Debian apresentava
**67 HIGH + 1 CRITICAL**. A imagem Chainguard com WeasyPrint 70 e runtime sem
ferramentas de instalação ficou com **0 HIGH + 0 CRITICAL** no Trivy.

O scanner é uma fotografia do banco de vulnerabilidades; deve rodar novamente a
cada atualização de base, dependência ou deploy.
