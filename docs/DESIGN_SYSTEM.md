# Design system do ProdSuite

## Fonte da verdade

Os tokens e componentes existentes ficam em `static/css/theme.css` e
`static/css/app.css`. Nenhuma tela nova deve criar uma linguagem visual paralela.

## Contrato para mudanças de interface

1. Reutilize os componentes existentes: `page-head`, `bento-card`, `btn`,
   `form-control`, `chip`, `card-head`, `card-title`, `empty-state`, `icon-btn`.
2. Use os tokens de tema em vez de cores literais:
   `--bg-0`, `--bg-1`, `--panel`, `--panel-2`, `--line`, `--line-strong`,
   `--text`, `--muted`, `--dim`, `--emerald`, `--emerald-dim`, `--cyan`,
   `--amber`, `--green`, `--coral`, `--surface`, `--surface-soft`.
3. Não use `#fff`, `#000` ou cores fixas para superfícies, textos, bordas e
   estados de componentes web. Se precisar de uma cor semântica nova, crie um
   token nos dois temas.
4. Preserve foco visível, contraste, estados vazios, hover, disabled e
   responsividade.
5. Toda alteração visual deve ser conferida em **tema claro e tema escuro**.
6. Gráficos e relatórios devem usar os mesmos tokens dos cards e textos.

## Exceções

- `templates/report_pdf.html` tem paleta própria para impressão. O PDF não
  segue o tema da tela: ele é um documento A4 independente.
- Ilustrações SVG, como o copo de água, podem ter cores próprias para representar
  o objeto, mas precisam de ajustes específicos nos dois temas.
- Cores de dados em gráficos podem usar os tokens semânticos ou a paleta já
  definida no componente, nunca cores soltas na template quando houver token.

## Botões

- Use os componentes `.btn`, `.btn-sm` ou `.btn-xs`; não crie um botão com
  altura ou raio próprios sem necessidade.
- Botões de texto têm **34 px de altura** e cantos arredondados pelo
  `--radius-sm`.
- A largura é automática e depende do ícone e do texto. Não use largura fixa
  nem estique o botão para preencher a linha, salvo um CTA de formulário
  explicitamente full-width.
- Botões na mesma linha ou grupo devem compartilhar a mesma altura.
- Ícones dentro de botões devem ter tamanho relativo ao texto e herdar a cor do
  botão; não podem desaparecer por regras globais de estado vazio.
- `icon-btn`, `icon-btn-sm` e `btn-close` são utilitários de ícone e não seguem
  a largura de um botão de texto, mas mantêm o raio do sistema.
- `mode-btn` (segmentos) e `md-btn` (barra do editor) seguem a altura e o raio
  do sistema; `water-quick-btn` é um tile de ação, não um botão de texto.
- Não use `w-100`, `flex-grow`, `white-space: normal` ou `flex-shrink` em
  botões de texto: a largura deve vir do conteúdo e o texto deve permanecer em
  uma linha. Largura total só é permitida em um CTA de formulário explicitamente
  projetado para isso.

## Validação mínima

- Abrir as páginas alteradas em `data-theme="light"` e `data-theme="dark"`.
- Conferir títulos, cards, bordas, textos secundários, chips, botões, campos,
  gráficos, estados vazios e foco de teclado.
- Rodar a suíte local e reconstruir a imagem Docker.
- Em mudanças de relatório/PDF, validar a geração real do PDF no container.
