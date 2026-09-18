# Preferência do usuário para a ordem das teses nos comboboxes (tela "Opções"). Sem
# dependência de Tkinter, para poder ser testado isoladamente - ver tests/test_preferencias.py.

import json
import os
import sys

from teses import TESES


def _caminho_preferencias():
    base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'preferencias.json')


def ler_ordem_teses():
    """Lista de chaves de tese na ordem salva pelo usuário, ou None se nunca foi salva
    (nesse caso o padrão é ordem alfabética pelo nome de exibição)."""
    caminho = _caminho_preferencias()
    if not os.path.isfile(caminho):
        return None
    try:
        with open(caminho, encoding='utf-8') as f:
            dados = json.load(f)
        ordem = dados.get('ordem_teses')
        if not isinstance(ordem, list):
            return None
        return [chave for chave in ordem if chave in TESES]
    except Exception:
        return None


def salvar_ordem_teses(ordem_chaves):
    try:
        with open(_caminho_preferencias(), 'w', encoding='utf-8') as f:
            json.dump({'ordem_teses': list(ordem_chaves)}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def ordenar_chaves_teses(chaves=None):
    """Chaves de tese (restritas a 'chaves', se informado) na ordem preferida do usuário -
    teses nunca vistas na preferência salva (ex: adicionadas depois) vão ao final, em ordem
    alfabética, para não sumirem da lista."""
    universo = list(chaves) if chaves is not None else list(TESES.keys())
    ordem_salva = ler_ordem_teses()
    if not ordem_salva:
        return sorted(universo, key=lambda c: TESES[c]['nome'])

    no_universo = set(universo)
    ordenadas = [c for c in ordem_salva if c in no_universo]
    vistas = set(ordenadas)
    restantes = sorted((c for c in universo if c not in vistas), key=lambda c: TESES[c]['nome'])
    return ordenadas + restantes


def ordenar_nomes_teses(chaves=None):
    return [TESES[c]['nome'] for c in ordenar_chaves_teses(chaves)]
