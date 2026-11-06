import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import docx
import pytest

import sinteticas
from autopedidos.detector import DetectorRegras, ALTA, BAIXA
from autopedidos.leitor import ler_peticao


def _peticao(tmp_path, secoes):
    """secoes: lista de (nivel, titulo, [paragrafos]) -> .docx sintético com numeração automática."""
    f = tmp_path / 'p.docx'
    d = docx.Document()
    sinteticas._numbering(d)
    for nivel, titulo, corpo in secoes:
        sinteticas._titulo(d, titulo, nivel)
        for t in corpo:
            d.add_paragraph(t)
    d.save(f)
    return ler_peticao(f)


@pytest.mark.parametrize('titulo, esperado', [
    ('ACIDENTES DE TRAJETO', 'acidente_trajeto'),
    ('Auxílio-acidente por acidente de trabalho (B94) – decorrente de acidente de trajeto', 'acidente_trajeto'),
    ('PRESCRIÇÃO QUINQUENAL', 'prescricao_quinquenal'),
    ('Contestação administrativa, efeito suspensivo e prazo prescricional', 'contestacao_administrativa'),
    ('Acidentes ocorridos antes de abril de 2007', 'acidente_anterior_2007'),
    ('Atribuição indevida de nexo técnico previdenciário – reconhecimento judicial da ausência de nexo causal '
     'e de concausalidade', 'ausencia_nexo_causal_concausalidade'),
    ('Benefícios acidentários concedidos em razão de acidentes não relacionados à empresa Autora',
     'acidente_sem_relacao_empresa'),
    ('Concessão concomitante de auxílio por incapacidade temporária (B91) com aposentadoria',
     'concomitancia_outro_beneficio'),
    ('Benefícios acidentários com a mesma data de início (DIB) e cessação do benefício (DCB) – DIB = DCB',
     'dib_igual_dcb'),
    ('Benefícios dos mesmos segurados com menos de 60 dias entre a data da cessação do primeiro benefício (DCB) '
     'e a data do início do segundo', 'restabelecimento_beneficio_anterior'),
    ('Taxa média de rotatividade – ilegalidade da aplicação do “bloqueio de rotatividade”', 'rotatividade'),
    ('Erro no número médio de vínculos', 'erro_vinculos'),
    ('Nexos técnicos contabilizados de forma indevida', 'cat_nao_vinculada'),
    ('Nexo técnico previdenciário duplicado', 'ntp_duplicado'),
    ('BENEFÍCIO DE AUXÍLIO-ACIDENTE POR ACIDENTE DE TRABALHO COMPUTADO DUAS VEZES PELO INSS',
     'computado_duas_vezes'),
    ('Benefícios acidentários concedidos a segurados sem vínculo com os estabelecimentos na data dos acidentes',
     'acidente_outro_estabelecimento'),
])
def test_titulos_formulaicos_confianca_alta(tmp_path, titulo, esperado):
    p = _peticao(tmp_path, [(1, titulo, ['Texto fictício.'])])
    r = DetectorRegras().detectar(p)
    assert [d.tese_key for d in r.deteccoes] == [esperado]
    assert r.deteccoes[0].confianca == ALTA
    assert r.deteccoes[0].evidencia            # sempre traz evidência curta
    assert len(r.deteccoes[0].evidencia) <= 80


def test_secao_estrutural_nao_e_tese_nem_pendencia(tmp_path):
    p = _peticao(tmp_path, [(1, 'OBJETO DA AÇÃO', ['x']), (1, 'PEDIDOS', ['y'])])
    r = DetectorRegras().detectar(p)
    assert r.deteccoes == [] and r.nao_classificadas == []
    assert len(r.estruturais) == 2


def test_titulo_desconhecido_vai_para_nao_classificadas_sem_inventar(tmp_path):
    p = _peticao(tmp_path, [(1, 'Tema totalmente diferente', ['Nada relevante aqui.'])])
    r = DetectorRegras().detectar(p)
    assert r.deteccoes == []
    assert r.nao_classificadas == [('1', 'Tema totalmente diferente')]


def test_deteccao_pelo_corpo_nunca_e_alta(tmp_path):
    p = _peticao(tmp_path, [(1, 'Fundamentos', ['O benefício decorreu de acidente de trajeto.'])])
    r = DetectorRegras().detectar(p)
    assert r.deteccoes[0].tese_key == 'acidente_trajeto'
    assert r.deteccoes[0].confianca == BAIXA and r.deteccoes[0].origem == 'corpo'


def test_subsecao_sem_pista_herda_do_pai_com_confianca_media(tmp_path):
    p = _peticao(tmp_path, [
        (1, 'ACIDENTES DE TRAJETO', ['x']),
        (2, 'Espécie B91', ['Tabela abaixo.']),
    ])
    r = DetectorRegras().detectar(p)
    herdada = [d for d in r.deteccoes if d.origem == 'herdada']
    assert herdada and herdada[0].secao_numero == '1.1' and herdada[0].tese_key == 'acidente_trajeto'
    assert herdada[0].confianca == 'media'


def test_possiveis_nao_detectadas_lista_tese_citada_no_texto(tmp_path):
    p = _peticao(tmp_path, [
        (1, 'Fatos relevantes', ['O benefício foi concedido com abril de 2007 como marco e rotatividade alta.']),
    ])
    r = DetectorRegras().detectar(p)
    chaves = {k for k, *_ in r.possiveis_nao_detectadas}
    # a seção casou por corpo (uma tese), as demais ficam como "possíveis" apenas se não foram detectadas
    detectadas = {d.tese_key for d in r.deteccoes}
    assert chaves.isdisjoint(detectadas)


def test_peticao_basica_sintetica_de_ponta_a_ponta(tmp_path):
    f = tmp_path / 'b.docx'
    sinteticas.gerar_basica(f)
    r = DetectorRegras().detectar(ler_peticao(f))
    por_num = {d.secao_numero: d.tese_key for d in r.deteccoes}
    assert por_num['3'] == por_num['3.1'] == por_num['3.2'] == 'acidente_trajeto'
    assert por_num['4'] == 'prescricao_quinquenal'
    assert r.nao_classificadas == []
