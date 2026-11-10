import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import docx
import pytest

import sinteticas
from autopedidos.beneficios import ler_beneficios
from autopedidos.detector import DetectorRegras
from autopedidos.gerapedvendor import gerador_pedido, validacao
from autopedidos.leitor import ler_peticao
from autopedidos.pedidos import montar_pedidos

CAB = ['Item', 'Vigência do FAP', 'CNPJ', 'Empregado', 'NIT', 'Tipo', 'Benefício', 'DIB', 'DCB']
CNPJ = '00.000.000/0001-00'


def linha(item, vig, nome, nit, tipo, num, dib='01/02/2023', dcb='01/03/2023'):
    return [str(item), vig, CNPJ, nome, nit, tipo, num, dib, dcb]


def _peticao(tmp_path, blocos):
    """blocos: ('h', nivel, titulo) | ('t', linhas_sem_cabecalho) | ('p', texto) | ('tab', cab, linhas)."""
    f = tmp_path / 'p.docx'
    d = docx.Document()
    sinteticas._numbering(d)
    for b in blocos:
        if b[0] == 'h':
            sinteticas._titulo(d, b[2], b[1])
        elif b[0] == 'p':
            d.add_paragraph(b[1])
        elif b[0] == 't':
            sinteticas._tabela(d, [CAB] + b[1])
        elif b[0] == 'tab':
            sinteticas._tabela(d, [b[1]] + b[2])
    d.save(f)
    return ler_peticao(f)


@pytest.fixture
def proposta(tmp_path):
    p = _peticao(tmp_path, [
        ('h', 1, 'OBJETO DA AÇÃO'), ('p', 'Texto fictício.'),
        ('h', 1, 'ACIDENTES DE TRAJETO'),
        ('h', 2, 'Auxílio por incapacidade temporária por acidente de trabalho (B91) – decorrente de acidente de trajeto'),
        ('t', [linha(1, '2023', 'Pessoa A', '100000000-1', 'B91', '9990000001'),
               linha(2, '2023', 'Pessoa B', '100000000-2', 'B91', '9990000002')]),
        ('h', 2, 'Auxílio-acidente por acidente de trabalho (B94) – decorrente de acidente de trajeto'),
        ('t', [linha(3, '2023', 'Pessoa C', '100000000-3', 'B94', '9990000003')]),
        ('h', 1, 'Atribuição indevida de nexo técnico previdenciário – reconhecimento judicial da ausência de '
                 'nexo causal e de concausalidade'),
        ('t', [linha(1, '2023', 'Pessoa A', '100000000-1', 'B91', '9990000001')]),
        ('h', 1, 'PRESCRIÇÃO QUINQUENAL'),
        ('tab', ['Item', 'Vigência do FAP', 'CNPJ'], [['1', '2022', CNPJ], ['2', '2023', CNPJ]]),
        ('h', 1, 'Concessão concomitante de auxílio por incapacidade temporária (B91) com aposentadoria'),
        ('t', [linha(1, '2023', 'Pessoa D', '100000000-4', 'B42', '9990000004', '01/01/2020', '01/01/2030'),
               linha(1, '2023', 'Pessoa D', '100000000-4', 'B91', '9990000005', '01/06/2023', '01/07/2023')]),
        ('h', 1, 'PEDIDOS'),
    ])
    return montar_pedidos(p, DetectorRegras().detectar(p))


def test_tabela_de_beneficios_le_especie_e_numero(tmp_path):
    p = _peticao(tmp_path, [('h', 1, 'ACIDENTES DE TRAJETO'),
                            ('t', [linha(1, '2023', 'Pessoa A', '100000000-1', 'B91', '9990000001')])])
    b = ler_beneficios(p.secao_por_numero('1').tabelas[0])
    assert [(x.especie, x.numero, x.vigencias) for x in b] == [('B91', '9990000001', {'2023'})]


def test_pedidos_principais_um_por_secao_com_tabela(proposta):
    assert [x.secao_numero for x in proposta.pedidos] == ['2.1', '2.2', '3', '4', '5']  # '2' é só o pai


