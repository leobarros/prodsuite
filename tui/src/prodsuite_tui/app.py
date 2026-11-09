"""ProdSuite TUI beta — aplicação Textual local."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    Markdown,
    OptionList,
    Select,
    Static,
    TextArea,
)
from textual.widgets.option_list import Option

from . import __version__
from .db import Store
from .paths import database_path


PRIORITY_LABELS = {"low": "baixa", "medium": "média", "high": "alta"}
STATUS_LABELS = {"todo": "a fazer", "doing": "em andamento", "done": "concluída"}


class NavItem(Static):
    """Item de navegação clicável e focável."""

    can_focus = True

    def __init__(self, label: str, page_id: str, **kwargs) -> None:
        super().__init__(label, id=f"nav-{page_id}", classes="nav-item", **kwargs)
        self.page_id = page_id

    def on_click(self) -> None:
        self.app.switch_page(self.page_id)

    def on_key(self, event) -> None:
        if event.key in {"enter", "space"}:
            event.stop()
            self.app.switch_page(self.page_id)


class Page(VerticalScroll):
    """Base das telas; o app injeta o store."""

    def __init__(self, store: Store, **kwargs) -> None:
        super().__init__(**kwargs)
        self.store = store

    def refresh_data(self) -> None:
        """Sobrescrito pelas páginas."""


class DashboardPage(Page):
    WEEKDAYS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
    MONTHS = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")

    def compose(self) -> ComposeResult:
        with Horizontal(classes="dash-top"):
            with Vertical(classes="dash-heading"):
                yield Static("", id="dash-kicker", classes="kicker")
                yield Static("", id="dash-title", classes="page-title")
                yield Static("O essencial à vista, sem excesso.", classes="page-sub")
            with Horizontal(classes="dash-actions"):
                yield Button("Capturar", id="dash-capture", classes="action primary")
                yield Button("Foco", id="dash-focus", classes="action")
                yield Button("Tarefas", id="dash-tasks", classes="action")
        with Horizontal(id="dash-grid"):
            with Vertical(classes="dash-main"):
                yield Static("", id="dash-next", classes="card")
                yield Static("", id="dash-focus-card", classes="card")
                yield Static("", id="dash-priorities", classes="card")
            with Vertical(classes="dash-side"):
                yield Static("", id="dash-inbox", classes="card")
                yield Static("", id="dash-care", classes="card")
                yield Static("", id="dash-week", classes="card")

    def refresh_data(self) -> None:
        if not self.is_mounted:
            return
        data = self.store.dashboard()
        now = datetime.now()
        day = date.today()
        self.query_one("#dash-kicker", Static).update(
            f"[#82738c]{now:%H:%M} · {self.WEEKDAYS[day.weekday()]}, {day.day:02d} {self.MONTHS[day.month - 1]}[/#82738c]"
        )
        greeting = "Bom dia" if now.hour < 12 else ("Boa tarde" if now.hour < 18 else "Boa noite")
        self.query_one("#dash-title", Static).update(f"{greeting}.")
        next_task = data["next_task"]
        if next_task:
            next_block = (
                f"[b #cbb9e8]PRÓXIMA AÇÃO[/b #cbb9e8]  [dim]prioridade do dia[/dim]\n\n"
                f"[b]{escape(next_task['title'])}[/b]\n"
                f"[dim]{STATUS_LABELS.get(next_task['status'], next_task['status'])} · "
                f"prioridade {PRIORITY_LABELS.get(next_task['priority'], next_task['priority'])}[/dim]\n\n"
                "[dim]↵ abrir   f iniciar foco   m prioridades[/dim]"
            )
        else:
            next_block = "[b #cbb9e8]PRÓXIMA AÇÃO[/b #cbb9e8]\n\n[dim]Nenhuma tarefa aberta. Capture uma ideia.[/dim]"
        self.query_one("#dash-next", Static).update(next_block)
        focus = data["focus"]
        self.query_one("#dash-focus-card", Static).update(
            "[b #cbb9e8]FOCO[/b #cbb9e8]  [dim]sessão de 25 minutos[/dim]\n\n"
            "[b]25:00[/b]  [dim]foco[/dim]\n"
            "[dim]────────────────────────[/dim]\n"
            f"[dim]{focus['sessions']} sessões · {_minutes(focus['minutes'])} nesta semana[/dim]\n"
            "[dim]Enter abre o Pomodoro[/dim]"
        )
        tasks = self.store.list_tasks(include_done=False)[:3]
        if tasks:
            lines = []
            for index, task in enumerate(tasks, 1):
                lines.append(f"[b #e3c18c]{index}[/b #e3c18c]  {escape(task['title'])}")
            priorities = "\n".join(lines)
        else:
            priorities = "[dim]Nenhuma prioridade aberta.[/dim]"
        self.query_one("#dash-priorities", Static).update(
            f"[b #cbb9e8]PRIORIDADES DO DIA[/b #cbb9e8]  [dim]{len(tasks)}/3[/dim]\n\n{priorities}"
        )
        inbox = self.store.list_inbox("open")[:4]
        inbox_text = "\n".join(f"[#cbb9e8]•[/#cbb9e8] {escape(row['content'][:70])}" for row in inbox) if inbox else "[dim]Nada na cabeça agora.[/dim]"
        self.query_one("#dash-inbox", Static).update(
            f"[b #cbb9e8]CAIXA DE ENTRADA[/b #cbb9e8]  [dim]{data['inbox_open']} a decidir[/dim]\n\n{inbox_text}"
        )
        self.query_one("#dash-care", Static).update(
            "[b #cbb9e8]CUIDADO[/b #cbb9e8]\n\n"
            f"[dim]Água hoje[/dim]   [b]{data['water'] / 1000:.2f} L[/b]\n"
            f"[dim]Humor[/dim]       [b]{data['mood']['mood']:.1f}/5[/b] · {data['mood']['entries']} check-ins"
        )
        days = self.store.focus_last_days()
        max_value = max((value for _, value in days), default=0) or 1
        bars = "".join("▁▂▃▄▅▆▇█"[min(7, int(value / max_value * 7))] for _, value in days)
        labels = " ".join(label for label, _ in days)
        self.query_one("#dash-week", Static).update(
            f"[b #cbb9e8]FOCO NA SEMANA[/b #cbb9e8]  [dim]{_minutes(focus['minutes'])}[/dim]\n\n"
            f"[#cbb9e8]{bars}[/#cbb9e8]\n[dim]{labels}[/dim]"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        mapping = {"dash-capture": "inbox", "dash-focus": "focus", "dash-tasks": "tasks"}
        if event.button.id in mapping:
            self.app.switch_page(mapping[event.button.id])



class TasksPage(Page):
    def compose(self) -> ComposeResult:
        yield Static("Tarefas", classes="page-title")
        yield Static("Lista local, com teclado e mouse.", classes="page-sub")
        with Horizontal(classes="button-row"):
            yield Button("Nova", id="tasks-new", classes="action primary")
            yield Button("Concluir", id="tasks-done", classes="action")
            yield Button("Focar", id="tasks-focus", classes="action")
            yield Button("Iniciar", id="tasks-doing", classes="action")
        yield DataTable(id="tasks-table", zebra_stripes=True, cursor_type="row")
        yield Static("Selecione uma tarefa para agir.", id="tasks-hint", classes="hint")

    def on_mount(self) -> None:
        table = self.query_one("#tasks-table", DataTable)
        table.add_columns("Tarefa", "Status", "Prioridade", "Prazo")
        self.refresh_data()

    def refresh_data(self) -> None:
        if not self.is_mounted:
            return
        table = self.query_one("#tasks-table", DataTable)
        table.clear()
        self._task_ids: list[int] = []
        for row in self.store.list_tasks():
            self._task_ids.append(int(row["id"]))
            table.add_row(
                row["title"],
                STATUS_LABELS.get(row["status"], row["status"]),
                PRIORITY_LABELS.get(row["priority"], row["priority"]),
                row["due_date"] or "—",
                key=str(row["id"]),
            )
        self.query_one("#tasks-hint", Static).update(
            f"{len(self._task_ids)} tarefa{'s' if len(self._task_ids) != 1 else ''} · "
            "use ↑/↓ e os botões"
        )

    def _selected(self) -> int | None:
        table = self.query_one("#tasks-table", DataTable)
        if table.cursor_row < 0 or table.cursor_row >= len(self._task_ids):
            return None
        return self._task_ids[table.cursor_row]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id
        if button == "tasks-new":
            self.app.push_screen(TaskModal(self.store), self._after_modal)
            return
        task_id = self._selected()
        if task_id is None:
            self.app.notify("Selecione uma tarefa primeiro.", severity="warning")
            return
        if button == "tasks-done":
            self.store.complete_task(task_id, True)
            self.app.notify("Tarefa concluída.")
        elif button == "tasks-doing":
            self.store.move_task(task_id, "doing")
            self.app.notify("Tarefa em andamento.")
        elif button == "tasks-focus":
            self.app.focus_task_id = task_id
            self.app.switch_page("focus")
            return
        self.refresh_data()

    def _after_modal(self, result: bool | None) -> None:
        if result:
            self.refresh_data()
            self.app.notify("Tarefa criada.")


class InboxPage(Page):
    def compose(self) -> ComposeResult:
        yield Static("Caixa de entrada", classes="page-title")
        yield Static("Tire da cabeça. Decida depois.", classes="page-sub")
        with Horizontal(classes="button-row"):
            yield Button("Capturar", id="inbox-capture", classes="action primary")
            yield Button("A decidir", id="inbox-tab-open", classes="action")
            yield Button("Talvez", id="inbox-tab-someday", classes="action")
        yield Input(placeholder="O que está na sua cabeça agora?", id="inbox-input")
        yield OptionList(id="inbox-list")
        with Horizontal(classes="button-row"):
            yield Button("Virar tarefa", id="inbox-task", classes="action")
            yield Button("Virar nota", id="inbox-note", classes="action")
            yield Button("Talvez", id="inbox-someday", classes="action")
            yield Button("Feito", id="inbox-done", classes="action")
        yield Static("", id="inbox-hint", classes="hint")

    def on_mount(self) -> None:
        self.state = "open"
        self.selected_id: int | None = None
        self.refresh_data()

    def refresh_data(self) -> None:
        if not self.is_mounted:
            return
        option_list = self.query_one("#inbox-list", OptionList)
        option_list.clear_options()
        rows = self.store.list_inbox(self.state)
        self._inbox_ids = []
        for row in rows:
            self._inbox_ids.append(int(row["id"]))
            option_list.add_option(Option(row["content"], id=str(row["id"])))
        self.selected_id = self._inbox_ids[0] if self._inbox_ids else None
        if rows and self.selected_id is not None:
            option_list.highlighted = 0
        self.query_one("#inbox-hint", Static).update(
            f"{len(rows)} item{'s' if len(rows) != 1 else ''} em "
            f"{'A decidir' if self.state == 'open' else 'Talvez'}"
        )

    def _selected(self) -> int | None:
        option_list = self.query_one("#inbox-list", OptionList)
        highlighted = option_list.highlighted
        if highlighted is not None and 0 <= highlighted < len(self._inbox_ids):
            return self._inbox_ids[highlighted]
        return self.selected_id

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        try:
            self.selected_id = int(event.option.id or 0)
        except (TypeError, ValueError):
            self.selected_id = None

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "inbox-input":
            self._capture()

    def _capture(self) -> None:
        field = self.query_one("#inbox-input", Input)
        try:
            self.store.capture(field.value)
        except ValueError as exc:
            self.app.notify(str(exc), severity="warning")
            return
        field.value = ""
        self.refresh_data()
        self.app.notify("Capturado na caixa de entrada.")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id
        if button == "inbox-capture":
            self._capture()
            return
        if button == "inbox-tab-open":
            self.state = "open"
            self.refresh_data()
            return
        if button == "inbox-tab-someday":
            self.state = "someday"
            self.refresh_data()
            return
        item_id = self._selected()
        if item_id is None:
            self.app.notify("Nenhum item selecionado.", severity="warning")
            return
        item = self.store.inbox_item(item_id)
        if item is None:
            self.refresh_data()
            return
        content = item["content"]
        if button == "inbox-task":
            self.store.add_task(content.splitlines()[0][:160] or "Captura", content)
            self.store.set_inbox_state(item_id, "done")
            self.app.notify("Captura virou tarefa.")
        elif button == "inbox-note":
            first_line = next((line.strip() for line in content.splitlines() if line.strip()), "Captura")
            self.store.save_note(first_line[:160], content)
            self.store.set_inbox_state(item_id, "done")
            self.app.notify("Captura virou nota.")
        elif button == "inbox-someday":
            self.store.set_inbox_state(item_id, "someday" if self.state == "open" else "open")
            self.app.notify("Estado atualizado.")
        elif button == "inbox-done":
            self.store.set_inbox_state(item_id, "done")
            self.app.notify("Item resolvido.")
        self.refresh_data()


class FocusPage(Page):
    def compose(self) -> ComposeResult:
        yield Static("Foco", classes="page-title")
        yield Static("Um passo por vez. A pausa também faz parte.", classes="page-sub")
        yield Static("25:00", id="focus-time", classes="timer")
        yield Static("", id="focus-mode", classes="hint")
        with Horizontal(classes="button-row"):
            yield Button("Iniciar", id="focus-start", classes="action primary")
            yield Button("Pausar", id="focus-pause", classes="action")
            yield Button("Reiniciar", id="focus-reset", classes="action")
            yield Button("Pausa 5", id="focus-break", classes="action")
        yield Static("Tarefa (opcional)", classes="section-label")
        yield OptionList(id="focus-tasks")

    def on_mount(self) -> None:
        self.remaining = 25 * 60
        self.running = False
        self.break_mode = False
        self.interval = self.set_interval(1, self.tick)
        self.refresh_data()

    def refresh_data(self) -> None:
        if not self.is_mounted:
            return
        option_list = self.query_one("#focus-tasks", OptionList)
        option_list.clear_options()
        self._focus_ids = []
        for row in self.store.list_tasks(include_done=False):
            self._focus_ids.append(int(row["id"]))
            option_list.add_option(Option(row["title"], id=str(row["id"])))
        focus_id = getattr(self.app, "focus_task_id", None)
        if focus_id in self._focus_ids:
            option_list.highlighted = self._focus_ids.index(focus_id)
        self._paint_timer()

    def _selected_task(self) -> int | None:
        option_list = self.query_one("#focus-tasks", OptionList)
        highlighted = option_list.highlighted
        if highlighted is not None and 0 <= highlighted < len(self._focus_ids):
            return self._focus_ids[highlighted]
        return None

    def _paint_timer(self) -> None:
        minutes, seconds = divmod(max(0, self.remaining), 60)
        self.query_one("#focus-time", Static).update(f"{minutes:02d}:{seconds:02d}")
        self.query_one("#focus-mode", Static).update(
            f"{'Pausa' if self.break_mode else 'Foco'} · "
            f"{'rodando' if self.running else 'pausado'} · espaço reinicia o ciclo"
        )

    def tick(self) -> None:
        if not self.running:
            return
        self.remaining -= 1
        if self.remaining <= 0:
            self.running = False
            if not self.break_mode:
                self.store.log_focus(self._selected_task(), 25, "focus")
                self.app.notify("Sessão de foco concluída. Faça uma pausa.")
            else:
                self.app.notify("Pausa concluída. Volte ao foco.")
            self.remaining = 5 * 60 if self.break_mode else 25 * 60
        self._paint_timer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "focus-start":
            self.running = True
        elif event.button.id == "focus-pause":
            self.running = False
        elif event.button.id == "focus-reset":
            self.running = False
            self.break_mode = False
            self.remaining = 25 * 60
        elif event.button.id == "focus-break":
            self.running = False
            self.break_mode = True
            self.remaining = 5 * 60
        self._paint_timer()


class NotesPage(Page):
    def compose(self) -> ComposeResult:
        yield Static("Notas", classes="page-title")
        yield Static("Markdown, tags e prévia no terminal.", classes="page-sub")
        with Horizontal(classes="notes-columns"):
            with Vertical(classes="notes-list-column"):
                with Horizontal(classes="button-row"):
                    yield Button("Nova", id="notes-new", classes="action primary")
                    yield Button("Salvar", id="notes-save", classes="action")
                    yield Button("Prévia", id="notes-preview", classes="action")
                yield OptionList(id="notes-list")
            with Vertical(classes="notes-editor-column"):
                yield Input(placeholder="Título da nota", id="note-title")
                yield Input(placeholder="Tags: estudo, projeto", id="note-tags")
                yield TextArea(id="note-body", language="markdown")
                yield Markdown("", id="note-preview")

    def on_mount(self) -> None:
        self.current_note_id: int | None = None
        self.previewing = False
        self.query_one("#note-preview", Markdown).display = False
        self.refresh_data()

    def refresh_data(self) -> None:
        if not self.is_mounted:
            return
        option_list = self.query_one("#notes-list", OptionList)
        option_list.clear_options()
        notes = self.store.list_notes()
        self._note_ids = [int(row["id"]) for row in notes]
        for row in notes:
            option_list.add_option(Option(row["title"], id=str(row["id"])))
        if self.current_note_id not in self._note_ids and notes:
            self.current_note_id = int(notes[0]["id"])
        if self._note_ids:
            option_list.highlighted = self._note_ids.index(self.current_note_id)
        self._load_note()

    def _load_note(self) -> None:
        note = self.store.note(self.current_note_id) if self.current_note_id else None
        self.query_one("#note-title", Input).value = note["title"] if note else ""
        self.query_one("#note-tags", Input).value = note["tags"] if note else ""
        self.query_one("#note-body", TextArea).load_text(note["body"] if note else "")
        self.query_one("#note-preview", Markdown).update(note["body"] if note else "")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        try:
            self.current_note_id = int(event.option.id or 0)
        except (TypeError, ValueError):
            self.current_note_id = None
        self._load_note()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "notes-new":
            self.current_note_id = None
            self._load_note()
            self.query_one("#note-title", Input).focus()
        elif event.button.id == "notes-save":
            self._save()
        elif event.button.id == "notes-preview":
            self.previewing = not self.previewing
            editor = self.query_one("#note-body", TextArea)
            preview = self.query_one("#note-preview", Markdown)
            editor.display = not self.previewing
            preview.display = self.previewing
            preview.update(editor.text)

    def _save(self) -> None:
        title = self.query_one("#note-title", Input).value
        tags = self.query_one("#note-tags", Input).value
        body = self.query_one("#note-body", TextArea).text
        try:
            self.current_note_id = self.store.save_note(title, body, tags, self.current_note_id)
        except ValueError as exc:
            self.app.notify(str(exc), severity="warning")
            return
        self.refresh_data()
        self.app.notify("Nota salva.")


class CarePage(Page):
    def compose(self) -> ComposeResult:
        yield Static("Cuidado pessoal", classes="page-title")
        yield Static("Água e humor, sem cobrança.", classes="page-sub")
        yield Static("", id="care-stats", classes="panel")
        with Horizontal(classes="button-row"):
            yield Button("+200 ml", id="water-200", classes="action primary")
            yield Button("+300 ml", id="water-300", classes="action")
            yield Button("+500 ml", id="water-500", classes="action")
        with Horizontal(classes="care-form"):
            yield Input(placeholder="ml personalizado", id="water-custom", type="integer")
            yield Button("Registrar", id="water-custom-btn", classes="action")
        yield Static("Check-in de humor", classes="section-label")
        with Horizontal(classes="care-form"):
            yield Input(placeholder="Humor 1-5", id="mood-value", value="3", type="integer")
            yield Input(placeholder="Energia 1-5", id="energy-value", value="3", type="integer")
            yield Input(placeholder="Tensão 1-5", id="tension-value", value="2", type="integer")
            yield Button("Salvar check-in", id="mood-save", classes="action primary")
        yield Input(placeholder="Nota curta (opcional)", id="mood-note")

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        if not self.is_mounted:
            return
        water = self.store.water_today()
        mood = self.store.mood_stats()
        self.query_one("#care-stats", Static).update(
            f"Água hoje: [b]{water / 1000:.2f} L[/b]\n"
            f"Humor: [b]{mood['mood']:.1f}/5[/b] · {mood['entries']} check-ins"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id
        if button and button.startswith("water-") and button != "water-custom-btn":
            amount = button.removeprefix("water-")
            if amount.isdigit():
                self.store.add_water(int(amount))
                self.refresh_data()
        elif button == "water-custom-btn":
            field = self.query_one("#water-custom", Input)
            try:
                amount = int(field.value)
                if amount <= 0:
                    raise ValueError
            except ValueError:
                self.app.notify("Informe uma quantidade em ml.", severity="warning")
                return
            self.store.add_water(amount)
            field.value = ""
            self.refresh_data()
        elif button == "mood-save":
            try:
                mood = int(self.query_one("#mood-value", Input).value)
                energy = int(self.query_one("#energy-value", Input).value)
                tension = int(self.query_one("#tension-value", Input).value)
            except ValueError:
                self.app.notify("Use valores de 1 a 5.", severity="warning")
                return
            self.store.add_mood(mood, energy, tension, self.query_one("#mood-note", Input).value)
            self.query_one("#mood-note", Input).value = ""
            self.refresh_data()
            self.app.notify("Check-in salvo.")


class ReviewPage(Page):
    def compose(self) -> ComposeResult:
        yield Static("Revisão", classes="page-title")
        yield Static("O que funcionou, o que pesou e qual é o próximo foco.", classes="page-sub")
        with Horizontal(classes="button-row"):
            yield Button("Salvar revisão", id="review-save", classes="action primary")
        yield Static("", id="review-stats", classes="panel")
        yield Static("O que funcionou?", classes="section-label")
        yield TextArea(id="review-wins")
        yield Static("O que foi difícil?", classes="section-label")
        yield TextArea(id="review-challenges")
        yield Static("Foco da próxima semana", classes="section-label")
        yield TextArea(id="review-next")

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        if not self.is_mounted:
            return
        report = self.store.report()
        self.query_one("#review-stats", Static).update(
            f"Foco: [b]{_minutes(report['focus_minutes'])}[/b] · "
            f"Tarefas concluídas: [b]{report['done']}/{report['tasks']}[/b] · "
            f"Água: [b]{report['water_ml'] / 1000:.2f} L[/b] · "
            f"Humor: [b]{report['mood']:.1f}/5[/b]"
        )
        review = self.store.current_review()
        if review:
            self.query_one("#review-wins", TextArea).load_text(review["wins"])
            self.query_one("#review-challenges", TextArea).load_text(review["challenges"])
            self.query_one("#review-next", TextArea).load_text(review["next_steps"])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "review-save":
            return
        self.store.save_review(
            self.query_one("#review-wins", TextArea).text,
            self.query_one("#review-challenges", TextArea).text,
            self.query_one("#review-next", TextArea).text,
        )
        self.refresh_data()
        self.app.notify("Revisão salva.")


class ReportPage(Page):
    def compose(self) -> ComposeResult:
        yield Static("Relatório", classes="page-title")
        yield Static("Uma leitura dos seus dados locais.", classes="page-sub")
        yield Static("", id="report-stats", classes="panel")
        yield Static("", id="report-note", classes="hint")

    def refresh_data(self) -> None:
        if not self.is_mounted:
            return
        data = self.store.report()
        self.query_one("#report-stats", Static).update(
            f"[b]Tarefas[/b]\n{data['done']} concluídas de {data['tasks']}\n\n"
            f"[b]Foco[/b]\n{_minutes(data['focus_minutes'])} em {data['focus_sessions']} sessões\n\n"
            f"[b]Água[/b]\n{data['water_ml'] / 1000:.2f} L registrados\n\n"
            f"[b]Humor[/b]\n{data['mood']:.1f}/5 em {data['mood_entries']} check-ins"
        )
        self.query_one("#report-note", Static).update(
            "Relatório local da TUI. O PDF continua disponível na versão web."
        )


class TaskModal(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancelar")]

    def __init__(self, store: Store) -> None:
        super().__init__()
        self.store = store

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label("Nova tarefa", classes="modal-title")
            yield Input(placeholder="O que precisa ser feito?", id="modal-task-title")
            yield Input(placeholder="Descrição (opcional)", id="modal-task-desc")
            yield Select(
                [("Baixa", "low"), ("Média", "medium"), ("Alta", "high")],
                value="medium",
                id="modal-task-priority",
            )
            with Horizontal(classes="button-row"):
                yield Button("Cancelar", id="modal-cancel", classes="action")
                yield Button("Criar", id="modal-save", classes="action primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "modal-cancel":
            self.dismiss(False)
        elif event.button.id == "modal-save":
            try:
                self.store.add_task(
                    self.query_one("#modal-task-title", Input).value,
                    self.query_one("#modal-task-desc", Input).value,
                    str(self.query_one("#modal-task-priority", Select).value),
                )
            except ValueError as exc:
                self.app.notify(str(exc), severity="warning")
                return
            self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class HelpModal(ModalScreen[None]):
    BINDINGS = [Binding("escape", "dismiss", "Fechar"), Binding("question_mark", "dismiss", "Fechar")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label("Atalhos", classes="modal-title")
            yield Static(
                "1–8  navegar entre telas\n"
                "c    capturar na caixa de entrada\n"
                "f    abrir foco\n"
                "n    nova tarefa/nota na tela atual\n"
                "Tab  mover entre controles\n"
                "Enter ativar botão ou confirmar\n"
                "?    abrir esta ajuda\n"
                "q    sair",
                classes="help-text",
            )
            yield Button("Fechar", id="help-close", classes="action primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "help-close":
            self.dismiss(None)


class ProdSuiteTUI(App):
    CSS_PATH = "app.tcss"
    TITLE = "ProdSuite TUI"
    SUB_TITLE = "beta local"
    BINDINGS = [
        Binding("1", "show_page('dashboard')", "Meu dia"),
        Binding("2", "show_page('tasks')", "Tarefas"),
        Binding("3", "show_page('inbox')", "Entrada"),
        Binding("4", "show_page('focus')", "Foco"),
        Binding("5", "show_page('notes')", "Notas"),
        Binding("6", "show_page('care')", "Cuidado"),
        Binding("7", "show_page('review')", "Revisão"),
        Binding("8", "show_page('report')", "Relatório"),
        Binding("c", "capture", "Capturar"),
        Binding("f", "focus", "Foco"),
        Binding("n", "new", "Novo"),
        Binding("question_mark", "help", "Ajuda"),
        Binding("q", "quit", "Sair"),
    ]

    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()
        self.store = Store(db_path)
        self.focus_task_id: int | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="shell"):
            with Vertical(id="sidebar"):
                yield Static(f"ProdSuite\n[dim]TUI {__version__} · beta[/dim]", id="brand")
                yield Static("MEU DIA", classes="nav-label")
                for page_id, label in (
                    ("dashboard", "Meu dia"),
                    ("tasks", "Tarefas"),
                    ("inbox", "Caixa de entrada"),
                    ("focus", "Pomodoro"),
                    ("notes", "Notas"),
                ):
                    yield NavItem(label, page_id)
                yield Static("CUIDADO", classes="nav-label")
                yield NavItem("Cuidado pessoal", "care")
                yield Static("FERRAMENTAS", classes="nav-label")
                yield NavItem("Revisão", "review")
                yield NavItem("Relatório", "report")
                yield Static("", id="sidebar-spacer")
                yield Static("local · SQLite\nsem nuvem", id="sidebar-foot")
            with Vertical(id="content"):
                with Vertical(id="pages"):
                    yield DashboardPage(self.store, id="dashboard")
                    yield TasksPage(self.store, id="tasks")
                    yield InboxPage(self.store, id="inbox")
                    yield FocusPage(self.store, id="focus")
                    yield NotesPage(self.store, id="notes")
                    yield CarePage(self.store, id="care")
                    yield ReviewPage(self.store, id="review")
                    yield ReportPage(self.store, id="report")
        yield Static(
            "1–8 navegar   c capturar   f foco   n novo   ? ajuda   q sair",
            id="statusbar",
        )

    def on_mount(self) -> None:
        self.switch_page("dashboard")

    def switch_page(self, page_id: str) -> None:
        for page in self.query(Page):
            page.display = page.id == page_id
        for item in self.query(NavItem):
            item.set_class(item.page_id == page_id, "active")
        page = self.query_one(f"#{page_id}", Page)
        page.refresh_data()

    def action_show_page(self, page_id: str) -> None:
        self.switch_page(page_id)

    def action_capture(self) -> None:
        self.switch_page("inbox")
        self.query_one("#inbox-input", Input).focus()

    def action_focus(self) -> None:
        self.switch_page("focus")

    def action_new(self) -> None:
        current = next((page.id for page in self.query(Page) if page.display), None)
        if current == "notes":
            self.query_one("#notes-new", Button).press()
        elif current == "tasks":
            self.query_one("#tasks-new", Button).press()
        else:
            self.action_capture()

    def action_help(self) -> None:
        self.push_screen(HelpModal())

    def on_unmount(self) -> None:
        self.store.close()


def _minutes(total: int) -> str:
    hours, minutes = divmod(max(0, int(total)), 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="prodsuite-tui", description="ProdSuite TUI beta")
    parser.add_argument("--db", type=Path, default=None, help="caminho do banco local")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    ProdSuiteTUI(args.db).run()


if __name__ == "__main__":
    main()
