# Instruções para agentes neste repositório

## Contrato de validação

Nenhuma alteração é considerada concluída apenas porque o código parece correto.
Antes de responder ao usuário:

1. Rode a suíte completa no ambiente local:
   ```bash
   .venv/bin/python -m pytest -q
   ```
2. Reconstrua uma imagem de teste com tag temporária e única:
   ```bash
   TEST_IMAGE="prodsuite:test-$(date +%s)"
   docker build -t "$TEST_IMAGE" .
   ```
3. Valide a aplicação dentro dessa imagem, não apenas no host. Quando a mudança
   tocar rotas, links, relatório ou PDF, faça um smoke test no container com
   banco e volume temporários e confirme status HTTP, links e geração de PDF.
4. Verifique que rotas, menus e links internos continuam válidos.
5. Atualize a contagem de testes na documentação quando ela mudar.
6. Incremente `CACHE_VERSION` em `static/sw.js` quando assets estáticos mudarem.

Local e Docker são obrigatórios. Se uma etapa falhar, não finalize a entrega sem
explicar o bloqueio real.

7. Quando o usuário solicitar uma implementação, depois de concluir e validar
   localmente e no Docker, crie o commit automaticamente. Use uma mensagem
   objetiva em português. Em seguida, faça push para `origin/main` sem force.
   Não peça permissão adicional para commit ou push.

## Limpeza obrigatória de testes em containers

- Todo teste em Docker/Podman deve usar nomes exclusivos e temporários para
  container, volume, rede, portas e imagem.
- Ao terminar — inclusive quando o teste falhar — remova o container, o volume,
  a rede, os diretórios temporários e os logs criados.
- Prefira `--rm` e `trap` de limpeza. Não deixe containers parados.
- Imagens: não acumule tags. É aceitável manter a imagem de produção e, no
  máximo, uma imagem local reutilizável; remova imagens de teste antigas ou
  órfãs. Se a validação exigir uma imagem temporária, use uma tag única e
  remova-a ao final, salvo pedido explícito para mantê-la.
- Nunca remova os recursos de produção: container `prodsuite`, volume
  `prodsuite_data`, imagem `nickolback/prodsuite:latest`, `instance/` ou
  `backups/`.
- Antes de finalizar, confirme com `docker ps -a`, `docker volume ls` e
  `docker images`; caches de navegador/scan usados só no teste também devem ser
  removidos.

## Segurança e dados

- Não apague `instance/` nem `backups/`.
- Nunca exponha senhas, `SECRET_KEY`, tokens CSRF, query strings sensíveis ou
  corpos de requisição em logs/respostas.
- O relatório e o PDF são privados: não inclua notas íntimas nem diagnósticos.

## Produto

- O ProdSuite é pessoal, não corporativo. Não crie quadros compartilhados,
  colaboração em tempo real, convites de equipe, comentários públicos ou links
  públicos de tarefas/notas.
- "Multiusuário" significa contas isoladas no mesmo servidor, não um workspace
  de equipe. Todo dado (board, tarefas, notas, caixa de entrada, revisão,
  Pomodoro e métricas) é privado do respectivo usuário.
- Compartilhar uma nota é uma exportação iniciada pelo usuário (clipboard);
  não criar link público ou acesso compartilhado no app.
- A interface é em português.
- Não transporte frases do chat literalmente para a interface. Reescreva em
  microcopy curta, profissional e consistente com o produto; se a informação
  vier do usuário, adapte o sentido sem copiar o tom da conversa.
- `Relatório` = dados e leitura; `Revisão` = decisões e fechamento da semana.
  Não duplique gráficos na revisão.


## Pomodoro: regressão obrigatória

- Qualquer mudança em `pomodoro.js`, `focus.html`, rotas/serviços de timer,
  ciclos, áudio ou cache do PWA exige o protocolo completo em
  `docs/POMODORO.md`.
- Validar sempre start, pause, resume, reset, modos 25/5/20, conclusão,
  pausa longa diária, áudio, notificações, persistência e o fluxo no Docker.
- Não considerar a mudança concluída apenas porque o arquivo alterado
  funciona isoladamente.

## Compatibilidade de runtime

- Imagens publicadas devem rodar em **x86-64 baseline**. O homelab alvo é um
  AMD A4-3305M sem SSE4.2/AVX; detalhes em `docs/CPU_COMPATIBILITY.md`.
- Antes de publicar, teste o binário Python da imagem no homelab. `exit 132`
  (SIGILL) indica base compilada para CPU mais nova.
- Não use `-march=native` em imagens publicadas.

## Design system

- Siga `docs/DESIGN_SYSTEM.md` e os componentes/tokens de `static/css/theme.css`.
- Toda mudança visual deve ser validada nos temas claro e escuro, além de
  contraste, foco, estados vazios, hover e responsividade.
- Não introduza cores literais em superfícies, textos, bordas ou botões web.
  Use tokens. PDF e ilustrações têm exceções documentadas.
- Relatório = dados; Revisão = decisões. Não duplique gráficos na revisão.
- Toda métrica ou dado registrado/exibido no app deve ter representação no
  relatório semanal web e no PDF. Inclua comparação com período anterior quando
  isso ajudar a leitura. Não crie dados órfãos no relatório.
- Botões: 34 px de altura, cantos arredondados e largura automática pelo
  conteúdo. Não crie alturas/larguras fixas por tela sem justificativa.
