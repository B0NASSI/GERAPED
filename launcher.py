# -*- coding: utf-8 -*-
"""
Launcher do GERAPED (Gerador de Pedidos), com auto-atualização via GitHub
Releases.

Fluxo:
  1. Lê a versão instalada (versao.txt)
  2. Consulta a API do GitHub Releases (releases/latest)
  3. Sem update (ou sem internet/GitHub fora) -> abre o GERAPED.exe e fecha, sem erro
  4. Com update -> mostra janela (versão atual, nova, barra de progresso). A
     atualização é obrigatória: não tem botão de pular, e fechar a janela
     não cancela nada.
     - baixa o .zip do asset para arquivo temporário e valida o tamanho
     - extrai o .zip numa pasta de preparo (staging) e confere que o
       GERAPED.exe veio, ANTES de mexer em qualquer coisa já instalada
     - fecha qualquer GERAPED.exe que esteja rodando (senão os arquivos
       ficam bloqueados na hora de substituir)
     - MESCLA o conteúdo no lugar: sempre sobrescreve o GERAPED.exe; a pasta
       _internal só é tocada nos arquivos que vieram dentro do .zip (se
       vieram) — o resto do _internal já instalado fica intocado. Isso
       permite pacotes de tamanho variável: uma atualização só de código
       Python pode trazer só o GERAPED.exe (poucos MB), sem precisar
       reenviar as dependências de terceiros (ttkbootstrap, Pillow, python-docx,
       Tcl/Tk) que raramente mudam entre versões.
     - faz backup de cada arquivo antes de sobrescrever (ou marca que ele
       era novo) e atualiza versao.txt
     - abre o GERAPED.exe atualizado e fecha o launcher
  5. Qualquer falha depois de começar a aplicar -> restaura cada arquivo
     tocado a partir do backup individual (remove os que eram novos)
     Falha antes de aplicar (download/extração/validação) -> nada foi tocado, só abre a versão existente
     Nenhum arquivo chegou a ser tocado numa falha -> avisa o usuário e não mexe em nada
"""
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

import requests
import ttkbootstrap as ttk
from PIL import ImageTk
from ttkbootstrap.constants import BOTH, X
from tkinter import messagebox

import log_setup
import tema
import visual

# ---------------------------------------------------------------------------
# Configuração - repositório do GERAPED no GitHub
# ---------------------------------------------------------------------------
GITHUB_OWNER = "B0NASSI"
GITHUB_REPO = "GERAPED"
ASSET_NAME = "GERAPED-app.zip"   # nome do arquivo anexado na release (GERAPED.exe + _internal/ zipados)
CHECKSUM_ASSET_NAME = ASSET_NAME + ".sha256"  # arquivo-texto opcional com o sha256 do zip, ver gerar_checksum.py
REQUEST_TIMEOUT = 10             # segundos para consultas de rede
DOWNLOAD_CHUNK_SIZE = 65536

LARGURA_JANELA = 460
ALTURA_BANNER = 78

NOME_JANELA_GERAPED = "GERAPED - Gerador de Pedidos"


