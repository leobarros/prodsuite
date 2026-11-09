import asyncio
from pathlib import Path

from prodsuite_tui.app import ProdSuiteTUI


def test_app_navigation_and_capture(tmp_path: Path):
    async def scenario():
        app = ProdSuiteTUI(tmp_path / "ui.db")
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            app.switch_page("inbox")
            await pilot.pause()
            app.query_one("#inbox-input").value = "Teste de captura"
            app.query_one("#inbox-capture").press()
            await pilot.pause()
            assert len(app.store.list_inbox()) == 1

            app.switch_page("notes")
            await pilot.pause()
            app.query_one("#note-title").value = "Nota TUI"
            app.query_one("#note-body").text = "# Olá"
            app.query_one("#notes-save").press()
            await pilot.pause()
            assert len(app.store.list_notes()) == 1

            app.switch_page("focus")
            await pilot.pause()
            assert app.query_one("#focus").size.width > 0
            app.switch_page("review")
            await pilot.pause()
            assert app.query_one("#review").size.width > 0
        app.store.close()

    asyncio.run(scenario())
