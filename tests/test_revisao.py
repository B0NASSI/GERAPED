import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import docx
import pytest

import test_pedidos as tp
from autopedidos import revisao
from autopedidos.leitor import ler_peticao


@pytest.fixture
def docx_sintetico(tmp_path):
    """Escreve a mesma petição sintética de test_pedidos em um .docx e devolve o caminho."""
    f = tmp_path / 'sintetica.docx'
    d = docx.Document()
    tp.sinteticas._numbering(d)
    blocos = [
        ('h', 1, 'OBJETO DA AÇÃO'), ('p', 'Texto fictício.'),
        ('h', 1, 'ACIDENTES DE TRAJETO'),
        ('h', 2, 'Auxílio por incapacidade temporária por acidente de trabalho (B91) – decorrente de acidente de trajeto'),
        ('t', [tp.linha(1, '2023', 'Pessoa A', '100000000-1', 'B91', '9990000001'),
               tp.linha(2, '2023', 'Pessoa B', '100000000-2', 'B91', '9990000002')]),
        ('h', 1, 'Atribuição indevida de nexo técnico previdenciário – reconhecimento judicial da ausência de '
                 'nexo causal e de concausalidade'),
        ('t', [tp.linha(1, '2023', 'Pessoa A', '100000000-1', 'B91', '9990000001')]),
        ('h', 1, 'PEDIDOS'),
    ]
    for b in blocos:
        if b[0] == 'h':
            tp.sinteticas._titulo(d, b[2], b[1])
        elif b[0] == 'p':
            d.add_paragraph(b[1])
        else:
            tp.sinteticas._tabela(d, [tp.CAB] + b[1])
    d.save(f)
    return f


def test_pipeline_completo_gera_docx_valido(docx_sintetico, tmp_path):
    peticao, resultado, proposta = revisao.processar(docx_sintetico)
    assert [p.secao_numero for p in proposta.pedidos] == ['2.1', '3']
    saida = tmp_path / 'saida' / 'pedidos.docx'
    revisao.gerar_arquivo(proposta.pedidos, saida)
    texto = '\n'.join(p.text for p in docx.Document(str(saida)).paragraphs)
    assert 'Determinar a exclusão de 2 (dois) benefícios' in texto and 'item 2.1 da petição inicial' in texto


def test_edicao_reflete_na_previa_e_revalida(docx_sintetico):
    _, _, proposta = revisao.processar(docx_sintetico)
    p = proposta.pedidos[0]
    antes = revisao.previa(p)
    revisao.aplicar_edicao(p, quantidade=5, especies=['B94', 'B91'])
    revisao.revalidar(proposta.pedidos)
    assert p.valido
    assert p.dados['especies'] == ['B91', 'B94'] and 'espécies B91 e B94' in revisao.previa(p)
    assert revisao.previa(p) != antes
    # a subsidiária "todos os benefícios" acompanha o principal
    sub = proposta.pedidos[0].dados['grupos_subsidiarios']
    assert all(g['quantidade_principal'] in (None, 5) for g in sub)


def test_edicao_invalida_vira_pendencia_e_bloqueia_geracao(docx_sintetico, tmp_path):
    _, _, proposta = revisao.processar(docx_sintetico)
    p = proposta.pedidos[0]
    revisao.aplicar_edicao(p, quantidade=1, especies=['B91', 'B94'])      # mais espécies que benefícios
    revisao.revalidar(proposta.pedidos)
    assert not p.valido and any('no máximo' in t for t in p.pendencias)
    with pytest.raises(revisao.ErroValidacao):
        revisao.gerar_arquivo(proposta.pedidos, tmp_path / 'x.docx')
    assert not (tmp_path / 'x.docx').exists()


def test_item_duplicado_e_barrado(docx_sintetico):
    _, _, proposta = revisao.processar(docx_sintetico)
    revisao.aplicar_edicao(proposta.pedidos[1], item_peticao=proposta.pedidos[0].dados['item_peticao'])
    revisao.revalidar(proposta.pedidos)
    assert not any(p.valido for p in proposta.pedidos)


def test_trocar_para_tese_sem_quantidade_ignora_especies(docx_sintetico):
    _, _, proposta = revisao.processar(docx_sintetico)
    p = proposta.pedidos[0]
    revisao.aplicar_edicao(p, tese_key='prescricao_quinquenal', campo_texto_valor='2023')
    revisao.revalidar(proposta.pedidos)
    assert p.dados['quantidade'] == 1 and p.dados['especies'] == [] and p.tese_nome == 'PRESCRIÇÃO QUINQUENAL'
    assert p.valido is False       # prescrição não admite subsidiária: o usuário precisa remover o grupo
    p.dados['grupos_subsidiarios'].clear()
    revisao.revalidar(proposta.pedidos)
    assert p.valido


def test_parse_beneficios_texto():
    assert revisao.parse_beneficios_texto('B91 9990000001\n94 nº 9990000002\n') == [
        ('B91', '9990000001'), ('B94', '9990000002')]
    with pytest.raises(ValueError):
        revisao.parse_beneficios_texto('abc')


