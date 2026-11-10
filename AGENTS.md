# Instruções para agentes neste repositório

## Contrato de validação

Nenhuma alteração é considerada concluída apenas porque o código parece correto.
Antes de responder ao usuário:

1. Rode a suíte completa no ambiente local:
   ```bash
   .venv/bin/python -m pytest -q
   ```
2. Reconstrua a imagem Docker:
   ```bash
   docker build -t prodsuite:1.0 .
   ```
3. Valide a aplicação dentro da imagem, não apenas no host. Quando a mudança
   tocar rotas, links, relatório ou PDF, faça um smoke test no container com
   banco temporário e confirme status HTTP, links e geração de PDF.
4. Verifique que rotas, menus e links internos continuam válidos.
5. Atualize a contagem de testes na documentação quando ela mudar.
6. Incremente `CACHE_VERSION` em `static/sw.js` quando assets estáticos mudarem.

Local e Docker são obrigatórios. Se uma etapa falhar, não finalize a entrega sem
explicar o bloqueio real.

7. Quando o usuário solicitar uma implementação, depois de concluir e validar
   localmente e no Docker, crie o commit automaticamente. Use uma mensagem
   objetiva em português. Em seguida, faça push para `origin/main` sem force.
   Não peça permissão adicional para commit ou push.

## Segurança e dados

- Não apague `instance/` nem `backups/`.
- Nunca exponha senhas, `SECRET_KEY`, tokens CSRF, query strings sensíveis ou
  corpos de requisição em logs/respostas.
- O relatório e o PDF são privados: não inclua notas íntimas nem diagnósticos.

## Produto

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