def _posicionar_janela(janela, largura: int, altura: int) -> None:
    """Centraliza `janela` sobre a janela do GERAPED, se ele já estiver aberto
    (ex.: o launcher rodou de novo com o programa já em uso) — assim a caixa
    de atualização aparece no mesmo monitor onde a pessoa está, em vez de
    sempre no monitor principal. Sem o GERAPED aberto (caso mais comum),
    centraliza no monitor principal como de costume."""
    janela.update_idletasks()
    try:
        import win32gui

        hwnds = []
        win32gui.EnumWindows(
            lambda hwnd, _: hwnds.append(hwnd)
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) == NOME_JANELA_GERAPED
            else None,
            None,
        )
        if hwnds:
            esquerda, topo, direita, baixo = win32gui.GetWindowRect(hwnds[0])
            x = esquerda + ((direita - esquerda) - largura) // 2
            y = topo + max(((baixo - topo) - altura) // 2 - 30, 0)
            janela.geometry(f"{largura}x{altura}+{x}+{y}")
            return
    except Exception:
        pass

    x = (janela.winfo_screenwidth() - largura) // 2
    y = max((janela.winfo_screenheight() - altura) // 2 - 50, 0)
    janela.geometry(f"{largura}x{altura}+{x}+{y}")


def _caminho_recurso(nome: str) -> str:
    # em modo congelado (.exe), os recursos ficam soltos em _MEIPASS; em modo
    # de desenvolvimento, launcher.py mora na raiz do projeto, junto dos recursos
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return str(base / nome)


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


BASE_DIR = get_base_dir()
APP_EXE = BASE_DIR / "GERAPED.exe"
APP_INTERNAL = BASE_DIR / "_internal"
STAGING_DIR = BASE_DIR / "_update_staging"
VERSION_FILE = BASE_DIR / "versao.txt"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Versão local / comparação
# ---------------------------------------------------------------------------
def read_local_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8-sig").strip()
    except FileNotFoundError:
        return "0.0.0"


def parse_version(version: str):
    version = version.strip().lstrip("vV")
    parts = version.split(".")
    nums = []
    for part in parts:
        digits = "".join(ch for ch in part if ch.isdigit())
        nums.append(int(digits) if digits else 0)
    return tuple(nums) if nums else (0,)


def is_newer(remote: str, local: str) -> bool:
    r, l = parse_version(remote), parse_version(local)
    length = max(len(r), len(l))
    r = r + (0,) * (length - len(r))
    l = l + (0,) * (length - len(l))
    return r > l


# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------
def get_latest_release():
    """Retorna dict com {tag_name, asset_url, asset_size, checksum_url} ou
    None se indisponível. checksum_url vem None se a release não tiver o
    arquivo de checksum (releases antigas, ou publicadas sem gerar_checksum.py)."""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "geraped-auto-updater"}
    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.info("Não foi possível consultar releases do GitHub: %s", exc)
        return None

    tag_name = data.get("tag_name")
    if not tag_name:
        logger.info("Resposta de releases/latest sem tag_name.")
        return None

    asset_url = None
    asset_size = None
    checksum_url = None
    for asset in data.get("assets", []):
        if asset.get("name") == ASSET_NAME:
            asset_url = asset.get("browser_download_url")
            asset_size = asset.get("size")
        elif asset.get("name") == CHECKSUM_ASSET_NAME:
            checksum_url = asset.get("browser_download_url")

    if not asset_url:
        logger.info("Release %s não tem o asset %s.", tag_name, ASSET_NAME)
        return None

    return {
        "tag_name": tag_name,
        "asset_url": asset_url,
        "asset_size": asset_size,
        "checksum_url": checksum_url,
    }


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
def download_asset(url: str, dest: Path, expected_size, progress_callback):
    """Baixa a URL para dest em streaming, chamando progress_callback(percent|None)."""
    headers = {"User-Agent": "geraped-auto-updater"}
    with requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, stream=True) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length") or 0) or expected_size
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    progress_callback(downloaded / total * 100, downloaded, total)
                else:
                    progress_callback(None, downloaded, None)

    actual_size = dest.stat().st_size
    if actual_size == 0:
        raise IOError("Arquivo baixado está vazio.")
    if expected_size and actual_size != expected_size:
        raise IOError(f"Tamanho do download não confere (esperado {expected_size}, obtido {actual_size}).")


def _sha256_de_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(DOWNLOAD_CHUNK_SIZE), b""):
            h.update(bloco)
    return h.hexdigest()


def verificar_checksum(zip_path: Path, checksum_url) -> None:
    """Confere o SHA256 do .zip baixado contra o publicado na release
    (gerar_checksum.py cria esse arquivo na hora de empacotar).

    A validação de tamanho em download_asset() já cobre a maioria dos
    downloads incompletos; isto cobre o caso raro de corrupção sem mudança
    de tamanho. Se a release não tiver o arquivo de checksum (esquecido na
    publicação, ou release antiga), não bloqueia a atualização — só avisa
    no log, para não travar todo mundo por causa de uma release mal feita."""
    if not checksum_url:
        logger.warning("Release sem %s; pulando verificação de integridade do download.", CHECKSUM_ASSET_NAME)
        return

    try:
        resposta = requests.get(checksum_url, headers={"User-Agent": "geraped-auto-updater"}, timeout=REQUEST_TIMEOUT)
        resposta.raise_for_status()
        esperado = resposta.text.strip().split()[0].lower()
    except (requests.RequestException, IndexError) as exc:
        logger.warning("Não foi possível obter/ler o checksum da release (%s); pulando verificação.", exc)
        return

    obtido = _sha256_de_arquivo(zip_path)
    if obtido.lower() != esperado:
        raise IOError(
            f"Checksum do download não confere (esperado {esperado}, obtido {obtido}). "
            "O arquivo parece ter sido corrompido no download."
        )
    logger.info("Checksum do pacote de atualização confirmado (sha256 ok).")