def test_word_gerado_traz_tabela_do_pedido_logo_apos_o_texto(docx_sintetico, tmp_path):
    _, _, proposta = revisao.processar(docx_sintetico)
    saida = tmp_path / 'p.docx'
    revisao.gerar_arquivo(proposta.pedidos, saida)
    d = docx.Document(str(saida))
    assert len(d.tables) == 2                                  # uma por pedido
    corpo = list(d.element.body)
    tag = lambda e: e.tag.rsplit('}', 1)[1]
    i = next(k for k, e in enumerate(corpo) if tag(e) == 'tbl')
    # pedido -> linha em branco -> tabela
    assert tag(corpo[i - 2]) == 'p' and 'Determinar a exclusão' in ''.join(corpo[i - 2].itertext())
    assert tag(corpo[i - 1]) == 'p' and ''.join(corpo[i - 1].itertext()).strip() == ''
    t = d.tables[0]
    assert [c.text for c in t.rows[0].cells][:1] == ['Item']
    cab = [c.text for c in t.rows[0].cells]
    assert cab[-3:] == ['CNPJ', 'Tipo', 'Benefício'][-3:] or 'Benefício' in cab
    assert [r.cells[0].text for r in t.rows[1:]] == ['1', '2']          # Item renumerado 1..n
    assert [r.cells[-1].text for r in t.rows[1:]] == ['9990000001', '9990000002']
    assert 'Empregado' not in cab and 'NIT' not in cab                    # colunas da tese que o pedido não traz


def test_desligar_incluir_tabela_remove_a_tabela(docx_sintetico, tmp_path):
    _, _, proposta = revisao.processar(docx_sintetico)
    for p in proposta.pedidos:
        p.incluir_tabela = False
    saida = tmp_path / 'p.docx'
    revisao.gerar_arquivo(proposta.pedidos, saida)
    assert len(docx.Document(str(saida)).tables) == 0


def test_tabela_com_quantidade_diferente_vira_pendencia_nao_bloqueante(docx_sintetico):
    _, _, proposta = revisao.processar(docx_sintetico)
    p = proposta.pedidos[0]
    revisao.aplicar_edicao(p, quantidade=3)
    revisao.revalidar(proposta.pedidos)
    assert p.valido and any(t.startswith('Tabela:') for t in p.pendencias)


def test_tabelas_padronizadas_mesma_largura_fonte_alinhamento_e_item(tmp_path):
    from docx.oxml.ns import qn
    f = tmp_path / 'p.docx'
    d = docx.Document()
    tp.sinteticas._numbering(d)
    cab2 = ['Item', 'Vigências do FAP', 'Vigências do FAP', 'CNPJ', 'Empregado', 'NIT', 'Tipo', 'Benefício']
    tp.sinteticas._titulo(d, 'ACIDENTES DE TRAJETO', 1)
    tp.sinteticas._tabela(d, [cab2,
                              ['1', '2023', '2024', tp.CNPJ, 'A', '1', 'B91', '9990000001'],
                              ['2', '2023', '2024', tp.CNPJ, 'B', '2', 'B91', '9990000002']])
    tp.sinteticas._titulo(d, 'PRESCRIÇÃO QUINQUENAL', 1)
    tp.sinteticas._tabela(d, [['Item', 'Vigência do FAP', 'CNPJ', 'Competências'],
                              ['1', '2022', tp.CNPJ, 'De 01/2022 a 12/2022']])
    tp.sinteticas._titulo(d, 'Benefícios dos mesmos segurados com menos de 60 dias entre a data da cessação do '
                             'primeiro benefício (DCB) e a data do início do segundo', 1)
    tp.sinteticas._tabela(d, [tp.CAB, tp.linha(1, '2023', 'A', '100000000-1', 'B91', '9990000009')])
    d.save(f)
    _, _, proposta = revisao.processar(f)
    saida = tmp_path / 'o.docx'
    revisao.gerar_arquivo(proposta.pedidos, saida)
    doc = docx.Document(str(saida))
    assert len(doc.tables) == 3
    from autopedidos.tabelas import ALTURA_CABECALHO, ALTURA_LINHA, LARGURAS
    fontes, tamanhos, alinh, espacos = set(), set(), set(), set()
    larg_por_papel = {}
    for t in doc.tables:
        grade = [int(g.get(qn('w:w'))) for g in t._tbl.tblGrid.findall(qn('w:gridCol'))]
        assert t._tbl.tblPr.find(qn('w:tblW')).get(qn('w:w')) == str(sum(grade))
        for cel, w in zip(t.rows[0].cells, grade):          # mesma largura para o mesmo tipo de coluna
            larg_por_papel.setdefault(cel.text, set()).add(w)
        assert [r.cells[0].text for r in t.rows[1:]] == [str(i) for i in range(1, len(t.rows))]  # Item 1..n, sem vazios
        for i, row in enumerate(t.rows):
            h = row._tr.trPr.find(qn('w:trHeight'))              # altura mínima como nas petições
            assert (h.get(qn('w:val')), h.get(qn('w:hRule'))) == (
                str(ALTURA_CABECALHO if i == 0 else ALTURA_LINHA), 'atLeast')
            for j, c in enumerate(row.cells):
                par = c.paragraphs[0]
                alinh.add(par.alignment)
                espacos.add((par.paragraph_format.space_before, par.paragraph_format.space_after))
                for r in par.runs:
                    fontes.add(r.font.name)
                    tamanhos.add(r.font.size)
                    if j == 0:                                    # coluna Item: negrito e colorida
                        assert r.bold is True
                fill = c._tc.tcPr.find(qn('w:shd'))
                assert (fill.get(qn('w:fill')) == 'D5DCE4') if (j == 0 or i == 0) else fill is None
    assert all(len(v) == 1 for v in larg_por_papel.values()), larg_por_papel
    assert larg_por_papel['Item'] == {LARGURAS['item']} and larg_por_papel['CNPJ'] == {LARGURAS['cnpj']}
    assert len(fontes) == 1 and len(tamanhos) == 1 and len(alinh) == 1 and len(espacos) == 1
    assert [t.rows[0].cells[0].text for t in doc.tables] == ['Item'] * 3
    assert sum(int(g.get(qn('w:w'))) for g in doc.tables[0]._tbl.tblGrid.findall(qn('w:gridCol'))) == 4905
    cab = [c.text for c in doc.tables[0].rows[0].cells]
    # o cabeçalho mesclado ocupa as 2 colunas de vigência; cada ano na sua coluna
    assert cab == ['Item', 'Vigências do FAP', 'Vigências do FAP', 'CNPJ', 'Tipo', 'Benefício']
    assert [c.text for c in doc.tables[0].rows[1].cells][1:3] == ['2023', '2024']
    assert [c.text for c in doc.tables[1].rows[0].cells][:2] == ['Item', 'Vigência do FAP']   # 1 vigência: singular


