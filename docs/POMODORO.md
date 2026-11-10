# Protocolo de regressão do Pomodoro

Toda alteração que toque no Pomodoro deve validar este documento. O recurso é
considerado concluído apenas quando o comportamento estiver confirmado no host
e no Docker, incluindo o estado compartilhado do servidor.

## Arquivos que disparam a regressão completa

- `static/js/pomodoro.js`
- `templates/focus.html` e componentes do HUD
- `templates/_focus_history.html` e `templates/_weekly_chart.html`
- `routes/pomodoro.py`
- `services/pomodoro.py`
- `services/timer_sync.py`
- `services/boards.py` quando afetar a tarefa em foco
- `static/audio/pomodoro-alert.wav`
- `static/sw.js` ou assets usados pelo Pomodoro
- rotas/modelos de ciclos, tarefas e notificações relacionadas

## 1. Controles básicos

- [ ] Iniciar em **Foco · 25 min**.
- [ ] Pausar imediatamente: o tempo restante não muda para 25:00.
- [ ] Pausar depois de alguns segundos: o restante exibido é menor que a duração.
- [ ] Retomar: o tempo continua de onde pausou; não reinicia.
- [ ] Reiniciar: volta ao início do modo atual.
- [ ] Alternar **Foco · 25**, **Intervalo · 5** e **Longo · 20**.
- [ ] Confirmar que não é possível trocar de modo enquanto o timer está rodando.
- [ ] Confirmar que nenhum modo exibe tempo acima da própria duração.
- [ ] Repetir pausa/retomada várias vezes seguidas.
- [ ] Testar os atalhos `Espaço` e `R`, sem disparar quando o foco está em um campo de texto.

## 2. Estado e sincronização

- [ ] Iniciar, pausar e recarregar a página: o estado permanece coerente.
- [ ] Navegar para outra página e voltar: o timer continua.
- [ ] Abrir uma segunda aba: pausar em uma aba é refletido na outra.
- [ ] Abrir em outro dispositivo: o estado compartilhado permanece coerente.
- [ ] Confirmar que a pausa usa o relógio do servidor, não apenas o do navegador.
- [ ] Confirmar que a resposta de pausa preserva o modo atual.
- [ ] Confirmar que `remaining` nunca é maior que `duration`.
- [ ] Confirmar que reinícios/atualizações não duplicam ciclos.

## 3. Ciclos e pausa longa

- [ ] Um foco concluído registra **um** ciclo no servidor.
- [ ] O ciclo aparece no histórico e no gráfico semanal.
- [ ] Um ciclo vinculado a tarefa incrementa `completed_pomodoros` uma única vez.
- [ ] Após o primeiro foco do dia, a sugestão é **pausa curta**.
- [ ] Após o quarto foco **do dia**, a sugestão é **pausa longa**.
- [ ] Ciclos de ontem não contam para a pausa longa de hoje.
- [ ] Uma pausa parada de um dia anterior volta para **Foco · 25**.
- [ ] A API `/foco/estado` informa `focusCyclesToday` e `focusDate` corretos.
- [ ] O ciclo não é contado duas vezes ao recarregar, reabrir o PWA ou reconectar.
- [ ] Ciclo offline fica pendente e é salvo quando a conexão volta.

## 4. Áudio

- [ ] O arquivo `static/audio/pomodoro-alert.wav` tem menos de 1,5 segundo.
- [ ] **Testar som** reproduz um único chime curto.
- [ ] A conclusão reproduz um único chime; não há som duplicado.
- [ ] Pausar, reiniciar ou trocar de modo não reproduz som.
- [ ] Escrever em Notas, criar tarefa ou navegar por outra página não reproduz o
      chime de desbloqueio.
- [ ] Abrir o app com um podcast/YouTube tocando não pausa o áudio externo.
- [ ] O som do Pomodoro mistura com podcast/música em vez de pausá-los
      (`navigator.audioSession.type = "ambient"`).
- [ ] O carregamento da página não cria AudioContext, não baixa o áudio para
      reprodução e não inicia keepalive.
- [ ] Voltar de outra tela ou de segundo plano não reproduz um som atrasado.
- [ ] O som continua funcionando no PWA instalado por HTTPS.
- [ ] Verificar o comportamento no iPhone/Safari, incluindo ativação por gesto.

## 5. Conclusão e interface

- [ ] A faixa de conclusão aparece ao terminar.
- [ ] O título da aba muda durante a conclusão.
- [ ] A notificação do navegador é criada quando permitida.
- [ ] A vibração funciona quando suportada.
- [ ] O próximo modo exibido é curto ou longo conforme o ciclo do dia.
- [ ] O botão da faixa leva ao modo correto.
- [ ] A interface mantém foco visível, contraste e navegação por teclado.
- [ ] Tema claro e escuro continuam corretos.

## 6. Docker e PWA

- [ ] Reconstruir a imagem: `docker build -t prodsuite:1.0 .`.
- [ ] Recriar o container com o volume `prodsuite_data` intacto.
- [ ] Confirmar `/healthz` e `/foco` no container.
- [ ] Iniciar, pausar, retomar e reiniciar dentro do Docker.
- [ ] Repetir pausa/retomada com o relógio do container.
- [ ] Confirmar que `focusCyclesToday` no container ignora ciclos de ontem.
- [ ] Atualizar o PWA, fechar e abrir; confirmar que o Service Worker novo assumiu.
- [ ] Confirmar que o áudio antigo de 5 segundos não está no cache.

## 6.1 HTTPS local

- [ ] Rodar `make run-https` e abrir `https://localhost:5001`.
- [ ] Confirmar que iniciar, pausar, retomar e reiniciar funcionam também no
      servidor de desenvolvimento HTTPS, não apenas no Docker.
- [ ] Abrir o console do navegador e confirmar que não há `ReferenceError` ou
      erro de síntaxe no `pomodoro.js`.

## 6.2 Layout por viewport

- [ ] Em **1366 × 768**, o card do timer não tem barra de rolagem interna e o
      seletor de tarefa continua visível.
- [ ] Em **1280 × 720**, o layout também cabe sem cortar o seletor.
- [ ] Em **1920 × 1080**, o anel mantém o tamanho máximo e a composição original.
- [ ] O corpo da página não ganha barra de rolagem vertical no desktop.
- [ ] O histórico lateral usa rolagem própria quando necessário, sem empurrar o
      timer.
- [ ] A sidebar inteira cabe em 1366×768 e 1280×720, com usuário e ações
      visíveis e sem barra de rolagem.
- [ ] O anel e os espaçamentos usam altura relativa (`vh`/`clamp`), não uma
      altura fixa de 300 px em todas as telas.

## 7. Comandos automatizados mínimos

```bash
node --check static/js/pomodoro.js
venv/bin/python -m pytest -q
docker build -t prodsuite:1.0 .
```

O teste automatizado deve cobrir, no mínimo:

- `/foco/estado` com ciclos de ontem e de hoje;
- pausa preservando modo e restante;
- pausa de um dia anterior voltando para foco;
- upload/duração curta do áudio;
- ciclo idempotente por `run_id`;
- criação do ciclo e atualização da tarefa.

## 8. Critério de conclusão

Não considerar uma alteração do Pomodoro concluída se qualquer item acima não
puder ser confirmado. Registre no RUNBOOK a data, o commit e o ambiente usado na
validação, especialmente quando a validação for feita no homelab com Docker.