# ---------------------------------------------------------------------------
# Aplicar atualização
# ---------------------------------------------------------------------------
def fechar_geraped_em_execucao() -> None:
    """Força o encerramento de qualquer GERAPED.exe em execução — o Windows
    não deixa substituir o arquivo de um programa que ainda está rodando.
    Não dá erro se não houver nenhum rodando (o taskkill só falha
    silenciosamente)."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", APP_EXE.name, "/T"],
            capture_output=True, timeout=10,
        )
    except Exception as exc:
        logger.warning("taskkill do GERAPED.exe falhou (%s); seguindo mesmo assim.", exc)
    time.sleep(0.5)  # dá um tempinho pro Windows liberar o handle do arquivo


BACKUP_DIR = BASE_DIR / "_update_backup"


def apply_update(zip_path: Path, new_version: str):
    """Extrai o .zip da nova versão numa pasta de preparo e MESCLA o
    conteúdo no lugar (sobrescreve só os arquivos que vieram no pacote),
    em vez de substituir o GERAPED.exe + _internal inteiros.

    Faz backup individual de cada arquivo que será sobrescrito (ou marca
    que ele não existia, se for novo) antes de aplicar, e restaura tudo
    automaticamente se algo falhar no meio do processo.
    """
    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR, ignore_errors=True)
    if BACKUP_DIR.exists():
        shutil.rmtree(BACKUP_DIR, ignore_errors=True)

    # manifesto: (caminho relativo a BASE_DIR, existia_antes)
    manifesto = []

    def _backup_e_aplicar(origem: Path, destino: Path, nome_relativo: str):
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            backup_destino = BACKUP_DIR / nome_relativo
            backup_destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destino, backup_destino)
            manifesto.append((nome_relativo, True))
        else:
            manifesto.append((nome_relativo, False))
        shutil.copy2(origem, destino)

    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(STAGING_DIR)

        staged_exe = STAGING_DIR / "GERAPED.exe"
        if not staged_exe.is_file():
            raise IOError("Pacote de atualização inválido: GERAPED.exe não encontrado no .zip baixado.")

        staged_internal = STAGING_DIR / "_internal"
        arquivos_internal = (
            [p.relative_to(staged_internal) for p in staged_internal.rglob("*") if p.is_file()]
            if staged_internal.is_dir()
            else []
        )

        fechar_geraped_em_execucao()

        _backup_e_aplicar(staged_exe, APP_EXE, "GERAPED.exe")
        for relativo in arquivos_internal:
            _backup_e_aplicar(
                staged_internal / relativo, APP_INTERNAL / relativo, str(Path("_internal") / relativo)
            )

        VERSION_FILE.write_text(new_version, encoding="utf-8")
    except Exception:
        if manifesto:
            for nome_relativo, existia in reversed(manifesto):
                destino = BASE_DIR / nome_relativo
                if existia:
                    shutil.copy2(BACKUP_DIR / nome_relativo, destino)
                elif destino.exists():
                    destino.unlink()
                    pasta = destino.parent
                    while pasta != BASE_DIR and pasta.is_dir() and not any(pasta.iterdir()):
                        pasta.rmdir()
                        pasta = pasta.parent
        else:
            messagebox.showwarning(
                "Atualização",
                "Falha ao aplicar a atualização e nenhum backup foi encontrado.\n"
                "Nada foi substituído.",
            )
        raise
    finally:
        shutil.rmtree(STAGING_DIR, ignore_errors=True)
        shutil.rmtree(BACKUP_DIR, ignore_errors=True)


def log_error(context: str, exc: Exception):
    logger.error(context, exc_info=exc)


def launch_app():
    if APP_EXE.exists():
        subprocess.Popen([str(APP_EXE)], cwd=str(BASE_DIR))
    else:
        messagebox.showerror("Erro", "GERAPED.exe não encontrado.")


# ---------------------------------------------------------------------------
# Interface gráfica (só aparece se houver atualização)
# ---------------------------------------------------------------------------
class UpdaterUI:
    def __init__(self, local_version, remote_version, release):
        self.release = release
        self._indeterminate_running = False

        self.root = ttk.Window(themename="litera", iconphoto=None)
        tema.aplicar(self.root)
        self.root.title("GERAPED - Atualização disponível")
        self.root.resizable(False, False)
        # atualização obrigatória: não tem como pular, nem fechando a janela
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)
        try:
            self.root.iconbitmap(_caminho_recurso("icone.ico"))
        except Exception:
            pass

        self._imagem_banner = ImageTk.PhotoImage(
            visual.gerar_banner(
                largura=LARGURA_JANELA,
                altura=ALTURA_BANNER,
                cor_inicio=tema.COR_PRIMARIA,
                cor_fim="#1A1C3D",
                cor_destaque=tema.COR_SECUNDARIA,
                icone_path=_caminho_recurso("icone.ico"),
                titulo="Nova versão disponível",
                subtitulo="GERAPED - Gerador de Pedidos",
            )
        )
        ttk.Label(self.root, image=self._imagem_banner, borderwidth=0).pack(fill=X)

        corpo = ttk.Frame(self.root, padding=(24, 18, 24, 20))
        corpo.pack(fill=BOTH, expand=True)

        ttk.Label(corpo, text=f"Versão atual: {local_version}", font=("Segoe UI", 10)).pack(anchor="w")
        ttk.Label(corpo, text=f"Nova versão: {remote_version}", font=("Segoe UI", 10, "bold")).pack(
            anchor="w", pady=(2, 14)
        )

        self.progress = ttk.Progressbar(corpo, orient="horizontal", mode="determinate", bootstyle="secondary")
        self.progress.pack(fill=X, pady=(0, 8))

        self.status_label = ttk.Label(corpo, text="Baixando atualização...", bootstyle="secondary")
        self.status_label.pack(anchor="w")

        self.root.update_idletasks()
        _posicionar_janela(self.root, LARGURA_JANELA, self.root.winfo_reqheight())

    def run(self):
        thread = threading.Thread(target=self._download_and_apply, daemon=True)
        thread.start()
        self.root.mainloop()

    def set_progress(self, percent, downloaded=None, total=None):
        if percent is None:
            self.progress.configure(mode="indeterminate")
            if not self._indeterminate_running:
                self.progress.start(10)
                self._indeterminate_running = True
        else:
            self.progress.configure(mode="determinate")
            self.progress.stop()
            self._indeterminate_running = False
            self.progress["value"] = percent

        if downloaded is not None:
            mb_downloaded = downloaded / (1024 * 1024)
            if total:
                mb_total = total / (1024 * 1024)
                self.set_status(f"Baixando atualização... {percent:.0f}% ({mb_downloaded:.1f} MB / {mb_total:.1f} MB)")
            else:
                self.set_status(f"Baixando atualização... {mb_downloaded:.1f} MB")
        self.root.update_idletasks()

    def set_status(self, text):
        self.status_label.configure(text=text)
        self.root.update_idletasks()

    def finish(self, success: bool, message: str = ""):
        self.root.destroy()
        if not success and message:
            messagebox.showerror("Atualização", message)
        launch_app()

    def _download_and_apply(self):
        tmp_path = None
        try:
            fd, tmp_name = tempfile.mkstemp(dir=str(BASE_DIR), suffix=".zip")
            os.close(fd)
            tmp_path = Path(tmp_name)

            download_asset(
                self.release["asset_url"],
                tmp_path,
                self.release.get("asset_size"),
                lambda p, d, t: self.root.after(0, self.set_progress, p, d, t),
            )
            verificar_checksum(tmp_path, self.release.get("checksum_url"))
            self.root.after(0, self.set_status, "Fechando o GERAPED e aplicando a atualização...")

            apply_update(tmp_path, self.release["tag_name"])

            logger.info("Atualização aplicada com sucesso: %s", self.release["tag_name"])
            self.root.after(0, self.finish, True, "")
        except Exception as exc:
            log_error("Falha ao baixar/aplicar atualização", exc)
            self.root.after(
                0,
                self.finish,
                False,
                f"Não foi possível concluir a atualização. A versão anterior será aberta.\n\nDetalhes: {exc}",
            )
        finally:
            # deixar o .zip temporário aqui seria um vazamento de espaço em
            # disco a cada atualização bem-sucedida
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    log_setup.configurar_logging("launcher.log", BASE_DIR)
    logger.info("Launcher iniciado.")
    local_version = read_local_version()
    release = get_latest_release()

    if release is None:
        # Sem internet, GitHub fora do ar, ou sem asset compatível: segue sem erro.
        logger.info("Sem release disponível; abrindo versão instalada (%s).", local_version)
        launch_app()
        return

    if not is_newer(release["tag_name"], local_version):
        logger.info("Já na versão mais recente (%s); abrindo.", local_version)
        launch_app()
        return

    logger.info("Atualização encontrada: %s -> %s", local_version, release["tag_name"])
    ui = UpdaterUI(local_version, release["tag_name"], release)
    ui.run()


if __name__ == "__main__":
    main()
