"""Camada da tela de revisão SEM interface gráfica (testável): processar, editar, prévia e gerar.

O texto final vem de `gerar_documento` do GERAPED (vendor), nunca reimplementado aqui.
"""
from __future__ import annotations

import re
from pathlib import Path

from .detector import DetectorRegras
from .gerapedvendor import PARAMETROS_TESE, TESES, gerador_pedido, teses as _teses
from .documento import gerar_documento_com_tabelas
from .leitor import ler_peticao
from .tabelas import tabela_do_pedido
from .pedidos import PedidoProposto, montar_pedidos, validar_pedidos

ESPECIES = list(_teses.TIPO_BENEFICIO_POR_ESPECIE)


class ErroValidacao(Exception):
    pass


def processar(caminho, detector=None):
    """.docx -> (Peticao, ResultadoDeteccao, Proposta). Tudo local."""
    detector = detector or DetectorRegras()
    peticao = ler_peticao(caminho)
    resultado = detector.detectar(peticao)
    return peticao, resultado, montar_pedidos(peticao, resultado)


# ── vocabulário de teses para a UI ──
def nomes_teses():
    return [t['nome'] for t in TESES.values()]


def chave_por_nome(nome):
    return _teses.nome_para_chave(nome)


def nomes_teses_subsidiarias():
    return [t['nome'] for t in TESES.values() if t.get('tipo_clausula') in (None, 'custo_cessado')]


def opcoes_parametro(tese_key):
    """[(valor, rótulo)] do parâmetro da tese, ou []."""
    pid = TESES[tese_key].get('parametro')
    return list(PARAMETROS_TESE[pid]['opcoes'].items()) if pid else []


def rotulo_parametro(tese_key):
    pid = TESES[tese_key].get('parametro')
    return PARAMETROS_TESE[pid]['label'] if pid else ''


# ── edição ──
def aplicar_edicao(p: PedidoProposto, **campos):
    """Aplica os campos editados (qualquer subconjunto de: tese_key, item_peticao, quantidade,
    especies, parametro_valor, campo_texto_valor, indice_singular, excluir_ntp, ntp_singular,
    varios_estabelecimentos). Respeita ignora_quantidade/ignora_especie da tese. Não valida:
    chame `revalidar` depois."""
    d = p.dados
    for k, v in campos.items():
        if k not in d or k == 'grupos_subsidiarios':
            raise KeyError(k)
        d[k] = v
    tese = TESES[d['tese_key']]
    if 'tese_key' in campos:
        p.tese_nome = tese['nome']
        if not tese.get('parametro'):
            d['parametro_valor'] = None
        if not tese.get('campo_texto'):
            d['campo_texto_valor'] = None
    if tese.get('ignora_quantidade'):
        d['quantidade'] = 1
    if tese.get('ignora_especie'):
        d['especies'] = []
    d['especies'] = [e for e in ESPECIES if e in d['especies']] + [e for e in d['especies'] if e not in ESPECIES]
    sincronizar_subsidiarias(p)


def sincronizar_subsidiarias(p: PedidoProposto):
    """Subsidiária 'todos os benefícios do principal' acompanha espécies/quantidade do principal."""
    for g in p.dados['grupos_subsidiarios']:
        if g['todos_beneficios_principal']:
            g['especies_principal'] = list(p.dados['especies'])
            g['quantidade_principal'] = p.dados['quantidade']
            g['numeros_com_especie'] = []
        else:
            g['especies_principal'] = g['quantidade_principal'] = None


_RX_LINHA_BENEFICIO = re.compile(r'^\s*[Bb]?\s?(\d{2})\s*(?:n[ºo°]?\.?\s*)?[:\-–]?\s*(\d{6,})\s*$')


def parse_beneficios_texto(texto):
    """'B91 9990000001' (uma por linha; 'B91 nº ...' também vale) -> [(especie, numero)]."""
    out = []
    for linha in texto.splitlines():
        if not linha.strip():
            continue
        m = _RX_LINHA_BENEFICIO.match(linha)
        if not m:
            raise ValueError(f'Linha de benefício inválida: "{linha.strip()}" (use: B91 9990000001).')
        out.append((f'B{m.group(1)}', m.group(2)))
    return out


def beneficios_para_texto(numeros_com_especie):
    return '\n'.join(f'{e} {n}' for e, n in numeros_com_especie)


def novo_grupo(tese_key, item, numeros_com_especie=(), todos=False, parametro_valor=None):
    return {
        'tese_subsidiaria_key': tese_key, 'item_peticao': item,
        'numeros_com_especie': [] if todos else list(numeros_com_especie),
        'parametro_valor': parametro_valor, 'todos_beneficios_principal': bool(todos),
        'especies_principal': None, 'quantidade_principal': None,
    }


def revalidar(pedidos):
    validar_pedidos(pedidos, remover_invalidas=False)


# ── prévia e geração ──
def previa(p: PedidoProposto):
    """Texto do pedido (como sairá no Word) ou a mensagem de erro."""
    try:
        doc = gerador_pedido.gerar_documento([p.dados])
        texto = '\n'.join(par.text for par in doc.paragraphs if par.text.strip())
    except KeyError as e:
        if e.args == (None,) and TESES[p.dados['tese_key']].get('parametro'):
            return '(escolha o parâmetro da tese, por exemplo o outro benefício, para ver o texto do pedido)'
        return f'(não foi possível gerar o texto ainda: KeyError: {e})'
    except Exception as e:      # noqa: BLE001
        return f'(não foi possível gerar o texto ainda: {type(e).__name__}: {e})'
    tab = tabela_do_pedido(p) if p.incluir_tabela else None
    if tab is not None:
        texto += '\n\nTABELA DO PEDIDO:\n' + tab.como_texto()
    return texto


def gerar_arquivo(pedidos, caminho):
    """Revalida tudo e salva o .docx via gerar_documento. ErroValidacao se algo estiver inválido."""
    revalidar(pedidos)
    ruins = [(i, p) for i, p in enumerate(pedidos, 1) if not p.valido]
    if ruins:
        msg = '\n'.join(f'Pedido {i} (item {p.dados["item_peticao"]}, {p.tese_nome}): ' +
                        '; '.join(t[len("Validação: "):] for t in p.pendencias if t.startswith('Validação:'))
                        for i, p in ruins)
        raise ErroValidacao(msg)
    if not pedidos:
        raise ErroValidacao('Não há pedidos para gerar.')
    doc = gerar_documento_com_tabelas(pedidos)
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(caminho))
    return caminho
