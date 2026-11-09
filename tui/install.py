#!/usr/bin/env python3
"""Instalador da ProdSuite TUI beta.

Uso remoto:
    curl -fsSL https://raw.githubusercontent.com/leobarros/prodsuite/main/tui/install.py -o /tmp/prodsuite-tui-install.py
    python3 /tmp/prodsuite-tui-install.py

Windows (PowerShell):
    irm https://raw.githubusercontent.com/leobarros/prodsuite/main/tui/install.py -OutFile "$env:TEMP\\prodsuite-tui-install.py"
    py "$env:TEMP\\prodsuite-tui-install.py"

O instalador detecta Windows, macOS e Linux/Debian, cria um ambiente virtual
isolado e não precisa de privilégios administrativos.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REMOTE_TARBALL = "https://github.com/leobarros/prodsuite/archive/refs/heads/{ref}.tar.gz"
MIN_PYTHON = (3, 10)


def system_label() -> str:
    system = platform.system()
    if system == "Windows":
        return "Windows"
    if system == "Darwin":
        return "macOS"
    if system == "Linux":
        try:
            release = Path("/etc/os-release").read_text(encoding="utf-8")
            for line in release.splitlines():
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
        return "Linux"
    return system or "sistema desconhecido"


def install_root() -> Path:
    if platform.system() == "Windows":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "ProdSuiteTUI" / "app"
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "ProdSuiteTUI" / "app"
    root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "prodsuite-tui" / "app"


def venv_python(root: Path) -> Path:
    if platform.system() == "Windows":
        return root / "venv" / "Scripts" / "python.exe"
    return root / "venv" / "bin" / "python"


def launcher_path(root: Path) -> Path:
    if platform.system() == "Windows":
        return root / "prodsuite-tui.cmd"
    return root / "prodsuite-tui"


def download_source(ref: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="prodsuite-tui-"))
    archive = tmp / "source.tar.gz"
    url = REMOTE_TARBALL.format(ref=ref)
    print(f"Baixando TUI de {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "prodsuite-tui-installer"})
    with urllib.request.urlopen(request, timeout=60) as response:
        archive.write_bytes(response.read())
    with tarfile.open(archive, "r:gz") as bundle:
        if hasattr(tarfile, "data_filter"):
            bundle.extractall(tmp, filter="data")
        else:  # Python 3.10/3.11
            bundle.extractall(tmp)
    roots = [path for path in tmp.iterdir() if path.is_dir() and (path / "tui").is_dir()]
    if not roots:
        raise RuntimeError("Pacote TUI não encontrado no arquivo baixado.")
    return roots[0] / "tui"


def run(command: list[str], *, cwd: Path | None = None) -> None:
    print("$", " ".join(str(part) for part in command))
    subprocess.run(command, cwd=cwd, check=True)


def create_launcher(root: Path) -> None:
    python = venv_python(root)
    if platform.system() == "Windows":
        launcher = launcher_path(root)
        launcher.write_text(
            "@echo off\r\n"
            f'"{python}" -m prodsuite_tui %*\r\n',
            encoding="utf-8",
        )
        windows_apps = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps"
        if windows_apps.is_dir():
            try:
                shutil.copy2(launcher, windows_apps / "prodsuite-tui.cmd")
            except OSError:
                pass
        print(f"Launcher: {launcher}")
        return

    launcher = launcher_path(root)
    launcher.write_text(
        "#!/usr/bin/env sh\n"
        f'exec "{python}" -m prodsuite_tui "$@"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    local_bin = Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    link = local_bin / "prodsuite-tui"
    try:
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(launcher)
        print(f"Comando: {link}")
    except OSError:
        print(f"Comando: {launcher}")
    print(f"Se necessário, adicione ao PATH: {local_bin}")


def uninstall(root: Path) -> None:
    if platform.system() == "Windows":
        for path in (launcher_path(root), Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "prodsuite-tui.cmd"):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    else:
        for path in (launcher_path(root), Path.home() / ".local" / "bin" / "prodsuite-tui"):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    if root.exists():
        shutil.rmtree(root)
    print(f"TUI removida. O banco local foi mantido em {install_root().parent}.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Instalador da ProdSuite TUI beta")
    parser.add_argument("--source", type=Path, help="pasta tui/ local, para desenvolvimento")
    parser.add_argument("--ref", default="main", help="branch/tag do GitHub (padrão: main)")
    parser.add_argument("--uninstall", action="store_true", help="remove a instalação, mantendo os dados")
    args = parser.parse_args()

    print(f"Sistema detectado: {system_label()}")
    print(f"Python: {sys.version.split()[0]}")
    if sys.version_info < MIN_PYTHON:
        print(f"É necessário Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+.")
        return 1
    root = install_root()
    if args.uninstall:
        uninstall(root)
        return 0
    if args.source:
        source = args.source.expanduser().resolve()
        if not (source / "pyproject.toml").is_file():
            print(f"Não encontrei pyproject.toml em {source}.")
            return 1
    else:
        source = download_source(args.ref)
    root.mkdir(parents=True, exist_ok=True)
    python = venv_python(root)
    if not python.exists():
        print(f"Criando ambiente isolado em {root / 'venv'}")
        run([sys.executable, "-m", "venv", str(root / "venv")])
    run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(python), "-m", "pip", "install", "--upgrade", str(source)])
    create_launcher(root)
    print("\nInstalação concluída. Inicie com: prodsuite-tui")
    print("Os dados ficam em um SQLite local; nada é enviado para a nuvem.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:  # noqa: BLE001 - instalador precisa de mensagem curta
        print(f"Falha na instalação: {exc}", file=sys.stderr)
        raise SystemExit(1)
