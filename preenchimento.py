"""Ponte entre o motor de leitura da petição (pacote autopedidos/) e a tela do GERAPED.

  ler_peticao_para_blocos(caminho)  -> ResultadoLeitura   (.docx -> pedidos propostos; tudo local)
  preencher_bloco(bloco, proposto)  -> preenche um BlocoPedido pelos mesmos handlers da tela
  aplicar_ntp(blocos)               -> aplica "excluir NTP" depois que a Janela liberou o NTP
  mostrar_resumo(...)               -> janela com confiança, pendências e o que o programa não leu

Nada aqui gera o Word: o usuário revisa/edita os blocos e clica em "Gerar Word" como sempre.
"""
from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk as _ttk

from teses import PARAMETROS_TESE, TESES, TIPO_BENEFICIO_POR_ESPECIE

ESPECIES = list(TIPO_BENEFICIO_POR_ESPECIE.keys())


@dataclass
class ResultadoLeitura:
    caminho: str
    peticao: object
    deteccao: object
    proposta: object


def ler_peticao_para_blocos(caminho):
    from autopedidos import revisao
    peticao, deteccao, proposta = revisao.processar(caminho)
    return ResultadoLeitura(caminho=caminho, peticao=peticao, deteccao=deteccao, proposta=proposta)


def _texto(entry, valor):
    entry.delete(0, 'end')
    entry.insert(0, valor)


def _rotulo_parametro(parametro_id, valor):
    return PARAMETROS_TESE[parametro_id]['opcoes'].get(valor, '') if valor else ''


def preencher_bloco(bloco, proposto):
    """Preenche um BlocoPedido recém-criado. Dispara os mesmos handlers que o usuário aciona ao
    escolher a tese/quantidade/espécie, para que as regras do GERAPED (campos que somem, limites
    de espécie, travas das subsidiárias...) continuem valendo."""
    d = proposto.dados
    tese = TESES[d['tese_key']]
    bloco.proposto = proposto

    bloco.combo_tese.set(tese['nome'])
    bloco._atualizar_parametro()
    bloco._atualizar_estado_especies()
    bloco._atualizar_estado_quantidade()
    bloco._atualizar_estado_subsidiario()
    bloco._atualizar_estado_ntp()
    bloco._on_mudar_vigencia_ntp()

    if not tese.get('ignora_quantidade'):
        _texto(bloco.entry_quantidade, str(d['quantidade']))
    for especie in ESPECIES:
        bloco.vars_especies[especie].set(especie in d['especies'])
    bloco._ao_mudar_quantidade()                       # atualiza "índice no singular" e travas
    bloco.var_indice_singular.set(bool(d['indice_singular']) and bloco._indice_singular_aplicavel())

    parametro_id = tese.get('parametro')
    if parametro_id and bloco.combo_parametro is not None:
        # parâmetro indeterminado: deixa o campo VAZIO (o GERAPED pré-seleciona a 1ª opção, o que
        # seria um palpite silencioso); a validação do GERAPED então pede a escolha.
        bloco.combo_parametro.set(_rotulo_parametro(parametro_id, d['parametro_valor']))
    if tese.get('campo_texto') and bloco.combo_parametro is not None and d['campo_texto_valor']:
        _texto(bloco.combo_parametro, d['campo_texto_valor'])
        bloco._on_mudar_vigencia_ntp()                 # a vigência pode liberar o NTP (Contestação até 2017)
    if bloco._varios_estabelecimentos_aplicavel():
        bloco.var_varios_estabelecimentos.set(bool(d['varios_estabelecimentos']))

    _texto(bloco.entry_item, d['item_peticao'])

    if d['grupos_subsidiarios']:
        bloco.var_subsidiario.set(True)
        bloco._posicionar_frame_subsidiario()
        for g in d['grupos_subsidiarios']:
            bloco.adicionar_grupo_subsidiario()
            grupo = bloco.grupos_subsidiarios[-1]
            tese_sub = TESES[g['tese_subsidiaria_key']]
            grupo.combo_tese.set(tese_sub['nome'])
            grupo._atualizar_parametro()
            pid = tese_sub.get('parametro')
            if pid and grupo.combo_parametro is not None:
                grupo.combo_parametro.set(_rotulo_parametro(pid, g['parametro_valor']))   # None -> vazio
            _texto(grupo.entry_item, g['item_peticao'])
            if not g['todos_beneficios_principal']:
                for especie, numero in g['numeros_com_especie']:
                    grupo.adicionar_beneficio()
                    linha = grupo.linhas_beneficio[-1]
                    linha.var_especie.set(especie)
                    _texto(linha.entry_numero, numero)
        bloco._atualizar_travamento_subsidiarias()
        bloco.atualizar_papeis_subsidiarias()          # subsidiária x alternativa, já com os benefícios preenchidos

    # a tabela do pedido só existe se a tese tiver tabela; senão a caixa nem aparece
    from autopedidos.tabelas import tabela_do_pedido
    if tabela_do_pedido(proposto) is not None:
        bloco.var_tabela.set(True)
        bloco.check_tabela.grid(row=8, column=0, sticky='w')


