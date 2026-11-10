"""Log de análise: o porquê das decisões do programa fica gravado em arquivo."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import docx

import test_pedidos as tp
from autopedidos import registro, revisao


def _peticao(tmp_path):
    f = tmp_path / 'Petição fictícia.docx'
    d = docx.Document()
    tp.sinteticas._numbering(d)
    cab = ['Item', 'Vigência do FAP', 'CNPJ', 'Empregado', 'NIT', 'Tipo', 'Benefício']
    tp.sinteticas._titulo(d, 'ACIDENTES DE TRAJETO', 1)
    tp.sinteticas._tabela(d, [cab,
                              ['1', '2016', tp.CNPJ, 'NOME SECRETO', '1', 'B91', '9990000001'],
                              ['2', '2016', tp.CNPJ, 'OUTRO NOME', '2', 'B91', '9990000002']])
    tp.sinteticas._titulo(d, 'Tema totalmente diferente', 1)
    d.save(f)
    return f


def test_analise_traz_tese_motivo_tabela_e_beneficios(tmp_path):
    f = _peticao(tmp_path)
    pet, det, prop = revisao.processar(f)
    arquivo = registro.salvar_analise(tmp_path, f, pet, det, prop, '9.9')
    assert arquivo.parent == tmp_path / 'logs' / 'analises' and arquivo.name.startswith('ANALISE ')
    txt = arquivo.read_text(encoding='utf-8')
    assert 'TESE acidente_trajeto | confiança alta | origem titulo' in txt          # por que a tese
    assert 'NÃO CLASSIFICADA' in txt and 'Tema totalmente diferente' in txt          # o que não entendeu
    assert 'TABELA DE BENEFÍCIOS: 2 benefício(s)' in txt                              # como leu a tabela
    assert 'NB 9990000001' in txt and 'decisão:' in txt                               # benefícios e decisão
    assert 'índice_singular=True' in txt and 'singular só com 1 vigência e 1 CNPJ' in txt
    assert 'NOME SECRETO' not in txt and 'OUTRO NOME' not in txt                      # nomes de empregados não vão para o log


def test_erro_de_leitura_grava_rastro(tmp_path):
    try:
        raise ValueError('falhou aqui')
    except ValueError as exc:
        arquivo = registro.salvar_erro(tmp_path, 'x/arquivo.docx', exc, '9.9')
    txt = arquivo.read_text(encoding='utf-8')
    assert 'ERRO AO LER A PETIÇÃO' in txt and 'ValueError: falhou aqui' in txt and 'Traceback' in txt


def test_geracao_registra_o_que_o_usuario_mudou(tmp_path):
    f = _peticao(tmp_path)
    pet, det, prop = revisao.processar(f)
    arquivo = registro.salvar_analise(tmp_path, f, pet, det, prop)
    proposto = prop.pedidos[0]
    final = dict(proposto.dados, quantidade=5, item_peticao='9')
    blocos = [SimpleNamespace(proposto=proposto), SimpleNamespace(proposto=None)]
    registro.anotar_geracao(arquivo, prop, blocos, [final, dict(final)], 'saida.docx')
    txt = arquivo.read_text(encoding='utf-8')
    assert 'GERAÇÃO DO WORD' in txt and 'ALTERADO pelo usuário' in txt
    assert "quantidade: 2 -> 5" in txt and 'ADICIONADO À MÃO' in txt


def test_analises_antigas_sao_podadas(tmp_path, monkeypatch):
    monkeypatch.setattr(registro, 'MANTER_ARQUIVOS', 3)
    pasta = registro.pasta_de_analises(tmp_path)
    for i in range(6):
        (pasta / f'ANALISE {i}.log').write_text('x')
    registro._podar(pasta)
    assert len(list(pasta.glob('ANALISE *.log'))) == 3
