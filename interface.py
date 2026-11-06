import json
import logging
import math
import os
import re
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from PIL import Image, ImageDraw, ImageFont, ImageTk
from ttkbootstrap.style import Colors

import tema
from teses import TESES, TIPO_BENEFICIO_POR_ESPECIE, nome_para_chave, PARAMETROS_TESE, chave_para_opcao_parametro
from gerador_pedido import gerar_documento, COR_ITEM_PETICAO, _grupo_ja_coberto
from validacao import (
    validar_quantidade, validar_especies, limite_especies_excedido, limitar_especies,
    validar_itens_duplicados, especie_unica_travada, beneficio_subsidiario_pode_herdar_do_principal,
    validar_beneficios_subsidiaria, tese_permite_subsidiario,
    tese_permite_indice_singular, tese_permite_exclusao_ntp, TESE_QUE_LIBERA_NTP, vigencia_libera_ntp,
)
from preferencias import ordenar_chaves_teses, ordenar_nomes_teses, salvar_ordem_teses, ordem_padrao_chaves

logger = logging.getLogger(__name__)

ESPECIES = list(TIPO_BENEFICIO_POR_ESPECIE.keys())
ESPECIES_SUBSIDIARIA = ['B91', 'B92', 'B93', 'B94']

# Teses que aparecem como opção de tese subsidiária (ver GrupoSubsidiario) - só as que
# seguem o formato "do(s) benefício(s) X, motivo" (têm 'motivo_singular') ou Custo cessado.
def _chaves_teses_subsidiarias_compativeis():
    return [
        chave for chave, t in TESES.items()
        if 'motivo_singular' in t or t.get('tipo_clausula') == 'custo_cessado'
    ]

LARGURA_SIDEBAR = 232


def _retangulo_janela(janela):
    """(esquerda, topo, direita, baixo) da janela inteira na tela, com barra de título e bordas."""
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL('user32')
        user32.GetAncestor.restype = wintypes.HWND
        retangulo = wintypes.RECT()
        user32.GetWindowRect(user32.GetAncestor(janela.winfo_id(), 2), ctypes.byref(retangulo))
        return retangulo.left, retangulo.top, retangulo.right, retangulo.bottom
    x, y = janela.winfo_rootx(), janela.winfo_rooty()
    return x, y, x + janela.winfo_width(), y + janela.winfo_height()


def _abrir_aviso_no_centro(janela, abrir):
    """Abre um aviso padrão do Windows (messagebox) exatamente no centro da janela inteira
    do app. Sozinho, o Windows o coloca deslocado para a direita/baixo; aqui um gancho CBT,
    ativo só durante esta chamada, reposiciona a caixa ao ser ativada (antes de aparecer)."""
    if sys.platform != 'win32':
        return abrir()
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL('user32')
    proc_tipo = ctypes.WINFUNCTYPE(wintypes.LPARAM, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    user32.SetWindowsHookExW.argtypes = (ctypes.c_int, proc_tipo, wintypes.HINSTANCE, wintypes.DWORD)
    user32.SetWindowsHookExW.restype = ctypes.c_void_p
    user32.CallNextHookEx.argtypes = (ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    user32.CallNextHookEx.restype = wintypes.LPARAM
    user32.UnhookWindowsHookEx.argtypes = (ctypes.c_void_p,)
    user32.GetAncestor.restype = wintypes.HWND
    WH_CBT, HCBT_ACTIVATE, GA_ROOT = 5, 5, 2
    SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x1, 0x4, 0x10

    janela_app = user32.GetAncestor(janela.winfo_id(), GA_ROOT)
    posicionado = []

    def gancho(codigo, wparam, lparam):
        if codigo == HCBT_ACTIVATE and not posicionado:
            classe = ctypes.create_unicode_buffer(16)
            user32.GetClassNameW(wintypes.HWND(wparam), classe, 16)
            if classe.value == '#32770':  # classe das caixas de diálogo do Windows
                app, caixa = wintypes.RECT(), wintypes.RECT()
                user32.GetWindowRect(janela_app, ctypes.byref(app))
                user32.GetWindowRect(wintypes.HWND(wparam), ctypes.byref(caixa))
                largura, altura = caixa.right - caixa.left, caixa.bottom - caixa.top
                x = (app.left + app.right - largura) // 2
                y = (app.top + app.bottom - altura) // 2
                user32.SetWindowPos(
                    wintypes.HWND(wparam), None, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
                )
                posicionado.append(True)
        return user32.CallNextHookEx(None, codigo, wparam, lparam)

    callback = proc_tipo(gancho)
    id_gancho = user32.SetWindowsHookExW(WH_CBT, callback, None, ctypes.windll.kernel32.GetCurrentThreadId())
    try:
        return abrir()
    finally:
        if id_gancho:
            user32.UnhookWindowsHookEx(id_gancho)


def _avisar(widget, titulo, mensagem):
    janela = widget.winfo_toplevel()
    _abrir_aviso_no_centro(janela, lambda: messagebox.showwarning(titulo, mensagem, parent=janela))


def _informar(widget, titulo, mensagem):
    janela = widget.winfo_toplevel()
    _abrir_aviso_no_centro(janela, lambda: messagebox.showinfo(titulo, mensagem, parent=janela))


def _erro(widget, titulo, mensagem):
    janela = widget.winfo_toplevel()
    _abrir_aviso_no_centro(janela, lambda: messagebox.showerror(titulo, mensagem, parent=janela))


def _confirmar(widget, titulo, mensagem):
    janela = widget.winfo_toplevel()
    return _abrir_aviso_no_centro(janela, lambda: messagebox.askyesno(titulo, mensagem, parent=janela))


# RASCUNHO - conteúdo do "Manual rápido" (ver _mostrar_manual). Cobre as regras que mais
# geram dúvida/erro na prática (subsidiária, espécie x quantidade, item repetido) - revisar
# e ajustar o texto antes de considerar pronto pra usuário final.
TEXTO_MANUAL = """\
GERAPED — Gerador de Pedidos

Ferramenta da equipe de revisão de insumos do FAP

Rodriguez & Sousa Advogados Associados


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMO FUNCIONA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Cada "Pedido" na tela monta o texto de UM pedido de exclusão da
petição inicial:

  1. Escolha a tese principal
  2. Informe a quantidade de benefícios e a(s) espécie(s)
  3. Informe o item da petição inicial a que esse pedido se refere
  4. Clique em "Gerar Word" quando todos os pedidos estiverem prontos

Use "+ Adicionar pedido" para montar vários pedidos de uma vez -
todos entram no mesmo documento Word, na ordem em que aparecem
na tela.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CARREGAR PETIÇÃO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"Carregar petição" lê a petição inicial (.docx) e preenche os
pedidos sozinho: tese, item, quantidade, espécie(s) e tabela. A
leitura é feita no seu computador, nada é enviado para fora.

  1. Clique em "Carregar petição" e escolha o arquivo .docx
  2. Leia a janela "Petição carregada": ela mostra o que precisa
     de conferência
  3. Confira cada pedido na tela e ajuste o que for preciso
  4. Clique em "Gerar Word"

O programa grava um LOG de cada petição carregada, com o porquê de
cada tese e de cada decisão. Para abri-lo, aperte CTRL+L (sem petição
carregada, abre a pasta dos logs). Útil para investigar um pedido
estranho.

ATENÇÃO: CONFIRA SEMPRE. O programa é um auxílio e pode errar;
não confie cegamente nele. Revise todos os pedidos (tese, item,
quantidade, espécies e tabela) contra a petição antes de gerar o
Word. A responsabilidade pela conferência é sua.

O programa sugere, você decide: nada é gerado sem o seu clique.

O nome da petição carregada fica no alto da tela. O botão
"Rever apontamentos" ao lado dele reabre a janela de conferência
quando você quiser.

A tabela de cada pedido vai junto no Word. Para tirá-la de um
pedido, desmarque "Incluir a tabela do pedido".

Na janela de conferência:
  - "Precisa da sua atenção": pedidos com pendência (ex.: tese com
    baixa confiança, parâmetro a escolher, vigência não encontrada)
  - "Seções não classificadas": o programa não reconheceu a tese;
    se houver pedido, adicione à mão
  - "Também aparecem no texto": teses citadas no corpo da petição
    sem uma seção própria; só confira se faltou algum pedido

ATENÇÃO: as teses ERRO DE MASSA SALARIAL e ERRO DE VÍNCULOS ainda
estão em construção e podem apresentar erros. Confira esses pedidos
com cuidado.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TESE PRINCIPAL X TESE SUBSIDIÁRIA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"Possui pedido subsidiário?" adiciona uma cláusula alternativa,
pro caso de o juiz não acatar a tese principal.

  - Uma tese subsidiária sem nenhum benefício informado vale pra
    TODOS os benefícios do pedido principal.
  - Ao informar um benefício específico numa tese subsidiária, o
    número dele é obrigatório.
  - Uma tese subsidiária, sozinha, não pode citar mais benefícios
    do que a quantidade do pedido principal.

Algumas teses NÃO admitem pedido subsidiário (o texto delas não
comporta essa estrutura) - o checkbox fica desabilitado para:
CAT NÃO VINCULADA, NTP DUPLICADO, CAT DUPLICADA, ERRO DE MASSA
SALARIAL, ERRO DE VÍNCULOS, ROTATIVIDADE, PRESCRIÇÃO QUINQUENAL
e CONTESTAÇÃO ADMINISTRATIVA.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUANTIDADE X ESPÉCIE(S) DO BENEFÍCIO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Não dá pra marcar mais espécies do que a quantidade informada
(ex: quantidade 2 aceita no máximo 2 espécies marcadas).

Algumas teses restringem quais espécies podem ser usadas (ex:
CONVERTIDO só aceita B31/B36) ou nem usam espécie/quantidade (ex:
ROTATIVIDADE, NTP DUPLICADO) - nesses casos o campo correspondente
fica desabilitado na tela.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ITEM DO PEDIDO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Cada pedido PRINCIPAL precisa referenciar um item diferente da
petição inicial - o GERAPED avisa se dois pedidos principais usarem
o mesmo item. Pedidos subsidiários ficam de fora dessa checagem
(é comum retomarem o item do pedido principal).


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ORDEM E HISTÓRICO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"Ordem" define em que sequência as teses aparecem na lista de
"Tese principal" - útil pra deixar as mais usadas no topo. "Restaurar
padrão" volta pra ordem definida pelo escritório.

"Histórico" lista os últimos documentos Word gerados nesta máquina,
com atalho pra reabrir o arquivo.
"""


_INDICADORES = {}


def _indicadores(widget):
    """Imagens de caixa de seleção e botão de opção - mesma receita do ttkbootstrap
    (create_checkbutton_assets/create_radiobutton_assets), já sobre o fundo branco do card e
    com largura que reproduz o espaçamento do indicador do ttk."""
    if _INDICADORES:
        return _INDICADORES
    fator = float(widget.tk.call('tk', 'scaling')) / 1.33398982438864281
    lado, largura = math.ceil(14 * fator), math.ceil(18 * fator)
    fundo, cor, marca = tema.COR_FUNDO, tema.COR_PRIMARIA, '#FFFFFF'
    borda = Colors.make_transparent(0.4, tema.COR_TEXTO, fundo)
    apagado = Colors.make_transparent(0.3, tema.COR_TEXTO, fundo)
    fonte = ImageFont.truetype('seguisym.ttf', 120)

    def gerar(desenhar):
        grande = Image.new('RGBA', (134, 134))
        desenhar(ImageDraw.Draw(grande))
        tela = Image.new('RGBA', (largura, lado), fundo)
        tela.alpha_composite(grande.resize((lado, lado), Image.LANCZOS))
        return ImageTk.PhotoImage(tela.convert('RGB'))

    quadrado = dict(xy=[2, 2, 132, 132], radius=16)
    _INDICADORES['caixa'] = {
        'off': gerar(lambda d: d.rounded_rectangle(**quadrado, outline=borda, width=6, fill=fundo)),
        'on': gerar(lambda d: (d.rounded_rectangle(**quadrado, fill=cor, outline=cor, width=3),
                               d.text((20, -20), '✓', font=fonte, fill=marca))),
        'dis': gerar(lambda d: d.rounded_rectangle(**quadrado, outline=apagado, width=3)),
        'dis_on': gerar(lambda d: (d.rounded_rectangle(**quadrado, fill=apagado, outline=apagado, width=3),
                                   d.text((20, -20), '✓', font=fonte, fill=fundo))),
    }
    circulo = [1, 1, 133, 133]
    _INDICADORES['opcao'] = {
        'off': gerar(lambda d: d.ellipse(circulo, outline=borda, width=6, fill=fundo)),
        'on': gerar(lambda d: (d.ellipse(circulo, fill=cor), d.ellipse([40, 40, 94, 94], fill=marca))),
        'dis': gerar(lambda d: d.ellipse(circulo, outline=apagado, width=3, fill=fundo)),
        'dis_on': gerar(lambda d: (d.ellipse(circulo, fill=apagado), d.ellipse([40, 40, 94, 94], fill=fundo))),
    }
    _INDICADORES['apagado'] = apagado
    return _INDICADORES


class _IndicadorLeve:
    """Checkbutton/Radiobutton do tk clássico com as imagens do tema no lugar do indicador.
    Mesma aparência do ttk, mas ~14x mais barato de redesenhar no Windows: com dezenas deles
    na tela, os do ttk deixavam redimensionar e adicionar pedidos/benefícios lentos."""

    _TIPO = None

    def __init__(self, parent, **kw):
        indicadores = _indicadores(parent)
        self._imagens = indicadores[self._TIPO]
        self._apagado = indicadores['apagado']
        self._desabilitado = False
        super().__init__(
            parent, image=self._imagens['off'], selectimage=self._imagens['on'], compound='left',
            indicatoron=False, font=('Segoe UI', 10), foreground=tema.COR_TEXTO,
            activeforeground=tema.COR_TEXTO, background=tema.COR_FUNDO,
            activebackground=tema.COR_FUNDO, selectcolor=tema.COR_FUNDO, borderwidth=0,
            relief='flat', offrelief='flat', overrelief='flat', highlightthickness=0,
            padx=0, pady=0, tristatevalue='\x00', cursor='arrow', autostyle=False, **kw,
        )
        for evento in ('<Button-1>', '<ButtonRelease-1>', '<space>'):
            self.bind(evento, lambda e: 'break' if self._desabilitado else None)

    def configure(self, cnf=None, **kw):
        # "disabled" de verdade faz o Tk pontilhar a imagem - aqui o estado é simulado:
        # imagem e texto apagados + cliques/teclado ignorados.
        if 'state' in kw:
            self._desabilitado = kw.pop('state') == 'disabled'
            sufixo = 'dis' if self._desabilitado else ''
            cor = self._apagado if self._desabilitado else tema.COR_TEXTO
            kw.update(
                image=self._imagens[sufixo or 'off'], selectimage=self._imagens[f'{sufixo}_on' if sufixo else 'on'],
                foreground=cor, activeforeground=cor, takefocus=0 if self._desabilitado else 1,
            )
        return super().configure(cnf, **kw)

    config = configure


class CaixaSelecao(_IndicadorLeve, tk.Checkbutton):
    _TIPO = 'caixa'


class BotaoOpcao(_IndicadorLeve, tk.Radiobutton):
    _TIPO = 'opcao'


# Widgets do tk clássico para a página Pedidos (dentro dos cards brancos): 2-3x mais
# baratos de redesenhar no Windows que os equivalentes ttk, com cores/fontes do tema.
FONTE = ('Segoe UI', 10)
COR_BORDA_CAMPO = tema.CORES['border']


def _rotulo(pai, texto='', ajuda=False, fundo=tema.COR_FUNDO, cor=None, fonte=None, **kw):
    return tk.Label(
        pai, text=texto, background=fundo,
        foreground=cor or (tema.COR_AJUDA if ajuda else tema.COR_TEXTO),
        font=fonte or (('Segoe UI', 9) if ajuda else FONTE), autostyle=False, **kw,
    )


def _campo(pai, largura):
    return tk.Entry(
        pai, width=largura, font=FONTE, relief='flat', borderwidth=5, background=tema.COR_FUNDO,
        foreground=tema.COR_TEXTO, insertbackground=tema.COR_TEXTO, highlightthickness=1,
        highlightbackground=COR_BORDA_CAMPO, highlightcolor=tema.COR_PRIMARIA,
        selectbackground=tema.COR_PRIMARIA, selectforeground='#FFFFFF', autostyle=False,
    )


def _escurecer(cor):
    return Colors.update_hsv(cor, vd=-0.12)


def _botao(pai, texto, comando, cor=tema.COR_PRIMARIA, padx=14, estilo='contorno', fundo=tema.COR_FUNDO):
    """Botão feito de Label clicável (no Windows o tk.Button não desenha a borda de
    highlight). Estilos, espelhando os bootstyles usados antes:
    'contorno' (texto/borda na cor, preenche ao passar o mouse), 'cheio' (fundo na cor),
    'link' (só texto) e 'suave' (fundo cinza-claro)."""
    branco = '#FFFFFF'
    normal, ativo = {
        'contorno': ((cor, fundo, cor), (branco, cor, cor)),
        'cheio': ((branco, cor, cor), (branco, _escurecer(cor), _escurecer(cor))),
        'link': ((cor, fundo, fundo), (_escurecer(cor), fundo, fundo)),
        'suave': ((tema.COR_TEXTO, tema.COR_FUNDO_SUAVE, tema.COR_FUNDO_SUAVE),
                  (tema.COR_TEXTO, _escurecer(tema.COR_FUNDO_SUAVE), _escurecer(tema.COR_FUNDO_SUAVE))),
    }[estilo]
    botao = tk.Label(
        pai, text=texto, font=FONTE, highlightthickness=1, padx=padx, pady=6, cursor='hand2',
        autostyle=False,
    )

    def aplicar(cores):
        texto_cor, fundo_cor, borda = cores
        botao.configure(foreground=texto_cor, background=fundo_cor, highlightbackground=borda, highlightcolor=borda)

    def soltar(evento):
        if 0 <= evento.x < botao.winfo_width() and 0 <= evento.y < botao.winfo_height():
            comando()

    aplicar(normal)
    botao.bind('<Enter>', lambda e: aplicar(ativo))
    botao.bind('<Leave>', lambda e: aplicar(normal))
    botao.bind('<ButtonRelease-1>', soltar)
    return botao


def _linha_divisoria(pai):
    return tk.Frame(pai, height=1, background=COR_BORDA_CAMPO, autostyle=False)


def _quadro(pai, fundo=tema.COR_FUNDO, **kw):
    return tk.Frame(pai, background=fundo, autostyle=False, **kw)


def _ignorar_scroll(event):
    """Bind de <MouseWheel> para comboboxes fechados: rolar o mouse exatamente sobre o
    campo não faz nada (nem troca o valor, nem rola a lista de pedidos)."""
    return 'break'


# True enquanto alguma lista suspensa de tese estiver aberta. A lista é uma janela própria,
# sobreposta na tela numa posição fixa - se a página rolar por baixo dela enquanto está
# aberta, o item destacado na lista fica dessincronizado do pedido que o usuário está vendo
# (a seleção acaba caindo no pedido errado). Por isso a página não pode rolar nesse momento.
_LISTA_TESE_ABERTA = False


def _caminho_recurso(nome):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nome)


def _caminho_historico():
    base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'historico.json')


