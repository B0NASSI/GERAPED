import json
import os
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from PIL import Image, ImageTk

import tema
import visual
from teses import TESES, TIPO_BENEFICIO_POR_ESPECIE, nome_para_chave, PARAMETROS_TESE, chave_para_opcao_parametro
from gerador_pedido import gerar_documento, COR_ITEM_PETICAO
from validacao import (
    validar_quantidade, validar_especies, limite_especies_excedido, limitar_especies,
    validar_itens_duplicados, especie_unica_travada, beneficio_subsidiario_pode_herdar_do_principal,
    validar_beneficios_subsidiaria,
)
from preferencias import ordenar_chaves_teses, ordenar_nomes_teses, salvar_ordem_teses

ESPECIES = list(TIPO_BENEFICIO_POR_ESPECIE.keys())
ESPECIES_SUBSIDIARIA = ['B91', 'B92', 'B93', 'B94']

# Teses que aparecem como opção de tese subsidiária (ver GrupoSubsidiario) - só as que
# seguem o formato "do(s) benefício(s) X, motivo" (têm 'motivo_singular') ou Custo cessado.
def _chaves_teses_subsidiarias_compativeis():
    return [
        chave for chave, t in TESES.items()
        if 'motivo_singular' in t or t.get('tipo_clausula') == 'custo_cessado'
    ]

LARGURA_BANNER = 760
ALTURA_BANNER  = 110


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


def _centralizar_janela(janela, root, largura, altura):
    janela.update_idletasks()
    x = root.winfo_x() + (root.winfo_width() - largura) // 2
    y = root.winfo_y() + (root.winfo_height() - altura) // 2
    # Evita que a janela fique cortada quando a janela principal está pequena
    # ou próxima da borda da tela (ex: com apenas 1 pedido, root fica bem baixo).
    # A barra de título fica acima da coordenada y informada - por isso a margem
    # no topo, senão ela é cortada pelo limite da tela.
    margem_topo = 40
    x = max(0, min(x, janela.winfo_screenwidth() - largura))
    y = max(margem_topo, min(y, janela.winfo_screenheight() - altura))
    janela.geometry(f'{largura}x{altura}+{x}+{y}')