def aplicar_ntp(blocos):
    """Depois que a Janela calculou se o NTP está liberado (regra do GERAPED: Contestação
    administrativa com vigência até 2017), marca "Incluir exclusão dos NTP" nos pedidos em que a
    petição indica NTP. Devolve os blocos em que a petição indica NTP mas a regra não libera."""
    nao_aplicados = []
    for bloco in blocos:
        d = bloco.proposto.dados if bloco.proposto is not None else None
        if not d or not d['excluir_ntp']:
            continue
        if bloco._ntp_aplicavel():
            bloco.var_excluir_ntp.set(True)
            bloco._atualizar_estado_ntp_singular()
            bloco.var_ntp_singular.set(bool(d['ntp_singular']) and bloco._ntp_singular_aplicavel())
        else:
            nao_aplicados.append(bloco)
    return nao_aplicados


_PREFIXOS = ('Validação: ', 'Tabela: ', 'Índices: ')


def _limpar_prefixo(texto):
    for prefixo in _PREFIXOS:
        if texto.startswith(prefixo):
            texto = texto[len(prefixo):]
            break
    return texto[:1].upper() + texto[1:]


def pontos_de_atencao(resultado, blocos, ntp_nao_aplicado=()):
    """O que o usuário precisa olhar, em frases curtas: [(titulo, [frases])]. Só entra o que exige
    decisão ou conferência - detalhes internos do programa (confiança alta, "seção repete benefícios"
    etc.) ficam de fora de propósito."""
    itens = []
    avisos = list(resultado.peticao.avisos)
    if avisos:
        itens.append(('Petição', avisos))
    for i, bloco in enumerate(blocos, start=1):
        p = bloco.proposto
        if p is None:
            continue
        frases = [_limpar_prefixo(t) for t in p.pendencias]
        if bloco in ntp_nao_aplicado:
            frases.append('A petição indica exclusão de NTP aqui, mas o GERAPED só libera o NTP com Contestação '
                          'administrativa de vigência até 2017: o NTP não foi incluído.')
        if frases:
            itens.append((f'Pedido {i} — {p.tese_nome} (item {p.dados["item_peticao"]})', frases))
    return itens