def _retangulo_monitor_atual(root):
    """(esquerda, topo, direita, baixo) do monitor do Windows que contém root - usado no
    lugar de winfo_screenwidth()/height(), que no Tk sempre reportam as dimensões do
    monitor PRINCIPAL, mesmo com o app aberto num monitor secundário. Sem isso, janelas
    secundárias (Ordem, Histórico, Notas de atualização...) eram empurradas de volta pro
    monitor principal em setups com múltiplos monitores. None se não for Windows ou algo
    der errado (nesse caso quem chama cai de volta em winfo_screenwidth/height)."""
    if sys.platform != 'win32':
        return None
    try:
        import ctypes

        class RECT(ctypes.Structure):
            _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                        ('right', ctypes.c_long), ('bottom', ctypes.c_long)]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [('cbSize', ctypes.c_ulong), ('rcMonitor', RECT),
                        ('rcWork', RECT), ('dwFlags', ctypes.c_ulong)]

        MONITOR_DEFAULTTONEAREST = 2
        hwnd = root.winfo_id()
        monitor = ctypes.windll.user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        r = info.rcWork
        return r.left, r.top, r.right, r.bottom
    except Exception:
        return None


def _aplicar_identidade(janela):
    """Janelas filhas (Toplevel) com o ícone do GERAPED (senão o Windows mostra o ícone padrão do Tk)."""
    try:
        janela.iconbitmap(_caminho_recurso('icone.ico'))
    except tk.TclError:
        pass


# janelas de apoio (conferência da petição, manual, notas) abrem um pouco à direita do centro, sempre no mesmo lugar
DESLOCAMENTO_JANELAS = 110


def _centralizar_janela(janela, root, largura, altura, deslocamento=0):
    janela.update_idletasks()
    _aplicar_identidade(janela)
    x = root.winfo_x() + (root.winfo_width() - largura) // 2 + deslocamento
    y = root.winfo_y() + (root.winfo_height() - altura) // 2
    # Evita que a janela fique cortada quando a janela principal está pequena
    # ou próxima da borda da tela (ex: com apenas 1 pedido, root fica bem baixo).
    # A barra de título fica acima da coordenada y informada - por isso a margem
    # no topo, senão ela é cortada pelo limite da tela.
    margem_topo = 40
    retangulo = _retangulo_monitor_atual(root)
    if retangulo:
        esquerda, topo, direita, baixo = retangulo
        x = max(esquerda, min(x, direita - largura))
        y = max(topo + margem_topo, min(y, baixo - altura))
    else:
        x = max(0, min(x, janela.winfo_screenwidth() - largura))
        y = max(margem_topo, min(y, janela.winfo_screenheight() - altura))
    janela.geometry(f'{largura}x{altura}+{x}+{y}')


_MARCADOR_ITEM = re.compile(r'^(-|\d+\.)\s+')


def _preparar_paragrafos_notas(texto):
    """Reagrupa o texto (quebrado em linhas fixas no .txt) em parágrafos lógicos, pra poder
    rejustificar do zero na largura real da janela. Linhas em branco separam blocos; dentro
    de um bloco, uma linha começando com "- " ou "1. " (lista numerada, usada no Manual
    rápido) inicia um item de lista, e as linhas indentadas seguintes são continuação do
    mesmo item (juntadas por espaço)."""
    blocos = []
    bloco_atual = []
    item_atual = None
    for linha_bruta in texto.split('\n'):
        linha = linha_bruta.rstrip()
        if not linha.strip():
            if item_atual is not None:
                bloco_atual.append(item_atual)
                item_atual = None
            if bloco_atual:
                blocos.append(bloco_atual)
                bloco_atual = []
            continue
        casado = _MARCADOR_ITEM.match(linha.lstrip())
        if casado:
            if item_atual is not None:
                bloco_atual.append(item_atual)
            marcador = casado.group(0)
            item_atual = (marcador, linha.lstrip()[len(marcador):].strip())
        elif item_atual is not None:
            item_atual = (item_atual[0], item_atual[1] + ' ' + linha.strip())
        else:
            item_atual = ('', linha.strip())
    if item_atual is not None:
        bloco_atual.append(item_atual)
    if bloco_atual:
        blocos.append(bloco_atual)
    return blocos


def _dividir_manual(texto):
    """Separa TEXTO_MANUAL em segmentos ('vazio'|'regra'|'titulo'|'prosa') - as linhas de
    régua (só "━") e de título de seção NUNCA entram no fluxo de justificação (ver
    _mostrar_manual): são estruturais, não prosa, e tentar justificá-las ou deixar que se
    misturem com o parágrafo vizinho (por estarem coladas, sem linha em branco entre
    régua/título/régua) resultava em texto quebrado/espremido. Só o texto "normal" vira
    parágrafo prosa, passível de reflow/justificação.

    Um título é identificado por estar tudo em maiúsculas E vir logo após uma linha de
    régua (o padrão real dos cabeçalhos: régua/título/régua) - não basta estar em
    maiúsculas: uma lista de nomes de teses (ex: "CAT NÃO VINCULADA, NTP DUPLICADO...")
    também é toda maiúscula, mas é prosa comum e precisa ser reflowada/justificada como
    qualquer outro parágrafo, não tratada como título."""
    segmentos = []
    prosa_atual = []
    ultimo_tipo = None

    def fecha_prosa():
        if prosa_atual:
            segmentos.append(('prosa', '\n'.join(prosa_atual)))
            prosa_atual.clear()

    for linha_bruta in texto.split('\n'):
        linha = linha_bruta.rstrip()
        stripped = linha.strip()
        if not stripped:
            fecha_prosa()
            segmentos.append(('vazio', ''))
            tipo = 'vazio'
        elif set(stripped) == {'━'}:
            fecha_prosa()
            segmentos.append(('regra', stripped))
            tipo = 'regra'
        elif ultimo_tipo == 'regra' and stripped == stripped.upper() and any(c.isalpha() for c in stripped):
            fecha_prosa()
            segmentos.append(('titulo', stripped))
            tipo = 'titulo'
        else:
            prosa_atual.append(linha)
            tipo = 'prosa'
        ultimo_tipo = tipo
    fecha_prosa()
    return segmentos


def _justificar_linha(palavras, fonte, largura_disponivel):
    """Insere espaços extras entre as palavras pra esticar a linha até largura_disponivel -
    aproximado (fonte proporcional, não monoespaçada), mas visualmente razoável."""
    if len(palavras) == 1:
        return palavras[0]
    largura_base = fonte.measure(' '.join(palavras))
    largura_espaco = fonte.measure(' ') or 1
    espacos_extra = max(0, round((largura_disponivel - largura_base) / largura_espaco))
    n_vaos = len(palavras) - 1
    base, resto = divmod(espacos_extra, n_vaos)
    partes = [palavras[0]]
    for i in range(1, len(palavras)):
        partes.append(' ' * (1 + base + (1 if (i - 1) < resto else 0)))
        partes.append(palavras[i])
    return ''.join(partes)


def _justificar_paragrafo(prefixo, texto_paragrafo, fonte, largura_px):
    """Quebra texto_paragrafo em linhas que caibam em largura_px (descontado o prefixo, ex:
    "- ") e justifica todas as linhas exceto a última (convenção usual de texto
    justificado - a última linha de um parágrafo fica alinhada à esquerda)."""
    palavras = texto_paragrafo.split()
    largura_disponivel = largura_px - fonte.measure(prefixo)

    linhas_palavras, linha = [], []
    for palavra in palavras:
        candidata = linha + [palavra]
        if fonte.measure(' '.join(candidata)) <= largura_disponivel or not linha:
            linha = candidata
        else:
            linhas_palavras.append(linha)
            linha = [palavra]
    if linha:
        linhas_palavras.append(linha)

    linhas_finais = []
    for i, palavras_linha in enumerate(linhas_palavras):
        marca = prefixo if i == 0 else ' ' * len(prefixo)
        eh_ultima = i == len(linhas_palavras) - 1
        if eh_ultima or len(palavras_linha) == 1:
            linhas_finais.append(marca + ' '.join(palavras_linha))
        else:
            linhas_finais.append(marca + _justificar_linha(palavras_linha, fonte, largura_disponivel))
    return linhas_finais


def _cor_run(run):
    """Retorna a cor RGB do run como string hex, ou None se não houver cor explícita."""
    try:
        cor = run.font.color.rgb
    except AttributeError:
        return None
    return str(cor) if cor is not None else None