def test_trajeto_quantidade_especies_item_e_indice(proposta):
    ped = {x.secao_numero: x.dados for x in proposta.pedidos}
    d = ped['2.1']
    assert (d['tese_key'], d['quantidade'], d['especies']) == ('acidente_trajeto', 2, ['B91'])
    assert d['indice_singular'] is True       # 2 benefícios, mesma vigência e mesmo CNPJ: "do índice do FAP"
    assert ped['2.2']['quantidade'] == 1 and ped['2.2']['especies'] == ['B94']


def test_secao_que_repete_beneficio_vira_subsidiaria_do_pedido_anterior(proposta):
    ped = {x.secao_numero: x.dados for x in proposta.pedidos}
    grupos = ped['2.1']['grupos_subsidiarios']
    assert len(grupos) == 1
    g = grupos[0]
    assert g['tese_subsidiaria_key'] == 'ausencia_nexo_causal_concausalidade' and g['item_peticao'] == '3'
    assert g['numeros_com_especie'] == [('B91', '9990000001')]   # só um dos 2 benefícios
    assert g['todos_beneficios_principal'] is False
    assert ped['2.2']['grupos_subsidiarios'] == []


def test_prescricao_usa_vigencias_da_tabela(proposta):
    d = {x.secao_numero: x.dados for x in proposta.pedidos}['4']
    assert d['tese_key'] == 'prescricao_quinquenal'
    assert d['campo_texto_valor'] == '2022 e 2023' and d['quantidade'] == 1 and d['especies'] == []


def test_concomitante_exclui_o_posterior_e_infere_o_outro_beneficio(proposta):
    x = {x.secao_numero: x for x in proposta.pedidos}['5']
    d = x.dados
    assert (d['tese_key'], d['quantidade'], d['especies']) == ('concomitancia_outro_beneficio', 1, ['B91'])
    assert d['parametro_valor'] == 'aposentadoria'
    assert [b.numero for b in x.beneficios] == ['9990000005']     # B42 (anterior) não é excluído


def test_todos_os_pedidos_passam_em_validacao_e_geram_documento(proposta):
    assert all(x.valido for x in proposta.pedidos), [x.pendencias for x in proposta.pedidos]
    validacao.validar_itens_duplicados([x.dados['item_peticao'] for x in proposta.pedidos])
    doc = gerador_pedido.gerar_documento([x.dados for x in proposta.pedidos])
    texto = '\n'.join(p.text for p in doc.paragraphs)
    assert 'item 2.1 da petição inicial' in texto
    assert 'Subsidiariamente' in texto and 'B91 nº 9990000001' in texto
    assert 'prescrição quinquenal' in texto


def test_sem_tabela_vira_pendencia_nao_palpite(tmp_path):
    p = _peticao(tmp_path, [('h', 1, 'ACIDENTES DE TRAJETO'), ('p', 'Sem tabela aqui.')])
    prop = montar_pedidos(p, DetectorRegras().detectar(p))
    x = prop.pedidos[0]
    assert x.valido is False
    assert any('Tabela de benefícios não encontrada' in t for t in x.pendencias)


def test_confianca_baixa_vira_pendencia(tmp_path):
    p = _peticao(tmp_path, [('h', 1, 'Fundamentos'), ('p', 'Houve acidente de trajeto.'),
                            ('t', [linha(1, '2023', 'Pessoa A', '100000000-1', 'B91', '9990000001')])])
    prop = montar_pedidos(p, DetectorRegras().detectar(p))
    assert any('confiança baixa' in t for t in prop.pedidos[0].pendencias)