def _selo_suave(simbolo, cor, fundo, pai, tamanho=46):
    """Círculo com símbolo, desenhado em 4x e reduzido (bordas suaves; o Canvas do Tk não suaviza)."""
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    k = 4
    img = Image.new('RGBA', (tamanho * k, tamanho * k), fundo)
    d = ImageDraw.Draw(img)
    d.ellipse((2 * k, 2 * k, (tamanho - 2) * k, (tamanho - 2) * k), fill=cor, outline='#FFFFFF', width=2 * k)
    try:
        fonte = ImageFont.truetype('segoeuib.ttf', int(tamanho * 0.5 * k))
    except OSError:
        fonte = ImageFont.load_default()
    if simbolo == '✓':
        c = tamanho * k
        d.line([(c * 0.29, c * 0.52), (c * 0.43, c * 0.66), (c * 0.72, c * 0.36)], fill='#FFFFFF', width=int(c * 0.09),
               joint='curve')
    else:
        d.text((tamanho * k / 2, tamanho * k / 2), simbolo, fill='#FFFFFF', font=fonte, anchor='mm')
    foto = ImageTk.PhotoImage(img.resize((tamanho, tamanho), Image.LANCZOS))
    rotulo = tk.Label(pai, image=foto, background=fundo, borderwidth=0, autostyle=False)
    rotulo.imagem = foto                    # evita o coletor de lixo apagar a imagem
    return rotulo


def _selo_confira(pai, fundo, cor, tamanho=92, angulo=-14):
    """Carimbo redondo "CONFIRA SEMPRE", levemente inclinado, desenhado como imagem (o Tk não gira texto):
    desenha em 4x, gira e reduz, com bordas lisas."""
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    k = 4
    s = tamanho * k
    try:
        grande, pequena = ImageFont.truetype('segoeuib.ttf', 15 * k), ImageFont.truetype('segoeuib.ttf', 11 * k)
    except OSError:
        grande = pequena = ImageFont.load_default()
    img = Image.new('RGBA', (s, s), fundo)
    d = ImageDraw.Draw(img)
    d.ellipse((2 * k, 2 * k, s - 2 * k, s - 2 * k), outline=cor, width=3 * k)           # anel externo
    d.ellipse((9 * k, 9 * k, s - 9 * k, s - 9 * k), outline=cor, width=k)               # anel interno
    d.text((s / 2, s / 2 - 9 * k), 'CONFIRA', fill=cor, font=grande, anchor='mm')
    d.line([(s * 0.30, s / 2 + k), (s * 0.70, s / 2 + k)], fill=cor, width=k)
    d.text((s / 2, s / 2 + 13 * k), 'SEMPRE', fill=cor, font=pequena, anchor='mm')
    img = img.rotate(angulo, resample=Image.BICUBIC, expand=False, fillcolor=fundo)
    img = img.resize((tamanho, tamanho), Image.LANCZOS)
    foto = ImageTk.PhotoImage(img)
    rotulo = tk.Label(pai, image=foto, background=fundo, borderwidth=0, autostyle=False)
    rotulo.imagem = foto
    return rotulo