def _mostrar_preview(root, doc, ao_salvar):
    janela = tk.Toplevel(root)
    janela.title('Preview — Pedidos gerados')
    _centralizar_janela(janela, root, 740, 680)
    janela.transient(root)
    janela.grab_set()
    janela.resizable(True, True)

    ttk.Label(janela, text='Confira o texto antes de salvar:', font=('Segoe UI', 10, 'bold')).pack(
        anchor='w', padx=16, pady=(14, 6),
    )

    frame_texto = ttk.Frame(janela, padding=(16, 0, 16, 0))
    frame_texto.pack(fill='both', expand=True)

    sb = ttk.Scrollbar(frame_texto)
    sb.pack(side='right', fill='y')
    txt = tk.Text(
        frame_texto, wrap='word', font=('Segoe UI', 10),
        yscrollcommand=sb.set, relief='flat', borderwidth=1, padx=10, pady=10,
    )
    sb.configure(command=txt.yview)
    txt.pack(side='left', fill='both', expand=True)

    txt.tag_configure('bold', font=('Segoe UI', 10, 'bold'))
    txt.tag_configure('italic', font=('Segoe UI', 10, 'italic'))
    txt.tag_configure('bold_italic', font=('Segoe UI', 10, 'bold italic'))
    txt.tag_configure('cor_item', foreground=f'#{COR_ITEM_PETICAO}')

    txt.tag_configure('tabela', font=('Consolas', 9), lmargin1=30, lmargin2=30, foreground='#444444')
    # percorre o corpo na ordem: parágrafos do pedido e (se houver) a tabela que vem logo depois
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    blocos = []
    for el in doc.element.body:
        if el.tag.endswith('}p'):
            par = Paragraph(el, doc._body)
            if par.text.strip():
                blocos.append(par)
        elif el.tag.endswith('}tbl'):
            blocos.append(Table(el, doc._body))
    for i, bloco in enumerate(blocos):
        if isinstance(bloco, Table):
            for linha in bloco.rows:
                celulas = []
                for c in linha.cells:
                    if not celulas or c.text != celulas[-1] or not c.text:
                        celulas.append(c.text)
                txt.insert('end', '  ' + '  |  '.join(celulas) + '\n', ('tabela',))
        else:
            for run in bloco.runs:
                if not run.text:
                    continue
                tags = []
                if run.bold and run.italic:
                    tags.append('bold_italic')
                elif run.bold:
                    tags.append('bold')
                elif run.italic:
                    tags.append('italic')
                if _cor_run(run) == str(COR_ITEM_PETICAO):
                    tags.append('cor_item')
                txt.insert('end', run.text, tuple(tags))
        if i < len(blocos) - 1:
            txt.insert('end', '\n' if isinstance(bloco, Table) else '\n\n')

    txt.config(state='disabled')

    ttk.Separator(janela).pack(fill='x', pady=(8, 0))
    botoes = ttk.Frame(janela, padding=(16, 10))
    botoes.pack(fill='x')
    ttk.Button(botoes, text='Fechar', command=janela.destroy, bootstyle='secondary-outline').pack(side='left')
    ttk.Button(
        botoes, text='Salvar documento', bootstyle='secondary',
        command=lambda: [janela.destroy(), ao_salvar()],
    ).pack(side='right')


def _reconstruir_combo_parametro(frame_parametro, combo_tese, label_widget=None):
    """Recria o campo extra da tese selecionada dentro de frame_parametro - um combobox
    (tese com 'parametro') ou um campo de texto livre (tese com 'campo_texto'). Retorna o
    widget criado (ambos suportam .get()), ou None se a tese não precisar de campo extra.

    Se label_widget for informado (BlocoPedido, que já tem uma coluna de rótulos alinhada
    em grid), o rótulo é escrito nele em vez de criar um Label solto dentro de
    frame_parametro - isso mantém o campo alinhado com os demais da coluna."""
    for widget in frame_parametro.winfo_children():
        widget.destroy()

    tese = TESES.get(nome_para_chave(combo_tese.get()))
    if not tese:
        if label_widget is not None:
            label_widget.configure(text='')
        return None

    parametro_id = tese.get('parametro')
    campo_texto = tese.get('campo_texto')
    rotulo = PARAMETROS_TESE[parametro_id]['label'] if parametro_id else (campo_texto['label'] if campo_texto else '')

    if label_widget is not None:
        label_widget.configure(text=rotulo)
    elif rotulo:
        _rotulo(frame_parametro, rotulo).pack(side='left', padx=(0, 6))

    if parametro_id:
        config = PARAMETROS_TESE[parametro_id]
        nomes_opcoes = list(config['opcoes'].values())
        combo_parametro = ttk.Combobox(frame_parametro, values=nomes_opcoes, state='readonly', width=38)
        combo_parametro.pack(side='left')
        if nomes_opcoes:
            combo_parametro.current(0)
        combo_parametro.bind('<MouseWheel>', _ignorar_scroll)
        return combo_parametro

    if campo_texto:
        entry_texto = _campo(frame_parametro, 42)
        entry_texto.pack(side='left')
        return entry_texto

    if label_widget is not None:
        label_widget.configure(text='')
    return None


def _carregar_logo_para_fundo_escuro(caminho, altura):
    """Logo do escritório para usar sobre o azul-marinho: o azul do logo vira
    branco e o laranja do "&" fica como está."""
    imagem = Image.open(caminho).convert('RGBA')
    imagem = imagem.resize((max(1, int(imagem.width * altura / imagem.height)), altura), Image.LANCZOS)
    pixels = imagem.load()
    for y in range(imagem.height):
        for x in range(imagem.width):
            r, g, b, a = pixels[x, y]
            laranja = r > 180 and 60 < g < 170 and b < 90
            if a and not laranja:
                pixels[x, y] = (255, 255, 255, a)
    return ImageTk.PhotoImage(imagem)


def _criar_cartao(parent, titulo, padding=14, **_ignorados):
    """Card com título DENTRO do quadrado, encostado na borda superior (visual igual ao
    ttk.Labelframe nativo usado antes) - mas sem usar Labelframe de verdade, que tem um bug
    de renderização real (reproduzido isolado, fora deste app, com qualquer tema
    ttkbootstrap): o traço da borda antes do texto do título simplesmente não desenha.
    Inofensivo enquanto o fundo ao redor do card era branco igual ao card (o padrão usado
    em todo o app antes) - ficou visível assim que a página passou a ter um fundo cinza ao
    redor dos cards (ver Pagina.TFrame). Aqui a borda é a do próprio ttk.Frame (estilo
    Cartao.TFrame) - como nada nunca desenha "por cima" dela, o bug não se aplica. O título
    usa place(), então não conflita com o grid/pack que os filhos do card usarem.

    Tentativa anterior usava cantos arredondados desenhados à mão num Canvas - abandonada:
    causava bugs visuais reais (borda invisível, corrida de redesenho em cards aninhados
    tipo "Tese subsidiária" dentro de "Pedido") sem terminar visualmente melhor que a borda
    quadrada simples. Card quadrado, mas 100% confiável, ganha da alternativa "bonita" mas
    quebrada.

    Retorna (casca, conteudo, rotulo_titulo): 'casca' é o que quem chama empacota/destrói;
    'conteudo' (hoje o mesmo widget que a casca) é o parent dos filhos do card;
    'rotulo_titulo' é pra poder trocar o texto do título (ex: renumerar "Pedido 2" ->
    "Pedido 1")."""
    # Um só widget para fundo, borda e conteúdo (antes eram 4 frames aninhados): no Windows,
    # cada nível de frame que muda de tamanho redesenha de novo tudo o que está dentro dele.
    # O título fica com place() no topo, e o padding superior reserva o espaço dele - assim
    # quem chama pode usar grid ou pack direto na casca.
    casca = ttk.Frame(parent, style="Cartao.TFrame")
    rotulo_titulo = tk.Label(
        casca, text=titulo, background=tema.COR_FUNDO, foreground=tema.COR_PRIMARIA,
        font=('Segoe UI', 11, 'bold'), borderwidth=0, padx=0, pady=0, autostyle=False,
    )
    borda = 1
    rotulo_titulo.place(x=borda + padding, y=borda + padding - 4, bordermode='ignore')
    casca.configure(padding=(padding, padding - 4 + rotulo_titulo.winfo_reqheight() + 8, padding, padding))
    return casca, casca, rotulo_titulo


class ComboboxPesquisavel(ttk.Combobox):
    """Combobox que filtra a lista de valores conforme o usuário digita."""

    def __init__(self, parent, valores, **kwargs):
        super().__init__(parent, **kwargs)
        self._valores = list(valores)
        self['values'] = self._valores
        self.bind('<KeyRelease>', self._ao_digitar)
        self.bind('<<ComboboxSelected>>', self._ao_selecionar)
        self.bind('<FocusOut>', self._ao_perder_foco)
        self.bind('<Button-1>', self._ao_clicar, add='+')
        self.bind('<MouseWheel>', _ignorar_scroll)
        self.bind('<Escape>', self._ao_fechar_lista, add='+')

    def atualizar_valores(self, novos_valores):
        """Troca a lista de opções (ex: nova ordem de teses salva em Ordem), preservando o
        valor atualmente selecionado."""
        selecionado = self.get()
        self._valores = list(novos_valores)
        self['values'] = self._valores
        self.set(selecionado)

    def _marcar_lista_aberta(self):
        global _LISTA_TESE_ABERTA
        _LISTA_TESE_ABERTA = True

    def _marcar_lista_fechada(self):
        global _LISTA_TESE_ABERTA
        _LISTA_TESE_ABERTA = False

    def _ao_clicar(self, event):
        self.tk.call('ttk::combobox::Post', self)
        self._marcar_lista_aberta()

    def _ao_fechar_lista(self, _event):
        self._marcar_lista_fechada()

    def _ao_digitar(self, event):
        if event.keysym in ('Up', 'Down', 'Return', 'Escape', 'Tab'):
            return
        texto = self.get().strip().lower()
        filtrados = [v for v in self._valores if texto in v.lower()] if texto else self._valores
        if filtrados == getattr(self, '_ultimos_filtrados', None):
            return  # evita reprocessar a lista quando o filtro não mudou
        self._ultimos_filtrados = filtrados
        self['values'] = filtrados
        if filtrados:
            self.tk.call('ttk::combobox::Post', self)
            self._marcar_lista_aberta()
        else:
            self.tk.call('ttk::combobox::Unpost', self)
            self._marcar_lista_fechada()

    def _ao_selecionar(self, _event):
        self['values'] = self._valores
        self.icursor('end')
        self._marcar_lista_fechada()

    def _ao_perder_foco(self, _event):
        if self.get() not in self._valores:
            self['values'] = self._valores
        self._marcar_lista_fechada()


class LinhaBeneficio:
    def __init__(self, parent, on_remover, especie_travada=None, antes=None):
        self.on_remover = on_remover

        self.frame = _quadro(parent)
        self.frame.pack(fill='x', anchor='w', pady=3, before=antes)

        self.var_especie = tk.StringVar(value='')
        self.radios_especie = {}
        for especie in ESPECIES_SUBSIDIARIA:
            radio = BotaoOpcao(self.frame, text=especie, variable=self.var_especie, value=especie)
            radio.pack(side='left', padx=(0, 10))
            self.radios_especie[especie] = radio

        _rotulo(self.frame, "Nº do benefício:").pack(side='left', padx=(8, 4))
        self.entry_numero = _campo(self.frame, 18)
        self.entry_numero.pack(side='left', padx=(0, 8))

        _botao(self.frame, "×", self._remover, cor=tema.COR_ERRO, padx=10).pack(side='left')

        if especie_travada:
            self.aplicar_travamento(especie_travada)

    def aplicar_travamento(self, especie_travada):
        """Quando a tese principal cita uma só espécie de benefício, a espécie das teses
        subsidiárias fica travada nessa mesma espécie (não faz sentido divergir)."""
        if especie_travada:
            self.var_especie.set(especie_travada)
            estado = 'disabled'
        else:
            estado = 'normal'
        for radio in self.radios_especie.values():
            radio.configure(state=estado)

    def _remover(self):
        self.frame.destroy()
        self.on_remover(self)

    def obter_dados(self):
        especie = self.var_especie.get()
        numero = self.entry_numero.get().strip()
        if not especie and not numero:
            return None
        if not especie:
            raise ValueError('selecione a espécie do benefício.')
        return (especie, numero or None)


