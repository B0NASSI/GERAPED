"""'Estabelecimento' no plural quando há mais de um (antes ficava sempre no singular):
 - OUTRO ESTABELECIMENTO com 2+ benefícios: "ocorridos em outros estabelecimentos";
 - correção de vínculos/massa salarial com 2+ CNPJs: "nas competências dos estabelecimentos"."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gerador_pedido
import test_pedidos as tp
from autopedidos.detector import DetectorRegras
from autopedidos.pedidos import montar_pedidos

BASE = {'quantidade': 1, 'especies': ['B91'], 'item_peticao': '4', 'parametro_valor': None,
        'campo_texto_valor': None, 'indice_singular': False, 'excluir_ntp': False, 'ntp_singular': False,
        'varios_estabelecimentos': False, 'grupos_subsidiarios': []}


def _texto(dados):
    return gerador_pedido.gerar_documento([dados]).paragraphs[0].text


def test_outro_estabelecimento_singular_e_plural():
    um = _texto({**BASE, 'tese_key': 'acidente_outro_estabelecimento'})
    dois = _texto({**BASE, 'tese_key': 'acidente_outro_estabelecimento', 'quantidade': 2, 'especies': ['B91', 'B94']})
    assert 'ocorrido em outro estabelecimento' in um
    assert 'ocorridos em outros estabelecimentos' in dois and 'em outro estabelecimento' not in dois


def test_correcao_texto_do_estabelecimento_singular_e_plural():
    for tese in ('erro_vinculos', 'erro_massa_salarial'):
        base = {**BASE, 'tese_key': tese, 'especies': [], 'campo_texto_valor': '2023'}
        assert 'nas competências do estabelecimento e vigências' in _texto(base)
        plural = _texto({**base, 'varios_estabelecimentos': True})
        assert 'nas competências dos estabelecimentos e vigências' in plural


def test_app_marca_varios_estabelecimentos_na_correcao_quando_ha_2_cnpjs(tmp_path):
    outro = '11.111.111/0001-11'
    p = tp._peticao(tmp_path, [
        ('h', 1, 'Erro no número médio de vínculos'),
        ('tab', ['Item', 'Vigência do FAP', 'CNPJ', 'Competências'],
         [['1', '2025', tp.CNPJ, 'Todas as competências do ano de 2023'],
          ['2', '2025', outro, 'Todas as competências do ano de 2023']]),
    ])
    x = montar_pedidos(p, DetectorRegras().detectar(p)).pedidos[0]
    assert x.dados['varios_estabelecimentos'] is True
    assert 'nas competências dos estabelecimentos' in _texto(x.dados)


def test_app_mantem_singular_na_correcao_com_1_cnpj(tmp_path):
    p = tp._peticao(tmp_path, [
        ('h', 1, 'Erro no número médio de vínculos'),
        ('tab', ['Item', 'Vigência do FAP', 'CNPJ', 'Competências'],
         [['1', '2025', tp.CNPJ, 'Todas as competências do ano de 2023']]),
    ])
    x = montar_pedidos(p, DetectorRegras().detectar(p)).pedidos[0]
    assert x.dados['varios_estabelecimentos'] is False
    assert 'nas competências do estabelecimento' in _texto(x.dados)
