import json

import preferencias
from teses import TESES


def _isolar(tmp_path, monkeypatch):
    caminho = str(tmp_path / 'preferencias.json')
    monkeypatch.setattr(preferencias, '_caminho_preferencias', lambda: caminho)
    return caminho


def test_ler_ordem_teses_sem_arquivo_retorna_none(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    assert preferencias.ler_ordem_teses() is None


def test_salvar_e_ler_ordem_teses(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    ordem = ['rotatividade', 'acidente_trajeto', 'custo_cessado']
    preferencias.salvar_ordem_teses(ordem)
    assert preferencias.ler_ordem_teses() == ordem


def test_ler_ordem_ignora_chaves_que_nao_existem_mais(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    preferencias.salvar_ordem_teses(['rotatividade', 'tese_que_nao_existe_mais'])
    assert preferencias.ler_ordem_teses() == ['rotatividade']


def test_ordenar_chaves_teses_sem_preferencia_usa_ordem_padrao(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    # 'acidente_trajeto' vem antes de 'rotatividade' na ORDEM_PADRAO, embora o inverso
    # seja verdade em ordem alfabética (ROTATIVIDADE < TRAJETO) - confirma que o padrão
    # sem preferência salva usa a curadoria, não A-Z.
    resultado = preferencias.ordenar_chaves_teses(['rotatividade', 'acidente_trajeto'])
    assert resultado == ['acidente_trajeto', 'rotatividade']


def test_convertido_vem_logo_apos_trajeto_na_ordem_padrao():
    idx_trajeto = preferencias.ORDEM_PADRAO.index('acidente_trajeto')
    idx_convertido = preferencias.ORDEM_PADRAO.index('convertido')
    assert idx_convertido == idx_trajeto + 1


def test_ntp_duplicado_e_cat_duplicada_vem_logo_apos_sobreposicao_na_ordem_padrao():
    idx_sobreposicao = preferencias.ORDEM_PADRAO.index('sobreposicao_concomitancia_beneficios')
    idx_ntp = preferencias.ORDEM_PADRAO.index('ntp_duplicado')
    idx_cat = preferencias.ORDEM_PADRAO.index('cat_duplicada')
    assert idx_ntp == idx_sobreposicao + 1
    assert idx_cat == idx_ntp + 1


def test_migracao_1_2_2_encaixa_convertido_ntp_e_cat_na_leitura(tmp_path, monkeypatch):
    caminho = _isolar(tmp_path, monkeypatch)
    ordem_antiga = [
        'contestacao_administrativa', 'prescricao_quinquenal', 'cat_nao_vinculada',
        'acidente_sem_relacao_empresa', 'acidente_trajeto', 'natureza_previdenciaria',
        'restabelecimento_beneficio_anterior', 'beneficio_cancelado_revogado', 'erro_implantacao',
        'acidente_outro_estabelecimento', 'concomitancia_outro_beneficio', 'dib_igual_dcb',
        'ausencia_nexo_causal_concausalidade', 'acidente_anterior_2007', 'custo_cessado',
        'sobreposicao_concomitancia_beneficios', 'erro_vinculos', 'erro_massa_salarial', 'rotatividade',
    ]
    # escreve o json bruto, sem 'migrado_1_2_2' - simula um arquivo salvo de verdade antes
    # dessa migração existir (salvar_ordem_teses já marcaria a flag, o que pularia a migração)
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump({'ordem_teses': ordem_antiga}, f)
    resultado = preferencias.ler_ordem_teses()
    assert resultado.index('convertido') == resultado.index('acidente_trajeto') + 1
    assert resultado.index('ntp_duplicado') == resultado.index('sobreposicao_concomitancia_beneficios') + 1
    assert resultado.index('cat_duplicada') == resultado.index('ntp_duplicado') + 1
    # a migração persiste no arquivo - uma segunda leitura não move mais nada
    assert preferencias.ler_ordem_teses() == resultado


def test_migracao_1_2_2_nao_repete_se_pessoa_remover_tese_de_proposito_depois(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    # salvar_ordem_teses já marca a flag de migrado - simula a pessoa removendo de
    # propósito 'cat_duplicada' da ordem numa edição posterior em "Ordem" e salvando.
    preferencias.salvar_ordem_teses(['rotatividade', 'convertido', 'ntp_duplicado'])
    assert preferencias.ler_ordem_teses() == ['rotatividade', 'convertido', 'ntp_duplicado']


def test_ordem_padrao_chaves_ignora_preferencia_salva(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    preferencias.salvar_ordem_teses(['rotatividade', 'acidente_trajeto'])
    resultado = preferencias.ordem_padrao_chaves(['rotatividade', 'acidente_trajeto'])
    assert resultado == ['acidente_trajeto', 'rotatividade']


def test_ordem_padrao_cobre_todas_as_teses_cadastradas():
    assert set(preferencias.ORDEM_PADRAO) == set(TESES.keys())


def test_ordenar_chaves_teses_usa_preferencia_salva(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    preferencias.salvar_ordem_teses(['custo_cessado', 'rotatividade', 'acidente_trajeto'])
    resultado = preferencias.ordenar_chaves_teses(['acidente_trajeto', 'rotatividade', 'custo_cessado'])
    assert resultado == ['custo_cessado', 'rotatividade', 'acidente_trajeto']


def test_ordenar_chaves_teses_novas_vao_para_o_final(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    preferencias.salvar_ordem_teses(['rotatividade'])
    resultado = preferencias.ordenar_chaves_teses(['rotatividade', 'acidente_trajeto', 'custo_cessado'])
    assert resultado[0] == 'rotatividade'
    assert set(resultado[1:]) == {'acidente_trajeto', 'custo_cessado'}


def test_ordenar_chaves_teses_restringe_ao_subconjunto_informado(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    preferencias.salvar_ordem_teses(['custo_cessado', 'rotatividade', 'acidente_trajeto'])
    resultado = preferencias.ordenar_chaves_teses(['rotatividade', 'acidente_trajeto'])
    assert resultado == ['rotatividade', 'acidente_trajeto']


def test_ordenar_nomes_teses_retorna_nomes_de_exibicao(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    assert preferencias.ordenar_nomes_teses(['rotatividade']) == ['ROTATIVIDADE']
