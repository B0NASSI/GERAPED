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