class GrupoSubsidiario:
    def __init__(self, parent, on_remover, numero=1, obter_especie_travada=None, antes=None, on_mudar=None):
        self.on_remover = on_remover
        # avisa o BlocoPedido quando os benefícios do grupo mudam (para reclassificar subsidiária x alternativa)
        self._on_mudar = on_mudar or (lambda: None)
        # Consultado a cada novo benefício adicionado, para travar a espécie na mesma da
        # tese principal quando esta citar uma só espécie (ver BlocoPedido).
        self.obter_especie_travada = obter_especie_travada or (lambda: None)
        # teses com 'tipo_clausula' próprio (ex: Rotatividade, Erro de massa salarial) não
        # seguem o formato "do(s) benefício(s) X, motivo" usado aqui, então ficam de fora -
        # exceto Custo cessado, que tem um motivo por tipo (ver _motivo em gerador_pedido.py).
        nomes_teses = ordenar_nomes_teses(_chaves_teses_subsidiarias_compativeis())

        self._casca, self.frame, self._rotulo_titulo = _criar_cartao(parent, f"Tese subsidiária {numero}", padding=12)
        self._casca.pack(fill='x', expand=True, pady=(0, 8), before=antes)
        # Papel desta tese no pedido: SUBSIDIÁRIA ou ALTERNATIVA (título + frase explicativa, sempre visíveis)
        self._cor_titulo = str(self._rotulo_titulo.cget('foreground'))
        self._rotulo_papel = _rotulo(self.frame, '', ajuda=True, wraplength=560, justify='left')
        self._rotulo_papel.pack(anchor='w', pady=(0, 8))

        linha = _quadro(self.frame)
        linha.pack(fill='x', anchor='w')
        _rotulo(linha, "Tese:").grid(row=0, column=0, sticky='w', padx=(0, 6))
        self.combo_tese = ComboboxPesquisavel(linha, valores=nomes_teses, width=38)
        self.combo_tese.grid(row=0, column=1, sticky='w')
        self.combo_tese.bind('<<ComboboxSelected>>', lambda e: self._atualizar_parametro(), add='+')

        _rotulo(linha, "Item da petição:").grid(row=0, column=2, sticky='w', padx=(16, 6))
        self.entry_item = _campo(linha, 10)
        self.entry_item.grid(row=0, column=3, sticky='w')

        self.frame_parametro = _quadro(self.frame)
        self.frame_parametro.pack(fill='x', anchor='w', pady=(8, 0))
        self.combo_parametro = None
        self._atualizar_parametro()

        _rotulo(self.frame, "Benefícios desta tese subsidiária:").pack(anchor='w', pady=(10, 4))
        _rotulo(
            self.frame, "Se todos os benefícios forem subsidiários da mesma tese, não adicione benefícios.",
            ajuda=True, wraplength=560, justify='left',
        ).pack(anchor='w', pady=(0, 6))
        self.linhas_beneficio = []

        # Linhas de benefício entram direto no card, antes do rodapé (sem frame próprio: um
        # nível a menos de aninhamento deixa adicionar/redimensionar bem mais leve).
        rodape = self._rodape = _quadro(self.frame)
        rodape.pack(fill='x', pady=(8, 0))
        _botao(rodape, "+ Adicionar benefício", self.adicionar_beneficio).pack(side='left')
        _botao(rodape, "Remover tese subsidiária", self._remover, cor=tema.COR_ERRO).pack(side='right')

        # Abre sem nenhum benefício adicionado (ver validar_beneficios_subsidiaria): o
        # usuário só adiciona uma linha se quiser especificar benefícios individuais - caso
        # contrário, entende-se que a tese subsidiária vale para todos os benefícios do
        # pedido principal.

    def _atualizar_parametro(self):
        self.combo_parametro = _reconstruir_combo_parametro(self.frame_parametro, self.combo_tese)

    def adicionar_beneficio(self):
        linha = LinhaBeneficio(
            self.frame, on_remover=self._remover_linha_beneficio,
            especie_travada=self.obter_especie_travada(), antes=self._rodape,
        )
        self.linhas_beneficio.append(linha)
        linha.entry_numero.bind('<KeyRelease>', lambda e: self._on_mudar(), add='+')
        linha.var_especie.trace_add('write', lambda *a: self._on_mudar())
        self._on_mudar()

    def _remover_linha_beneficio(self, linha):
        if linha in self.linhas_beneficio:
            self.linhas_beneficio.remove(linha)
        self._on_mudar()

    def dados_para_classificacao(self):
        """Benefícios deste grupo como o gerador os veria (sem validar): sem nenhuma linha = TODOS os
        benefícios do pedido principal."""
        numeros = []
        for linha in self.linhas_beneficio:
            especie, numero = linha.var_especie.get(), linha.entry_numero.get().strip()
            if especie and numero:
                numeros.append((especie, numero))
        return {'todos_beneficios_principal': not self.linhas_beneficio, 'numeros_com_especie': numeros}

    def definir_papel(self, alternativa, posicao):
        """Mostra no cartão se esta tese é SUBSIDIÁRIA ou ALTERNATIVA (regra do escritório: "Subsidiariamente"
        só no começo; as demais teses de um benefício já citado são "ou, alternativamente")."""
        if alternativa:
            self._rotulo_titulo.configure(text=f"Tese alternativa {posicao}  ·  \"ou, alternativamente\"",
                                          foreground=tema.COR_SECUNDARIA)
            self._rotulo_papel.configure(text='ALTERNATIVA: fala de benefício(s) já citado(s) em uma tese anterior. '
                                              'No Word entra como "– ou, alternativamente, ...".')
        else:
            self._rotulo_titulo.configure(text=f"Tese subsidiária {posicao}", foreground=self._cor_titulo)
            if posicao == 1:
                self._rotulo_papel.configure(text='SUBSIDIÁRIA: abre a parte "Subsidiariamente, não sendo esse o '
                                                  'entendimento de V. Exa., ..." do pedido.')
            else:
                self._rotulo_papel.configure(text='SUBSIDIÁRIA (benefício ainda não citado): entra encadeada às '
                                                  'anteriores, sem "ou, alternativamente".')

    def atualizar_travamento_especie(self):
        especie_travada = self.obter_especie_travada()
        for linha in self.linhas_beneficio:
            linha.aplicar_travamento(especie_travada)

    def _remover(self):
        if not _confirmar(
            self.frame,
            'Remover tese subsidiária',
            'Tem certeza que deseja remover esta tese subsidiária? Os dados preenchidos serão perdidos.',
        ):
            return
        self._casca.destroy()
        self.on_remover(self)

    def obter_dados(self, quantidade_principal=None, especies_principal=None):
        tese_key = nome_para_chave(self.combo_tese.get())
        if tese_key is None:
            raise ValueError('selecione a tese.')

        parametro_id = TESES[tese_key].get('parametro')
        parametro_valor = None
        if parametro_id:
            nome_opcao = self.combo_parametro.get() if self.combo_parametro else ''
            parametro_valor = chave_para_opcao_parametro(parametro_id, nome_opcao)
            if parametro_valor is None:
                raise ValueError(f"selecione \"{PARAMETROS_TESE[parametro_id]['label']}\"")

        item_peticao = self.entry_item.get().strip()
        if not item_peticao:
            raise ValueError('informe o item da petição inicial.')

        numeros_com_especie = []
        for linha in self.linhas_beneficio:
            dado = linha.obter_dados()
            if dado is not None:
                numeros_com_especie.append(dado)

        if numeros_com_especie:
            validar_beneficios_subsidiaria(numeros_com_especie, quantidade_principal)

        # Nenhum benefício informado: se a quantidade do pedido principal for conhecida,
        # entende-se que o subsidiário se aplica a todos os benefícios dele (singular com
        # quantidade 1, plural com mais - ver montar_grupo_subsidiaria). Sem quantidade
        # informada ainda é obrigatório informar o benefício, por não dar pra saber quantos
        # existem.
        todos_beneficios_principal = False
        if not numeros_com_especie:
            if beneficio_subsidiario_pode_herdar_do_principal(quantidade_principal):
                todos_beneficios_principal = True
            else:
                raise ValueError('informe ao menos um benefício.')

        return {
            'tese_subsidiaria_key': tese_key,
            'item_peticao': item_peticao,
            'numeros_com_especie': numeros_com_especie,
            'parametro_valor': parametro_valor,
            'todos_beneficios_principal': todos_beneficios_principal,
            'especies_principal': especies_principal if todos_beneficios_principal else None,
            'quantidade_principal': quantidade_principal if todos_beneficios_principal else None,
        }


