import logging
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import ttkbootstrap

import log_setup
import tema
from interface import Janela

logger = logging.getLogger(__name__)


def caminho_recurso(nome):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nome)


def _pasta_executavel():
    """Pasta do GERAPED.exe (modo congelado) ou do próprio main.py (modo dev) - onde
    ficam versao.txt, logs/ etc., ao lado do executável, NUNCA em _MEIPASS (essa é
    temporária e recriada a cada abertura)."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _avisar_se_desatualizado(root) -> None:
    """Rede de segurança para quando o GERAPED.exe é aberto direto, sem passar pelo
    launcher (ex.: atalho fixado errado na barra de tarefas - "Fixar na barra de tarefas"
    a partir da janela já aberta, em vez do atalho da área de trabalho, que fixa o
    launcher). O launcher.py é quem normalmente baixa e aplica a atualização; aqui só
    avisamos, sem baixar nem travar o uso - e falha em silêncio se não conseguir checar
    (sem internet, GitHub fora etc.), do mesmo jeito que o launcher já faz.
    Mesmo padrão usado no ANEXT e no RequerimentoGERID."""
    def _checar():
        try:
            from launcher import get_latest_release, is_newer, read_local_version
            release = get_latest_release()
            if release is None or not is_newer(release['tag_name'], read_local_version()):
                return
        except Exception as exc:
            logger.info('Checagem de versão (fora do launcher) não pôde ser concluída: %r', exc)
            return
        root.after(0, lambda: messagebox.showinfo(
            'Nova versão disponível',
            'Há uma versão mais nova do GERAPED disponível.\n\n'
            'Feche o programa e abra pelo atalho da área de trabalho (GERAPED) '
            'para atualizar automaticamente.',
        ))

    threading.Thread(target=_checar, daemon=True).start()


def _ativar_dpi_awareness():
    """No Windows, sem isso o SO estica o bitmap da janela durante o resize,
    deixando sobras pretas na borda. Sem efeito em outros sistemas."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _ativar_cor_barra_titulo(root):
    """Pinta a barra de título nativa do Windows com a mesma cor navy da barra lateral (em
    vez do branco padrão do Windows), pra combinar com o resto da tela - só funciona no
    Windows 11+ (API DWM DWMWA_CAPTION_COLOR, build 22000+); falha em silêncio em versões
    mais antigas do Windows ou outros SOs, ficando com a barra de título padrão."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes

        GA_ROOT = 2
        DWMWA_CAPTION_COLOR = 35
        DWMWA_TEXT_COLOR = 36

        def _bgr(cor_hex):
            r, g, b = int(cor_hex[1:3], 16), int(cor_hex[3:5], 16), int(cor_hex[5:7], 16)
            return r | (g << 8) | (b << 16)

        hwnd = ctypes.windll.user32.GetAncestor(root.winfo_id(), GA_ROOT)
        cor = ctypes.c_int(_bgr(tema.COR_PRIMARIA))
        texto = ctypes.c_int(_bgr('#FFFFFF'))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(cor), ctypes.sizeof(cor))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_TEXT_COLOR, ctypes.byref(texto), ctypes.sizeof(texto))
    except Exception:
        pass


if __name__ == '__main__':
    log_setup.configurar_logging('geraped.log', _pasta_executavel())
    logger.info('GERAPED iniciado.')
    _ativar_dpi_awareness()
    LARGURA, ALTURA = 1000, 888

    root = ttkbootstrap.Window(themename='litera')
    root.title('GERAPED - Gerador de Pedidos')
    root.minsize(900, 580)
    try:
        root.iconbitmap(caminho_recurso('icone.ico'))
    except tk.TclError:
        pass

    root.update_idletasks()
    _ativar_cor_barra_titulo(root)
    x = (root.winfo_screenwidth()  - LARGURA) // 2
    # Um pouco acima do centro vertical, para sobrar mais espaço embaixo na tela.
    y = max(20, (root.winfo_screenheight() - ALTURA) // 2 - 60)
    root.geometry(f'{LARGURA}x{ALTURA}+{x}+{y}')

    tema.aplicar(root)
    Janela(root, caminho_recurso)
    _avisar_se_desatualizado(root)
    root.mainloop()
    logger.info('GERAPED encerrado.')
