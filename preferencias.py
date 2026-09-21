# Preferência do usuário para a ordem das teses nos comboboxes (tela "Opções"). Sem
# dependência de Tkinter, para poder ser testado isoladamente - ver tests/test_preferencias.py.

import json
import os
import sys

from teses import TESES

# Ordem padrão curada (não alfabética) usada quando o usuário nunca salvou uma
# preferência própria em "Opções" - pedido do escritório. Teses que existirem em TESES mas
# não estiverem aqui (ex: adicionadas depois e esquecidas desta lista) vão para o final, em
# ordem alfabética, via ordenar_chaves_teses - nunca somem da tela.
ORDEM_PADRAO = [
    'contestacao_administrativa',
    'prescricao_quinquenal',
    'cat_nao_vinculada',
    'acidente_sem_relacao_empresa',
    'acidente_trajeto',
    'convertido',
    'natureza_previdenciaria',
    'restabelecimento_beneficio_anterior',
    'beneficio_cancelado_revogado',
    'erro_implantacao',
    'acidente_outro_estabelecimento',
    'concomitancia_outro_beneficio',
    'dib_igual_dcb',
    'ausencia_nexo_causal_concausalidade',
    'acidente_anterior_2007',
    'custo_cessado',
    'sobreposicao_concomitancia_beneficios',
    'ntp_duplicado',
    'cat_duplicada',
    'erro_vinculos',
    'erro_massa_salarial',
    'rotatividade',
]


def _caminho_preferencias():
    base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'preferencias.json')


# Migração pontual da v1.2.2: quem salvou uma ordem em "Ordem" antes de CONVERTIDO, NTP
# DUPLICADO e CAT DUPLICADA existirem ficava sem essas 3 teses na lista salva (iam pro
# final, fora da posição curada, da próxima vez que abrissem a tela). Encaixa essas 3 na
# posição certa - mas só a primeira vez que o arquivo for lido após essa atualização (flag
# 'migrado_1_2_2' no json, setada por salvar_ordem_teses a partir daqui pra frente): se a
# pessoa depois tirar de propósito uma dessas teses da ordem, a migração não pode voltar a
# adicionar de novo. Pedido do escritório: só essa atualização mexe na ordem já salva pelo
# usuário - por isso é hardcoded pra essas 3 chaves, e não um mecanismo genérico (teses
# futuras não devem reordenar a preferência salva; ver ORDEM_PADRAO/_completar_e_filtrar).
def _migrar_teses_1_2_2(ordem):
    ordem = list(ordem)
    if 'convertido' not in ordem:
        if 'acidente_trajeto' in ordem:
            ordem.insert(ordem.index('acidente_trajeto') + 1, 'convertido')
        else:
            ordem.append('convertido')
    if 'ntp_duplicado' not in ordem:
        if 'sobreposicao_concomitancia_beneficios' in ordem:
            ordem.insert(ordem.index('sobreposicao_concomitancia_beneficios') + 1, 'ntp_duplicado')
        else:
            ordem.append('ntp_duplicado')
    if 'cat_duplicada' not in ordem:
        if 'ntp_duplicado' in ordem:
            ordem.insert(ordem.index('ntp_duplicado') + 1, 'cat_duplicada')
        else:
            ordem.append('cat_duplicada')
    return ordem


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
        ordem = [chave for chave in ordem if chave in TESES]
        if not dados.get('migrado_1_2_2'):
            ordem_migrada = _migrar_teses_1_2_2(ordem)
            salvar_ordem_teses(ordem_migrada)
            return ordem_migrada
        return ordem
    except Exception:
        return None


def salvar_ordem_teses(ordem_chaves):
    try:
        with open(_caminho_preferencias(), 'w', encoding='utf-8') as f:
            json.dump(
                {'ordem_teses': list(ordem_chaves), 'migrado_1_2_2': True},
                f, ensure_ascii=False, indent=2,
            )
    except Exception:
        pass


def _completar_e_filtrar(base, universo):
    """Filtra 'base' (uma ordem de chaves, possivelmente incompleta) para o universo dado,
    completando com ORDEM_PADRAO e por fim ordem alfabética para o que faltar - assim
    nenhuma chave do universo some da lista."""
    no_universo = set(universo)
    vistas = set(base)
    completa = list(base)
    for chave in ORDEM_PADRAO:
        if chave not in vistas:
            completa.append(chave)
            vistas.add(chave)

    ordenadas = [c for c in completa if c in no_universo]
    vistas_no_universo = set(ordenadas)
    restantes = sorted((c for c in universo if c not in vistas_no_universo), key=lambda c: TESES[c]['nome'])
    return ordenadas + restantes


def ordenar_chaves_teses(chaves=None):
    """Chaves de tese (restritas a 'chaves', se informado), na ordem preferida do usuário
    (se ele já salvou uma em "Opções"), completada pela ORDEM_PADRAO curada para o que não
    estiver na preferência salva - e só cai para ordem alfabética o que nem isso tiver (ex:
    tese nova, ainda não incluída em ORDEM_PADRAO), pra nunca sumir da lista."""
    universo = list(chaves) if chaves is not None else list(TESES.keys())
    return _completar_e_filtrar(ler_ordem_teses() or [], universo)


def ordem_padrao_chaves(chaves=None):
    """Como ordenar_chaves_teses, mas ignorando qualquer preferência salva - usada pelo
    botão "Restaurar padrão" em Opções, pra descartar a customização do usuário de propósito."""
    universo = list(chaves) if chaves is not None else list(TESES.keys())
    return _completar_e_filtrar([], universo)


def ordenar_nomes_teses(chaves=None):
    return [TESES[c]['nome'] for c in ordenar_chaves_teses(chaves)]
