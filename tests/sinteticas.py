"""Gera petições .docx SINTÉTICAS (nomes/números inventados) para os testes.

Cobre os pontos que quebram leitores de Word: numeração automática (direta e herdada do
estilo), runs quebrados, tabela de benefícios mesclada e continuada, caixa de texto,
revisões pendentes e nota de rodapé.
"""
import copy
import zipfile
from pathlib import Path

import docx
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

NS = nsdecls('w')


def _numbering(doc):
    """Lista multinível: nível 0 '%1.' e nível 1 '%1.%2' (numId 90) + lista de letras (numId 91)."""
    el = doc.part.numbering_part.element
    abstract = parse_xml(
        f'<w:abstractNum {NS} w:abstractNumId="90"><w:multiLevelType w:val="multilevel"/>'
        '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl>'
        '<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1.%2"/></w:lvl>'
        '<w:lvl w:ilvl="2"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="%3)"/></w:lvl>'
        '</w:abstractNum>')
    letras = parse_xml(
        f'<w:abstractNum {NS} w:abstractNumId="91"><w:multiLevelType w:val="singleLevel"/>'
        '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="%1."/></w:lvl>'
        '</w:abstractNum>')
    primeiro_num = el.find(qn('w:num'))
    for a in (abstract, letras):
        if primeiro_num is not None:
            primeiro_num.addprevious(a)
        else:
            el.append(a)
    el.append(parse_xml(f'<w:num {NS} w:numId="90"><w:abstractNumId w:val="90"/></w:num>'))
    el.append(parse_xml(f'<w:num {NS} w:numId="91"><w:abstractNumId w:val="91"/></w:num>'))


def _set_numpr(par_ou_style_el, num_id, ilvl):
    ppr = par_ou_style_el.get_or_add_pPr()
    for antigo in ppr.findall(qn('w:numPr')):
        ppr.remove(antigo)
    ppr.append(parse_xml(f'<w:numPr {NS}><w:ilvl w:val="{ilvl}"/><w:numId w:val="{num_id}"/></w:numPr>'))


def _titulo(doc, texto, nivel, auto=True, via_estilo=False):
    p = doc.add_paragraph(texto, style=f'Heading {nivel}')
    if auto and not via_estilo:
        _set_numpr(p._p, 90, nivel - 1)
    return p


def _quebrado(doc, partes, style=None):
    """Parágrafo com o texto partido em vários runs (inclusive no meio de palavras)."""
    p = doc.add_paragraph(style=style)
    for parte in partes:
        p.add_run(parte)
    return p


def _tabela(doc, linhas):
    t = doc.add_table(rows=len(linhas), cols=len(linhas[0]))
    for i, l in enumerate(linhas):
        for j, v in enumerate(l):
            t.cell(i, j).text = v
    return t


CAB = ['Item', 'Vigência do FAP', 'CNPJ', 'Empregado', 'NIT', 'Tipo', 'Benefício']


def gerar_basica(caminho, numeracao='auto'):
    """Petição fictícia: 1 Objeto, 2 Fatos, 3 Trajeto (3.1, 3.2), 4 Prescrição, 5 Pedidos."""
    doc = docx.Document()
    auto = numeracao in ('auto', 'estilo')
    if auto:
        _numbering(doc)
    if numeracao == 'estilo':
        for n in (1, 2):
            _set_numpr(doc.styles[f'Heading {n}'].element, 90, n - 1)

    def T(txt, n):
        return _titulo(doc, txt if auto else f'{"3" if False else ""}{txt}', n, auto=auto, via_estilo=(numeracao == 'estilo'))

    doc.add_paragraph('EXCELENTÍSSIMO SENHOR DOUTOR JUIZ FEDERAL (texto fictício)')
    T('OBJETO DA AÇÃO', 1)
    doc.add_paragraph('A empresa Alfa Fictícia Ltda., CNPJ 00.000.000/0001-00, ajuíza a presente ação.')
    T('SÍNTESE FÁTICA', 1)
    doc.add_paragraph('Texto de fatos inventado.')
    T('ACIDENTES DE TRAJETO', 1)
    _quebrado(doc, ['Os benefícios foram conce', 'didos em razão de aci', 'dente de trajeto.'])
    T('Auxílio por incapacidade temporária por acidente de trabalho (B91) – decorrente de acidente de trajeto', 2)
    _tabela(doc, [CAB, ['1', '2023', '00.000.000/0001-00', 'João Inventado', '100.000.000-0', 'B91', '999000111']])
    T('Auxílio-acidente por acidente de trabalho (B94) – decorrente de acidente de trajeto', 2)
    _tabela(doc, [CAB, ['2', '2023', '00.000.000/0001-00', 'Maria Inventada', '100.000.000-1', 'B94', '999000222']])
    T('PRESCRIÇÃO QUINQUENAL', 1)
    doc.add_paragraph('Não há prescrição para as vigências de 2023.')
    T('PEDIDOS', 1)
    doc.add_paragraph('No mérito, sejam julgados procedentes os pedidos para:', style='Normal')
    p = doc.add_paragraph('Determinar a exclusão de 1 (um) benefício – item 3.1 da petição inicial.')
    _set_numpr(p._p, 91, 0)
    if not auto:
        # numeração digitada no texto (fallback)
        for par in doc.paragraphs:
            if par.style.name.startswith('Heading'):
                pass
    doc.save(caminho)


