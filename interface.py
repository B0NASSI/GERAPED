import json
import os
import re
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog

import ttkbootstrap as ttk
from PIL import Image, ImageTk

import tema
from teses import TESES, TIPO_BENEFICIO_POR_ESPECIE, nome_para_chave, PARAMETROS_TESE, chave_para_opcao_parametro
from gerador_pedido import gerar_documento, COR_ITEM_PETICAO
from validacao import (
    validar_quantidade, validar_especies, limite_especies_excedido, limitar_especies,
    validar_itens_duplicados, especie_unica_travada, beneficio_subsidiario_pode_herdar_do_principal,
    validar_beneficios_subsidiaria, tese_permite_subsidiario,
)
from preferencias import ordenar_chaves_teses, ordenar_nomes_teses, salvar_ordem_teses, ordem_padrao_chaves

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


def _dialogo(widget, titulo, mensagem, icone, cor_icone, botoes):
    """Diálogo modal customizado (ícone + mensagem + botão(ões)) - substitui o messagebox
    nativo do Tk. O nativo, no Windows, sempre centraliza sobre a janela raiz de verdade
    (winfo_toplevel), ignorando qualquer "parent" auxiliar que a gente crie pra tentar
    deslocar a posição - não dava pra colocar o "Aviso" no lugar pedido usando ele. Aqui a
    posição é 100% nossa: mesma fórmula do toast de sucesso (ver Janela._mostrar_toast),
    que já está no lugar certo."""
    raiz = widget.winfo_toplevel()
    dialogo = tk.Toplevel(raiz)
    dialogo.title(titulo)
    dialogo.resizable(False, False)
    dialogo.transient(raiz)
    dialogo.configure(background=tema.COR_FUNDO)

    corpo = ttk.Frame(dialogo, padding=(24, 20))
    corpo.pack(fill='both', expand=True)
    linha = ttk.Frame(corpo)
    linha.pack(fill='x')
    ttk.Label(linha, text=icone, font=('Segoe UI', 18), foreground=cor_icone).pack(side='left', padx=(0, 16))
    ttk.Label(linha, text=mensagem, font=('Segoe UI', 10), wraplength=300, justify='left').pack(
        side='left', fill='x', expand=True,
    )

    resultado = {'valor': None}

    def escolher(valor):
        resultado['valor'] = valor
        dialogo.destroy()

    dialogo.protocol('WM_DELETE_WINDOW', lambda: escolher(None))

    rodape = ttk.Frame(corpo)
    rodape.pack(fill='x', pady=(20, 0))
    for i, texto in enumerate(botoes):
        estilo = 'primary' if i == len(botoes) - 1 else 'secondary-outline'
        ttk.Button(
            rodape, text=texto, command=lambda v=texto: escolher(v), bootstyle=estilo, width=10,
        ).pack(side='right', padx=(8, 0))

    dialogo.update_idletasks()
    largura, altura = dialogo.winfo_reqwidth(), dialogo.winfo_reqheight()
    largura_conteudo = raiz.winfo_width() - LARGURA_SIDEBAR
    x = raiz.winfo_rootx() + LARGURA_SIDEBAR + max(0, (largura_conteudo - largura) // 2)
    y = raiz.winfo_rooty() + (raiz.winfo_height() - altura) // 2
    dialogo.geometry(f'{largura}x{altura}+{x}+{y}')
    dialogo.grab_set()
    dialogo.wait_window()
    return resultado['valor']


def _avisar(widget, titulo, mensagem):
    _dialogo(widget, titulo, mensagem, '⚠', tema.COR_AVISO, ('OK',))


def _informar(widget, titulo, mensagem):
    _dialogo(widget, titulo, mensagem, '✓', tema.COR_SUCESSO, ('OK',))


def _erro(widget, titulo, mensagem):
    _dialogo(widget, titulo, mensagem, '✕', tema.COR_ERRO, ('OK',))


def _confirmar(widget, titulo, mensagem):
    return _dialogo(widget, titulo, mensagem, '?', tema.COR_PRIMARIA, ('Cancelar', 'Sim')) == 'Sim'

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


def _centralizar_janela(janela, root, largura, altura):
    janela.update_idletasks()
    x = root.winfo_x() + (root.winfo_width() - largura) // 2
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

    paragrafos = [p for p in doc.paragraphs if p.text.strip()]
    for i, paragrafo in enumerate(paragrafos):
        for run in paragrafo.runs:
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
        if i < len(paragrafos) - 1:
            txt.insert('end', '\n\n')

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
        ttk.Label(frame_parametro, text=rotulo).pack(side='left', padx=(0, 6))

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
        entry_texto = ttk.Entry(frame_parametro, width=42)
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
    redor dos cards (ver Pagina.TFrame). Aqui a borda é só um Frame de 1px (moldura) - como
    nada nunca desenha "por cima" dela, o bug não se aplica. 'interior' empacota o título
    (pack) e 'conteudo' (pack) como irmãos - 'conteudo' fica livre para os filhos reais do
    card usarem grid ou pack à vontade, sem conflitar com o pack do próprio título.

    Tentativa anterior usava cantos arredondados desenhados à mão num Canvas - abandonada:
    causava bugs visuais reais (borda invisível, corrida de redesenho em cards aninhados
    tipo "Tese subsidiária" dentro de "Pedido") sem terminar visualmente melhor que a borda
    quadrada simples. Card quadrado, mas 100% confiável, ganha da alternativa "bonita" mas
    quebrada.

    Retorna (casca, conteudo, rotulo_titulo): 'casca' é o que quem chama empacota/destrói;
    'conteudo' cumpre o mesmo papel de parent pros filhos que o Labelframe cumpria antes;
    'rotulo_titulo' é pra poder trocar o texto do título (ex: renumerar "Pedido 2" ->
    "Pedido 1")."""
    casca = ttk.Frame(parent, style="Pagina.TFrame")
    moldura = tk.Frame(casca, background=tema.COR_BORDA)
    moldura.pack(fill='both', expand=True)
    interior = ttk.Frame(moldura, padding=(padding, padding - 4, padding, padding))
    interior.pack(fill='both', expand=True, padx=1, pady=1)
    rotulo_titulo = ttk.Label(interior, text=titulo, style="TituloCartaoInterno.TLabel")
    rotulo_titulo.pack(anchor='w', pady=(0, 8))
    conteudo = ttk.Frame(interior)
    conteudo.pack(fill='both', expand=True)
    return casca, conteudo, rotulo_titulo


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
    def __init__(self, parent, on_remover, especie_travada=None):
        self.on_remover = on_remover

        self.frame = ttk.Frame(parent)
        self.frame.pack(fill='x', anchor='w', pady=3)

        self.var_especie = tk.StringVar(value='')
        self.radios_especie = {}
        for especie in ESPECIES_SUBSIDIARIA:
            radio = ttk.Radiobutton(self.frame, text=especie, variable=self.var_especie, value=especie)
            radio.pack(side='left', padx=(0, 10))
            self.radios_especie[especie] = radio

        ttk.Label(self.frame, text="Nº do benefício:").pack(side='left', padx=(8, 4))
        self.entry_numero = ttk.Entry(self.frame, width=18)
        self.entry_numero.pack(side='left', padx=(0, 8))

        ttk.Button(self.frame, text="×", width=3, command=self._remover, bootstyle='danger-outline').pack(side='left')

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
    def __init__(self, parent, on_remover, numero=1, obter_especie_travada=None):
        self.on_remover = on_remover
        # Consultado a cada novo benefício adicionado, para travar a espécie na mesma da
        # tese principal quando esta citar uma só espécie (ver BlocoPedido).
        self.obter_especie_travada = obter_especie_travada or (lambda: None)
        # teses com 'tipo_clausula' próprio (ex: Rotatividade, Erro de massa salarial) não
        # seguem o formato "do(s) benefício(s) X, motivo" usado aqui, então ficam de fora -
        # exceto Custo cessado, que tem um motivo por tipo (ver _motivo em gerador_pedido.py).
        nomes_teses = ordenar_nomes_teses(_chaves_teses_subsidiarias_compativeis())

        self._casca, self.frame, self._rotulo_titulo = _criar_cartao(parent, f"Tese subsidiária {numero}", padding=12)
        self._casca.pack(fill='x', expand=True, pady=(0, 8))

        linha = ttk.Frame(self.frame)
        linha.pack(fill='x', anchor='w')
        ttk.Label(linha, text="Tese:").grid(row=0, column=0, sticky='w', padx=(0, 6))
        self.combo_tese = ComboboxPesquisavel(linha, valores=nomes_teses, width=38)
        self.combo_tese.grid(row=0, column=1, sticky='w')
        self.combo_tese.bind('<<ComboboxSelected>>', lambda e: self._atualizar_parametro(), add='+')

        ttk.Label(linha, text="Item da petição:").grid(row=0, column=2, sticky='w', padx=(16, 6))
        self.entry_item = ttk.Entry(linha, width=10)
        self.entry_item.grid(row=0, column=3, sticky='w')

        self.frame_parametro = ttk.Frame(self.frame)
        self.frame_parametro.pack(fill='x', anchor='w', pady=(8, 0))
        self.combo_parametro = None
        self._atualizar_parametro()

        ttk.Label(self.frame, text="Benefícios desta tese subsidiária:").pack(anchor='w', pady=(10, 4))
        ttk.Label(
            self.frame,
            text="Se todos os benefícios forem subsidiários da mesma tese, não adicione benefícios.",
            style='Ajuda.TLabel', wraplength=560, justify='left',
        ).pack(anchor='w', pady=(0, 6))
        self.frame_beneficios = ttk.Frame(self.frame)
        self.frame_beneficios.pack(fill='x', anchor='w')
        self.linhas_beneficio = []

        rodape = ttk.Frame(self.frame)
        rodape.pack(fill='x', pady=(8, 0))
        ttk.Button(rodape, text="+ Adicionar benefício", command=self.adicionar_beneficio, bootstyle='primary-outline').pack(side='left')
        ttk.Button(rodape, text="Remover tese subsidiária", command=self._remover, bootstyle='danger-outline').pack(side='right')

        # Abre sem nenhum benefício adicionado (ver validar_beneficios_subsidiaria): o
        # usuário só adiciona uma linha se quiser especificar benefícios individuais - caso
        # contrário, entende-se que a tese subsidiária vale para todos os benefícios do
        # pedido principal.

    def _atualizar_parametro(self):
        self.combo_parametro = _reconstruir_combo_parametro(self.frame_parametro, self.combo_tese)

    def adicionar_beneficio(self):
        linha = LinhaBeneficio(
            self.frame_beneficios, on_remover=self._remover_linha_beneficio,
            especie_travada=self.obter_especie_travada(),
        )
        self.linhas_beneficio.append(linha)

    def _remover_linha_beneficio(self, linha):
        if linha in self.linhas_beneficio:
            self.linhas_beneficio.remove(linha)

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
    def __init__(self, parent, on_remover, numero=1):
        self.on_remover = on_remover
        nomes_teses = ordenar_nomes_teses()

        self._casca, self.frame, self._rotulo_titulo = _criar_cartao(parent, f"Pedido {numero}")
        self._casca.pack(fill='x', expand=True, pady=(0, 14), padx=2)

        # Espaço fixo entre a coluna de rótulos e a coluna de campos (~1cm), para não ficar
        # colado no rótulo mais curto. 'pad' soma espaço APÓS a coluna 0, empurrando a
        # coluna 1 (campos) para a direita. weight=1 faz a coluna de campos crescer com a
        # largura da caixa, em vez de sobrar uma faixa em branco à direita.
        self.frame.columnconfigure(0, pad=38)
        self.frame.columnconfigure(1, weight=1)

        ttk.Label(self.frame, text="Tese principal:").grid(row=0, column=0, sticky='w', pady=(0, 4))
        self.combo_tese = ComboboxPesquisavel(self.frame, valores=nomes_teses, width=45)
        self.combo_tese.grid(row=0, column=1, sticky='w', pady=(0, 4))
        self.combo_tese.bind(
            '<<ComboboxSelected>>',
            lambda e: [
                self._atualizar_parametro(), self._atualizar_estado_especies(), self._atualizar_estado_quantidade(),
                self._atualizar_estado_subsidiario(),
            ],
            add='+',
        )

        self.label_quantidade = ttk.Label(self.frame, text="Quantidade de benefícios:")
        self.label_quantidade.grid(row=1, column=0, sticky='w', pady=(8, 4))
        self.entry_quantidade = ttk.Entry(self.frame, width=10)
        self.entry_quantidade.grid(row=1, column=1, sticky='w', pady=(8, 4))
        self.entry_quantidade.bind('<KeyRelease>', lambda e: self._ao_mudar_quantidade())
        self._atualizar_estado_quantidade()

        self.label_especies = ttk.Label(self.frame, text="Espécie(s):")
        self.label_especies.grid(row=2, column=0, sticky='w', pady=(8, 4))
        self.frame_especies = frame_especies = ttk.Frame(self.frame)
        frame_especies.grid(row=2, column=1, sticky='w', pady=(8, 4))
        self.vars_especies = {especie: tk.BooleanVar(value=(i == 0)) for i, especie in enumerate(ESPECIES)}
        self.checks_especies = {}
        for especie in ESPECIES:
            check = ttk.Checkbutton(
                frame_especies, text=especie, variable=self.vars_especies[especie],
                command=lambda e=especie: self._ao_marcar_especie(e),
            )
            check.pack(side='left', padx=(0, 10))
            self.checks_especies[especie] = check
        self._atualizar_estado_especies()

        self.label_parametro = ttk.Label(self.frame)
        self.label_parametro.grid(row=3, column=0, sticky='w', pady=(8, 4))
        self.frame_parametro = ttk.Frame(self.frame)
        self.frame_parametro.grid(row=3, column=1, sticky='we', pady=(8, 4))
        self.combo_parametro = None
        self._atualizar_parametro()

        ttk.Label(self.frame, text="Item do pedido:").grid(row=4, column=0, sticky='w', pady=(8, 4))
        self.entry_item = ttk.Entry(self.frame, width=12)
        self.entry_item.grid(row=4, column=1, sticky='w', pady=(8, 4))

        self.grupos_subsidiarios = []

        self.var_subsidiario = tk.BooleanVar(value=False)
        self.check_subsidiario = ttk.Checkbutton(
            self.frame, text="Possui pedido subsidiário?", variable=self.var_subsidiario,
            command=self._alternar_subsidiario,
        )
        self.check_subsidiario.grid(row=5, column=0, columnspan=2, sticky='w', pady=(14, 0))

        self.frame_subsidiario = ttk.Frame(self.frame)
        self.frame_grupos = ttk.Frame(self.frame_subsidiario)
        self.frame_grupos.pack(fill='x', anchor='w')
        ttk.Button(
            self.frame_subsidiario, text="+ Adicionar tese subsidiária",
            command=self.adicionar_grupo_subsidiario, bootstyle='primary-outline',
        ).pack(anchor='w', pady=(6, 0))
        self._atualizar_estado_subsidiario()

        ttk.Separator(self.frame).grid(row=7, column=0, columnspan=2, sticky='ew', pady=(14, 10))
        ttk.Button(self.frame, text="Remover este pedido", command=self._remover, bootstyle='danger-outline').grid(
            row=8, column=0, columnspan=2, sticky='e',
        )

    def _atualizar_parametro(self):
        self.combo_parametro = _reconstruir_combo_parametro(
            self.frame_parametro, self.combo_tese, label_widget=self.label_parametro,
        )
        # Teses sem campo extra não reservam a linha (some o espaço em branco e "Item do
        # pedido" sobe, ficando logo abaixo de "Tese principal").
        if self.combo_parametro is None:
            self.label_parametro.grid_remove()
            self.frame_parametro.grid_remove()
        else:
            self.label_parametro.grid(row=3, column=0, sticky='w', pady=(8, 4))
            self.frame_parametro.grid(row=3, column=1, sticky='we', pady=(8, 4))

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
            self.entry_quantidade.grid_remove()
        else:
            self.label_quantidade.grid()
            self.entry_quantidade.grid()

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
            self.frame_grupos, on_remover=self._remover_grupo_subsidiario, numero=len(self.grupos_subsidiarios) + 1,
            obter_especie_travada=self._especie_unica_travada,
        )
        self.grupos_subsidiarios.append(grupo)

    def _especie_unica_travada(self):
        especies = [e for e in ESPECIES if self.vars_especies[e].get()]
        return especie_unica_travada(especies, ESPECIES_SUBSIDIARIA)

    def _atualizar_travamento_subsidiarias(self):
        for grupo in self.grupos_subsidiarios:
            grupo.atualizar_travamento_especie()

    def _remover_grupo_subsidiario(self, grupo):
        if grupo in self.grupos_subsidiarios:
            self.grupos_subsidiarios.remove(grupo)
        for i, g in enumerate(self.grupos_subsidiarios, start=1):
            g._rotulo_titulo.configure(text=f"Tese subsidiária {i}")

    def _remover(self):
        if not _confirmar(
            self.frame,
            'Remover pedido',
            'Tem certeza que deseja remover este pedido? Os dados preenchidos serão perdidos.',
        ):
            return
        self._casca.destroy()
        self.on_remover(self)

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
        principal = ttk.Frame(root)
        principal.pack(side='left', fill='both', expand=True)

        area_paginas = ttk.Frame(principal)
        area_paginas.pack(fill='both', expand=True)
        area_paginas.grid_rowconfigure(0, weight=1)
        area_paginas.grid_columnconfigure(0, weight=1)

        self._pagina_pedidos = ttk.Frame(area_paginas)
        self._pagina_historico = ttk.Frame(area_paginas)
        self._pagina_ordem = ttk.Frame(area_paginas)
        for pagina in (self._pagina_pedidos, self._pagina_historico, self._pagina_ordem):
            pagina.grid(row=0, column=0, sticky='nsew')

        botoes = ttk.Frame(self._pagina_pedidos, padding=(28, 12, 28, 16), style="Pagina.TFrame")
        botoes.pack(fill='x', side='bottom')
        ttk.Separator(self._pagina_pedidos).pack(fill='x', side='bottom')
        ttk.Button(botoes, text="+ Adicionar pedido", command=self.adicionar_pedido, bootstyle='primary-outline').pack(side='left')
        ttk.Button(botoes, text="Limpar", command=self._limpar_tudo, bootstyle='danger-link').pack(side='left', padx=(8, 0))
        ttk.Button(botoes, text="Gerar Word", bootstyle='secondary', command=self.gerar).pack(side='right')
        # só aparecem depois que existe um documento gerado
        self._botoes_resultado = ttk.Frame(botoes)
        ttk.Button(self._botoes_resultado, text="Abrir documento", command=self._abrir_ultimo_documento, bootstyle='light').pack(side='left', padx=(0, 8))
        ttk.Button(self._botoes_resultado, text="Abrir pasta", command=self._abrir_pasta_ultimo_documento, bootstyle='light').pack(side='left', padx=(0, 12))

        container = ttk.Frame(self._pagina_pedidos, padding=(28, 24, 20, 12), style="Pagina.TFrame")
        container.pack(fill='both', expand=True)

        cabecalho = ttk.Frame(container, style="Pagina.TFrame")
        cabecalho.pack(fill='x', pady=(0, 16))
        ttk.Label(cabecalho, text="Pedidos", style="Titulo.TLabel").pack(anchor='w')
        ttk.Label(
            cabecalho, text="Monte os pedidos de exclusão de benefícios e gere o texto em Word",
            style="Descricao.TLabel",
        ).pack(anchor='w', pady=(2, 0))

        self.canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0, background=tema.COR_FUNDO_SUAVE)

        def _ao_mover_scrollbar(*args):
            self.canvas.yview(*args)
            # Arrastar a barra chama canvas.yview diretamente - sem isso, arrastar o
            # "polegar" (ou clicar na calha) conseguia mover o conteúdo mesmo quando ele já
            # cabia inteiro na tela, já que só a roda do mouse (_ao_rolar) tinha essa trava.
            self._atualizar_scrollregion()

        scrollbar = ttk.Scrollbar(container, orient='vertical', command=_ao_mover_scrollbar)
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
        self.canvas.configure(yscrollcommand=scrollbar.set, yscrollincrement=15)
        self.canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        # bind no root (não bind_all!) - bind_all usa a bindtag "all", que também afeta a
        # lista suspensa da tese (é uma janela própria, mas "all" é realmente global). Preso
        # ao root, só dispara para widgets desta janela, deixando a lista suspensa em paz.
        self.root.bind('<MouseWheel>', self._ao_rolar)

        self.adicionar_pedido()
        # No arranque, a janela ainda não foi mapeada na tela quando adicionar_pedido() roda
        # (estamos antes do mainloop) - a largura/altura reais do canvas só ficam corretas
        # depois disso, então o ajuste de posição feito lá pode errar. after_idle roda assim
        # que o loop principal começar a processar eventos, já com o layout final.
        self.root.after_idle(self._corrigir_posicao_inicial)

        self._mostrar_pagina('pedidos')

    def _montar_sidebar(self, root):
        barra = ttk.Frame(root, style="Sidebar.TFrame", width=LARGURA_SIDEBAR)
        barra.pack(side='left', fill='y')
        barra.pack_propagate(False)

        topo = ttk.Frame(barra, style="Sidebar.TFrame", padding=(20, 26, 20, 18))
        topo.pack(fill='x')
        caminho_logo = self._res('logo_completa.png')
        if os.path.isfile(caminho_logo):
            self._imagem_marca = _carregar_logo_para_fundo_escuro(caminho_logo, 40)
            ttk.Label(topo, image=self._imagem_marca, style="Sidebar.TLabel").pack(anchor='w')
        ttk.Frame(barra, style="Acento.TFrame", height=3).pack(fill='x', padx=20)

        produto = ttk.Frame(barra, style="Sidebar.TFrame", padding=(20, 16, 20, 14))
        produto.pack(fill='x')
        ttk.Label(produto, text="GERAPED", style="Sidebar.TLabel", font=("Segoe UI", 20, "bold")).pack(anchor='w')
        ttk.Label(produto, text="Gerador de Pedidos", style="SidebarSuave.TLabel").pack(anchor='w')

        # As 3 páginas (Pedidos/Histórico/Ordem) ficam sobrepostas na mesma janela (ver
        # area_paginas no __init__) - aqui só guardamos as referências de cada linha
        # (acento + botão) pra alternar o destaque visual em _mostrar_pagina, já que agora
        # qualquer uma das 3 pode estar ativa (antes só "Pedidos" existia e ficava sempre
        # marcada).
        self._linhas_nav = {}
        for nome, texto, comando in (
            ('pedidos', "☰   Pedidos", lambda: self._mostrar_pagina('pedidos')),
            ('historico', "↻   Histórico", lambda: self._mostrar_pagina('historico')),
            ('ordem', "⚙   Ordem", lambda: self._mostrar_pagina('ordem')),
        ):
            linha = ttk.Frame(barra, style="Sidebar.TFrame")
            linha.pack(fill='x')
            acento = ttk.Frame(linha, style="Sidebar.TFrame", width=4)
            acento.pack(side='left', fill='y')
            botao = ttk.Button(linha, text=texto, style="Nav.TButton", command=comando)
            botao.pack(side='left', fill='x', expand=True)
            self._linhas_nav[nome] = (acento, botao)

        rodape = ttk.Frame(barra, style="Sidebar.TFrame", padding=(0, 0, 0, 16))
        rodape.pack(side='bottom', fill='x')
        # divisor sutil separando o rodapé do resto da sidebar - sem ele o rodapé ficava
        # "boiando" no meio do azul, sem nada delimitando onde a navegação termina. side=
        # 'bottom' e packado DEPOIS de "rodape" (que também é 'bottom') - assim ele ocupa a
        # fatia logo ACIMA do rodapé, não logo abaixo dos itens de navegação lá em cima
        # (pack empilha widgets 'bottom' na ordem em que são chamados, de baixo pra cima).
        ttk.Frame(barra, style="SidebarDivisor.TFrame", height=1).pack(side='bottom', fill='x', padx=20, pady=(0, 4))
        self._criar_link_sidebar(rodape, 'ⓘ', 'Notas de atualização', self._mostrar_notas_atualizacao)
        self._criar_link_sidebar(rodape, '?', 'Manual rápido', self._mostrar_manual)
        ttk.Label(rodape, text=f"Versão {self._versao}", style="SidebarSuave.TLabel").pack(anchor='w', padx=20, pady=(12, 0))

    def _criar_link_sidebar(self, pai, icone, texto, comando):
        """Link do rodapé da barra lateral (ícone + texto). Dois rótulos em vez de um único
        Button com "ícone + espaços + título": o ícone fica numa coluna de largura FIXA EM
        PIXELS (pack_propagate desligado), então o texto sempre começa no mesmo X."""
        linha = ttk.Frame(pai, style="Sidebar.TFrame", cursor='hand2')
        linha.pack(fill='x')
        caixa_icone = ttk.Frame(linha, style="Sidebar.TFrame", width=28, height=24)
        caixa_icone.pack(side='left', padx=(20, 0), pady=6)
        caixa_icone.pack_propagate(False)
        rotulo_icone = ttk.Label(caixa_icone, text=icone, style="SidebarIcone.TLabel", anchor='center')
        rotulo_icone.pack(fill='both', expand=True)
        rotulo_texto = ttk.Label(linha, text=texto, style="SidebarLink.TLabel", anchor='w')
        rotulo_texto.pack(side='left', fill='x', expand=True, pady=6)

        def _ao_passar(_evt=None):
            rotulo_icone.configure(style="SidebarIconeAtivo.TLabel")
            rotulo_texto.configure(style="SidebarLinkAtivo.TLabel")

        def _ao_sair(_evt=None):
            rotulo_icone.configure(style="SidebarIcone.TLabel")
            rotulo_texto.configure(style="SidebarLink.TLabel")

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
        paginas[nome].tkraise()

        for chave, (acento, botao) in self._linhas_nav.items():
            ativo = chave == nome
            acento.configure(style="Acento.TFrame" if ativo else "Sidebar.TFrame")
            botao.configure(style="NavAtivo.TButton" if ativo else "Nav.TButton")

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
        tk.Label(
            toast, text=mensagem, background=cor_fundo, foreground='#FFFFFF',
            font=('Segoe UI', 10, 'bold'), padx=22, pady=12,
        ).pack()
        toast.update_idletasks()
        largura, altura = toast.winfo_reqwidth(), toast.winfo_reqheight()
        # Centralizado verticalmente no meio da janela inteira (mesmo eixo em que o
        # messagebox padrão, ex: o "Aviso" de validação, sempre aparece, pra ficar
        # previsível - não perto do topo, sobrepondo o cabeçalho da página). Horizontalmente,
        # centralizado só na área de CONTEÚDO (excluindo a sidebar): centralizar na janela
        # inteira jogava o toast visualmente pra esquerda, "puxado" pela sidebar, que não tem
        # contraparte à direita.
        largura_conteudo = self.root.winfo_width() - LARGURA_SIDEBAR
        x = self.root.winfo_rootx() + LARGURA_SIDEBAR + max(0, (largura_conteudo - largura) // 2)
        y = self.root.winfo_rooty() + (self.root.winfo_height() - altura) // 2
        toast.geometry(f'{largura}x{altura}+{x}+{y}')
        toast.after(1300, toast.destroy)

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
        bloco = BlocoPedido(self.frame_interno, on_remover=self._remover_bloco, numero=len(self.blocos) + 1)
        self.blocos.append(bloco)
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
        _centralizar_janela(janela, self.root, 620, 560)
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
                    for prefixo, paragrafo in (item for bloco in _preparar_paragrafos_notas(conteudo) for item in bloco):
                        linhas = _justificar_paragrafo(prefixo, paragrafo, fonte_manual, largura_px)
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
        _centralizar_janela(janela, self.root, 560, 520)
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
            doc = gerar_documento(pedidos)
        except Exception as exc:
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
            self._ultimo_documento = caminho
            self._botoes_resultado.pack(side='right')
            self._registrar_historico(caminho)
            _informar(self.root, 'Sucesso', f'Documento gerado em:\n{caminho}')

        _mostrar_preview(self.root, doc, _salvar)
