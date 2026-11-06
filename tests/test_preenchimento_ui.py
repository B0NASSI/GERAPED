"""Teste de ponta a ponta com a tela real do GERAPED: petição sintética -> blocos preenchidos ->
obter_dados() igual ao proposto -> Word com tabelas -> pré-visualização com tabelas.
Pula sozinho se não houver display (Tk indisponível)."""
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

tk = pytest.importorskip('tkinter')
ttkbootstrap = pytest.importorskip('ttkbootstrap')

import docx                                                  # noqa: E402

import test_pedidos as tp                                    # noqa: E402
from autopedidos.documento import gerar_documento_com_tabelas_lista   # noqa: E402


@pytest.fixture(scope='module')
def janela():
    import tema
    import interface
    try:
        root = ttkbootstrap.Window(themename='litera')
    except tk.TclError:
        pytest.skip('sem display')
    root.geometry('1000x800+20+20')
    tema.aplicar(root)
    j = interface.Janela(root, lambda n: str(RAIZ / n))
    yield j
    root.destroy()


@pytest.fixture
def peticao_docx(tmp_path):
    f = tmp_path / 'p.docx'
    d = docx.Document()
    tp.sinteticas._numbering(d)
    cab = ['Item', 'Vigência do FAP', 'CNPJ', 'Empregado', 'NIT', 'Tipo', 'NTP', 'Benefício']
    tp.sinteticas._titulo(d, 'ACIDENTES DE TRAJETO', 1)
    tp.sinteticas._tabela(d, [cab,
                              ['1', '2016', tp.CNPJ, 'A', '1', 'B91', 'ntp', '9990000001'],
                              ['2', '2016', tp.CNPJ, 'B', '2', 'B91', '-', '9990000002']])
    tp.sinteticas._titulo(d, 'Atribuição indevida de nexo técnico previdenciário – reconhecimento judicial da '
                             'ausência de nexo causal e de concausalidade', 1)
    tp.sinteticas._tabela(d, [['Item', 'Vigência do FAP', 'CNPJ', 'Empregado', 'NIT', 'Tipo', 'Benefício'],
                              ['1', '2016', tp.CNPJ, 'A', '1', 'B91', '9990000001']])
    tp.sinteticas._titulo(d, 'Contestação administrativa, efeito suspensivo e prazo prescricional', 1)
    tp.sinteticas._tabela(d, [['Item', 'Vigência do FAP', 'CNPJ'], ['1', '2016', tp.CNPJ]])
    tp.sinteticas._titulo(d, 'PEDIDOS', 1)
    d.save(f)
    return str(f)


def _limpar(j):
    for b in list(j.blocos):
        b._casca.destroy()
    j.blocos.clear()
    j.adicionar_pedido()


def test_preencher_da_peticao_devolve_os_mesmos_dados_pela_tela(janela, peticao_docx, monkeypatch):
    import preenchimento
    monkeypatch.setattr(preenchimento, 'mostrar_resumo', lambda *a, **k: None)
    _limpar(janela)
    janela.preencher_da_peticao(peticao_docx)
    janela.root.update()
    assert [b.proposto.secao_numero for b in janela.blocos] == ['1', '2', '3']
    for b in janela.blocos:
        d = b.obter_dados()
        p = b.proposto.dados
        assert (d['tese_key'], d['quantidade'], d['especies'], d['item_peticao']) == \
               (p['tese_key'], p['quantidade'], p['especies'], p['item_peticao'])
        assert [(g['tese_subsidiaria_key'], g['item_peticao'], g['todos_beneficios_principal'])
                for g in d['grupos_subsidiarios']] == \
               [(g['tese_subsidiaria_key'], g['item_peticao'], g['todos_beneficios_principal'])
                for g in p['grupos_subsidiarios']]
    primeiro = janela.blocos[0].obter_dados()
    assert primeiro['excluir_ntp'] is True and primeiro['ntp_singular'] is True   # 1 benefício com NTP (liberado pela contestação ≤2017)
    assert janela.blocos[0].check_tabela.winfo_manager() == 'grid'                # caixa "incluir tabela" visível