def gerar_tabela_mesclada_continuada(caminho):
    """Tabela de benefícios com célula mesclada (gridSpan e vMerge) continuada em outra tabela
    (cabeçalho repetido) e uma tabela aninhada."""
    doc = docx.Document()
    _numbering(doc)
    _titulo(doc, 'ACIDENTES DE TRAJETO', 1)
    t1 = _tabela(doc, [CAB,
                       ['1', '2023', '00.000.000/0001-00', 'Pessoa A', '100.000.000-0', 'B91', '999000001'],
                       ['2', '2023', '00.000.000/0001-00', 'Pessoa B', '100.000.000-1', 'B91', '999000002']])
    # mescla vertical da coluna "Vigência" nas linhas 1-2 e horizontal CNPJ+Empregado na linha 2
    t1.cell(1, 1).merge(t1.cell(2, 1)).text = '2023'   # merge do python-docx concatena os textos
    # continuação: nova tabela com o cabeçalho repetido
    t2 = _tabela(doc, [CAB,
                       ['3', '2024', '00.000.000/0001-00', 'Pessoa C', '100.000.000-2', 'B94', '999000003']])
    # linha de cabeçalho repetida dentro da mesma tabela (quebra de página)
    t1.add_row()
    for j, v in enumerate(CAB):
        t1.rows[-1].cells[j].text = v
    # tabela aninhada na última célula de t2
    celula = t2.cell(1, 6)
    celula.add_table(rows=1, cols=2).cell(0, 0).text = 'aninhada'
    _titulo(doc, 'PEDIDOS', 1)
    doc.save(caminho)


def gerar_com_extras(caminho):
    """Caixa de texto, revisão pendente (ins/del), cabeçalho/rodapé e nota de rodapé."""
    doc = docx.Document()
    _numbering(doc)
    doc.sections[0].header.paragraphs[0].text = 'Cabeçalho fictício'
    doc.sections[0].footer.paragraphs[0].text = 'Rodapé fictício'
    _titulo(doc, 'OBJETO DA AÇÃO', 1)
    p = doc.add_paragraph('Texto com ')
    p._p.append(parse_xml(f'<w:ins {NS} w:id="1" w:author="x" w:date="2026-01-01T00:00:00Z">'
                          '<w:r><w:t>inserção</w:t></w:r></w:ins>'))
    p._p.append(parse_xml(f'<w:del {NS} w:id="2" w:author="x" w:date="2026-01-01T00:00:00Z">'
                          '<w:r><w:delText> EXCLUIDO</w:delText></w:r></w:del>'))
    # caixa de texto (mc:AlternateContent com Choice e Fallback duplicados)
    caixa = parse_xml(
        f'<w:r {NS} xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
        '<mc:AlternateContent><mc:Choice Requires="wps"><w:pict><w:txbxContent>'
        '<w:p><w:r><w:t>Texto na caixa</w:t></w:r></w:p></w:txbxContent></w:pict></mc:Choice>'
        '<mc:Fallback><w:pict><w:txbxContent><w:p><w:r><w:t>Texto na caixa</w:t></w:r></w:p>'
        '</w:txbxContent></w:pict></mc:Fallback></mc:AlternateContent></w:r>')
    p._p.append(caixa)
    doc.save(caminho)
    # nota de rodapé: injeta footnotes.xml no zip
    tmp = Path(str(caminho) + '.tmp')
    with zipfile.ZipFile(caminho) as zin, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            zout.writestr(item, zin.read(item.filename))
        zout.writestr('word/footnotes.xml',
                      f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:footnotes {NS}>'
                      '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
                      '<w:footnote w:id="1"><w:p><w:r><w:t>Nota de rodapé fictícia</w:t></w:r></w:p></w:footnote>'
                      '</w:footnotes>')
    tmp.replace(caminho)