def _preparar_paragrafos_notas(texto):
    """Reagrupa o texto (quebrado em linhas fixas no .txt) em parágrafos lógicos, pra poder
    rejustificar do zero na largura real da janela. Linhas em branco separam blocos; dentro
    de um bloco, uma linha começando com "- " inicia um item de lista, e as linhas
    indentadas seguintes são continuação do mesmo item (juntadas por espaço)."""
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
        if linha.lstrip().startswith('- '):
            if item_atual is not None:
                bloco_atual.append(item_atual)
            item_atual = ('- ', linha.lstrip()[2:].strip())
        elif item_atual is not None:
            item_atual = (item_atual[0], item_atual[1] + ' ' + linha.strip())
        else:
            item_atual = ('', linha.strip())
    if item_atual is not None:
        bloco_atual.append(item_atual)
    if bloco_atual:
        blocos.append(bloco_atual)
    return blocos


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
        """Troca a lista de opções (ex: nova ordem de teses salva em Opções), preservando o
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

        ttk.Label(self.frame, text="Nº do benefício (opcional):").pack(side='left', padx=(8, 4))
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

        self.frame = ttk.Labelframe(parent, text=f"Tese subsidiária {numero}", padding=12, bootstyle='secondary')
        self.frame.pack(fill='x', expand=True, pady=(0, 8))

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
            bootstyle='secondary', font=('Segoe UI', 8), wraplength=560, justify='left',
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
        if not messagebox.askyesno(
            'Remover tese subsidiária',
            'Tem certeza que deseja remover esta tese subsidiária? Os dados preenchidos serão perdidos.',
            parent=self.frame.winfo_toplevel(),
        ):
            return
        self.frame.destroy()
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

        # Nenhum benefício informado: se o pedido principal tiver mais de 1 benefício,
        # entende-se que o subsidiário se aplica a todos eles (fica no plural, sem números
        # avulsos). Com quantidade principal 1 (ou não informada) ainda é obrigatório
        # informar o benefício.
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
        }


class BlocoPedido:
    def __init__(self, parent, on_remover, numero=1):
        self.on_remover = on_remover
        nomes_teses = ordenar_nomes_teses()

        self.frame = ttk.Labelframe(parent, text=f"Pedido {numero}", padding=14, bootstyle='secondary')
        self.frame.pack(fill='x', expand=True, pady=(0, 14), padx=2)

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
            ],
            add='+',
        )

        ttk.Label(self.frame, text="Quantidade de benefícios:").grid(row=1, column=0, sticky='w', pady=(8, 4))
        self.entry_quantidade = ttk.Entry(self.frame, width=10)
        self.entry_quantidade.grid(row=1, column=1, sticky='w', pady=(8, 4))
        self.entry_quantidade.bind('<KeyRelease>', lambda e: self._ao_mudar_quantidade())
        self._atualizar_estado_quantidade()

        ttk.Label(self.frame, text="Espécie(s):").grid(row=2, column=0, sticky='w', pady=(8, 4))
        frame_especies = ttk.Frame(self.frame)
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
        ttk.Checkbutton(
            self.frame, text="Possui pedido subsidiário?", variable=self.var_subsidiario,
            command=self._alternar_subsidiario,
        ).grid(row=5, column=0, columnspan=2, sticky='w', pady=(14, 0))

        self.frame_subsidiario = ttk.Frame(self.frame)
        self.frame_grupos = ttk.Frame(self.frame_subsidiario)
        self.frame_grupos.pack(fill='x', anchor='w')
        ttk.Button(
            self.frame_subsidiario, text="+ Adicionar tese subsidiária",
            command=self.adicionar_grupo_subsidiario, bootstyle='primary-outline',
        ).pack(anchor='w', pady=(6, 0))

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
        """Desabilita (cinza, só visual) a escolha de espécie quando a tese selecionada não
        depende da espécie do benefício (ex: Rotatividade, CAT não vinculada)."""
        tese = TESES.get(nome_para_chave(self.combo_tese.get()))
        ignora = bool(tese and tese.get('ignora_especie'))
        estado = 'disabled' if ignora else 'normal'
        for check in self.checks_especies.values():
            check.configure(state=estado)

    def _atualizar_estado_quantidade(self):
        """Desabilita (cinza, só visual) a quantidade quando a tese selecionada não depende
        dela (ex: Prescrição quinquenal, Erro de massa salarial - só citam vigência)."""
        tese = TESES.get(nome_para_chave(self.combo_tese.get()))
        ignora = bool(tese and tese.get('ignora_quantidade'))
        self.entry_quantidade.configure(state='disabled' if ignora else 'normal')

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
            messagebox.showwarning(
                'Aviso',
                f'Com quantidade {quantidade}, selecione no máximo {quantidade} espécie{plural} de benefício.',
                parent=self.frame.winfo_toplevel(),
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
            g.frame.configure(text=f"Tese subsidiária {i}")

    def _remover(self):
        if not messagebox.askyesno(
            'Remover pedido',
            'Tem certeza que deseja remover este pedido? Os dados preenchidos serão perdidos.',
            parent=self.frame.winfo_toplevel(),
        ):
            return
        self.frame.destroy()
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

        # ── Banner (regenerado ao redimensionar, para cobrir a largura toda) ────
        self._icone_banner = _res('icone.ico')
        self._largura_banner_atual = LARGURA_BANNER
        self._debounce_banner_id = None
        self._label_banner = tk.Label(root, borderwidth=0, background=tema.COR_PRIMARIA)
        self._label_banner.pack(fill='x')
        self._atualizar_banner(LARGURA_BANNER)
        self._label_banner.bind('<Configure>', self._ao_redimensionar_banner)

        # ── Rodapé (pack side=bottom ANTES do conteúdo) ───────────────────────
        rodape = ttk.Frame(root, padding=(14, 8, 14, 8))
        rodape.pack(fill='x', side='bottom')
        caminho_logo = _res('logo_completa.png')
        if os.path.isfile(caminho_logo):
            img = Image.open(caminho_logo).convert('RGBA')
            h = 26
            w = int(img.width * h / img.height)
            self._logo = ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))
            tk.Label(rodape, image=self._logo, borderwidth=0, background=tema.COR_FUNDO).pack(side='left')
        ttk.Label(rodape, text=f'versão {self._versao}', bootstyle='secondary', font=('Segoe UI', 8)).pack(side='right')

        # ── Barra de botões (side=bottom) ────────────────────────────────────
        ttk.Separator(root).pack(fill='x', side='bottom')
        botoes = ttk.Frame(root, padding=(18, 10, 18, 12))
        botoes.pack(fill='x', side='bottom')
        ttk.Button(botoes, text="+ Adicionar pedido", command=self.adicionar_pedido, bootstyle='primary').pack(side='left')
        ttk.Button(botoes, text="Limpar", command=self._limpar_tudo, bootstyle='danger-outline').pack(side='left', padx=(8, 0))
        ttk.Button(botoes, text="Gerar Word", bootstyle='secondary', command=self.gerar).pack(side='right')
        ttk.Button(botoes, text="Abrir documento", command=self._abrir_ultimo_documento, bootstyle='primary-outline').pack(side='right', padx=(0, 8))
        ttk.Button(botoes, text="Abrir pasta", command=self._abrir_pasta_ultimo_documento, bootstyle='primary-outline').pack(side='right', padx=(0, 8))

        # ── Área de conteúdo (preenche o espaço restante) ────────────────────
        container = ttk.Frame(root, padding=(18, 12, 18, 12))
        container.pack(fill='both', expand=True)

        barra_topo = ttk.Frame(container)
        barra_topo.pack(fill='x', pady=(0, 10))
        ttk.Button(barra_topo, text="Histórico", command=self._mostrar_historico, bootstyle='primary-outline').pack(side='right')
        ttk.Button(barra_topo, text="Opções", command=self._mostrar_opcoes, bootstyle='primary-outline').pack(side='right', padx=(0, 8))
        ttk.Button(
            barra_topo, text="Notas de atualização", command=self._mostrar_notas_atualizacao, bootstyle='primary-outline',
        ).pack(side='right', padx=(0, 8))

        self.canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0, background=tema.COR_FUNDO)

        def _ao_mover_scrollbar(*args):
            self.canvas.yview(*args)
            # Arrastar a barra chama canvas.yview diretamente - sem isso, arrastar o
            # "polegar" (ou clicar na calha) conseguia mover o conteúdo mesmo quando ele já
            # cabia inteiro na tela, já que só a roda do mouse (_ao_rolar) tinha essa trava.
            self._atualizar_scrollregion()

        scrollbar = ttk.Scrollbar(container, orient='vertical', command=_ao_mover_scrollbar)
        self.frame_interno = ttk.Frame(self.canvas)
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

    def _atualizar_banner(self, largura):
        largura = max(largura, 300)
        self._imagem_banner = ImageTk.PhotoImage(
            visual.gerar_banner(
                largura=largura,
                altura=ALTURA_BANNER,
                cor_inicio=tema.COR_PRIMARIA,
                cor_fim='#1A1C3D',
                cor_destaque=tema.COR_SECUNDARIA,
                icone_path=self._icone_banner,
                titulo='GERAPED - Gerador de Pedidos',
                subtitulo='Monte os pedidos de exclusão de benefícios e gere o texto em Word',
            )
        )
        self._label_banner.configure(image=self._imagem_banner)
        self._largura_banner_atual = largura

    def _ao_redimensionar_banner(self, event):
        if abs(event.width - self._largura_banner_atual) < 4:
            return
        if self._debounce_banner_id:
            self.root.after_cancel(self._debounce_banner_id)
        largura = event.width
        self._debounce_banner_id = self.root.after(120, lambda: self._atualizar_banner(largura))

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
            b.frame.configure(text=f"Pedido {i}")

    # ── Limpar tudo ───────────────────────────────────────────────────────────

    def _limpar_tudo(self):
        if not messagebox.askyesno(
            'Limpar tudo',
            'Tem certeza que deseja limpar todos os pedidos preenchidos?',
        ):
            return
        for bloco in list(self.blocos):
            bloco.frame.destroy()
        self.blocos.clear()
        self.adicionar_pedido()

    # ── Último documento gerado ──────────────────────────────────────────────

    def _abrir_pasta_ultimo_documento(self):
        if not self._ultimo_documento or not os.path.isfile(self._ultimo_documento):
            messagebox.showwarning('Aviso', 'Nenhum documento foi salvo ainda nesta sessão.')
            return
        os.startfile(os.path.dirname(self._ultimo_documento))

    def _abrir_ultimo_documento(self):
        if not self._ultimo_documento or not os.path.isfile(self._ultimo_documento):
            messagebox.showwarning('Aviso', 'Nenhum documento foi salvo ainda nesta sessão.')
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

    # ── Opções (ordem das teses) ─────────────────────────────────────────────

    def _atualizar_ordem_teses_em_todos_combos(self):
        """Aplica a nova ordem salva aos combos de tese já existentes na tela (pedidos e
        teses subsidiárias abertos), sem precisar recriar os blocos."""
        chaves_subsidiaria = _chaves_teses_subsidiarias_compativeis()
        for bloco in self.blocos:
            bloco.combo_tese.atualizar_valores(ordenar_nomes_teses())
            for grupo in bloco.grupos_subsidiarios:
                grupo.combo_tese.atualizar_valores(ordenar_nomes_teses(chaves_subsidiaria))

    def _mostrar_opcoes(self):
        chaves_estado = ordenar_chaves_teses()

        janela = tk.Toplevel(self.root)
        janela.title('Opções — Ordem das teses')
        _centralizar_janela(janela, self.root, 460, 520)
        janela.transient(self.root)
        janela.grab_set()
        janela.resizable(True, True)

        ttk.Label(
            janela, text='Ordem de exibição das teses nos comboboxes:', font=('Segoe UI', 10, 'bold'),
        ).pack(anchor='w', padx=16, pady=(14, 2))
        ttk.Label(
            janela, text='Selecione uma tese e use os botões para movê-la.',
            bootstyle='secondary', font=('Segoe UI', 9),
        ).pack(anchor='w', padx=16, pady=(0, 8))

        frame_lista = ttk.Frame(janela, padding=(16, 0, 16, 0))
        frame_lista.pack(fill='both', expand=True)

        lista = tk.Listbox(frame_lista, activestyle='none', font=('Segoe UI', 10), exportselection=False)
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
            chaves_estado[:] = sorted(TESES.keys(), key=lambda c: TESES[c]['nome'])
            lista.delete(0, 'end')
            for chave in chaves_estado:
                lista.insert('end', TESES[chave]['nome'])

        def salvar():
            salvar_ordem_teses(chaves_estado)
            self._atualizar_ordem_teses_em_todos_combos()
            janela.destroy()

        botoes_mover = ttk.Frame(janela, padding=(16, 8, 16, 0))
        botoes_mover.pack(fill='x')
        ttk.Button(botoes_mover, text='▲ Mover para cima', command=lambda: mover(-1), bootstyle='primary-outline').pack(
            side='left',
        )
        ttk.Button(botoes_mover, text='▼ Mover para baixo', command=lambda: mover(1), bootstyle='primary-outline').pack(
            side='left', padx=(8, 0),
        )

        ttk.Separator(janela).pack(fill='x', pady=(12, 0))
        botoes = ttk.Frame(janela, padding=(16, 10))
        botoes.pack(fill='x')
        ttk.Button(botoes, text='Restaurar padrão (A-Z)', command=restaurar_padrao, bootstyle='secondary-outline').pack(
            side='left',
        )
        ttk.Button(botoes, text='Cancelar', command=janela.destroy, bootstyle='secondary-outline').pack(
            side='left', padx=(8, 0),
        )
        ttk.Button(botoes, text='Salvar', command=salvar, bootstyle='secondary').pack(side='right')

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

        ttk.Separator(janela).pack(fill='x', pady=(8, 0))
        botoes = ttk.Frame(janela, padding=(16, 10))
        botoes.pack(fill='x')
        ttk.Button(botoes, text='Fechar', command=janela.destroy, bootstyle='secondary-outline').pack(side='right')

    def _mostrar_historico(self):
        historico = self._ler_historico()

        janela = tk.Toplevel(self.root)
        janela.title('Histórico de documentos gerados')
        _centralizar_janela(janela, self.root, 620, 380)
        janela.transient(self.root)
        janela.grab_set()
        janela.resizable(True, True)

        ttk.Label(janela, text='Documentos gerados recentemente:', font=('Segoe UI', 10, 'bold')).pack(
            anchor='w', padx=16, pady=(14, 6),
        )

        frame_lista = ttk.Frame(janela, padding=(16, 0, 16, 0))
        frame_lista.pack(fill='both', expand=True)

        cols = ('data', 'arquivo')
        tree = ttk.Treeview(frame_lista, columns=cols, show='headings', selectmode='browse', bootstyle='secondary')
        tree.heading('data', text='Data')
        tree.heading('arquivo', text='Arquivo')
        tree.column('data', width=130, stretch=False)
        tree.column('arquivo', width=440)

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
                messagebox.showwarning('Arquivo não encontrado', f'O arquivo não existe mais:\n{caminho}', parent=janela)

        tree.bind('<Double-1>', abrir_selecionado)

        def limpar_historico():
            if not messagebox.askyesno(
                'Limpar histórico',
                'Tem certeza que deseja limpar todo o histórico de documentos gerados?\n'
                '(Os arquivos .docx já salvos não são apagados, só a lista de histórico.)',
                parent=janela,
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

        ttk.Separator(janela).pack(fill='x', pady=(8, 0))
        botoes = ttk.Frame(janela, padding=(16, 10))
        botoes.pack(fill='x')
        ttk.Button(botoes, text='Fechar', command=janela.destroy, bootstyle='secondary-outline').pack(side='left')
        ttk.Button(botoes, text='Limpar histórico', command=limpar_historico, bootstyle='danger-outline').pack(
            side='left', padx=(8, 0),
        )
        ttk.Button(botoes, text='Abrir arquivo', command=abrir_selecionado, bootstyle='secondary').pack(side='right')

    # ── Geração do documento ─────────────────────────────────────────────────

    def gerar(self):
        if not self.blocos:
            messagebox.showwarning('Aviso', 'Adicione ao menos um pedido.')
            return

        pedidos = []
        for i, bloco in enumerate(self.blocos, start=1):
            try:
                pedidos.append(bloco.obter_dados())
            except ValueError as exc:
                messagebox.showwarning('Aviso', f'Pedido {i}: {exc}')
                return

        try:
            validar_itens_duplicados([pedido['item_peticao'] for pedido in pedidos])
        except ValueError as exc:
            messagebox.showwarning('Aviso', str(exc))
            return

        try:
            doc = gerar_documento(pedidos)
        except Exception as exc:
            messagebox.showerror('Erro ao gerar', str(exc))
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
            self._registrar_historico(caminho)
            messagebox.showinfo('Sucesso', f'Documento gerado em:\n{caminho}')

        _mostrar_preview(self.root, doc, _salvar)
