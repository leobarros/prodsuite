# ProdSuite TUI beta

Uma versão local do ProdSuite para rodar no terminal. Os dados ficam em um
SQLite próprio no seu computador — nada é enviado para nuvem, Docker ou para a
instalação web.

## Instalação

### Linux e macOS

```bash
curl -fsSL https://raw.githubusercontent.com/leobarros/prodsuite/main/tui/install.py -o /tmp/prodsuite-tui-install.py
python3 /tmp/prodsuite-tui-install.py
```

### Windows

No PowerShell:

```powershell
irm https://raw.githubusercontent.com/leobarros/prodsuite/main/tui/install.py -OutFile "$env:TEMP\prodsuite-tui-install.py"
py "$env:TEMP\prodsuite-tui-install.py"
```

O instalador detecta Windows, macOS ou Linux/Debian, cria um ambiente virtual
isolado e instala o comando `prodsuite-tui`.

Para desenvolvimento, aponte para a pasta local:

```bash
python3 tui/install.py --source tui
```

## Executar

```bash
prodsuite-tui
```

Ou com um banco específico:

```bash
prodsuite-tui --db ~/meu-prodsuite.db
```

## O que tem na beta

- Meu dia com próximas tarefas, foco, água e humor.
- Tarefas com criação, conclusão, andamento e envio para foco.
- Caixa de entrada local com captura, tarefas, notas, Talvez e resolvidas.
- Pomodoro de 25 minutos e pausa de 5 minutos.
- Notas em Markdown com tags e prévia.
- Água e check-in de humor.
- Revisão semanal e relatório local.
- Navegação por mouse e teclado.
- Atalhos de 1 a 8, `c`, `f`, `n`, `?` e `q`.

## Conceitos

As referências visuais da TUI estão em:

- `../docs/images/tui-concept-1.png`
- `../docs/images/tui-concept-2.png`
- `../docs/images/tui-concept-3.png`

## Dados

O banco fica em:

- Linux: `~/.local/share/prodsuite-tui/prodsuite.db`
- macOS: `~/Library/Application Support/ProdSuiteTUI/prodsuite.db`
- Windows: `%LOCALAPPDATA%\ProdSuiteTUI\prodsuite.db`

Também pode ser controlado por:

```bash
PRODSUITE_TUI_DATA=/caminho/para/dados prodsuite-tui
```

## Limites conhecidos da beta

- Uma pessoa por instalação, sem login.
- Relatório em texto; o PDF continua na versão web.
- Sem Web Push. A TUI pode ser executada no terminal quando você quiser.
- Sem sincronização entre TUI e app web.
- Gráficos e imagens ficam para uma próxima versão.

## Desinstalar

```bash
python3 tui/install.py --uninstall
```

O comando remove o ambiente e os launchers, mas preserva o banco local.