def test_word_pela_tela_traz_as_tabelas_e_o_pedido_manual_continua_sem_tabela(janela, peticao_docx, monkeypatch):
    import preenchimento
    monkeypatch.setattr(preenchimento, 'mostrar_resumo', lambda *a, **k: None)
    _limpar(janela)
    janela.preencher_da_peticao(peticao_docx)
    dados = [b.obter_dados() for b in janela.blocos]
    tabelas = [b.tabela_para_documento(d) for b, d in zip(janela.blocos, dados)]
    assert all(t is not None for t in tabelas)
    doc = gerar_documento_com_tabelas_lista(dados, tabelas)
    assert len(doc.tables) == 3
    assert [c.text for c in doc.tables[0].rows[0].cells] == ['Item', 'Vigência do FAP', 'CNPJ', 'Tipo', 'NTP', 'Benefício']
    # desmarcar "incluir tabela" tira só a tabela daquele pedido
    janela.blocos[1].var_tabela.set(False)
    assert janela.blocos[1].tabela_para_documento(dados[1]) is None


def test_preview_mostra_as_tabelas(janela, peticao_docx, monkeypatch):
    import interface
    import preenchimento
    monkeypatch.setattr(preenchimento, 'mostrar_resumo', lambda *a, **k: None)
    _limpar(janela)
    janela.preencher_da_peticao(peticao_docx)
    dados = [b.obter_dados() for b in janela.blocos]
    doc = gerar_documento_com_tabelas_lista(dados, [b.tabela_para_documento(d) for b, d in zip(janela.blocos, dados)])
    antes = set(janela.root.winfo_children())
    interface._mostrar_preview(janela.root, doc, lambda: None)
    janela.root.update()
    novas = [w for w in janela.root.winfo_children() if w not in antes]
    assert novas
    texto = ''
    for w in novas[0].winfo_children():
        for filho in w.winfo_children():
            if isinstance(filho, tk.Text):
                texto = filho.get('1.0', 'end')
    assert 'Item' in texto and '9990000001' in texto and 'Benefício' in texto
    novas[0].destroy()


def test_preencher_sem_nenhuma_tese_avisa_e_nao_apaga_a_tela(janela, tmp_path, monkeypatch):
    avisos = []
    import interface
    monkeypatch.setattr(interface, '_avisar', lambda w, t, m: avisos.append(m))
    f = tmp_path / 'vazia.docx'
    d = docx.Document()
    tp.sinteticas._numbering(d)
    tp.sinteticas._titulo(d, 'OBJETO DA AÇÃO', 1)
    d.save(f)
    _limpar(janela)
    n = len(janela.blocos)
    janela.preencher_da_peticao(str(f))
    assert avisos and 'Não encontrei nenhuma tese' in avisos[0] and len(janela.blocos) == n