def mostrar_resumo(root, resultado, blocos, ntp_nao_aplicado=()):
    """Janela curta e direta: quantos pedidos foram preenchidos e, só se houver, o que precisa da
    sua atenção. Cartões simples sobre fundo claro; nada além disso."""
    import re
    import interface
    import tema
    atencao = pontos_de_atencao(resultado, blocos, ntp_nao_aplicado)
    det = resultado.deteccao
    n = sum(1 for b in blocos if b.proposto is not None)
    branco, fundo = tema.COR_FUNDO, '#E8ECF5'
    fonte = 'Segoe UI'
    # (fundo da ficha, texto da ficha): cheias, para destacar sobre o cabeçalho azul-marinho
    laranja, verde, azul = (tema.COR_SECUNDARIA, '#FFFFFF'), (tema.COR_SUCESSO, '#FFFFFF'), (tema.COR_INFO, '#FFFFFF')
    marinho = tema.COR_PRIMARIA
    LARGURA = 720
    texto_max = LARGURA - 190

    janela = tk.Toplevel(root)
    janela.title('Petição carregada')
    janela.configure(background=fundo)
    janela.geometry(f'{LARGURA}x560+-3000+0')           # fora da tela até medir o conteúdo
    interface._aplicar_identidade(janela)
    janela.transient(root)
    janela.resizable(True, True)

    def ficha(pai, texto, cores):
        return tk.Label(pai, text=texto, background=cores[0], foreground=cores[1], font=(fonte, 9, 'bold'),
                        padx=10, pady=3, autostyle=False)

    # ── cabeçalho: selo, título e fichas de resumo ──
    cab = interface._quadro(janela, fundo=marinho)
    cab.pack(fill='x')
    cor_selo = tema.COR_SUCESSO if not atencao else tema.COR_SECUNDARIA
    selo = _selo_suave('✓' if not atencao else '!', cor_selo, marinho, cab)
    selo.pack(side='left', padx=(30, 16), pady=18)
    textos = interface._quadro(cab, fundo=marinho)
    textos.pack(side='left', fill='x', pady=14)
    plural = 's' if n != 1 else ''
    titulo = interface._rotulo(textos, f'{n} pedido{plural} preenchido{plural}', fundo=marinho, cor='#FFFFFF',
                               fonte=(fonte, 17, 'bold'))
    titulo.pack(anchor='w')
    # carimbo no canto direito do cabeçalho (fora da coluna do texto, não empurra nada)
    _selo_confira(cab, marinho, '#E8A25E').pack(side='right', padx=(0, 30))
    interface._rotulo(textos, 'Confira os pontos abaixo antes de gerar o Word.' if atencao else
                      'Nenhuma pendência encontrada. Confira os pedidos mesmo assim.',
                      fundo=marinho, cor=tema.COR_NAV_TEXTO, fonte=(fonte, 10)).pack(anchor='w', pady=(1, 8))
    fichas = interface._quadro(textos, fundo=marinho)
    fichas.pack(anchor='w')
    if atencao:
        ficha(fichas, f'{len(atencao)} com pendência' if len(atencao) != 1 else '1 com pendência', laranja
              ).pack(side='left', padx=(0, 6))
    else:
        ficha(fichas, 'tudo em ordem', verde).pack(side='left', padx=(0, 6))
    if det.nao_classificadas:
        ficha(fichas, f'{len(det.nao_classificadas)} seção(ões) sem classificação', azul).pack(side='left')
    interface._quadro(janela, fundo=tema.COR_SECUNDARIA, height=3).pack(fill='x')

    # ── rodapé (antes do corpo, senão o corpo o empurra para fora) ──
    rodape = interface._quadro(janela, fundo=fundo)
    rodape.pack(fill='x', side='bottom')
    interface._botao(rodape, 'Entendi', janela.destroy, cor=tema.COR_SECUNDARIA, estilo='cheio', padx=30,
                     fundo=fundo).pack(side='right', padx=30, pady=(10, 20))

    # ── corpo rolável com cartões ──
    corpo = interface._quadro(janela, fundo=fundo)
    corpo.pack(fill='both', expand=True)
    tela = tk.Canvas(corpo, background=fundo, highlightthickness=0, borderwidth=0, autostyle=False)
    barra = tk.Scrollbar(corpo, orient='vertical', command=tela.yview)
    tela.configure(yscrollcommand=barra.set)
    lista = interface._quadro(tela, fundo=fundo)
    item = tela.create_window((0, 0), window=lista, anchor='nw')
    tela.bind('<Configure>', lambda e: tela.itemconfigure(item, width=e.width))
    lista.bind('<Configure>', lambda e: tela.configure(scrollregion=(0, 0, 1, lista.winfo_reqheight())))
    tela.pack(side='left', fill='both', expand=True)

    def rolar(evento):
        if lista.winfo_reqheight() > tela.winfo_height():
            tela.yview_scroll(-1 if evento.delta > 0 else 1, 'units')
    janela.bind('<MouseWheel>', rolar)

    def cartao(cor_faixa):
        borda = interface._quadro(lista, fundo='#D0D7E8')
        borda.pack(fill='x', padx=(30, 16), pady=(0, 10))
        miolo = interface._quadro(borda, fundo=branco)
        miolo.pack(fill='x', padx=1, pady=1)
        interface._quadro(miolo, fundo=cor_faixa, width=4).pack(side='left', fill='y')
        dentro = interface._quadro(miolo, fundo=branco)
        dentro.pack(side='left', fill='x', expand=True, padx=16, pady=12)
        return dentro

    def titulo_de_secao(texto):
        interface._rotulo(lista, texto.upper(), fundo=fundo, cor='#4A5A86', fonte=(fonte, 9, 'bold')
                          ).pack(anchor='w', padx=32, pady=(16, 8))

    if atencao:
        titulo_de_secao('Precisa da sua atenção')
        for titulo, frases in atencao:
            dentro = cartao(tema.COR_SECUNDARIA)
            linha = interface._quadro(dentro, fundo=branco)
            linha.pack(anchor='w', fill='x')
            m = re.match(r'^(Pedido \d+) — (.*) \(item (.*)\)$', titulo)
            if m:
                interface._rotulo(linha, m.group(1), fundo=branco, cor=tema.COR_AJUDA, fonte=(fonte, 9, 'bold')
                                  ).pack(side='left')
                interface._rotulo(linha, m.group(2), fundo=branco, cor=tema.COR_PRIMARIA, fonte=(fonte, 11, 'bold')
                                  ).pack(side='left', padx=(10, 8))
                ficha(linha, f'item {m.group(3)}', ('#EEF0F5', tema.COR_AJUDA)).pack(side='left')
            else:
                interface._rotulo(linha, titulo, fundo=branco, cor=tema.COR_PRIMARIA, fonte=(fonte, 11, 'bold')
                                  ).pack(side='left')
            for frase in frases:
                tk.Label(dentro, text=frase, background=branco, foreground=tema.COR_TEXTO, font=(fonte, 10),
                         wraplength=texto_max, justify='left', anchor='w', autostyle=False
                         ).pack(anchor='w', pady=(6, 0))

    if det.nao_classificadas:
        titulo_de_secao('Seções que o programa não soube classificar')
        dentro = cartao(tema.COR_INFO)
        tk.Label(dentro, text='Se alguma delas tem pedido, adicione à mão:', background=branco,
                 foreground=tema.COR_AJUDA, font=(fonte, 10), anchor='w', autostyle=False).pack(anchor='w')
        for numero, titulo in det.nao_classificadas:
            tk.Label(dentro, text=f'{numero or "-"}  {titulo}', background=branco, foreground=tema.COR_TEXTO,
                     font=(fonte, 10), wraplength=texto_max, justify='left', anchor='w', autostyle=False
                     ).pack(anchor='w', pady=(4, 0))
    if det.possiveis_nao_detectadas:
        nomes = ', '.join(sorted({TESES[chave]['nome'] for chave, _, _ in det.possiveis_nao_detectadas}))
        titulo_de_secao('Também aparecem no texto')
        dentro = cartao('#8C98BD')
        tk.Label(dentro, text=f'{nomes}.', background=branco, foreground=tema.COR_TEXTO, font=(fonte, 10, 'bold'),
                 wraplength=texto_max, justify='left', anchor='w', autostyle=False).pack(anchor='w')
        tk.Label(dentro, text='Só confira se faltou algum pedido dessas teses.', background=branco,
                 foreground=tema.COR_AJUDA, font=(fonte, 10), anchor='w', autostyle=False
                 ).pack(anchor='w', pady=(2, 0))
    if atencao or det.nao_classificadas or det.possiveis_nao_detectadas:
        barra.pack(side='right', fill='y')
        interface._quadro(lista, fundo=fundo, height=4).pack()

    # altura sob medida (entre 300 e 640); posição igual à do manual e das notas
    janela.update_idletasks()
    altura = cab.winfo_reqheight() + rodape.winfo_reqheight() + lista.winfo_reqheight() + 8
    altura = max(300, min(altura, 640))
    interface._centralizar_janela(janela, root, LARGURA, altura, interface.DESLOCAMENTO_JANELAS)
    return janela
