from pathlib import Path

from prodsuite_tui.db import Store


def test_tasks_and_inbox_roundtrip(tmp_path: Path):
    store = Store(tmp_path / "test.db")
    task_id = store.add_task("Comprar café", "Mercado", "high")
    assert store.task(task_id)["title"] == "Comprar café"
    store.move_task(task_id, "doing")
    assert store.task(task_id)["status"] == "doing"
    store.complete_task(task_id)
    assert store.task(task_id)["status"] == "done"

    item_id = store.capture("Ligar para o dentista")
    assert store.inbox_item(item_id)["state"] == "open"
    store.set_inbox_state(item_id, "someday")
    assert store.inbox_item(item_id)["state"] == "someday"
    store.close()


def test_notes_tags_and_review(tmp_path: Path):
    store = Store(tmp_path / "test.db")
    note_id = store.save_note("Rotina de foco", "# Foco", "foco, rotina")
    note = store.note(note_id)
    assert note["tags"] == "foco, rotina"
    assert store.save_note("Rotina de foco", "# Foco atualizado", "foco", note_id) == note_id
    assert "atualizado" in store.note(note_id)["body"]

    store.save_review("Funcionou", "Pesou", "Próximo")
    assert store.current_review()["wins"] == "Funcionou"
    store.close()


def test_care_stats(tmp_path: Path):
    store = Store(tmp_path / "test.db")
    store.add_water(300)
    store.add_water(200)
    assert store.water_today() == 500
    store.add_mood(5, 4, 1, "Bom dia")
    assert store.mood_stats()["entries"] == 1
    store.log_focus(None, 25)
    assert store.focus_stats()["sessions"] == 1
    store.close()