def test_cartoes_das_subsidiarias_mostram_se_sao_subsidiarias_ou_alternativas(janela, tmp_path, monkeypatch):
    import preenchimento
    monkeypatch.setattr(preenchimento, 'mostrar_resumo', lambda *a, **k: None)
    b1 = tp.linha(1, '2023', 'A', '100000000-1', 'B91', '9990000001')
    b2 = tp.linha(2, '2023', 'B', '100000000-2', 'B91', '9990000002')
    tp._peticao(tmp_path, [
        ('h', 1, 'ACIDENTES DE TRAJETO'), ('t', [b1, b2]),
        ('h', 1, 'Atribuição indevida de nexo técnico previdenciário – reconhecimento judicial da ausência de '
                 'nexo causal e de concausalidade'), ('t', [b1]),
        ('h', 1, 'Acidentes ocorridos antes de abril de 2007'), ('t', [b1]),
        ('h', 1, 'PEDIDOS'),
    ])
    _limpar(janela)
    janela.preencher_da_peticao(str(tmp_path / 'p.docx'))
    janela.root.update()
    bloco = janela.blocos[0]
    g1, g2 = bloco.grupos_subsidiarios
    assert g1._rotulo_titulo.cget('text') == 'Tese subsidiária 1'
    assert 'Subsidiariamente' in g1._rotulo_papel.cget('text')
    assert g2._rotulo_titulo.cget('text').startswith('Tese alternativa 2')              # mesmo benefício: alternativa
    assert 'ou, alternativamente' in g2._rotulo_papel.cget('text')
    # mudar o benefício da 2ª tese para um ainda não citado => passa a subsidiária, na hora
    g2.linhas_beneficio[0].entry_numero.delete(0, 'end')
    g2.linhas_beneficio[0].entry_numero.insert(0, '9990000002')
    bloco.atualizar_papeis_subsidiarias()
    assert g2._rotulo_titulo.cget('text') == 'Tese subsidiária 2'
    # o Word segue a mesma classificação
    dados = bloco.obter_dados()
    from gerador_pedido import gerar_documento
    texto = gerar_documento([dados]).paragraphs[0].text
    assert 'alternativamente' not in texto


def test_faixa_com_o_nome_da_peticao_e_rever_apontamentos(janela, peticao_docx, monkeypatch):
    import preenchimento
    chamadas = []
    monkeypatch.setattr(preenchimento, 'mostrar_resumo', lambda *a, **k: chamadas.append(a))
    _limpar(janela)
    janela.preencher_da_peticao(peticao_docx)
    janela.root.update()
    assert janela._rotulo_peticao.cget('text') == 'Petição: p.docx'
    assert janela._faixa_peticao.winfo_manager() == 'pack'
    janela._rever_apontamentos()
    assert len(chamadas) == 2                      # ao carregar + ao clicar em "Rever apontamentos"
    janela._resultado_peticao = None
    janela._mostrar_faixa_peticao('')
    assert janela._faixa_peticao.winfo_manager() == ''


def test_ctrl_l_abre_o_log_da_peticao_carregada(janela, peticao_docx, monkeypatch):
    import preenchimento
    monkeypatch.setattr(preenchimento, 'mostrar_resumo', lambda *a, **k: None)
    abertos = []
    monkeypatch.setattr(os, 'startfile', lambda caminho: abertos.append(caminho), raising=False)
    _limpar(janela)
    janela.preencher_da_peticao(peticao_docx)
    assert janela._arquivo_analise and os.path.isfile(janela._arquivo_analise)
    janela.root.focus_force()
    janela.root.event_generate('<Control-l>')
    janela.root.update()
    assert abertos == [str(janela._arquivo_analise)]


def test_plural_da_contestacao_marca_sozinha_com_mais_de_uma_vigencia(janela):
    _limpar(janela)
    b = janela.blocos[0]
    b.combo_tese.set('CONTESTAÇÃO ADMINISTRATIVA')
    b._atualizar_parametro()
    janela.root.update()

    def digitar(texto):
        b.combo_parametro.delete(0, 'end')
        b.combo_parametro.insert(0, texto)
        b.combo_parametro.focus_force()                         # evento de teclado vai para o widget com foco
        b.combo_parametro.event_generate('<KeyRelease>')
        janela.root.update()
    digitar('2017')
    assert b.var_varios_estabelecimentos.get() is False
    digitar('2017, 2019')
    assert b.var_varios_estabelecimentos.get() is True           # mais de uma vigência: "Plural" marcada
    digitar('2017')
    assert b.var_varios_estabelecimentos.get() is False          # voltou a uma só: desmarca (foi ela que marcou)
    b.var_varios_estabelecimentos.set(True)                      # marcada à mão (vários CNPJs): não desmarca sozinha
    digitar('2017, 2019')
    digitar('2017')
    assert b.var_varios_estabelecimentos.get() is True
