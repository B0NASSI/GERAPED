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


def test_ordenar_chaves_teses_sem_preferencia_usa_alfabetica(tmp_path, monkeypatch):
    _isolar(tmp_path, monkeypatch)
    chaves = ['rotatividade', 'acidente_trajeto']
    resultado = preferencias.ordenar_chaves_teses(chaves)
    assert resultado == sorted(chaves, key=lambda c: TESES[c]['nome'])


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
