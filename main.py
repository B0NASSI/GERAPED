import os
import sys
import tkinter as tk

import ttkbootstrap

import tema
from interface import Janela


def caminho_recurso(nome):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nome)


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


if __name__ == '__main__':
    _ativar_dpi_awareness()
    LARGURA, ALTURA = 760, 888

    root = ttkbootstrap.Window(themename='litera')
    root.title('GERAPED - Gerador de Pedidos')
    root.minsize(700, 580)
    try:
        root.iconbitmap(caminho_recurso('icone.ico'))
    except tk.TclError:
        pass

    root.update_idletasks()
    x = (root.winfo_screenwidth()  - LARGURA) // 2
    # Um pouco acima do centro vertical, para sobrar mais espaço embaixo na tela.
    y = max(20, (root.winfo_screenheight() - ALTURA) // 2 - 60)
    root.geometry(f'{LARGURA}x{ALTURA}+{x}+{y}')

    tema.aplicar(root)
    Janela(root, caminho_recurso)
    root.mainloop()