def test_varias_vigencias_ou_estabelecimentos_usam_indices_no_plural(tmp_path):
    outro = '11.111.111/0001-11'
    casos = [
        [linha(1, '2023', 'Pessoa A', '100000000-1', 'B91', '9990000001'),
         linha(2, '2024', 'Pessoa B', '100000000-2', 'B91', '9990000002')],                 # 2 vigências
        [linha(1, '2023', 'Pessoa A', '100000000-1', 'B91', '9990000001'),
         ['2', '2023', outro, 'Pessoa B', '100000000-2', 'B91', '9990000002', '01/02/2023', '01/03/2023']],  # 2 CNPJs
    ]
    for linhas in casos:
        p = _peticao(tmp_path, [('h', 1, 'ACIDENTES DE TRAJETO'), ('t', linhas)])
        x = montar_pedidos(p, DetectorRegras().detectar(p)).pedidos[0]
        assert x.dados["quantidade"] == 2 and x.dados["indice_singular"] is False
        texto = '\n'.join(par.text for par in gerador_pedido.gerar_documento([x.dados]).paragraphs)
        assert 'dos índices do FAP' in texto


def test_um_beneficio_uma_vigencia_um_estabelecimento_usa_indice_singular(tmp_path):
    p = _peticao(tmp_path, [('h', 1, 'ACIDENTES DE TRAJETO'),
                            ('t', [linha(1, '2023', 'Pessoa A', '100000000-1', 'B91', '9990000001')])])
    x = montar_pedidos(p, DetectorRegras().detectar(p)).pedidos[0]
    assert x.dados['quantidade'] == 1
    texto = '\n'.join(par.text for par in gerador_pedido.gerar_documento([x.dados]).paragraphs)
    assert 'abaixo arrolado, da base de cálculo do índice do FAP' in texto
    assert 'dos índices' not in texto


def test_dois_beneficios_mesma_vigencia_e_estabelecimento_usam_indice_singular(tmp_path):
    p = _peticao(tmp_path, [('h', 1, 'ACIDENTES DE TRAJETO'),
                            ('t', [linha(1, '2023', 'Pessoa A', '100000000-1', 'B91', '9990000001'),
                                   linha(2, '2023', 'Pessoa B', '100000000-2', 'B91', '9990000002')])])
    x = montar_pedidos(p, DetectorRegras().detectar(p)).pedidos[0]
    assert x.dados['quantidade'] == 2 and x.dados['indice_singular'] is True
    texto = '\n'.join(par.text for par in gerador_pedido.gerar_documento([x.dados]).paragraphs)
    assert 'abaixo arrolados, da base de cálculo do índice do FAP' in texto


def test_tabela_do_pedido_beneficios_vigencias_duplas_e_prescricao(tmp_path):
    from autopedidos.tabelas import tabela_do_pedido
    cab2 = ['Item', 'Vigências do FAP', 'Vigências do FAP', 'CNPJ', 'Empregado', 'NIT', 'Tipo', 'Benefício']
    p = _peticao(tmp_path, [
        ('h', 1, 'ACIDENTES DE TRAJETO'),
        ('tab', cab2, [['1', '2023', '2024', CNPJ, 'Pessoa A', '100000000-1', 'B91', '9990000001']]),
        ('h', 1, 'PRESCRIÇÃO QUINQUENAL'),
        ('tab', ['Item', 'Vigência do FAP', 'CNPJ', 'Competências'],
         [['1', '2022', CNPJ, 'De 01/2022 a 12/2022'], ['2', '2023', CNPJ, 'De 01/2023 a 12/2023']]),
    ])
    prop = montar_pedidos(p, DetectorRegras().detectar(p))
    t1 = tabela_do_pedido(prop.pedidos[0])
    # duas vigências: cada uma na sua coluna, sob o cabeçalho mesclado "Vigências do FAP"
    assert [c for c in t1.cabecalho] == [('Item', 1), ('Vigências do FAP', 2), ('CNPJ', 1), ('Tipo', 1), ('Benefício', 1)]
    assert t1.linhas == [['1', '2023', '2024', CNPJ, 'B91', '9990000001']]
    assert t1.larguras == [510, 567, 567, 1560, 567, 1134]          # as 2 sub-colunas somam 1 coluna (1134)
    assert prop.pedidos[0].dados['indice_singular'] is False and prop.pedidos[0].dados['quantidade'] == 1
    t2 = tabela_do_pedido(prop.pedidos[1])
    # tabela só de vigência com 2 vigências (uma por linha): cabeçalho no plural, como nas petições reais
    assert [t for t, _ in t2.cabecalho] == ['Item', 'Vigências do FAP', 'CNPJ', 'Competências']
    assert t2.linhas[1] == ['2', '2023', CNPJ, 'De 01/2023 a 12/2023']


