# Compatibilidade de CPU do homelab

## Alvo mínimo

O homelab principal usa:

```text
AMD A4-3305M APU with Radeon HD Graphics
```

Essa CPU é **x86-64 baseline** e não possui:

- SSE4.2
- AVX
- AVX2

## Regra para imagens publicadas

A imagem `nickolback/prodsuite` deve rodar nessa CPU. Não publicar imagens
compiladas com `-march=native`, x86-64-v2, x86-64-v3 ou instruções AVX.

Bases que exigem SSE4.2 podem iniciar o shell e falhar no Python com:

```text
ExitCode: 132  → SIGILL (instrução ilegal)
```

## Base atual

- Alpine Python 3.13, compatível com x86-64 baseline.
- WeasyPrint 70 e pydyf 0.13.
- UID/GID 10001.
- Sem `pip`, `setuptools` ou `wheel` no runtime.

A base Chainguard/Wolfi foi testada e falhou neste homelab com SIGILL. Ela pode
ser usada apenas em hosts com CPU que suporte SSE4.2.

## Teste antes de publicar

Na máquina de build:

```bash
docker build -t nickolback/prodsuite:latest .
docker run --rm --entrypoint python nickolback/prodsuite:latest -c 'print("python ok")'
```

No homelab, após o pull:

```bash
docker inspect -f 'exit={{.State.ExitCode}} restarts={{.RestartCount}}' prodsuite
docker logs --tail 50 prodsuite
curl http://127.0.0.1:8090/healthz
```

O esperado é `exit=0`, sem reinícios, e `{"status":"ok"}`.

## Fallback

Se uma base nova falhar com `exit 132`, testar imediatamente:

```dockerfile
FROM python:3.11-slim
```

Essa base já rodou no homelab, mas tem mais vulnerabilidades conhecidas. O
fallback é temporário; a meta é manter uma base compatível e com o menor número
possível de CVEs.
