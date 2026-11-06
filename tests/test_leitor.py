import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

import sinteticas
from autopedidos.leitor import ler_peticao


@pytest.mark.parametrize('modo', ['auto', 'estilo'])
def test_numeracao_automatica_reconstruida(tmp_path, modo):
    f = tmp_path / 'p.docx'
    sinteticas.gerar_basica(f, numeracao=modo)
    p = ler_peticao(f)
    numeros = {s.titulo[:12]: s.numero for s in p.secoes if s.nivel}
    assert numeros['OBJETO DA AÇ'] == '1'
    assert numeros['ACIDENTES DE'] == '3'
    assert numeros['PRESCRIÇÃO Q'] == '4'
    assert numeros['PEDIDOS'] == '5'
    subs = [s.numero for s in p.secoes if s.nivel == 2]
    assert subs == ['3.1', '3.2']      # numeração só existe no XML, não no texto
    assert all(s.origem_numero == 'auto' for s in p.secoes if s.nivel)
    assert not any(s.titulo.startswith(('1', '3.')) for s in p.secoes)


def test_runs_quebrados_sao_concatenados(tmp_path):
    f = tmp_path / 'p.docx'
    sinteticas.gerar_basica(f)
    p = ler_peticao(f)
    trajeto = p.secao_por_numero('3')
    assert 'acidente de trajeto' in trajeto.texto


def test_tabela_de_beneficios_por_secao(tmp_path):
    f = tmp_path / 'p.docx'
    sinteticas.gerar_basica(f)
    p = ler_peticao(f)
    t = p.secao_por_numero('3.1').tabelas[0]
    assert t.cabecalho[0] == 'Item' and t.cabecalho[-1] == 'Benefício'
    assert t.linhas[1][5:] == ['B91', '999000111']


def test_tabela_mesclada_continuada_e_aninhada(tmp_path):
    f = tmp_path / 'p.docx'
    sinteticas.gerar_tabela_mesclada_continuada(f)
    p = ler_peticao(f)
    tabelas = p.secao_por_numero('1').tabelas
    assert len(tabelas) == 1                      # t2 foi unida a t1 (cabeçalho repetido)
    t = tabelas[0]
    assert t.continuada
    assert t.n_linhas == 4                        # cabeçalho + 3 benefícios; cabeçalhos repetidos removidos
    assert [l[0] for l in t.linhas[1:]] == ['1', '2', '3']
    assert t.linhas[1][1] == t.linhas[2][1] == '2023'   # vMerge herda o valor de cima
    assert 'aninhada' in t.linhas[3][6]           # tabela aninhada incluída como texto da célula


def test_extras_caixa_revisoes_cabecalho_notas(tmp_path):
    f = tmp_path / 'p.docx'
    sinteticas.gerar_com_extras(f)
    p = ler_peticao(f)
    sec = p.secao_por_numero('1')
    textos = [b.texto for b in sec.paragrafos]
    assert any('inserção' in t and 'EXCLUIDO' not in t for t in textos)   # lido como exibido
    caixas = [b for b in sec.paragrafos if b.caixa_de_texto]
    assert [c.texto for c in caixas] == ['Texto na caixa']                # Fallback não duplica
    assert any('revisões pendentes' in a for a in p.avisos)
    assert 'Cabeçalho fictício' in p.cabecalhos_rodapes and 'Rodapé fictício' in p.cabecalhos_rodapes
    assert p.notas_rodape == ['Nota de rodapé fictícia']


def test_tabela_continuada_sem_repetir_o_cabecalho(tmp_path):
    import docx
    f = tmp_path / 'p.docx'
    d = docx.Document()
    sinteticas._numbering(d)
    sinteticas._titulo(d, 'Tese', 1)
    sinteticas._tabela(d, [sinteticas.CAB,
                           ['1', '2023', '11.111.111/0001-11', 'A', '111', 'B91', '6111111111'],
                           ['2', '2023', '11.111.111/0001-11', 'B', '222', 'B91', '6222222222']])
    sinteticas._tabela(d, [['3', '2023', '11.111.111/0001-11', 'C', '333', 'B91', '6333333333'],
                           ['4', '2023', '11.111.111/0001-11', 'D', '444', 'B91', '6444444444']])
    d.save(f)
    tabelas = ler_peticao(f).secao_por_numero('1').tabelas
    assert len(tabelas) == 1
    assert [l[0] for l in tabelas[0].linhas[1:]] == ['1', '2', '3', '4']