def test_tabela_so_de_vigencia_usa_singular_com_uma_vigencia_e_plural_com_varias(tmp_path):
    from autopedidos.tabelas import tabela_do_pedido

    def cabecalho(linhas):
        p = _peticao(tmp_path, [('h', 1, 'CONTESTAÇÃO ADMINISTRATIVA, EFEITO SUSPENSIVO E PRAZO PRESCRICIONAL'),
                                ('tab', ['Item', 'Vigência do FAP', 'CNPJ'], linhas)])
        prop = montar_pedidos(p, DetectorRegras().detectar(p))
        return [c for c, _ in tabela_do_pedido(prop.pedidos[0]).cabecalho][1]
    assert cabecalho([['1', '2017', CNPJ]]) == 'Vigência do FAP'
    assert cabecalho([['1', '2017', CNPJ], ['2', '2019', CNPJ], ['3', '2020', CNPJ], ['4', '2021', CNPJ]]) == 'Vigências do FAP'


def test_celula_com_dois_anos_vira_duas_colunas_de_vigencia(tmp_path):
    from autopedidos.tabelas import tabela_do_pedido
    p = _peticao(tmp_path, [
        ('h', 1, 'ACIDENTES DE TRAJETO'),
        ('tab', ['Item', 'Vigência do FAP', 'CNPJ', 'Tipo', 'Benefício'],
         [['1', '2021 e 2022', CNPJ, 'B91', '9990000001'], ['2', '2021/2022', CNPJ, 'B91', '9990000002']]),
        ('h', 1, 'PRESCRIÇÃO QUINQUENAL'),
        ('tab', ['Item', 'Vigência do FAP', 'CNPJ'], [['1', '2021 e 2022', CNPJ], ['2', '2023', CNPJ]]),
    ])
    prop = montar_pedidos(p, DetectorRegras().detectar(p))
    t = tabela_do_pedido(prop.pedidos[0])
    assert t.cabecalho[:2] == [('Item', 1), ('Vigências do FAP', 2)]
    assert t.linhas == [['1', '2021', '2022', CNPJ, 'B91', '9990000001'],
                        ['2', '2021', '2022', CNPJ, 'B91', '9990000002']]
    # a regra "dos índices" também enxerga as duas vigências
    assert prop.pedidos[0].dados['indice_singular'] is False
    t2 = tabela_do_pedido(prop.pedidos[1])
    assert t2.cabecalho[:2] == [('Item', 1), ('Vigências do FAP', 2)]
    assert t2.linhas == [['1', '2021', '2022', CNPJ], ['2', '2023', None, CNPJ]]


def _peticao_ntp(tmp_path, ntp_por_beneficio):
    cab = ['Item', 'Vigência do FAP', 'CNPJ', 'Empregado', 'NIT', 'Tipo', 'NTP', 'Benefício']
    linhas = [[str(k), '2016', CNPJ, f'Pessoa {k}', f'10000000{k}-0', 'B91', ntp, f'99900000{k:02d}']
              for k, ntp in enumerate(ntp_por_beneficio, 1)]
    return _peticao(tmp_path, [('h', 1, 'ACIDENTES DE TRAJETO'), ('tab', cab, linhas)])


def test_ntp_um_beneficio_com_ntp_exclui_ntp_no_singular(tmp_path):
    from autopedidos.tabelas import tabela_do_pedido
    p = _peticao_ntp(tmp_path, ['-', 'ntp', '-'])
    x = montar_pedidos(p, DetectorRegras().detectar(p)).pedidos[0]
    assert x.dados['excluir_ntp'] is True and x.dados['ntp_singular'] is True
    assert not any('Vigência até 2017' in t for t in x.pendencias)          # a tabela já decidiu
    texto = '\n'.join(par.text for par in gerador_pedido.gerar_documento([x.dados]).paragraphs)
    assert 'bem como a exclusão do Nexo Técnico Previdenciário (NTP)' in texto
    t = tabela_do_pedido(x)
    assert [c for c, _ in t.cabecalho] == ['Item', 'Vigência do FAP', 'CNPJ', 'Tipo', 'NTP', 'Benefício']  # Tipo | NTP | Benefício
    assert [l[4] for l in t.linhas] == ['-', 'NTP', '-']                    # só o 2º benefício tem NTP
    assert [l[5] for l in t.linhas] == ['9990000001', '9990000002', '9990000003']


