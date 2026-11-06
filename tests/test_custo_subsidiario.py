"""Custo cessado como tese SUBSIDIÁRIA: o pedido é de CORREÇÃO do índice de custo, nunca de "exclusão do
benefício" (modelo do escritório; antes saía "requer-se a exclusão do benefício B94, esta correspondente
ao dia imediatamente anterior ao óbito")."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gerador_pedido

BASE = {'quantidade': 1, 'especies': ['B94'], 'tese_key': 'acidente_sem_relacao_empresa', 'item_peticao': '5',
        'parametro_valor': None, 'campo_texto_valor': None, 'indice_singular': False, 'excluir_ntp': False,
        'ntp_singular': False, 'varios_estabelecimentos': False}


def grupo(tese, item, numeros=(), parametro=None, todos=False, qtd=None, especies=None):
    return {'tese_subsidiaria_key': tese, 'item_peticao': item, 'numeros_com_especie': [] if todos else list(numeros),
            'parametro_valor': parametro, 'todos_beneficios_principal': todos,
            'especies_principal': especies if todos else None, 'quantidade_principal': qtd if todos else None}


def texto(grupos, **extra):
    d = {**BASE, 'grupos_subsidiarios': grupos, **extra}
    return gerador_pedido.gerar_documento([d]).paragraphs[0].text


CONDICAO_OBITO = ('limitando a apuração do valor ao período compreendido entre a DIB e a DCB, esta correspondente '
                  'ao dia imediatamente anterior ao óbito, devendo ser considerado o novo valor para o campo '
                  '"TOTAL PAGO" do sistema FAP')


def test_custo_subsidiario_obito_pede_correcao_e_nao_exclusao():
    t = texto([grupo('custo_cessado', '9', todos=True, qtd=1, especies=['B94'], parametro='obito')])
    assert t.endswith('Subsidiariamente, não sendo esse o entendimento de V. Exa., requer-se a correção no cálculo '
                      'do índice de custo do benefício B94, ' + CONDICAO_OBITO + ' – item 9 da petição inicial.')
    sub = t[t.index('Subsidiariamente'):]
    assert 'exclusão' not in sub


def test_custo_subsidiario_com_benefico_numerado_e_aposentadoria():
    t = texto([grupo('custo_cessado', '9', numeros=[('B94', '6358354675')], parametro='aposentadoria')])
    assert ('requer-se a correção no cálculo do índice de custo do benefício B94 nº 6358354675, limitando a '
            'apuração do valor ao período compreendido entre a DIB e a DCB, sendo este o dia imediatamente '
            'anterior à concessão da aposentadoria, devendo ser considerado o novo valor para o campo '
            '"TOTAL PAGO" do sistema FAP – item 9 da petição inicial.') in t


def test_custo_subsidiario_no_plural():
    nums = [('B91', '1'), ('B94', '2')]
    t = texto([grupo('custo_cessado', '9', numeros=nums, parametro='obito')], quantidade=2, especies=['B91', 'B94'])
    assert 'correção no cálculo do índice de custo dos benefícios B91 nº 1 e B94 nº 2, limitando' in t


def test_exclusao_seguida_de_custo_troca_a_acao_no_meio_da_frase():
    t = texto([grupo('acidente_trajeto', '4', numeros=[('B94', '1')]),
               grupo('custo_cessado', '9', numeros=[('B94', '2')], parametro='obito')])
    assert 'requer-se a exclusão do benefício B94 nº 1, decorrente de acidente de trajeto – item 4 da petição ' \
           'inicial –, e a correção no cálculo do índice de custo do benefício B94 nº 2, limitando' in t


def test_custo_como_alternativa_aos_mesmos_beneficios():
    b = ('B94', '1')
    t = texto([grupo('acidente_trajeto', '4', numeros=[b]), grupo('custo_cessado', '9', numeros=[b], parametro='obito')])
    assert ('– item 4 da petição inicial – ou, alternativamente, a correção no cálculo do índice de custo, '
            'limitando a apuração do valor') in t
    # e o contrário: custo primeiro, exclusão como alternativa
    t2 = texto([grupo('custo_cessado', '9', numeros=[b], parametro='obito'), grupo('acidente_trajeto', '4', numeros=[b])])
    assert t2[t2.index('Subsidiariamente'):].startswith('Subsidiariamente, não sendo esse o entendimento de V. Exa., '
                                                        'requer-se a correção no cálculo do índice de custo do benefício')
    assert ' – ou, alternativamente, a exclusão, decorrente de acidente de trajeto – item 4' in t2


def test_principal_de_custo_cessado_nao_mudou():
    d = {**BASE, 'tese_key': 'custo_cessado', 'parametro_valor': 'obito', 'grupos_subsidiarios': []}
    t = gerador_pedido.gerar_documento([d]).paragraphs[0].text
    assert t.startswith('Determinar a correção do índice de custo de 1 (um) benefício de auxílio-acidente')
