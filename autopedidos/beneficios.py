"""Leitura da tabela de benefícios das petições (colunas típicas:
Item | Vigência do FAP | CNPJ | Empregado | NIT | Tipo | Benefício | DIB | DCB).

Robusta a variações: usa o cabeçalho quando a linha tem a mesma largura dele e, senão (células
mescladas deslocam as colunas), reconhece os valores pelo formato (espécie "B91", número do
benefício com 9-11 dígitos, CNPJ, ano de vigência).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .gabarito import norm

RX_ESPECIE = re.compile(r'^[Bb]\s?(\d{2})$')
RX_NUMERO = re.compile(r'^\d{9,11}$')
RX_CNPJ = re.compile(r'\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}')
RX_ANO = re.compile(r'\b((?:19|20)\d{2})\b')
RX_DATA = re.compile(r'\d{2}/\d{2}/\d{4}')


@dataclass
class Beneficio:
    numero: str
    especie: str                        # "B91"
    vigencias: set = field(default_factory=set)      # anos (str)
    cnpjs: set = field(default_factory=set)
    dib: Optional[str] = None
    dcb: Optional[str] = None
    nit: str = ''                       # NIT/empregado (identifica o segurado, quando a coluna existe)
    item: str = ''                    # valor da coluna "Item" (benefícios de um mesmo caso repetem o item)
    ordem: int = 0                      # posição da linha na tabela
    ntp: Optional[bool] = None          # True/False conforme a coluna NTP da tabela da tese; None = sem coluna
    linhas: list = field(default_factory=list)   # linhas de origem (dicts) p/ montar a tabela do pedido
    vigs_anteriores: list = field(default_factory=list)  # anos de FAP dos benefícios anteriores do mesmo segurado (60 dias)
    decisao: str = ''                   # por que foi excluído / mantido como anterior (vai para o log de análise)


def _data_ordenavel(d):
    return d[6:10] + d[3:5] + d[0:2] if d else ''


def _so_digitos(s):
    return re.sub(r'\D', '', s)


def anos_da_celula(texto):
    """Uma célula de vigência pode trazer vários anos ("2021 e 2022", "2021/2022"): devolve
    cada ano separado (cada um vai para sua coluna na tabela do pedido). Sem ano, o texto cru."""
    anos = RX_ANO.findall(texto)
    return anos if anos else ([texto.strip()] if texto.strip() else [])


def _linha_fonte(linha, alinhada, i_vigs, i_cnpj, i_ind, especie, numero, bt=False):
    """Campos da linha usados na tabela do pedido. Linha com largura diferente do cabeçalho
    (célula mesclada deslocou as colunas) é lida por formato: anos antes do CNPJ."""
    if alinhada:
        vigs = [a for i in i_vigs for a in anos_da_celula(linha[i])]
        cnpj = linha[i_cnpj].strip() if i_cnpj is not None else ''
        ind = linha[i_ind].strip() if i_ind is not None else ''
    else:
        k = next((j for j, c in enumerate(linha) if RX_CNPJ.search(c)), None)
        vigs = [a for c in (linha[1:k] if k else linha[1:2]) if RX_ANO.search(c) for a in anos_da_celula(c)]
        cnpj = linha[k].strip() if k is not None else ''
        ind = ''
    return {'item': linha[0].strip() if linha else '', 'vigs': vigs, 'cnpj': cnpj,
            'tipo': especie, 'beneficio': numero, 'indices': ind, 'bt': bt}


def _coluna_numero(tabela):
    """Índice da coluna com o número do benefício/NTP ("Benefício" ou "NTP do benefício"), ou None."""
    for i, c in enumerate(norm(x) for x in tabela.cabecalho):
        if c.startswith('beneficio') or c.startswith('ntp do beneficio'):
            return i
    return None


def eh_tabela_de_beneficios(tabela, sem_especie=False):
    """`sem_especie`: teses que excluem NTP (CAT não vinculada, NTP duplicado) não dependem da espécie;
    basta a coluna do número ter números de benefício."""
    if any(RX_ESPECIE.match(c.strip()) for l in tabela.linhas[1:] for c in l):
        return True
    if sem_especie:
        j = _coluna_numero(tabela)
        return j is not None and any(len(l) == len(tabela.cabecalho) and RX_NUMERO.match(_so_digitos(l[j]))
                                     for l in tabela.linhas[1:])
    return False


def ler_beneficios(tabela, sem_especie=False):
    """Lista de Beneficio (um por número; repetições de vigência/CNPJ são unidas). `sem_especie`: aceita
    linhas sem espécie (coluna "Tipo" ausente); o benefício fica com especie ''."""
    cab = [norm(c) for c in tabela.cabecalho]

    def idx(*nomes):
        for i, c in enumerate(cab):
            if any(c.startswith(n) for n in nomes):
                return i
        return None
    i_num, i_tipo = _coluna_numero(tabela), idx('tipo')
    # o cabeçalho "Vigências do FAP" pode ocupar 2+ colunas (benefício que pesa em mais de uma vigência)
    i_vigs = [i for i, c in enumerate(cab) if c.startswith('vigenc')]
    i_cnpj = idx('cnpj')
    i_dib, i_dcb = idx('dib'), idx('dcb')
    i_nit, i_ind = idx('nit'), idx('indices')
    i_ntp = next((i for i, c in enumerate(cab) if c == 'ntp'), None)     # coluna "NTP" (não "NTP do benefício")
    por_numero = {}

    for linha in tabela.linhas[1:]:
        especie = numero = None
        alinhada = len(linha) == len(cab)
        if alinhada and i_tipo is not None and i_num is not None:
            m = RX_ESPECIE.match(linha[i_tipo].strip())
            n = _so_digitos(linha[i_num])
            if m and RX_NUMERO.match(n):
                especie, numero = f'B{m.group(1)}', n
        if especie is None:
            # por formato: espécie e, ao lado, o número do benefício
            for k, c in enumerate(linha):
                m = RX_ESPECIE.match(c.strip())
                if not m:
                    continue
                viz = [k + 1, k - 1] if (i_num is None or i_tipo is None or i_num > i_tipo) else [k - 1, k + 1]
                for v in viz:
                    if 0 <= v < len(linha) and RX_NUMERO.match(_so_digitos(linha[v])) and '.' not in linha[v]:
                        especie, numero = f'B{m.group(1)}', _so_digitos(linha[v])
                        break
                if especie:
                    break
        if especie is None and sem_especie and alinhada and i_num is not None and RX_NUMERO.match(_so_digitos(linha[i_num])):
            especie, numero = '', _so_digitos(linha[i_num])
        if especie is None:
            continue
        b = por_numero.setdefault(numero, Beneficio(numero=numero, especie=especie,
                                                    item=(linha[0].strip() if linha else ''), ordem=len(por_numero)))
        b.linhas.append(_linha_fonte(linha, alinhada, i_vigs, i_cnpj, i_ind, especie, numero,
                                     bt=(i_num is not None and i_tipo is not None and i_num < i_tipo)))
        # coluna NTP da tabela da tese: "NTP" = o benefício tem NTP (sem CAT vinculada); "-" = não tem
        if alinhada and i_ntp is not None:
            if norm(linha[i_ntp]).startswith('ntp'):
                b.ntp = True
            elif b.ntp is None:
                b.ntp = False
        elif not alinhada and any(norm(c) == 'ntp' for c in linha):
            b.ntp = True
        if not alinhada:
            datas = RX_DATA.findall(' '.join(linha))
            if len(datas) >= 2 and b.dib is None:
                b.dib, b.dcb = datas[0], datas[1]
        if alinhada:
            if i_nit is not None and not b.nit:
                b.nit = _so_digitos(linha[i_nit])
            for iv in i_vigs:
                b.vigencias.update(RX_ANO.findall(linha[iv]))
            if i_cnpj is not None:
                b.cnpjs.update(_so_digitos(x) for x in RX_CNPJ.findall(linha[i_cnpj]))
            if i_dib is not None and RX_DATA.search(linha[i_dib]):
                b.dib = RX_DATA.search(linha[i_dib]).group(0)
            if i_dcb is not None and RX_DATA.search(linha[i_dcb]):
                b.dcb = RX_DATA.search(linha[i_dcb]).group(0)
        else:
            for c in linha:
                if RX_CNPJ.search(c):
                    b.cnpjs.update(_so_digitos(x) for x in RX_CNPJ.findall(c))
            if len(linha) > 1 and RX_ANO.search(linha[1]) and not RX_CNPJ.search(linha[1]):
                b.vigencias.update(RX_ANO.findall(linha[1]))
    return list(por_numero.values())


def vigencias_e_cnpjs_da_tabela(tabela):
    """Para teses sem benefícios (prescrição, contestação, massa salarial, vínculos,
    rotatividade): anos de vigência e CNPJs citados nas linhas de dados."""
    cab = [norm(c) for c in tabela.cabecalho]
    i_vigs = [i for i, c in enumerate(cab) if c.startswith('vigenc')]
    anos, cnpjs = set(), set()
    for linha in tabela.linhas[1:]:
        if i_vigs and len(linha) == len(cab):
            for iv in i_vigs:
                anos.update(RX_ANO.findall(linha[iv]))
        elif len(linha) > 1 and not RX_CNPJ.search(linha[1]):
            anos.update(RX_ANO.findall(linha[1]))
        for c in linha:
            cnpjs.update(_so_digitos(x) for x in RX_CNPJ.findall(c))
    return anos, cnpjs