def test_ntp_varios_beneficios_com_ntp_exclui_no_plural(tmp_path):
    p = _peticao_ntp(tmp_path, ['ntp', 'ntp', '-'])
    x = montar_pedidos(p, DetectorRegras().detectar(p)).pedidos[0]
    assert x.dados['excluir_ntp'] is True and x.dados['ntp_singular'] is False
    texto = '\n'.join(par.text for par in gerador_pedido.gerar_documento([x.dados]).paragraphs)
    assert 'bem como a exclusão dos Nexos Técnicos Previdenciários (NTP)' in texto


def test_ntp_sem_nenhum_benefício_com_ntp_nao_exclui(tmp_path):
    p = _peticao_ntp(tmp_path, ['-', '-'])
    x = montar_pedidos(p, DetectorRegras().detectar(p)).pedidos[0]
    assert x.dados['excluir_ntp'] is False
    assert not any('Vigência até 2017' in t for t in x.pendencias)          # coluna existe e diz "sem NTP"


def test_correcao_massa_e_vinculos_usa_a_tabela_de_competencias_e_nao_a_matriz(tmp_path):
    from autopedidos.tabelas import tabela_do_pedido
    matriz = ['Item', 'CNPJ', 'Competência', 'Ano do insumo: 2023', 'Ano do insumo: 2023']
    p = _peticao(tmp_path, [
        ('h', 1, 'Erro no número médio de vínculos'),
        ('tab', matriz, [['1', CNPJ, 'Janeiro', '10', '12'], ['1', CNPJ, 'Fevereiro', '11', '13']]),
        ('tab', ['Item', 'Vigência do FAP', 'CNPJ', 'Competências para correção'],
         [['1', '2025', CNPJ, 'Todas as competências do ano de 2023'],
          ['2', '2025', '11.111.111/0001-11', 'Competências de 01/2023 a 12/2023']]),
    ])
    prop = montar_pedidos(p, DetectorRegras().detectar(p))
    t = tabela_do_pedido(prop.pedidos[0])
    assert [c for c, _ in t.cabecalho] == ['Item', 'Vigência do FAP', 'CNPJ', 'Competências']
    assert t.linhas == [['1', '2025', CNPJ, 'Todas as competências do ano de 2023'],
                        ['2', '2025', '11.111.111/0001-11', 'De 01/2023 a 12/2023']]      # "Competências de" -> "De"
    assert 'Janeiro' not in t.como_texto()


def test_60_dias_preenche_a_coluna_indices_pela_regra_das_duas_vigencias(tmp_path):
    from autopedidos.tabelas import tabela_do_pedido
    cab = ['Item', 'Vigência do FAP', 'CNPJ', 'Empregado', 'NIT', 'Tipo', 'Benefício', 'DIB', 'DCB']
    p = _peticao(tmp_path, [
        ('h', 1, 'Benefícios dos mesmos segurados com menos de 60 dias entre a data da cessação do primeiro '
                 'benefício (DCB) e a data do início do segundo'),
        ('tab', cab, [linha(1, '2023', 'A', '100000000-1', 'B91', '9990000001', '01/01/2023', '01/02/2023'),
                      linha(1, '2023', 'A', '100000000-1', 'B91', '9990000002', '10/02/2023', '01/03/2023')]),
    ])
    x = montar_pedidos(p, DetectorRegras().detectar(p)).pedidos[0]
    t = tabela_do_pedido(x)
    assert [c for c, _ in t.cabecalho][-1] == 'Índices'                  # a coluna existe...
    assert [l[-1] for l in t.linhas] == ['Frequência e gravidade']       # ...anterior e posterior em 2023: 1 vigência
    assert not any(tx.startswith('Índices') for tx in x.pendencias)      # sem aviso sobre o preenchimento


