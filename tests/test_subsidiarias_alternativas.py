"""Mais de uma tese subsidiária sobre os MESMOS benefícios: encadeadas com "– ou, alternativamente," e
sem repetir o benefício; qualquer quantidade (2, 3...). Benefícios diferentes mantêm o encadeamento
aditivo de antes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gerador_pedido

BASE = {'quantidade': 3, 'especies': ['B91'], 'tese_key': 'acidente_trajeto', 'item_peticao': '4.1',
        'parametro_valor': None, 'campo_texto_valor': None, 'indice_singular': False, 'excluir_ntp': False,
        'ntp_singular': False, 'varios_estabelecimentos': False}


def grupo(tese, item, numeros, parametro=None):
    return {'tese_subsidiaria_key': tese, 'item_peticao': item, 'numeros_com_especie': list(numeros),
            'parametro_valor': parametro, 'todos_beneficios_principal': False, 'especies_principal': None,
            'quantidade_principal': None}


def texto(grupos, **extra):
    d = {**BASE, 'grupos_subsidiarios': grupos, **extra}
    return gerador_pedido.gerar_documento([d]).paragraphs[0].text


B = ('B91', '6358354675')


def test_exemplo_do_escritorio_com_duas_subsidiarias_sobre_o_mesmo_beneficio():
    t = texto([grupo('restabelecimento_beneficio_anterior', '6', [B]),
               grupo('acidente_outro_estabelecimento', '7', [B])])
    assert t == (
        'Determinar a exclusão de 3 (três) benefícios de auxílio por incapacidade temporária por acidente de '
        'trabalho, espécie B91, abaixo arrolados, da base de cálculo dos índices do FAP, decorrentes de acidentes '
        'de trajeto – item 4.1 da petição inicial. Subsidiariamente, não sendo esse o entendimento de V. Exa., '
        'requer-se a exclusão do benefício B91 nº 6358354675, por se tratar de restabelecimento de benefício '
        'anterior – item 6 da petição inicial – ou, alternativamente, por ser decorrente de acidente ocorrido em '
        'outro estabelecimento – item 7 da petição inicial.')


def test_tres_ou_mais_teses_encadeiam_com_ou_alternativamente_cada_uma():
    t = texto([grupo('restabelecimento_beneficio_anterior', '6', [B]),
               grupo('acidente_outro_estabelecimento', '7', [B]),
               grupo('acidente_anterior_2007', '8', [B])])
    assert t.count(' – ou, alternativamente, ') == 2
    assert t.count('benefício B91 nº 6358354675') == 1               # o benefício só é citado na 1ª
    assert 'por ser decorrente de acidente anterior a abril de 2007 – item 8 da petição inicial' in t
    assert ' –, e ' not in t


def test_plural_usa_por_serem_decorrentes_e_por_terem_sido_concedidos():
    nums = [('B91', '1'), ('B91', '2')]
    t = texto([grupo('restabelecimento_beneficio_anterior', '6', nums),
               grupo('acidente_outro_estabelecimento', '7', nums)])
    assert 'dos benefícios B91 nº 1 e B91 nº 2, por se tratar de restabelecimentos de benefícios anteriores' in t
    assert ' – ou, alternativamente, por serem decorrentes de acidentes ocorridos em outros estabelecimentos' in t
    t2 = texto([grupo('restabelecimento_beneficio_anterior', '6', [B]),
                grupo('concomitancia_outro_beneficio', '7', [B], parametro='aposentadoria')])
    assert ' – ou, alternativamente, por ter sido concedido enquanto o segurado já usufruía de outro benefício de ' \
           'aposentadoria – item 7' in t2


def test_motivos_que_ja_tem_conectivo_nao_ganham_verbo():
    t = texto([grupo('acidente_outro_estabelecimento', '7', [B]),
               grupo('ausencia_nexo_causal_concausalidade', '9', [B])])
    assert ' – ou, alternativamente, tendo em vista que o nexo causal e de concausalidade foram afastados' in t


def test_benefícios_diferentes_mantem_o_encadeamento_antigo():
    t = texto([grupo('restabelecimento_beneficio_anterior', '6', [B]),
               grupo('acidente_outro_estabelecimento', '7', [('B91', '999')])])
    assert 'alternativamente' not in t
    assert ' –, e do benefício B91 nº 999, decorrente de acidente ocorrido em outro estabelecimento' in t


def test_uma_so_subsidiaria_nao_muda():
    t = texto([grupo('restabelecimento_beneficio_anterior', '6', [B])])
    assert 'alternativamente' not in t
    assert t.endswith('por se tratar de restabelecimento de benefício anterior – item 6 da petição inicial.')


def test_subsidiarias_que_herdam_todos_os_beneficios_tambem_encadeiam():
    g1 = {**grupo('restabelecimento_beneficio_anterior', '6', []), 'todos_beneficios_principal': True,
          'especies_principal': ['B91'], 'quantidade_principal': 3}
    g2 = {**grupo('acidente_outro_estabelecimento', '7', []), 'todos_beneficios_principal': True,
          'especies_principal': ['B91'], 'quantidade_principal': 3}
    t = texto([g1, g2])
    assert 'dos benefícios B91, por se tratar de restabelecimentos' in t
    assert ' – ou, alternativamente, por serem decorrentes de acidentes ocorridos em outros estabelecimentos – item 7' in t


def test_alternativa_a_tese_que_nao_e_a_imediatamente_anterior_cita_o_beneficio():
    """Benefício A tem 2 teses, separadas pela tese do benefício B: a 2ª tese de A é alternativa (benefício já
    citado) e como não é a imediatamente anterior, o benefício volta a ser citado."""
    a, b = ('B91', '111'), ('B91', '222')
    t = texto([grupo('restabelecimento_beneficio_anterior', '6', [a]),
               grupo('acidente_anterior_2007', '8', [b]),
               grupo('acidente_outro_estabelecimento', '7', [a])])
    assert t.count('Subsidiariamente') == 1                          # só uma vez, no começo
    assert ('– item 6 da petição inicial –, do benefício B91 nº 222, decorrente de acidente anterior a abril de '
            '2007 – item 8 da petição inicial') in t                 # benefício B é novo: subsidiária (aditiva)
    assert ('– item 8 da petição inicial – ou, alternativamente, do benefício B91 nº 111, decorrente de acidente '
            'ocorrido em outro estabelecimento – item 7 da petição inicial.') in t


def test_benefício_novo_continua_subsidiario_e_so_o_repetido_vira_alternativa():
    a, b = ('B91', '111'), ('B91', '222')
    t = texto([grupo('restabelecimento_beneficio_anterior', '6', [a]),
               grupo('acidente_outro_estabelecimento', '7', [b])])
    assert 'alternativamente' not in t
    # superconjunto (traz benefício novo junto com um já citado): é subsidiária nova, não alternativa
    t2 = texto([grupo('restabelecimento_beneficio_anterior', '6', [a]),
                grupo('acidente_outro_estabelecimento', '7', [a, b])])
    assert 'alternativamente' not in t2


def test_depois_de_uma_tese_para_todos_os_beneficios_qualquer_outra_e_alternativa():
    g1 = {**grupo('restabelecimento_beneficio_anterior', '6', []), 'todos_beneficios_principal': True,
          'especies_principal': ['B91'], 'quantidade_principal': 3}
    t = texto([g1, grupo('acidente_outro_estabelecimento', '7', [('B91', '111')])])
    assert ' – ou, alternativamente, do benefício B91 nº 111, decorrente de acidente ocorrido em outro estabelecimento' in t
