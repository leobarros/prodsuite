"""Copia o banco local com a API de backup do SQLite.

A cópia pode ser feita com o servidor aberto: o SQLite cria um snapshot
consistente, incluindo o que estiver no WAL, sem copiar o arquivo “a quente”.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "instance" / "prodsuite.db"
BACKUPS = ROOT / "backups"


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit("Banco local não encontrado em instance/prodsuite.db")
    BACKUPS.mkdir(exist_ok=True)
    destination = BACKUPS / f"prodsuite-local-{datetime.now():%Y-%m-%d-%H%M}.db"
    source = sqlite3.connect(SOURCE)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    print(f"Cópia criada em {destination.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