class BlocoPedido:
    def __init__(self, parent, on_remover, numero=1, on_mudar_vigencia_ntp=None):
        self.on_remover = on_remover
        self._on_mudar_vigencia_ntp = on_mudar_vigencia_ntp or (lambda: None)
        # Liberado pela Janela quando algum pedido de Contestação administrativa cita vigência até 2017.
        self._ntp_disponivel = False
        nomes_teses = ordenar_nomes_teses()

        self._casca, self.frame, self._rotulo_titulo = _criar_cartao(parent, f"Pedido {numero}")
        self._casca.pack(fill='x', expand=True, pady=(0, 14), padx=2)

        # Espaço fixo entre a coluna de rótulos e a coluna de campos (~1cm), para não ficar
        # colado no rótulo mais curto. 'pad' soma espaço APÓS a coluna 0, empurrando a
        # coluna 1 (campos) para a direita. weight=1 faz a coluna de campos crescer com a
        # largura da caixa, em vez de sobrar uma faixa em branco à direita.
        self.frame.columnconfigure(0, pad=38)
        self.frame.columnconfigure(1, weight=1)

        _rotulo(self.frame, "Tese principal:").grid(row=0, column=0, sticky='w', pady=(0, 4))
        self.combo_tese = ComboboxPesquisavel(self.frame, valores=nomes_teses, width=45)
        self.combo_tese.grid(row=0, column=1, sticky='w', pady=(0, 4))
        self.combo_tese.bind(
            '<<ComboboxSelected>>',
            lambda e: [
                self._atualizar_parametro(), self._atualizar_estado_especies(), self._atualizar_estado_quantidade(),
                self._atualizar_estado_subsidiario(), self._atualizar_estado_ntp(), self._on_mudar_vigencia_ntp(),
            ],
            add='+',
        )

        self.label_quantidade = _rotulo(self.frame, "Quantidade de benefícios:")
        self.label_quantidade.grid(row=1, column=0, sticky='w', pady=(8, 4))
        self.frame_quantidade = _quadro(self.frame)
        self.frame_quantidade.grid(row=1, column=1, sticky='w', pady=(8, 4))
        self.entry_quantidade = _campo(self.frame_quantidade, 10)
        self.entry_quantidade.pack(side='left')
        self.entry_quantidade.bind('<KeyRelease>', lambda e: self._ao_mudar_quantidade())
        self.var_indice_singular = tk.BooleanVar(value=False)
        self.check_indice_singular = CaixaSelecao(
            self.frame_quantidade, text="Índice do FAP no singular",
            variable=self.var_indice_singular,
        )
        self._atualizar_estado_quantidade()

        self.label_especies = _rotulo(self.frame, "Espécie(s):")
        self.label_especies.grid(row=2, column=0, sticky='w', pady=(8, 4))
        self.frame_especies = frame_especies = _quadro(self.frame)
        frame_especies.grid(row=2, column=1, sticky='w', pady=(8, 4))
        self.vars_especies = {especie: tk.BooleanVar(value=(i == 0)) for i, especie in enumerate(ESPECIES)}
        self.checks_especies = {}
        for especie in ESPECIES:
            check = CaixaSelecao(
                frame_especies, text=especie, variable=self.vars_especies[especie],
                command=lambda e=especie: self._ao_marcar_especie(e),
            )
            check.pack(side='left', padx=(0, 10))
            self.checks_especies[especie] = check
        self._atualizar_estado_especies()

        self.label_parametro = _rotulo(self.frame)
        self.label_parametro.grid(row=3, column=0, sticky='w', pady=(8, 4))
        self.frame_parametro = _quadro(self.frame)
        self.frame_parametro.grid(row=3, column=1, sticky='we', pady=(8, 4))
        self.combo_parametro = None
        self.var_varios_estabelecimentos = tk.BooleanVar(value=False)
        self._atualizar_parametro()

        _rotulo(self.frame, "Item do pedido:").grid(row=4, column=0, sticky='w', pady=(8, 4))
        frame_item = _quadro(self.frame)
        frame_item.grid(row=4, column=1, sticky='w', pady=(8, 4))
        self.entry_item = _campo(frame_item, 12)
        self.entry_item.pack(side='left')
        self.var_excluir_ntp = tk.BooleanVar(value=False)
        self.check_excluir_ntp = CaixaSelecao(
            frame_item, text="Incluir exclusão dos NTP", variable=self.var_excluir_ntp,
            command=self._atualizar_estado_ntp_singular,
        )
        self.var_ntp_singular = tk.BooleanVar(value=False)
        self.check_ntp_singular = CaixaSelecao(
            frame_item, text="NTP no singular", variable=self.var_ntp_singular,
        )
        self._atualizar_estado_ntp()

        self.grupos_subsidiarios = []

        self.var_subsidiario = tk.BooleanVar(value=False)
        self.check_subsidiario = CaixaSelecao(
            self.frame, text="Possui pedido subsidiário?", variable=self.var_subsidiario,
            command=self._alternar_subsidiario,
        )
        self.check_subsidiario.grid(row=5, column=0, columnspan=2, sticky='w', pady=(14, 0))

        # Cards das teses subsidiárias entram direto aqui, antes do botão (sem frame próprio).
        self.frame_subsidiario = _quadro(self.frame)
        self._botao_adicionar_subsidiaria = _botao(
            self.frame_subsidiario, "+ Adicionar tese subsidiária", self.adicionar_grupo_subsidiario,
        )
        self._botao_adicionar_subsidiaria.pack(anchor='w', pady=(6, 0))
        self._atualizar_estado_subsidiario()

        _linha_divisoria(self.frame).grid(row=7, column=0, columnspan=2, sticky='ew', pady=(14, 10))
        _botao(self.frame, "Remover este pedido", self._remover, cor=tema.COR_ERRO).grid(
            row=8, column=0, columnspan=2, sticky='e',
        )

        # ── Integração com a leitura da petição (AutoPedidos) ──────────────────────────────
        # `proposto` = PedidoProposto que originou este bloco (None se preenchido à mão). Só ele
        # carrega a tabela do pedido; a caixa só aparece quando há tabela para incluir.
        self.proposto = None
        self.var_tabela = tk.BooleanVar(value=True)
        self.check_tabela = CaixaSelecao(
            self.frame, text="Incluir a tabela do pedido (lida da petição)", variable=self.var_tabela,
        )
    def _atualizar_parametro(self):
        self.combo_parametro = _reconstruir_combo_parametro(
            self.frame_parametro, self.combo_tese, label_widget=self.label_parametro,
        )
        if nome_para_chave(self.combo_tese.get()) == TESE_QUE_LIBERA_NTP and self.combo_parametro is not None:
            self.combo_parametro.bind('<KeyRelease>', lambda e: self._on_mudar_vigencia_ntp())
        self.var_varios_estabelecimentos.set(False)
        self._plural_automatico = False
        if nome_para_chave(self.combo_tese.get()) == 'contestacao_administrativa' and self.combo_parametro is not None:
            # mais de uma vigência digitada marca "Plural" sozinha (e desmarca ao voltar a uma só, se foi ela que marcou)
            self.combo_parametro.bind('<KeyRelease>', lambda e: self._plural_pelas_vigencias(), add='+')
        if self._varios_estabelecimentos_aplicavel():
            CaixaSelecao(
                self.frame_parametro,
                text=("Mais de um estab./vigência" if nome_para_chave(self.combo_tese.get()) == 'contestacao_administrativa'
                      else "Mais de um estabelecimento"),
                variable=self.var_varios_estabelecimentos,
            ).pack(side='left', padx=(16, 0))
        # Teses sem campo extra não reservam a linha (some o espaço em branco e "Item do
        # pedido" sobe, ficando logo abaixo de "Tese principal").
        if self.combo_parametro is None:
            self.label_parametro.grid_remove()
            self.frame_parametro.grid_remove()
        else:
            self.label_parametro.grid(row=3, column=0, sticky='w', pady=(8, 4))
            self.frame_parametro.grid(row=3, column=1, sticky='we', pady=(8, 4))

    def _plural_pelas_vigencias(self):
        """CONTESTAÇÃO ADMINISTRATIVA: mais de uma vigência no campo => caixa "Plural" marcada automaticamente."""
        anos = set(re.findall(r'(?:19|20)\d{2}', self.combo_parametro.get()))
        if len(anos) > 1 and not self.var_varios_estabelecimentos.get():
            self.var_varios_estabelecimentos.set(True)
            self._plural_automatico = True
        elif len(anos) <= 1 and self._plural_automatico:
            self.var_varios_estabelecimentos.set(False)
            self._plural_automatico = False

    def _atualizar_estado_especies(self):
        """Some a linha "Espécie(s)" inteira (rótulo + campo) quando a tese selecionada não
        depende de espécie do benefício (ex: Rotatividade, CAT não vinculada) - em vez de
        deixar cinza/desabilitada ocupando espaço à toa. Quando depende, some só a espécie
        que não se aplica (ex: Convertido só aceita B31/B36) - desmarcando qualquer espécie
        que tenha ficado marcada e não seja mais permitida."""
        tese = TESES.get(nome_para_chave(self.combo_tese.get()))
        ignora = bool(tese and tese.get('ignora_especie'))
        if ignora:
            for especie in ESPECIES:
                self.vars_especies[especie].set(False)
            self.label_especies.grid_remove()
            self.frame_especies.grid_remove()
            return
        self.label_especies.grid()
        self.frame_especies.grid()
        permitidas = tese.get('especies_permitidas') if tese else None
        for especie in ESPECIES:
            self.checks_especies[especie].pack_forget()
        for especie in ESPECIES:
            if permitidas is not None and especie not in permitidas:
                self.vars_especies[especie].set(False)
                continue
            self.checks_especies[especie].pack(side='left', padx=(0, 10))

    def _atualizar_estado_quantidade(self):
        """Some a linha "Quantidade de benefícios" inteira (rótulo + campo) quando a tese
        selecionada não depende dela (ex: Prescrição quinquenal, Erro de massa salarial -
        só citam vigência) - em vez de deixar cinza/desabilitada ocupando espaço à toa."""
        tese = TESES.get(nome_para_chave(self.combo_tese.get()))
        ignora = bool(tese and tese.get('ignora_quantidade'))
        if ignora:
            self.label_quantidade.grid_remove()
            self.frame_quantidade.grid_remove()
        else:
            self.label_quantidade.grid()
            self.frame_quantidade.grid()
        self._atualizar_estado_indice_singular()

    def _indice_singular_aplicavel(self):
        tese_key = nome_para_chave(self.combo_tese.get())
        quantidade = self._quantidade_atual()
        return (
            tese_key is not None and tese_permite_indice_singular(tese_key)
            and quantidade is not None and quantidade > 1
        )

    def _atualizar_estado_indice_singular(self):
        if self._indice_singular_aplicavel():
            self.check_indice_singular.pack(side='left', padx=(16, 0))
        else:
            self.var_indice_singular.set(False)
            self.check_indice_singular.pack_forget()

    def _varios_estabelecimentos_aplicavel(self):
        tese = TESES.get(nome_para_chave(self.combo_tese.get()))
        # contestação (motivo próprio) e correção de massa salarial/vínculos ("dos estabelecimentos")
        return bool(tese and ('motivo_fixo_varios_estabelecimentos' in tese
                              or tese.get('tipo_clausula') == 'correcao_com_vigencia'))

    def libera_ntp(self):
        if nome_para_chave(self.combo_tese.get()) != TESE_QUE_LIBERA_NTP or self.combo_parametro is None:
            return False
        return vigencia_libera_ntp(self.combo_parametro.get())

    def definir_ntp_disponivel(self, disponivel):
        self._ntp_disponivel = disponivel
        self._atualizar_estado_ntp()

    def _ntp_aplicavel(self):
        tese_key = nome_para_chave(self.combo_tese.get())
        return self._ntp_disponivel and tese_key is not None and tese_permite_exclusao_ntp(tese_key)

    def _atualizar_estado_ntp(self):
        if self._ntp_aplicavel():
            self.check_excluir_ntp.pack(side='left', padx=(16, 0))
        else:
            self.var_excluir_ntp.set(False)
            self.check_excluir_ntp.pack_forget()
        self._atualizar_estado_ntp_singular()

    def _ntp_singular_aplicavel(self):
        quantidade = self._quantidade_atual()
        return self.var_excluir_ntp.get() and self._ntp_aplicavel() and quantidade is not None and quantidade > 1

    def _atualizar_estado_ntp_singular(self):
        if self._ntp_singular_aplicavel():
            self.check_ntp_singular.pack(side='left', padx=(16, 0))
        else:
            self.var_ntp_singular.set(False)
            self.check_ntp_singular.pack_forget()

    def _atualizar_estado_subsidiario(self):
        """Desabilita (e desmarca) o checkbox "Possui pedido subsidiário?" para teses que
        não admitem benefício subsidiário (ex: Rotatividade, CAT não vinculada - pedido do
        escritório), removendo qualquer tese subsidiária já adicionada."""
        tese_key = nome_para_chave(self.combo_tese.get())
        permite = tese_key is None or tese_permite_subsidiario(tese_key)
        if permite:
            self.check_subsidiario.configure(state='normal')
            return
        if self.var_subsidiario.get():
            self.var_subsidiario.set(False)
            self.frame_subsidiario.grid_forget()
        for grupo in list(self.grupos_subsidiarios):
            grupo._casca.destroy()
        self.grupos_subsidiarios = []
        self.check_subsidiario.configure(state='disabled')

    def _quantidade_atual(self):
        texto = self.entry_quantidade.get().strip()
        return int(texto) if texto.isdigit() else None

    def _ao_marcar_especie(self, especie_clicada):
        """Marcar uma espécie além do limite permitido pela quantidade (ver validacao.py)
        desmarca a que acabou de ser clicada."""
        quantidade = self._quantidade_atual()
        marcadas = [e for e in ESPECIES if self.vars_especies[e].get()]
        if limite_especies_excedido(quantidade, marcadas):
            self.vars_especies[especie_clicada].set(False)
            plural = '' if quantidade == 1 else 's'
            _avisar(
                self.frame,
                'Aviso',
                f'Com quantidade {quantidade}, selecione no máximo {quantidade} espécie{plural} de benefício.',
            )
        self._atualizar_travamento_subsidiarias()

    def _ao_mudar_quantidade(self):
        quantidade = self._quantidade_atual()
        marcadas = [e for e in ESPECIES if self.vars_especies[e].get()]
        permitidas = set(limitar_especies(marcadas, quantidade))
        for especie in marcadas:
            if especie not in permitidas:
                self.vars_especies[especie].set(False)
        self._atualizar_travamento_subsidiarias()
        self._atualizar_estado_indice_singular()
        self._atualizar_estado_ntp_singular()

    def _posicionar_frame_subsidiario(self):
        self.frame_subsidiario.grid(row=6, column=0, columnspan=2, sticky='ew', pady=(8, 0))

    def _alternar_subsidiario(self):
        if self.var_subsidiario.get():
            self._posicionar_frame_subsidiario()
            if not self.grupos_subsidiarios:
                self.adicionar_grupo_subsidiario()
        else:
            self.frame_subsidiario.grid_forget()

    def adicionar_grupo_subsidiario(self):
        grupo = GrupoSubsidiario(
            self.frame_subsidiario, on_remover=self._remover_grupo_subsidiario, numero=len(self.grupos_subsidiarios) + 1,
            obter_especie_travada=self._especie_unica_travada, antes=self._botao_adicionar_subsidiaria,
            on_mudar=self.atualizar_papeis_subsidiarias,
        )
        self.grupos_subsidiarios.append(grupo)
        self.atualizar_papeis_subsidiarias()

    def atualizar_papeis_subsidiarias(self):
        """Marca cada tese como SUBSIDIÁRIA ou ALTERNATIVA, pela mesma regra do texto do Word
        (gerador_pedido._grupo_ja_coberto): benefício já citado em tese anterior = alternativa."""
        vistos, todos_visto = set(), False
        for i, grupo in enumerate(self.grupos_subsidiarios):
            dados = grupo.dados_para_classificacao()
            grupo.definir_papel(i > 0 and _grupo_ja_coberto(dados, vistos, todos_visto), i + 1)
            if dados['todos_beneficios_principal']:
                todos_visto = True
            else:
                vistos |= set(dados['numeros_com_especie'])

    def _especie_unica_travada(self):
        especies = [e for e in ESPECIES if self.vars_especies[e].get()]
        return especie_unica_travada(especies, ESPECIES_SUBSIDIARIA)

    def _atualizar_travamento_subsidiarias(self):
        for grupo in self.grupos_subsidiarios:
            grupo.atualizar_travamento_especie()

    def _remover_grupo_subsidiario(self, grupo):
        if grupo in self.grupos_subsidiarios:
            self.grupos_subsidiarios.remove(grupo)
        self.atualizar_papeis_subsidiarias()

    def _remover(self):
        if not _confirmar(
            self.frame,
            'Remover pedido',
            'Tem certeza que deseja remover este pedido? Os dados preenchidos serão perdidos.',
        ):
            return
        self._casca.destroy()
        self.on_remover(self)

    # ── Preenchimento a partir da petição (ver preenchimento.py) ─────────────────────────

    def preencher(self, proposto):
        """Preenche TODOS os campos do bloco com um PedidoProposto, usando os mesmos handlers
        que o usuário aciona à mão (assim as regras do GERAPED continuam valendo)."""
        import preenchimento
        preenchimento.preencher_bloco(self, proposto)

    def tabela_para_documento(self, dados):
        """TabelaPedido a inserir logo após este pedido no Word, ou None. `dados` = obter_dados()."""
        if self.proposto is None or not self.var_tabela.get():
            return None
        from autopedidos.tabelas import tabela_do_pedido
        self.proposto.dados['excluir_ntp'] = bool(dados.get('excluir_ntp'))
        return tabela_do_pedido(self.proposto)

    def obter_dados(self):
        tese_key = nome_para_chave(self.combo_tese.get())
        if tese_key is None:
            raise ValueError('Selecione a tese principal.')

        if TESES[tese_key].get('ignora_quantidade'):
            quantidade = 1
        else:
            quantidade = validar_quantidade(self.entry_quantidade.get().strip())

        especies = [especie for especie in ESPECIES if self.vars_especies[especie].get()]
        validar_especies(tese_key, especies, quantidade)

        parametro_id = TESES[tese_key].get('parametro')
        parametro_valor = None
        if parametro_id:
            nome_opcao = self.combo_parametro.get() if self.combo_parametro else ''
            parametro_valor = chave_para_opcao_parametro(parametro_id, nome_opcao)
            if parametro_valor is None:
                raise ValueError(f"Selecione \"{PARAMETROS_TESE[parametro_id]['label']}\"")

        campo_texto_valor = None
        if TESES[tese_key].get('campo_texto'):
            campo_texto_valor = self.combo_parametro.get().strip() if self.combo_parametro else ''

        item_peticao = self.entry_item.get().strip()
        if not item_peticao:
            raise ValueError('Informe o item do pedido na petição inicial.')

        dados = {
            'quantidade': quantidade,
            'especies': especies,
            'tese_key': tese_key,
            'item_peticao': item_peticao,
            'parametro_valor': parametro_valor,
            'campo_texto_valor': campo_texto_valor,
            'indice_singular': self.var_indice_singular.get() and self._indice_singular_aplicavel(),
            # 1 benefício com mais de uma vigência (lido da petição): sempre "dos índices do FAP"
            'indice_plural': bool(self.proposto is not None and self.proposto.dados.get('indice_plural')) and quantidade == 1,
            'excluir_ntp': self.var_excluir_ntp.get() and self._ntp_aplicavel(),
            'ntp_singular': self.var_ntp_singular.get() and self._ntp_singular_aplicavel(),
            'varios_estabelecimentos': self.var_varios_estabelecimentos.get() and self._varios_estabelecimentos_aplicavel(),
            'grupos_subsidiarios': [],
        }

        if self.var_subsidiario.get():
            if not tese_permite_subsidiario(tese_key):
                raise ValueError('esta tese não admite benefício subsidiário.')
            grupos = []
            for i, grupo in enumerate(self.grupos_subsidiarios, start=1):
                try:
                    grupos.append(grupo.obter_dados(quantidade_principal=quantidade, especies_principal=especies))
                except ValueError as exc:
                    raise ValueError(f'tese subsidiária {i}: {exc}')
            if not grupos:
                raise ValueError('adicione ao menos uma tese subsidiária ou desmarque a opção.')
            dados['grupos_subsidiarios'] = grupos

        return dados