def test_fonte_das_tabelas_e_avenir_next_lt_pro_light(docx_sintetico, tmp_path):
    _, _, proposta = revisao.processar(docx_sintetico)
    saida = tmp_path / 'f.docx'
    revisao.gerar_arquivo(proposta.pedidos, saida)
    d = docx.Document(str(saida))
    nomes = {r.font.name for t in d.tables for row in t.rows for c in row.cells for r in c.paragraphs[0].runs}
    assert nomes == {'Avenir Next LT Pro Light'}


def test_vigencia_unica_sob_duas_colunas_fica_mesclada(tmp_path):
    from docx.oxml.ns import qn
    f = tmp_path / 'p.docx'
    d = docx.Document()
    tp.sinteticas._numbering(d)
    tp.sinteticas._titulo(d, 'ACIDENTES DE TRAJETO', 1)
    cab2 = ['Item', 'Vigências do FAP', 'Vigências do FAP', 'CNPJ', 'Empregado', 'NIT', 'Tipo', 'Benefício']
    tp.sinteticas._tabela(d, [cab2,
                              ['1', '2021', '', tp.CNPJ, 'A', '1', 'B91', '9990000001'],        # só 2021
                              ['2', '2021', '2022', tp.CNPJ, 'B', '2', 'B91', '9990000002'],
                              ['3', '2021', '2022', tp.CNPJ, 'C', '3', 'B91', '9990000003']])
    d.save(f)
    _, _, proposta = revisao.processar(f)
    saida = tmp_path / 'o.docx'
    revisao.gerar_arquivo(proposta.pedidos, saida)
    t = docx.Document(str(saida)).tables[0]
    linhas = t._tbl.findall(qn('w:tr'))
    def spans(tr):
        return [int((tc.tcPr.find(qn('w:gridSpan')).get(qn('w:val')) if tc.tcPr.find(qn('w:gridSpan')) is not None else 1))
                for tc in tr.findall(qn('w:tc'))]
    assert spans(linhas[0]) == [1, 2, 1, 1, 1]                 # cabeçalho mesclado sobre as 2 colunas
    assert spans(linhas[1]) == [1, 2, 1, 1, 1]                 # benefício com 1 vigência: 2021 ocupa as 2 colunas
    assert spans(linhas[2]) == [1, 1, 1, 1, 1, 1]              # benefício com 2 vigências: uma em cada coluna
    assert [c.text for c in t.rows[1].cells][1] == '2021'
    assert [c.text for c in t.rows[2].cells][1:3] == ['2021', '2022']


def test_cabecalho_da_tabela_nao_repete_na_pagina_seguinte(docx_sintetico, tmp_path):
    """Sem "Repetir linhas de cabeçalho" (w:tblHeader): a tabela que continua na página seguinte começa
    direto nas linhas de dados."""
    from docx.oxml.ns import qn
    _, _, proposta = revisao.processar(docx_sintetico)
    saida = tmp_path / 'p.docx'
    revisao.gerar_arquivo(proposta.pedidos, saida)
    d = docx.Document(str(saida))
    assert d.tables
    assert not list(d.element.body.iter(qn('w:tblHeader')))