def test_subsidiaria_so_no_primeiro_topico_do_beneficio(tmp_path):
    """Um NB que está em 3 tópicos é pedido principal em todos, mas as teses subsidiária/alternativa dele
    constam só no pedido do 1º tópico em que aparece."""
    x = linha(1, '2023', 'Pessoa A', '100000000-1', 'B91', '9990000001')
    y = linha(2, '2023', 'Pessoa B', '100000000-2', 'B91', '9990000002')
    p = _peticao(tmp_path, [
        ('h', 1, 'ACIDENTES DE TRAJETO'),
        ('h', 2, 'Auxílio por incapacidade temporária por acidente de trabalho (B91) – decorrente de acidente de trajeto'),
        ('t', [x, y]),
        ('h', 2, 'Auxílio-acidente por acidente de trabalho (B94) – decorrente de acidente de trajeto'),
        ('t', [x]),
        ('h', 1, 'Atribuição indevida de nexo técnico previdenciário – reconhecimento judicial da ausência de '
                 'nexo causal e de concausalidade'),
        ('t', [x]),
    ])
    ped = {q.secao_numero: q.dados for q in montar_pedidos(p, DetectorRegras().detectar(p)).pedidos}
    assert ped['1.1']['quantidade'] == 2 and ped['1.2']['quantidade'] == 1 and ped['2']['quantidade'] == 1
    assert [g['item_peticao'] for g in ped['1.1']['grupos_subsidiarios']] == ['1.2', '2']
    assert ped['1.2']['grupos_subsidiarios'] == []


def test_um_beneficio_com_mais_de_uma_vigencia_fica_no_plural(tmp_path):
    from autopedidos.documento import gerar_documento_com_tabelas
    cab = ['Item', 'Vigência do FAP', 'Vigência do FAP', 'CNPJ', 'Empregado', 'NIT', 'Tipo', 'Benefício', 'DIB', 'DCB']
    l = ['1', '2021', '2022', CNPJ, 'Pessoa A', '100000000-1', 'B91', '9990000001', '01/02/2021', '01/03/2021']
    p = _peticao(tmp_path, [('h', 1, 'ACIDENTES DE TRAJETO'), ('tab', cab, [l])])
    x = montar_pedidos(p, DetectorRegras().detectar(p)).pedidos[0]
    assert x.dados['quantidade'] == 1 and x.dados['indice_plural'] is True
    texto = '\n'.join(q.text for q in gerar_documento_com_tabelas([x]).paragraphs)
    assert 'dos índices do FAP' in texto and 'do índice do FAP' not in texto


def test_concomitancia_com_aposentadoria_anterior_mantem_todos_os_b91_do_segurado():
    """O "outro benefício" (aposentadoria) é o anterior do segurado: os dois B91 dele ficam no pedido
    (antes o B91 mais antigo era descartado como se fosse o anterior)."""
    from autopedidos.beneficios import Beneficio
    from autopedidos.pedidos import _beneficios_excluidos

    def b(num, esp, dib, ordem):
        return Beneficio(numero=num, especie=esp, nit='1', dib=dib, ordem=ordem)
    lista = [b('111111111', 'B46', '02/01/2015', 0), b('222222222', 'B91', '17/09/2015', 1),
             b('333333333', 'B91', '05/07/2018', 2)]
    escolhidos, _, anteriores = _beneficios_excluidos('concomitancia_outro_beneficio', lista)
    assert [x.numero for x in escolhidos] == ['222222222', '333333333']
    assert anteriores == ['B46']