class Janela:
    def __init__(self, root, caminho_recurso_fn=None):
        self.root = root
        self.blocos = []
        self._ultimo_documento = None
        self._arquivo_analise = None            # log de análise da petição carregada (ver autopedidos/registro.py)
        _res = caminho_recurso_fn or _caminho_recurso
        self._res = _res
        self._versao = self._ler_versao()

        # Desliga o comportamento padrão do Tk de trocar o valor do combobox ao rolar a
        # roda do mouse sobre ele (nível de classe - "instance.bind + break" não é o
        # suficiente para sobrepor, pois o Tk despacha o evento também pela classe do
        # widget). Sem isso, rolar a roda do mouse sobre "Tese principal" muda a tese
        # selecionada, o que reconstrói o campo de parâmetro abaixo e faz o bloco pular.
        root.unbind_class('TCombobox', '<MouseWheel>')

        # ── Barra lateral ────────────────────────────────────────────────────
        self._montar_sidebar(root)

        # ── Área principal: páginas empilhadas (Pedidos / Histórico / Ordem) ─
        # As 3 páginas da sidebar (Pedidos, Histórico, Ordem) ficam todas dentro da mesma
        # janela, sobrepostas em area_paginas (grid + tkraise), em vez de Histórico/Ordem
        # abrirem um Toplevel próprio - nesse layout com sidebar, uma segunda janela
        # flutuante quebrava a sensação de "app de uma tela só" que a barra lateral propõe.
        # Histórico e Ordem reconstroem o conteúdo toda vez que a página é aberta (dados
        # sempre atuais; edição de Ordem não salva sem clicar em "Salvar" - trocar de
        # página sem salvar simplesmente descarta o que tinha mudado, como um Cancelar).
        # Hierarquia rasa de propósito: no Windows, cada nível de frame que muda de tamanho
        # redesenha de novo tudo o que está abaixo dele (redimensionar ficava lento).
        area_paginas = ttk.Frame(root)
        area_paginas.pack(side='left', fill='both', expand=True)
        area_paginas.grid_rowconfigure(0, weight=1)
        area_paginas.grid_columnconfigure(0, weight=1)

        self._pagina_pedidos = ttk.Frame(area_paginas, style="Pagina.TFrame")
        self._pagina_historico = ttk.Frame(area_paginas)
        self._pagina_ordem = ttk.Frame(area_paginas)
        for pagina in (self._pagina_pedidos, self._pagina_historico, self._pagina_ordem):
            pagina.grid(row=0, column=0, sticky='nsew')

        suave = tema.COR_FUNDO_SUAVE
        botoes = _quadro(self._pagina_pedidos, fundo=suave, padx=28, pady=14)
        botoes.pack(fill='x', side='bottom')
        _linha_divisoria(self._pagina_pedidos).pack(fill='x', side='bottom')
        _botao(botoes, "+ Adicionar pedido", self.adicionar_pedido).pack(side='left')
        _botao(botoes, "Carregar petição", self.preencher_da_peticao, cor=tema.COR_SECUNDARIA).pack(
            side='left', padx=(8, 0),
        )
        _botao(botoes, "Limpar", self._limpar_tudo, cor=tema.COR_ERRO, estilo='link').pack(side='left', padx=(8, 0))
        _botao(botoes, "Gerar Word", self.gerar, cor=tema.COR_SECUNDARIA, estilo='cheio').pack(side='right')
        # só aparecem depois que existe um documento gerado
        self._botoes_resultado = _quadro(botoes, fundo=suave)
        # (estilo 'suave' tinha o mesmo cinza da barra e os botões pareciam texto solto; contorno, como
        # os outros botões da barra, deixa claro que são clicáveis)
        _botao(self._botoes_resultado, "Abrir documento", self._abrir_ultimo_documento).pack(side='left', padx=(0, 8))
        _botao(self._botoes_resultado, "Abrir pasta", self._abrir_pasta_ultimo_documento).pack(side='left', padx=(0, 12))

        container = self._pagina_pedidos

        _rotulo(
            container, "Pedidos", fundo=suave, cor=tema.COR_PRIMARIA, fonte=('Segoe UI', 16, 'bold'),
        ).pack(anchor='w', padx=(28, 20), pady=(24, 0))
        _rotulo(
            container, "Monte os pedidos de exclusão de benefícios e gere o texto em Word",
            fundo=suave, cor=tema.COR_AJUDA,
        ).pack(anchor='w', padx=(28, 20), pady=(2, 16))

        # faixa com o nome da petição carregada + botão para rever os apontamentos (só depois de carregar)
        self._resultado_peticao = None
        self._ntp_nao_aplicado = ()
        self._faixa_peticao = _quadro(container, fundo=suave)
        self._rotulo_peticao = _rotulo(
            self._faixa_peticao, '', fundo=suave, cor=tema.COR_PRIMARIA, fonte=('Segoe UI', 10, 'bold'),
        )
        self._rotulo_peticao.pack(side='left')
        _botao(self._faixa_peticao, '↻ Rever apontamentos', self._rever_apontamentos, padx=10).pack(
            side='left', padx=(12, 0))

        self.canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0, background=tema.COR_FUNDO_SUAVE)

        def _ao_mover_scrollbar(*args):
            # Arrastar a barra gera dezenas de eventos por segundo; o Windows só desenha (WM_PAINT) quando a
            # fila de mensagens esvazia, então o conteúdo ficava em branco/remendado durante o arrasto.
            # Aqui só guardamos a posição mais recente e aplicamos no máximo ~60x/s, desenhando de fato a cada vez.
            self._yview_pendente = args
            if not self._yview_agendado:
                self._yview_agendado = True
                self.root.after(16, self._aplicar_yview)

        scrollbar = tk.Scrollbar(container, orient='vertical', command=_ao_mover_scrollbar)
        self.frame_interno = ttk.Frame(self.canvas, style="Pagina.TFrame")
        self._id_frame_interno = self.canvas.create_window((0, 0), window=self.frame_interno, anchor='nw')
        # canvas.bbox('all') (bbox do item-janela) demorava a refletir a altura real do
        # conteúdo depois de itemconfigure(width=...), deixando o scrollregion maior que o
        # conteúdo de fato - com isso sobrava espaço para rolar à toa e os pedidos "pulavam"
        # de posição. winfo_reqheight() do próprio frame é o valor confiável.
        self.frame_interno.bind('<Configure>', lambda e: self._atualizar_scrollregion())

        def _ao_redimensionar_canvas(e):
            self.canvas.itemconfigure(self._id_frame_interno, width=e.width)
            self._atualizar_scrollregion()

        self.canvas.bind('<Configure>', _ao_redimensionar_canvas)

        # Enquanto a janela é redimensionada (arrastar a borda, maximizar), os pedidos ficam
        # ocultos e só são redesenhados uma vez, ao final - redesenhar dezenas de campos a
        # cada pixel arrastado é o que deixava o redimensionamento travado.
        self._tamanho_janela = None
        self._reexibir_pedidos = None
        self._yview_pendente = None
        self._yview_agendado = False
        marca = f'redimensionar{id(self)}'
        self.root.bindtags((marca,) + self.root.bindtags())
        self.root.bind_class(marca, '<Configure>', self._ao_redimensionar_janela)
        self.canvas.configure(yscrollcommand=scrollbar.set, yscrollincrement=15)
        self.canvas.pack(side='left', fill='both', expand=True, padx=(28, 0), pady=(0, 12))
        scrollbar.pack(side='right', fill='y', padx=(0, 20), pady=(0, 12))
        # bind no root (não bind_all!) - bind_all usa a bindtag "all", que também afeta a
        # lista suspensa da tese (é uma janela própria, mas "all" é realmente global). Preso
        # ao root, só dispara para widgets desta janela, deixando a lista suspensa em paz.
        self.root.bind('<MouseWheel>', self._ao_rolar)
        for atalho in ('<Control-l>', '<Control-L>'):
            self.root.bind(atalho, lambda e: self._abrir_log_de_analise())

        self.adicionar_pedido()
        # No arranque, a janela ainda não foi mapeada na tela quando adicionar_pedido() roda
        # (estamos antes do mainloop) - a largura/altura reais do canvas só ficam corretas
        # depois disso, então o ajuste de posição feito lá pode errar. after_idle roda assim
        # que o loop principal começar a processar eventos, já com o layout final.
        self.root.after_idle(self._corrigir_posicao_inicial)

        self._mostrar_pagina('pedidos')

    def _montar_sidebar(self, root):
        # tk clássico (não ttk) e sem frames intermediários: a barra lateral é redesenhada a
        # cada passo de redimensionamento da janela.
        azul = tema.COR_PRIMARIA
        barra = _quadro(root, fundo=azul, width=LARGURA_SIDEBAR)
        barra.pack(side='left', fill='y')
        barra.pack_propagate(False)

        caminho_logo = self._res('logo_completa.png')
        if os.path.isfile(caminho_logo):
            self._imagem_marca = _carregar_logo_para_fundo_escuro(caminho_logo, 40)
            tk.Label(barra, image=self._imagem_marca, background=azul, borderwidth=0, autostyle=False).pack(
                anchor='w', padx=20, pady=(26, 18),
            )
        _quadro(barra, fundo=tema.COR_SECUNDARIA, height=3).pack(fill='x', padx=20)

        _rotulo(barra, "GERAPED", fundo=azul, cor='#FFFFFF', fonte=("Segoe UI", 20, "bold")).pack(
            anchor='w', padx=20, pady=(16, 0),
        )
        _rotulo(barra, "Gerador de Pedidos", fundo=azul, cor=tema.COR_NAV_TEXTO, fonte=("Segoe UI", 9)).pack(
            anchor='w', padx=20, pady=(0, 14),
        )

        # As 3 páginas (Pedidos/Histórico/Ordem) ficam sobrepostas na mesma janela (ver
        # area_paginas no __init__) - aqui só guardamos as referências de cada linha
        # (acento + botão) pra alternar o destaque visual em _mostrar_pagina, já que agora
        # qualquer uma das 3 pode estar ativa (antes só "Pedidos" existia e ficava sempre
        # marcada).
        self._linhas_nav = {}
        self._pagina_ativa = None
        for nome, texto in (('pedidos', "☰   Pedidos"), ('historico', "↻   Histórico"), ('ordem', "⚙   Ordem")):
            # acento = borda esquerda laranja do item ativo
            botao = tk.Label(
                barra, text=texto, background=azul, foreground=tema.COR_NAV_TEXTO,
                font=("Segoe UI", 11), anchor="w", padx=24, pady=12, cursor="hand2",
                highlightthickness=0, autostyle=False,
            )
            botao.pack(fill='x')
            acento = _quadro(botao, fundo=azul, width=4)
            acento.place(x=0, y=0, relheight=1)

            def _passar(_e, n=nome, b=botao):
                if n != self._pagina_ativa:
                    b.configure(background=tema.COR_NAV_ATIVO, foreground='#FFFFFF')

            def _sair(_e, n=nome, b=botao):
                if n != self._pagina_ativa:
                    b.configure(background=azul, foreground=tema.COR_NAV_TEXTO)

            botao.bind('<Enter>', _passar)
            botao.bind('<Leave>', _sair)
            botao.bind('<Button-1>', lambda _e, n=nome: self._mostrar_pagina(n))
            acento.bind('<Button-1>', lambda _e, n=nome: self._mostrar_pagina(n))
            self._linhas_nav[nome] = (acento, botao)

        rodape = _quadro(barra, fundo=azul)
        rodape.pack(side='bottom', fill='x', pady=(0, 16))
        # divisor sutil separando o rodapé do resto da sidebar - sem ele o rodapé ficava
        # "boiando" no meio do azul, sem nada delimitando onde a navegação termina. side=
        # 'bottom' e packado DEPOIS de "rodape" (que também é 'bottom') - assim ele ocupa a
        # fatia logo ACIMA do rodapé, não logo abaixo dos itens de navegação lá em cima
        # (pack empilha widgets 'bottom' na ordem em que são chamados, de baixo pra cima).
        _quadro(barra, fundo=tema.COR_NAV_DIVISOR, height=1).pack(side='bottom', fill='x', padx=20, pady=(0, 4))
        self._criar_link_sidebar(rodape, 'ⓘ', 'Notas de atualização', self._mostrar_notas_atualizacao)
        self._criar_link_sidebar(rodape, '?', 'Manual rápido', self._mostrar_manual)
        _rotulo(rodape, f"Versão {self._versao}", fundo=azul, cor=tema.COR_NAV_TEXTO, fonte=("Segoe UI", 9)).pack(
            anchor='w', padx=20, pady=(12, 0),
        )

    def _criar_link_sidebar(self, pai, icone, texto, comando):
        """Link do rodapé da barra lateral (ícone + texto). Dois rótulos em vez de um único
        Button com "ícone + espaços + título": o ícone fica numa coluna de largura FIXA EM
        PIXELS (pack_propagate desligado), então o texto sempre começa no mesmo X."""
        azul = tema.COR_PRIMARIA
        linha = _quadro(pai, fundo=azul, cursor='hand2')
        linha.pack(fill='x')
        caixa_icone = _quadro(linha, fundo=azul, width=28, height=24)
        caixa_icone.pack(side='left', padx=(20, 0), pady=6)
        caixa_icone.pack_propagate(False)
        rotulo_icone = _rotulo(caixa_icone, icone, fundo=azul, cor=tema.COR_NAV_ICONE, fonte=("Segoe UI", 9), anchor='center')
        rotulo_icone.pack(fill='both', expand=True)
        rotulo_texto = _rotulo(linha, texto, fundo=azul, cor=tema.COR_NAV_TEXTO, fonte=("Segoe UI", 9), anchor='w')
        rotulo_texto.pack(side='left', fill='x', expand=True, pady=6)

        def _ao_passar(_evt=None):
            rotulo_icone.configure(foreground=tema.COR_SECUNDARIA)
            rotulo_texto.configure(foreground=tema.COR_SECUNDARIA, font=("Segoe UI", 9, "underline"))

        def _ao_sair(_evt=None):
            rotulo_icone.configure(foreground=tema.COR_NAV_ICONE)
            rotulo_texto.configure(foreground=tema.COR_NAV_TEXTO, font=("Segoe UI", 9))

        for widget in (linha, caixa_icone, rotulo_icone, rotulo_texto):
            widget.configure(cursor='hand2')
            widget.bind('<Enter>', _ao_passar)
            widget.bind('<Leave>', _ao_sair)
            widget.bind('<Button-1>', lambda _evt: comando())

    def _mostrar_pagina(self, nome):
        """Traz uma das 3 páginas (pedidos/historico/ordem) pra frente (tkraise) e destaca
        o item correspondente na sidebar. Histórico e Ordem reconstroem o conteúdo do zero
        a cada troca - editar a ordem e sair sem clicar "Salvar" simplesmente descarta a
        mudança (equivalente a fechar/cancelar na antiga janela separada)."""
        paginas = {
            'pedidos': self._pagina_pedidos,
            'historico': self._pagina_historico,
            'ordem': self._pagina_ordem,
        }
        if nome == 'historico':
            self._construir_pagina_historico()
        elif nome == 'ordem':
            self._construir_pagina_ordem()
        # grid_remove (não só tkraise): página escondida atrás de outra continua sendo
        # relayoutada e redesenhada a cada redimensionamento da janela.
        for chave, pagina in paginas.items():
            if chave == nome:
                pagina.grid()
            else:
                pagina.grid_remove()

        self._pagina_ativa = nome
        for chave, (acento, botao) in self._linhas_nav.items():
            ativo = chave == nome
            acento.configure(background=tema.COR_SECUNDARIA if ativo else tema.COR_PRIMARIA)
            botao.configure(
                background=tema.COR_NAV_ATIVO if ativo else tema.COR_PRIMARIA,
                foreground='#FFFFFF' if ativo else tema.COR_NAV_TEXTO,
                font=("Segoe UI", 11, "bold") if ativo else ("Segoe UI", 11),
            )

    def _mostrar_toast(self, mensagem, cor_fundo=None):
        """Aviso temporário que aparece sozinho e some sozinho (sem precisar clicar em
        "Fechar"/"OK") - usado depois de ações que voltam pra outra página na hora (ex:
        Salvar em Ordem), onde um messagebox tradicional pediria um clique extra só pra
        confirmar algo que já deu certo. Janela solta (sem barra de título, overrideredirect),
        não um widget dentro da página - assim funciona em cima de qualquer página, sem
        precisar existir dentro da árvore de widgets de quem chamou."""
        cor_fundo = cor_fundo or tema.COR_SUCESSO
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        try:
            toast.attributes('-topmost', True)
        except Exception:
            pass
        toast.configure(background=cor_fundo)
        # autostyle=False: sem isso o ttkbootstrap troca o fundo verde pelo branco do tema.
        tk.Label(
            toast, text=mensagem, background=cor_fundo, foreground='#FFFFFF',
            font=('Segoe UI', 10, 'bold'), padx=22, pady=12, autostyle=False,
        ).pack()
        toast.update_idletasks()
        largura, altura = toast.winfo_reqwidth(), toast.winfo_reqheight()
        # Centro exato da janela inteira (com barra de título), igual aos avisos padrão
        # (ver _abrir_aviso_no_centro).
        esquerda, topo, direita, baixo = _retangulo_janela(self.root)
        x = (esquerda + direita - largura) // 2
        y = (topo + baixo - altura) // 2
        toast.geometry(f'{largura}x{altura}+{x}+{y}')
        toast.after(1300, toast.destroy)

    def _ao_redimensionar_janela(self, evento):
        tamanho = (evento.width, evento.height)
        if tamanho == self._tamanho_janela:
            return  # só moveu a janela
        primeira_vez = self._tamanho_janela is None
        self._tamanho_janela = tamanho
        if primeira_vez:
            return
        self.canvas.itemconfigure(self._id_frame_interno, state='hidden')
        if self._reexibir_pedidos is not None:
            self.root.after_cancel(self._reexibir_pedidos)
        self._reexibir_pedidos = self.root.after(150, self._mostrar_pedidos)

    def _mostrar_pedidos(self):
        self._reexibir_pedidos = None
        self.canvas.itemconfigure(self._id_frame_interno, state='normal')

    def _corrigir_posicao_inicial(self):
        self.root.update_idletasks()
        self._atualizar_scrollregion()

    def _atualizar_scrollregion(self):
        """Recalcula o scrollregion a partir da altura REALMENTE requisitada pelo
        frame_interno (winfo_reqheight), em vez de canvas.bbox('all') - o bbox do item-
        janela do canvas ficava des sincronizado da altura real do conteúdo (sobrava
        espaço "fantasma" para rolar, fazendo os pedidos parecerem pular de posição).

        Quando o conteúdo cabe inteiro na área visível, também força a rolagem de volta
        para o topo (yview_moveto(0)) - o Tk não faz isso sozinho: se o canvas tiver
        rolado antes (ex: com mais pedidos) e o conteúdo depois encolher a ponto de caber
        de novo, o deslocamento antigo fica "preso", fazendo tudo parecer flutuar com um
        vão em branco em cima. Ao repetir essa correção toda vez que o scrollregion for
        recalculado (inclusive a cada tentativa de rolar - ver _ao_rolar), a posição volta
        a ficar consistente mesmo se algo tiver ficado dessincronizado durante o
        carregamento inicial da janela.

        Retorna a altura de conteúdo usada, para quem for decidir se cabe na tela."""
        largura = max(self.canvas.winfo_width(), self.frame_interno.winfo_reqwidth())
        altura = self.frame_interno.winfo_reqheight()
        self.canvas.configure(scrollregion=(0, 0, largura, altura))
        if altura <= self.canvas.winfo_height():
            self.canvas.yview_moveto(0)
        return altura

    def _aplicar_yview(self):
        self._yview_agendado = False
        args, self._yview_pendente = self._yview_pendente, None
        if args:
            self.canvas.yview(*args)
            # sem isso, arrastar o "polegar" (ou clicar na calha) movia o conteúdo mesmo quando ele já cabia
            # inteiro na tela, já que só a roda do mouse (_ao_rolar) tinha essa trava.
            self._atualizar_scrollregion()
            self.canvas.update()           # força o desenho agora (ver _ao_mover_scrollbar)

    def _conteudo_cabe_na_tela(self):
        return self._atualizar_scrollregion() <= self.canvas.winfo_height()

    def _ao_rolar(self, event):
        if _LISTA_TESE_ABERTA:
            return

        # Quando todos os pedidos já cabem inteiros na área visível, não há nada para rolar.
        if self._conteudo_cabe_na_tela():
            return

        topo, base = self.canvas.yview()
        direcao = -1 if event.delta > 0 else 1
        if (direcao < 0 and topo <= 0) or (direcao > 0 and base >= 1):
            return
        # passo fixo por "clique" da roda - evita variação/jitter entre mouses diferentes
        self.canvas.yview_scroll(direcao * 3, 'units')

    def adicionar_pedido(self):
        bloco = BlocoPedido(
            self.frame_interno, on_remover=self._remover_bloco, numero=len(self.blocos) + 1,
            on_mudar_vigencia_ntp=self._atualizar_disponibilidade_ntp,
        )
        self.blocos.append(bloco)
        self._atualizar_disponibilidade_ntp()
        # update_idletasks() (do root, não só do frame_interno) garante que a largura do
        # canvas já esteja sincronizada (ver _ao_redimensionar_canvas) antes de medir a
        # altura real do conteúdo.
        self.root.update_idletasks()
        if self._conteudo_cabe_na_tela():
            self.canvas.yview_moveto(0)
        else:
            self.canvas.yview_moveto(1.0)

    def _remover_bloco(self, bloco):
        if bloco in self.blocos:
            self.blocos.remove(bloco)
        for i, b in enumerate(self.blocos, start=1):
            b._rotulo_titulo.configure(text=f"Pedido {i}")
        self._atualizar_disponibilidade_ntp()

    def _atualizar_disponibilidade_ntp(self):
        disponivel = any(b.libera_ntp() for b in self.blocos)
        for b in self.blocos:
            b.definir_ntp_disponivel(disponivel)

    # ── Preencher a partir da petição inicial (.docx) ────────────────────────────────────

    def preencher_da_peticao(self, caminho=None):
        """Lê a petição (.docx, 100% local), propõe os pedidos e preenche os blocos. O usuário
        revisa/edita tudo na tela como sempre; nada é gerado sem clicar em "Gerar Word"."""
        if caminho is None:
            caminho = filedialog.askopenfilename(
                title='Petição inicial (.docx)', filetypes=[('Documento Word', '*.docx')],
            )
        if not caminho:
            return
        tem_dados = any(b.entry_item.get().strip() or b.entry_quantidade.get().strip() for b in self.blocos)
        if tem_dados and not _confirmar(
            self.root, 'Preencher da petição',
            'Os pedidos já preenchidos serão substituídos pelos lidos da petição. Continuar?',
        ):
            return
        self.root.configure(cursor='watch')
        self.root.update_idletasks()
        try:
            import preenchimento
            resultado = preenchimento.ler_peticao_para_blocos(caminho)
        except Exception as exc:    # noqa: BLE001 - qualquer falha de leitura vira aviso ao usuário
            self.root.configure(cursor='')
            logger.exception('Falha ao ler a petição %s', os.path.basename(caminho))
            try:
                from autopedidos import registro
                arquivo = registro.salvar_erro(self._pasta_do_programa(), caminho, exc, self._versao)
                logger.info('Rastro do erro gravado em %s', arquivo)
            except Exception:      # noqa: BLE001 - o log nunca derruba o programa
                logger.exception('Não foi possível gravar o log do erro')
            _erro(self.root, 'Não foi possível ler a petição', f'{type(exc).__name__}: {exc}')
            return
        self.root.configure(cursor='')
        if not resultado.proposta.pedidos:
            _avisar(self.root, 'Preencher da petição',
                    'Não encontrei nenhuma tese com tabela de benefícios nesta petição. '
                    'Verifique se é a petição inicial no modelo do escritório.')
            return
        for bloco in list(self.blocos):
            bloco._casca.destroy()
        self.blocos.clear()
        for proposto in resultado.proposta.pedidos:
            self.adicionar_pedido()
            self.blocos[-1].preencher(proposto)
        self._atualizar_disponibilidade_ntp()
        ntp_nao_aplicado = preenchimento.aplicar_ntp(self.blocos)   # depois de saber se o NTP está liberado
        self.root.update_idletasks()
        self.canvas.yview_moveto(0)
        self._atualizar_scrollregion()
        self._resultado_peticao, self._ntp_nao_aplicado = resultado, ntp_nao_aplicado
        self._mostrar_faixa_peticao(os.path.basename(caminho))
        self._gravar_log_de_analise(caminho, resultado)
        preenchimento.mostrar_resumo(self.root, resultado, self.blocos, ntp_nao_aplicado)

    def _pasta_do_programa(self):
        return os.environ.get('GERAPED_PASTA_LOGS') or os.path.dirname(_caminho_historico())

    def _gravar_log_de_analise(self, caminho, resultado):
        """Um arquivo por petição em logs/analises, com o porquê das decisões do programa."""
        self._arquivo_analise = None
        try:
            from autopedidos import registro
            self._arquivo_analise = registro.salvar_analise(
                self._pasta_do_programa(), caminho, resultado.peticao, resultado.deteccao, resultado.proposta,
                self._versao)
            logger.info('Petição %s carregada: %d pedido(s); análise em %s', os.path.basename(caminho),
                        len(resultado.proposta.pedidos), self._arquivo_analise)
        except Exception:          # noqa: BLE001 - o log nunca derruba o programa
            logger.exception('Não foi possível gravar o log de análise')

    def _abrir_log_de_analise(self):
        """Ctrl+L: abre o log de análise da petição carregada; sem petição, abre a pasta dos logs."""
        try:
            alvo = self._arquivo_analise
            if not alvo or not os.path.isfile(alvo):
                from autopedidos import registro
                alvo = registro.pasta_de_analises(self._pasta_do_programa())
            if sys.platform == 'win32':
                os.startfile(str(alvo))
            else:
                import subprocess
                subprocess.Popen(['xdg-open', str(alvo)])
        except Exception as exc:    # noqa: BLE001
            logger.exception('Não foi possível abrir o log de análise')
            _avisar(self.root, 'Log de análise', f'Não foi possível abrir o log: {exc}')

    def _anotar_geracao_no_log(self, pedidos, caminho_docx):
        if not self._arquivo_analise or self._resultado_peticao is None:
            return
        try:
            from autopedidos import registro
            registro.anotar_geracao(self._arquivo_analise, self._resultado_peticao.proposta, self.blocos, pedidos,
                                    caminho_docx)
        except Exception:          # noqa: BLE001
            logger.exception('Não foi possível anotar a geração no log de análise')

    def _mostrar_faixa_peticao(self, nome):
        """Nome da petição carregada, visível na tela."""
        if nome:
            self._rotulo_peticao.configure(text=f'Petição: {nome}')
            self._faixa_peticao.pack(fill='x', padx=(28, 20), pady=(0, 10), before=self.canvas)
        else:
            self._faixa_peticao.pack_forget()

    def _rever_apontamentos(self):
        """Abre de novo a janela de apontamentos da última petição carregada (com o estado atual dos pedidos)."""
        if self._resultado_peticao is None:
            return
        import preenchimento
        preenchimento.mostrar_resumo(self.root, self._resultado_peticao, self.blocos, self._ntp_nao_aplicado)

    # ── Limpar tudo ───────────────────────────────────────────────────────────

    def _limpar_tudo(self):
        if not _confirmar(
            self.root,
            'Limpar tudo',
            'Tem certeza que deseja limpar todos os pedidos preenchidos?',
        ):
            return
        for bloco in list(self.blocos):
            bloco._casca.destroy()
        self.blocos.clear()
        self._resultado_peticao, self._ntp_nao_aplicado = None, ()
        self._arquivo_analise = None
        self._mostrar_faixa_peticao('')
        self.adicionar_pedido()

    # ── Último documento gerado ──────────────────────────────────────────────

    def _abrir_pasta_ultimo_documento(self):
        if not self._ultimo_documento or not os.path.isfile(self._ultimo_documento):
            _avisar(self.root, 'Aviso', 'Nenhum documento foi salvo ainda nesta sessão.')
            return
        os.startfile(os.path.dirname(self._ultimo_documento))

    def _abrir_ultimo_documento(self):
        if not self._ultimo_documento or not os.path.isfile(self._ultimo_documento):
            _avisar(self.root, 'Aviso', 'Nenhum documento foi salvo ainda nesta sessão.')
            return
        os.startfile(self._ultimo_documento)

    # ── Histórico de documentos gerados ─────────────────────────────────────

    def _registrar_historico(self, caminho):
        from datetime import datetime
        historico = self._ler_historico()
        entrada = {'caminho': caminho, 'data': datetime.now().strftime('%d/%m/%Y %H:%M')}
        historico = [e for e in historico if e['caminho'] != caminho]
        historico.insert(0, entrada)
        try:
            with open(_caminho_historico(), 'w', encoding='utf-8') as f:
                json.dump(historico[:20], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _ler_historico(self):
        try:
            if os.path.isfile(_caminho_historico()):
                with open(_caminho_historico(), encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    # ── Ordem (ordem das teses) ───────────────────────────────────────────────

    def _atualizar_ordem_teses_em_todos_combos(self):
        """Aplica a nova ordem salva aos combos de tese já existentes na tela (pedidos e
        teses subsidiárias abertos), sem precisar recriar os blocos."""
        chaves_subsidiaria = _chaves_teses_subsidiarias_compativeis()
        for bloco in self.blocos:
            bloco.combo_tese.atualizar_valores(ordenar_nomes_teses())
            for grupo in bloco.grupos_subsidiarios:
                grupo.combo_tese.atualizar_valores(ordenar_nomes_teses(chaves_subsidiaria))

    def _construir_pagina_ordem(self):
        for filho in self._pagina_ordem.winfo_children():
            filho.destroy()
        chaves_estado = ordenar_chaves_teses()

        container = ttk.Frame(self._pagina_ordem, padding=(28, 24, 20, 12), style="Pagina.TFrame")
        container.pack(fill='both', expand=True)

        cabecalho = ttk.Frame(container, style="Pagina.TFrame")
        cabecalho.pack(fill='x', pady=(0, 16))
        ttk.Label(cabecalho, text="Ordem", style="Titulo.TLabel").pack(anchor='w')
        ttk.Label(
            cabecalho, text="Selecione uma tese e use os botões para movê-la na ordem de exibição da lista.",
            style="Descricao.TLabel",
        ).pack(anchor='w', pady=(2, 0))

        # Card com borda (igual ao "Pedido 1" da página Pedidos) em volta da lista - sem
        # isso a lista era um Listbox branco solto direto no fundo branco da página, sem
        # nenhum contorno que desse "chão" pro conteúdo (ficava com cara de flutuando).
        cartao_casca, cartao, _ = _criar_cartao(container, 'Teses cadastradas', expandir=True)
        cartao_casca.pack(fill='both', expand=True)

        frame_lista = ttk.Frame(cartao)
        frame_lista.pack(fill='both', expand=True)

        lista = tk.Listbox(
            frame_lista, activestyle='none', font=('Segoe UI', 10), exportselection=False,
            relief='solid', borderwidth=1, highlightthickness=0,
            background=tema.COR_FUNDO, foreground=tema.COR_TEXTO,
            selectbackground=tema.COR_PRIMARIA, selectforeground='#FFFFFF',
        )
        for chave in chaves_estado:
            lista.insert('end', TESES[chave]['nome'])
        sb = ttk.Scrollbar(frame_lista, command=lista.yview)
        lista.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        lista.pack(side='left', fill='both', expand=True)

        def mover(delta):
            selecao = lista.curselection()
            if not selecao:
                return
            i = selecao[0]
            j = i + delta
            if j < 0 or j >= lista.size():
                return
            chaves_estado[i], chaves_estado[j] = chaves_estado[j], chaves_estado[i]
            texto_i, texto_j = lista.get(i), lista.get(j)
            lista.delete(i)
            lista.insert(i, texto_j)
            lista.delete(j)
            lista.insert(j, texto_i)
            lista.selection_set(j)

        def restaurar_padrao():
            chaves_estado[:] = ordem_padrao_chaves()
            lista.delete(0, 'end')
            for chave in chaves_estado:
                lista.insert('end', TESES[chave]['nome'])

        def salvar():
            salvar_ordem_teses(chaves_estado)
            self._atualizar_ordem_teses_em_todos_combos()
            self._mostrar_pagina('pedidos')
            self._mostrar_toast('✓ Ordem salva com sucesso')

        botoes_mover = ttk.Frame(cartao, padding=(0, 10, 0, 0))
        botoes_mover.pack(fill='x')
        ttk.Button(botoes_mover, text='▲ Mover para cima', command=lambda: mover(-1), bootstyle='primary-outline').pack(
            side='left',
        )
        ttk.Button(botoes_mover, text='▼ Mover para baixo', command=lambda: mover(1), bootstyle='primary-outline').pack(
            side='left', padx=(8, 0),
        )

        ttk.Separator(container).pack(fill='x', pady=(12, 0))
        botoes = ttk.Frame(container, padding=(0, 10, 0, 0), style="Pagina.TFrame")
        botoes.pack(fill='x')
        ttk.Button(botoes, text='Restaurar padrão', command=restaurar_padrao, bootstyle='secondary-outline').pack(
            side='left',
        )
        ttk.Button(botoes, text='Cancelar', command=lambda: self._mostrar_pagina('pedidos'), bootstyle='secondary-outline').pack(
            side='left', padx=(8, 0),
        )
        ttk.Button(botoes, text='Salvar', command=salvar, bootstyle='secondary').pack(side='right')

    # ── Manual rápido ────────────────────────────────────────────────────────

    def _mostrar_manual(self):
        janela = tk.Toplevel(self.root)
        janela.title('Manual rápido')
        _centralizar_janela(janela, self.root, 620, 560, DESLOCAMENTO_JANELAS - int(self.root.winfo_fpixels('1c')))
        janela.transient(self.root)
        janela.grab_set()
        janela.resizable(True, True)

        botoes = ttk.Frame(janela, padding=(16, 10))
        botoes.pack(fill='x', side='bottom')
        ttk.Button(botoes, text='Fechar', command=janela.destroy, bootstyle='secondary-outline').pack(side='right')
        ttk.Separator(janela).pack(fill='x', side='bottom', pady=(8, 0))

        frame_texto = ttk.Frame(janela, padding=(16, 14, 16, 0))
        frame_texto.pack(fill='both', expand=True)

        sb = ttk.Scrollbar(frame_texto)
        sb.pack(side='right', fill='y')
        fonte_manual = tkfont.Font(family='Segoe UI', size=10)
        fonte_titulo_secao = tkfont.Font(family='Segoe UI', size=10, weight='bold')
        # wrap='none': a quebra de linha é feita por nós (_justificar_paragrafo), igual em
        # _mostrar_notas_atualizacao - ver comentário lá.
        txt = tk.Text(
            frame_texto, wrap='none', font=fonte_manual,
            yscrollcommand=sb.set, relief='flat', borderwidth=1, padx=10, pady=10,
        )
        sb.configure(command=txt.yview)
        txt.pack(side='left', fill='both', expand=True)
        txt.tag_configure('titulo_secao', font=fonte_titulo_secao)
        txt.tag_configure('aviso', font=fonte_titulo_secao)       # parágrafo do alerta "CONFIRA SEMPRE" em negrito

        def renderizar(_event=None):
            largura_px = int((txt.winfo_width() - 20) * 0.90)
            if largura_px <= 10:
                return
            txt.config(state='normal')
            txt.delete('1.0', 'end')
            for tipo, conteudo in _dividir_manual(TEXTO_MANUAL):
                if tipo == 'vazio':
                    txt.insert('end', '\n')
                elif tipo == 'regra':
                    txt.insert('end', conteudo + '\n')
                elif tipo == 'titulo':
                    txt.insert('end', conteudo + '\n', 'titulo_secao')
                else:
                    aviso = conteudo.lstrip().startswith('ATENÇÃO: CONFIRA SEMPRE')
                    fonte_do_bloco = fonte_titulo_secao if aviso else fonte_manual
                    for prefixo, paragrafo in (item for bloco in _preparar_paragrafos_notas(conteudo) for item in bloco):
                        linhas = _justificar_paragrafo(prefixo, paragrafo, fonte_do_bloco, largura_px)
                        if aviso:
                            txt.insert('end', '\n'.join(linhas) + '\n', 'aviso')
                        else:
                            txt.insert('end', '\n'.join(linhas) + '\n')
            txt.config(state='disabled')

        txt.bind('<Configure>', renderizar)

    # ── Notas de atualização ─────────────────────────────────────────────────

    def _ler_versao(self):
        try:
            with open(self._res('versao.txt'), encoding='utf-8-sig') as f:
                return f.read().strip()
        except Exception:
            return '1.0'

    def _ler_notas_atualizacao(self, versao):
        caminho = self._res(os.path.join('NOTAS DE ATUALIZAÇÃO', f'{versao}.txt'))
        try:
            with open(caminho, encoding='utf-8') as f:
                return f.read().strip()
        except Exception:
            return None

    def _listar_historico_notas(self):
        """Todas as notas de atualização disponíveis (bundladas junto do app), da mais
        recente para a mais antiga - não só a da versão instalada."""
        pasta = self._res('NOTAS DE ATUALIZAÇÃO')
        try:
            nomes = [n for n in os.listdir(pasta) if n.lower().endswith('.txt')]
        except Exception:
            return []

        def chave_versao(nome):
            partes = nome[:-4].split('.')
            return tuple(int(''.join(c for c in p if c.isdigit()) or 0) for p in partes)

        nomes.sort(key=chave_versao, reverse=True)
        historico = []
        for nome in nomes:
            versao = nome[:-4]
            texto = self._ler_notas_atualizacao(versao)
            if texto:
                historico.append((versao, texto))
        return historico

    def _mostrar_notas_atualizacao(self):
        historico = self._listar_historico_notas()
        if not historico:
            historico = [(self._versao, f'Nenhuma nota de atualização encontrada para a versão {self._versao}.')]

        janela = tk.Toplevel(self.root)
        janela.title('Notas de atualização')
        _centralizar_janela(janela, self.root, 560, 520, DESLOCAMENTO_JANELAS - int(self.root.winfo_fpixels('1c')))
        janela.transient(self.root)
        janela.grab_set()
        janela.resizable(True, True)

        ttk.Label(
            janela, text=f'Histórico de versões (instalada: {self._versao})',
            font=('Segoe UI', 10, 'bold'),
        ).pack(anchor='w', padx=16, pady=(14, 6))

        # Empacota a barra de botões (e o separador acima dela) ANTES da área de texto -
        # assim o gerenciador de geometria reserva esse espaço primeiro, e a área de texto
        # (abaixo, com expand=True) nunca cresce por cima dela, não importa quanto texto
        # tenha (foi o que causava o botão "Fechar" ficando espremido/sobreposto pelo
        # texto quando o histórico de notas cresceu).
        botoes = ttk.Frame(janela, padding=(16, 10))
        botoes.pack(fill='x', side='bottom')
        ttk.Button(botoes, text='Fechar', command=janela.destroy, bootstyle='secondary-outline').pack(side='right')
        ttk.Separator(janela).pack(fill='x', side='bottom', pady=(8, 0))

        frame_texto = ttk.Frame(janela, padding=(16, 0, 16, 0))
        frame_texto.pack(fill='both', expand=True)

        sb = ttk.Scrollbar(frame_texto)
        sb.pack(side='right', fill='y')
        fonte_notas = tkfont.Font(family='Segoe UI', size=10)
        fonte_titulo_versao = tkfont.Font(family='Segoe UI', size=10, weight='bold')
        # wrap='none': a quebra de linha é feita por nós (_justificar_paragrafo), com
        # espaços extras inseridos pra esticar cada linha - o wrap automático do Tk não
        # sabe nada sobre esses espaços e cortaria errado.
        txt = tk.Text(
            frame_texto, wrap='none', font=fonte_notas,
            yscrollcommand=sb.set, relief='flat', borderwidth=1, padx=10, pady=10,
        )
        sb.configure(command=txt.yview)
        txt.pack(side='left', fill='both', expand=True)
        txt.tag_configure('titulo_versao', font=fonte_titulo_versao)

        def renderizar(_event=None):
            # Descontando o padx interno (10 de cada lado) e uma margem de segurança
            # proporcional - font.measure() não bate 100% com a renderização real do
            # widget, e o erro cresce com o tamanho da linha, então uma margem fixa em
            # pixels não bastava (linhas longas ainda cortavam na borda direita).
            largura_px = int((txt.winfo_width() - 20) * 0.90)
            if largura_px <= 10:
                return
            txt.config(state='normal')
            txt.delete('1.0', 'end')
            for i, (_versao, texto) in enumerate(historico):
                if i > 0:
                    txt.insert('end', '\n')
                # A primeira linha de cada nota ("GERAPED X.Y") já identifica a versão -
                # só destaca em negrito, sem duplicar como um título separado.
                primeira_linha, _, resto = texto.partition('\n')
                txt.insert('end', primeira_linha + '\n', 'titulo_versao')
                blocos = _preparar_paragrafos_notas(resto)
                for j, bloco in enumerate(blocos):
                    for prefixo, paragrafo in bloco:
                        linhas = _justificar_paragrafo(prefixo, paragrafo, fonte_notas, largura_px)
                        txt.insert('end', '\n'.join(linhas) + '\n')
                    if j < len(blocos) - 1:
                        txt.insert('end', '\n')
            txt.config(state='disabled')

        txt.bind('<Configure>', renderizar)

    def _construir_pagina_historico(self):
        for filho in self._pagina_historico.winfo_children():
            filho.destroy()
        historico = self._ler_historico()

        container = ttk.Frame(self._pagina_historico, padding=(28, 24, 20, 12), style="Pagina.TFrame")
        container.pack(fill='both', expand=True)

        cabecalho = ttk.Frame(container, style="Pagina.TFrame")
        cabecalho.pack(fill='x', pady=(0, 16))
        ttk.Label(cabecalho, text="Histórico", style="Titulo.TLabel").pack(anchor='w')
        ttk.Label(
            cabecalho, text="Documentos gerados recentemente - clique duas vezes para abrir.",
            style="Descricao.TLabel",
        ).pack(anchor='w', pady=(2, 0))

        # Card com borda (igual ao "Pedido 1" da página Pedidos) em volta da lista - ver o
        # mesmo comentário em _construir_pagina_ordem.
        cartao_casca, cartao, _ = _criar_cartao(container, 'Documentos gerados', expandir=True)
        cartao_casca.pack(fill='both', expand=True)

        frame_lista = ttk.Frame(cartao)
        frame_lista.pack(fill='both', expand=True)

        cols = ('data', 'arquivo')
        tree = ttk.Treeview(frame_lista, columns=cols, show='headings', selectmode='browse', bootstyle='secondary')
        # anchor='w' nos dois (cabeçalho e coluna) - por padrão o Treeview centraliza o
        # texto do cabeçalho mas alinha o valor das linhas à esquerda, o que destoava
        # visualmente (cabeçalho centralizado sobre valores alinhados à esquerda).
        tree.heading('data', text='Data', anchor='w')
        tree.heading('arquivo', text='Arquivo', anchor='w')
        tree.column('data', width=130, stretch=False, anchor='w')
        tree.column('arquivo', width=440, anchor='w')

        sb = ttk.Scrollbar(frame_lista, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        tree.pack(side='left', fill='both', expand=True)

        if not historico:
            tree.insert('', 'end', values=('—', 'Nenhum documento gerado ainda.'))
        else:
            for entrada in historico:
                nome = os.path.basename(entrada['caminho'])
                tree.insert('', 'end', values=(entrada['data'], nome), tags=(entrada['caminho'],))

        def abrir_selecionado(_event=None):
            sel = tree.selection()
            if not sel:
                return
            tags = tree.item(sel[0]).get('tags', [])
            if not tags:
                return
            caminho = tags[0]
            if os.path.isfile(caminho):
                os.startfile(caminho)
            else:
                _avisar(self.root, 'Arquivo não encontrado', f'O arquivo não existe mais:\n{caminho}')

        tree.bind('<Double-1>', abrir_selecionado)

        def limpar_historico():
            if not _confirmar(
                self.root,
                'Limpar histórico',
                'Tem certeza que deseja limpar todo o histórico de documentos gerados?\n'
                '(Os arquivos .docx já salvos não são apagados, só a lista de histórico.)',
            ):
                return
            try:
                with open(_caminho_historico(), 'w', encoding='utf-8') as f:
                    json.dump([], f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            for item in tree.get_children():
                tree.delete(item)
            tree.insert('', 'end', values=('—', 'Nenhum documento gerado ainda.'))

        ttk.Separator(container).pack(fill='x', pady=(8, 0))
        botoes = ttk.Frame(container, padding=(0, 10, 0, 0), style="Pagina.TFrame")
        botoes.pack(fill='x')
        ttk.Button(botoes, text='Limpar histórico', command=limpar_historico, bootstyle='danger-outline').pack(
            side='left',
        )
        ttk.Button(botoes, text='Abrir arquivo', command=abrir_selecionado, bootstyle='secondary').pack(side='right')

    # ── Geração do documento ─────────────────────────────────────────────────

    def gerar(self):
        if not self.blocos:
            _avisar(self.root, 'Aviso', 'Adicione ao menos um pedido.')
            return

        pedidos = []
        for i, bloco in enumerate(self.blocos, start=1):
            try:
                pedidos.append(bloco.obter_dados())
            except ValueError as exc:
                _avisar(self.root, 'Aviso', f'Pedido {i}: {exc}')
                return

        try:
            validar_itens_duplicados([pedido['item_peticao'] for pedido in pedidos])
        except ValueError as exc:
            _avisar(self.root, 'Aviso', str(exc))
            return

        try:
            # Pedidos vindos da petição trazem a tabela ("abaixo arrolados") logo após o texto; os
            # preenchidos à mão não têm tabela e saem exatamente como antes (gerar_documento do GERAPED).
            tabelas = [bloco.tabela_para_documento(dados) for bloco, dados in zip(self.blocos, pedidos)]
            if any(t is not None for t in tabelas):
                from autopedidos.documento import gerar_documento_com_tabelas_lista
                doc = gerar_documento_com_tabelas_lista(pedidos, tabelas)
            else:
                doc = gerar_documento(pedidos)
        except Exception as exc:
            logger.exception('Falha ao gerar o Word')
            _erro(self.root, 'Erro ao gerar', str(exc))
            return

        def _salvar():
            caminho = filedialog.asksaveasfilename(
                defaultextension='.docx',
                filetypes=[('Documento Word', '*.docx')],
                title='Salvar pedidos gerados',
            )
            if not caminho:
                return
            doc.save(caminho)
            self._anotar_geracao_no_log(pedidos, caminho)
            self._ultimo_documento = caminho
            self._botoes_resultado.pack(side='right')
            self._registrar_historico(caminho)
            _informar(self.root, 'Sucesso', f'Documento gerado em:\n{caminho}')

        _mostrar_preview(self.root, doc, _salvar)
