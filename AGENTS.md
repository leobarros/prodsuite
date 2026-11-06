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
   objetiva em português. Não peça permissão adicional para o commit e não faça
   push sem pedido explícito.

## Segurança e dados

- Não apague `instance/` nem `backups/`.
- Nunca exponha senhas, `SECRET_KEY`, tokens CSRF, query strings sensíveis ou
  corpos de requisição em logs/respostas.
- O relatório e o PDF são privados: não inclua notas íntimas nem diagnósticos.

## Produto

- A interface é em português.
- `Relatório` = dados e leitura; `Revisão` = decisões e fechamento da semana.
  Não duplique gráficos na revisão.


## Design system

- Siga `docs/DESIGN_SYSTEM.md` e os componentes/tokens de `static/css/theme.css`.
- Toda mudança visual deve ser validada nos temas claro e escuro, além de
  contraste, foco, estados vazios, hover e responsividade.
- Não introduza cores literais em superfícies, textos, bordas ou botões web.
  Use tokens. PDF e ilustrações têm exceções documentadas.
- Relatório = dados; Revisão = decisões. Não duplique gráficos na revisão.
- Botões: 34 px de altura, cantos arredondados e largura automática pelo
  conteúdo. Não crie alturas/larguras fixas por tela sem justificativa.