def test_restabelecimento_com_dib_depois_da_dcb_segue_a_ordem_da_tabela():
    """Planilha com DIB (01/11/2016) depois da própria DCB (12/02/2016): ordenar por DIB trocaria o
    anterior pelo restabelecimento. Vale a ordem da tabela e sai um aviso."""
    from autopedidos.beneficios import Beneficio
    from autopedidos.pedidos import _beneficios_excluidos
    ant = Beneficio(numero='111111111', especie='B91', nit='1', dib='01/11/2016', dcb='12/02/2016', ordem=0)
    rest = Beneficio(numero='222222222', especie='B91', nit='1', dib='13/02/2016', dcb='31/05/2019', ordem=1)
    escolhidos, notas, _ = _beneficios_excluidos('restabelecimento_beneficio_anterior', [ant, rest])
    assert [x.numero for x in escolhidos] == ['222222222']
    assert any('DIB posterior à DCB' in n and '111111111' in n for n in notas)


def test_restabelecimento_marcacao_do_item_vale_sobre_as_datas():
    """Um "-" e os demais numerados: o "-" é o anterior, mesmo que as datas apontem outro como o mais antigo."""
    from autopedidos.beneficios import Beneficio
    from autopedidos.pedidos import _beneficios_excluidos
    ant = Beneficio(numero='111111111', especie='B91', nit='1', dib='01/11/2017', dcb='12/02/2018', ordem=1, item='-')
    rest = Beneficio(numero='222222222', especie='B91', nit='1', dib='13/02/2016', dcb='31/05/2019', ordem=0, item='2')
    escolhidos, notas, _ = _beneficios_excluidos('restabelecimento_beneficio_anterior', [rest, ant])
    assert [x.numero for x in escolhidos] == ['222222222']
    assert any('marca o NB 111111111' in n for n in notas)


def test_restabelecimento_dois_pares_do_mesmo_segurado_mantem_todos_os_tracos():
    """Caso Angeloni: B31 "-" -> B91 "2" -> B31 "-" -> B91 "3" do mesmo NIT. Os dois B31 marcados com "-"
    são anteriores e ficam; cada B91 é posterior ao "-" logo acima dele."""
    from autopedidos.beneficios import Beneficio
    from autopedidos.pedidos import _beneficios_excluidos
    a1 = Beneficio(numero='6455139198', especie='B31', nit='1', dib='03/02/2021', dcb='25/04/2021', ordem=0, item='-')
    r1 = Beneficio(numero='6347969479', especie='B91', nit='1', dib='26/04/2021', dcb='03/07/2021', ordem=1, item='2')
    a2 = Beneficio(numero='6400451360', especie='B31', nit='1', dib='08/11/2021', dcb='12/04/2022', ordem=2, item='-')
    r2 = Beneficio(numero='6388465289', especie='B91', nit='1', dib='13/04/2022', dcb='31/01/2023', ordem=3, item='3')
    escolhidos, _, _ = _beneficios_excluidos('restabelecimento_beneficio_anterior', [a1, r1, a2, r2])
    assert [x.numero for x in escolhidos] == ['6347969479', '6388465289']
    assert 'posterior ao NB 6455139198' in r1.decisao
    assert 'posterior ao NB 6400451360' in r2.decisao
    assert a2.decisao.startswith('benefício anterior')


def test_restabelecimento_sem_marcacao_padrao_continua_por_data():
    from autopedidos.beneficios import Beneficio
    from autopedidos.pedidos import _beneficios_excluidos
    a = Beneficio(numero='111111111', especie='B91', nit='1', dib='01/01/2015', dcb='01/02/2015', ordem=1, item='1')
    b = Beneficio(numero='222222222', especie='B91', nit='1', dib='01/01/2016', dcb='01/02/2016', ordem=0, item='1')
    escolhidos, _, _ = _beneficios_excluidos('restabelecimento_beneficio_anterior', [b, a])
    assert [x.numero for x in escolhidos] == ['222222222']


def test_ordem_das_especies_coloca_b31_antes_das_demais():
    from autopedidos.pedidos import _ordenar_especies
    assert _ordenar_especies(['B91', 'B31']) == ['B31', 'B91']
    assert _ordenar_especies(['B94', 'B92', 'B91']) == ['B91', 'B92', 'B94']
    assert _ordenar_especies(['B36', 'B94', 'B31']) == ['B31', 'B94', 'B36']


