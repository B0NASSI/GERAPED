"""Gera o Word dos pedidos: texto pelo `gerar_documento` do GERAPED (vendor, intocado) e, logo
depois de cada pedido, a tabela dele (layout único e padronizado: ver tabelas.py)."""
from __future__ import annotations

import copy

from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from .gerapedvendor import gerador_pedido
from .tabelas import ACIMA, ALTURA_CABECALHO, ALTURA_LINHA, TabelaPedido, tabela_do_pedido

# Padrão medido nas tabelas de pedido das 52 petições reais: Avenir Next LT Pro Light 7 pt,
# espaçamento de 5 pt antes/depois, tudo centralizado, linhas com altura mínima fixa e a coluna
# Item pintada (mesmo cinza-azulado do cabeçalho) e em negrito. Larguras: tabelas.LARGURAS.
FONTE = 'Avenir Next LT Pro Light'
TAMANHO = Pt(7)
ESPACO = Pt(5)
FUNDO_CABECALHO = 'D5DCE4'
FUNDO_ITEM = 'D5DCE4'


def _borda(tbl):
    pr = tbl._tbl.tblPr
    b = OxmlElement('w:tblBorders')
    for lado in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        e = OxmlElement(f'w:{lado}')
        e.set(qn('w:val'), 'single')
        e.set(qn('w:sz'), '4')
        e.set(qn('w:space'), '0')
        e.set(qn('w:color'), 'auto')
        b.append(e)
    pr.append(b)


def _largura_celula(cell, twips):
    tcPr = cell._tc.get_or_add_tcPr()
    for w in tcPr.findall(qn('w:tcW')):
        tcPr.remove(w)
    w = OxmlElement('w:tcW')
    w.set(qn('w:w'), str(twips))
    w.set(qn('w:type'), 'dxa')
    tcPr.insert(0, w)


def _escrever(cell, texto, negrito=False):
    par = cell.paragraphs[0]
    for r in list(par.runs):
        r._r.getparent().remove(r._r)
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.paragraph_format.space_before = ESPACO
    par.paragraph_format.space_after = ESPACO
    par.paragraph_format.first_line_indent = Pt(0)
    run = par.add_run(texto)
    run.bold = negrito
    run.font.size = TAMANHO
    run.font.name = FONTE
    rPr = run._r.get_or_add_rPr()
    rf = rPr.find(qn('w:rFonts'))
    if rf is not None:
        rf.set(qn('w:hAnsi'), FONTE)
        rf.set(qn('w:cs'), FONTE)
    # como nas petições: negrito também para texto complexo (bCs), tamanho szCs e a mesma
    # formatação na marca de parágrafo
    if negrito:
        rPr.insert(list(rPr).index(rPr.find(qn('w:b'))) + 1, OxmlElement('w:bCs'))
    sz = rPr.find(qn('w:sz'))
    szcs = OxmlElement('w:szCs')
    szcs.set(qn('w:val'), sz.get(qn('w:val')))
    sz.addnext(szcs)
    pRPr = OxmlElement('w:rPr')
    for el in rPr:
        pRPr.append(copy.deepcopy(el))
    par._p.get_or_add_pPr().append(pRPr)
    tcPr = cell._tc.get_or_add_tcPr()
    va = OxmlElement('w:vAlign')
    va.set(qn('w:val'), 'center')
    tcPr.append(va)


def _altura(row, twips):
    trPr = row._tr.get_or_add_trPr()
    h = OxmlElement('w:trHeight')
    h.set(qn('w:val'), str(twips))
    h.set(qn('w:hRule'), 'atLeast')
    trPr.append(h)


def _fundo(cell, cor):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), cor)
    tcPr.append(shd)


def criar_tabela(doc, t: TabelaPedido):
    """Cria a tabela no fim do corpo (o chamador a move para o lugar certo)."""
    n_col = t.n_colunas
    tbl = doc.add_table(rows=1 + len(t.linhas), cols=n_col)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    _borda(tbl)
    larg = t.larguras if len(t.larguras) == n_col else [1200] * n_col
    grade = tbl._tbl.tblGrid
    for gc, w in zip(grade.findall(qn('w:gridCol')), larg):
        gc.set(qn('w:w'), str(w))
    tw = tbl._tbl.tblPr.find(qn('w:tblW'))
    if tw is None:
        tw = OxmlElement('w:tblW')
        tbl._tbl.tblPr.append(tw)
    tw.set(qn('w:w'), str(sum(larg)))
    tw.set(qn('w:type'), 'dxa')
    lay = OxmlElement('w:tblLayout')
    lay.set(qn('w:type'), 'fixed')
    tbl._tbl.tblPr.append(lay)
    for row in tbl.rows:
        for c, w in zip(row.cells, larg):
            _largura_celula(c, w)
    # altura mínima das linhas (cabeçalho e corpo), como nas petições
    for i, row in enumerate(tbl.rows):
        _altura(row, ALTURA_CABECALHO if i == 0 else ALTURA_LINHA)
    # O cabeçalho NÃO repete na página seguinte (decisão do usuário): sem "Repetir linhas de cabeçalho"
    # (w:tblHeader), a continuação da tabela começa direto nas linhas de dados.
    col = 0
    for texto, span in t.cabecalho:
        cel = tbl.cell(0, col)
        if span > 1:
            cel = cel.merge(tbl.cell(0, col + span - 1))
        _fundo(cel, FUNDO_CABECALHO)
        _escrever(cel, texto, negrito=True)
        col += span
    for i, linha in enumerate(t.linhas, 1):
        inicio = None                        # início de uma sequência mesclada (valor seguido de None)
        for j, v in enumerate(linha):
            cel = tbl.cell(i, j)
            if v is None:                    # mesclada com a da esquerda (ex.: 1 vigência sob 2 colunas)
                tbl.cell(i, inicio).merge(cel)
                continue
            if v == ACIMA:                   # mesclada com a de cima (item dividido por vigência)
                tbl.cell(i - 1, j).merge(cel)
                continue
            inicio = j
            if j == 0:                       # coluna Item: colorida e em negrito
                _fundo(cel, FUNDO_ITEM)
            _escrever(cel, v, negrito=(j == 0))
    return tbl


def gerar_documento_com_tabelas_lista(dados_lista, tabelas):
    """`dados_lista`: pedidos no formato do GERAPED; `tabelas`: uma TabelaPedido (ou None) por
    pedido, na mesma ordem. Cada pedido vira 'parágrafo + linha em branco + tabela + linha em
    branco'; pedido sem tabela sai exatamente como o `gerar_documento` do GERAPED o gera."""
    doc = gerador_pedido.gerar_documento(dados_lista)
    paragrafos = list(doc.paragraphs)
    assert len(paragrafos) == 2 * len(dados_lista), 'estrutura do documento do GERAPED mudou'
    for i, t in enumerate(tabelas):
        if t is None:
            continue
        tbl = criar_tabela(doc, t)
        # uma linha em branco (cópia do espaçador do próprio modelo) entre o pedido e a tabela
        espaco = copy.deepcopy(paragrafos[2 * i + 1]._p)
        paragrafos[2 * i]._p.addnext(espaco)
        espaco.addnext(tbl._tbl)
    return doc


def gerar_documento_com_tabelas(pedidos):
    """`pedidos`: lista de PedidoProposto (protótipo AutoPedidos). A tabela só entra se
    `incluir_tabela` estiver ligado e houver dados."""
    return gerar_documento_com_tabelas_lista(
        [p.dados for p in pedidos],
        [tabela_do_pedido(p) if getattr(p, 'incluir_tabela', True) else None for p in pedidos],
    )