def test_cat_nao_vinculada_usa_o_cabecalho_ntp_do_beneficio():
    """Na tese CAT NÃO VINCULADA o número da coluna é o do NTP: cabeçalho "NTP do benefício"."""
    from types import SimpleNamespace
    from autopedidos.beneficios import Beneficio
    from autopedidos.tabelas import LARGURAS, n_beneficios_na_tabela, tabela_do_pedido
    b = Beneficio(numero='6030880156', especie='B91', vigencias={'2017'}, cnpjs={'04368898000100'})
    b.linhas = [{'item': '1', 'vigs': ['2017'], 'cnpj': '04.368.898/0001-00', 'tipo': 'B91',
                 'beneficio': b.numero, 'indices': '', 'bt': False}]

    def pedido(chave):
        return SimpleNamespace(dados={'tese_key': chave}, beneficios=[b], tabela_base=None)
    t = tabela_do_pedido(pedido('cat_nao_vinculada'))
    assert [c for c, _ in t.cabecalho][-1] == 'NTP do benefício'
    assert n_beneficios_na_tabela(t) == 1
    assert [c for c, _ in tabela_do_pedido(pedido('ntp_duplicado')).cabecalho][-1] == 'NTP do benefício'
    assert [c for c, _ in tabela_do_pedido(pedido('cat_duplicada')).cabecalho][-1] == 'Benefício'
    # a coluna "NTP do benefício" é larga (cabeçalho e número de 10 dígitos numa linha só); antes caía na largura
    # estreita da coluna "NTP" e o número quebrava em 3 linhas
    larguras = dict(zip([c for c, _ in t.cabecalho], t.larguras))
    assert larguras['NTP do benefício'] == LARGURAS['ntp_beneficio'] > LARGURAS['beneficio']


def test_tese_de_ntp_le_tabela_sem_coluna_tipo():
    """CAT NÃO VINCULADA / NTP DUPLICADO excluem o NTP, não o benefício: a espécie não importa e a tabela
    pode nem ter a coluna "Tipo". Cada número da coluna é um NTP."""
    from autopedidos.beneficios import eh_tabela_de_beneficios, ler_beneficios
    from autopedidos.leitor import Tabela
    cab = ['Item', 'Vigência do FAP', 'CNPJ', 'Empregado', 'NIT', 'Benefício', 'CAT']
    linhas = [cab] + [[str(i), '2017', '04.368.898/0001-06', 'X', '1000000000' + str(i), '605156658' + str(i), '2013.1']
                      for i in (1, 2, 3)]
    t = Tabela(linhas=linhas)
    assert not eh_tabela_de_beneficios(t)
    assert eh_tabela_de_beneficios(t, sem_especie=True)
    bs = ler_beneficios(t, sem_especie=True)
    assert [b.numero for b in bs] == ['6051566581', '6051566582', '6051566583']
    assert all(b.especie == '' for b in bs)


def test_contestacao_com_varias_vigencias_usa_plural(tmp_path):
    """"às competências da vigência de" com uma vigência e "às competências das vigências de" quando a tabela traz mais de uma vigência."""
    def pedido(linhas):
        p = _peticao(tmp_path, [('h', 1, 'CONTESTAÇÃO ADMINISTRATIVA, EFEITO SUSPENSIVO E PRAZO PRESCRICIONAL'),
                                ('tab', ['Item', 'Vigência do FAP', 'CNPJ'], linhas)])
        return montar_pedidos(p, DetectorRegras().detectar(p)).pedidos[0]
    uma = pedido([['1', '2017', CNPJ]])
    varias = pedido([['1', '2017', CNPJ], ['2', '2019', CNPJ], ['3', '2020', CNPJ], ['4', '2021', CNPJ]])
    from autopedidos.gerapedvendor import gerador_pedido
    texto = lambda p: ' '.join(x.text for x in gerador_pedido.gerar_documento([p.dados]).paragraphs)
    assert 'em relação às competências da vigência de 2017 não alcançadas' in texto(uma)
    assert 'em relação às competências das vigências de ' in texto(varias)
