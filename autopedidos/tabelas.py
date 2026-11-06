"""Tabela que acompanha cada pedido ("abaixo arrolados"), PADRONIZADA.

Layout único para todos os pedidos (decisão do usuário: as petições reais variam, o app não):
  * benefícios:  Item | Vigência(s) do FAP | CNPJ | Tipo | Benefício
    - cada vigência do benefício em sua PRÓPRIA coluna, sob o cabeçalho mesclado "Vigências do FAP"
      (uma só vigência: cabeçalho "Vigência do FAP", uma coluna);
    - uma linha por benefício; Item = 1..n sem células em branco;
    - extras só quando a tese exige: Índices (60 dias), NTP (se o pedido exclui NTP), DIB/DCB (custo cessado);
  * teses por vigência (prescrição, contestação, vínculos, massa salarial, rotatividade):
                 Item | Vigência do FAP | CNPJ [| Competências]
  * largura por tipo de coluna, altura das linhas, fonte, tamanho, alinhamento e a COR da coluna
    Item: iguais em todas, seguindo o padrão medido nas petições reais (ver LARGURAS e documento.py).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .beneficios import anos_da_celula
from .gabarito import norm

TESES_POR_VIGENCIA = {'fixo', 'fixo_com_vigencia', 'correcao_com_vigencia'}
# Dimensões medidas nas 342 tabelas de pedido das 52 petições reais (valores mais frequentes):
# largura (twips) por TIPO de coluna; a tabela padrão de 5 colunas soma 4.905 (a mais comum).
LARGURAS = {'item': 510, 'vigencia': 1134, 'cnpj': 1560, 'tipo': 567, 'beneficio': 1134, 'indices': 2154,
            'competencias': 1814, 'ntp': 545, 'dib': 1134, 'dcb': 1134,
            'ntp_beneficio': 1400}      # "NTP do benefício": cabeçalho e número de 10 dígitos cabem em UMA linha
ALTURA_CABECALHO = 567        # twips, altura mínima da linha do cabeçalho (1,0 cm)
ALTURA_LINHA = 397            # twips, altura mínima das linhas do corpo (0,7 cm)
# Pedido de 60 dias: a coluna "Índices" aparece, mas FICA EM BRANCO por enquanto (decisão do usuário):
# a tabela da tese não traz esse dado e o valor varia ("Frequência e gravidade" ou também "custo").
# Se a tabela da petição já trouxer a coluna Índices preenchida, o valor da petição é mantido.
PADRAO_INDICES_60_DIAS = ''


@dataclass
class TabelaPedido:
    cabecalho: list                       # [(texto, span)]  (span é sempre 1 no layout padronizado)
    linhas: list                          # list[list[str | None]]; None = mesclada com a célula à esquerda
    larguras: list = field(default_factory=list)   # twips por coluna (ver LARGURAS)

    @property
    def n_colunas(self):
        return sum(s for _, s in self.cabecalho)

    def como_texto(self):
        cab = ' | '.join(t for t, _ in self.cabecalho)
        return '\n'.join([cab] + [' | '.join('' if c == ACIMA else (c or '') for c in l) for l in self.linhas])


def _larguras(rotulos, n_vig=1):
    """Largura (twips) de cada coluna, conforme o tipo dela (valores das petições reais).
    As `n_vig` sub-colunas de vigência dividem a largura de UMA coluna de vigência."""
    out = []
    for r in rotulos:
        n = norm(r)
        if n.startswith('vigenc'):
            base = LARGURAS['vigencia'] // n_vig
            out.append(base)
        elif n.startswith('ntp do'):       # "NTP do benefício" (o NÚMERO do NTP) não pode cair na largura estreita da coluna "NTP"
            out.append(LARGURAS['ntp_beneficio'])
        else:
            out.append(next((w for k, w in LARGURAS.items() if n.startswith(k[:6])), LARGURAS['cnpj']))
    if n_vig > 1:                      # resto da divisão vai para a última sub-coluna
        ult = max(i for i, r in enumerate(rotulos) if norm(r).startswith('vigenc'))
        out[ult] += LARGURAS['vigencia'] - base * n_vig
    return out


def _unicos(valores):
    """Valores não vazios e distintos, na ordem em que aparecem."""
    out = []
    for v in valores:
        v = v.strip()
        if v and v not in out:
            out.append(v)
    return out


def _juntar(valores):
    """'2022' / '2022, 2023' (só para o CNPJ, quando um benefício tem mais de um)."""
    return ', '.join(_unicos(valores))


def _celulas_vigencia(vigs, n_vig):
    """Células de vigência de uma linha: quando há menos anos que colunas, o último ano ocupa as
    colunas que sobram (None = "mesclada com a célula à esquerda"), em vez de deixar célula vazia."""
    if not vigs:
        return [''] + [None] * (n_vig - 1)
    return list(vigs) + [None] * (n_vig - len(vigs))


def _montar(n_vig, resto, linhas, varias_vigencias=False):
    """Cabeçalho padrão: Item | Vigência(s) do FAP (1 ou n colunas, cabeçalho mesclado) | resto...
    `varias_vigencias`: a tabela traz mais de uma vigência (ex.: uma por linha) -> "Vigências do FAP", como nas
    petições reais (nas tabelas só de vigência, 11 de 14 com várias vigências usam o plural)."""
    plural = n_vig > 1 or varias_vigencias
    cab = [('Item', 1), ('Vigências do FAP' if plural else 'Vigência do FAP', n_vig)] + [(r, 1) for r in resto]
    rotulos = ['Item'] + ['Vigência'] * n_vig + list(resto)
    return TabelaPedido(cabecalho=cab, linhas=linhas, larguras=_larguras(rotulos, n_vig))


ACIMA = '<<acima>>'      # célula mesclada com a de cima (item dividido em uma linha por vigência)
FREQ_GRAV = 'Frequência e gravidade'
FREQ_GRAV_CUSTO = 'Frequência, gravidade e custo'


def indices_por_vigencia(vigs, anteriores):
    """Pedido de 60 dias. O benefício só fica no FAP por DUAS vigências (somando as do benefício anterior,
    que é o mesmo benefício para esse fim): as duas primeiras levam frequência e gravidade; da 3ª em diante
    leva também o custo. `anteriores`: anos de FAP do anterior (vazio se ele não está no FAP).
    Devolve [(ano, índices)] para os anos do benefício, em ordem."""
    todos = sorted(set(anteriores) | set(vigs))
    livres = set(todos[:2])
    return [(a, FREQ_GRAV if a in livres else FREQ_GRAV_CUSTO) for a in sorted(vigs)]


ROTULO_NTP_DO_BENEFICIO = 'NTP do benefício'      # cabeçalho da coluna do número na tese CAT NÃO VINCULADA


def tabela_beneficios(beneficios, ntp=False, indices_padrao=None, datas=False, regra_60_dias=False,
                      rotulo_beneficio='Benefício'):
    """Uma linha por benefício excluído (ordem da tabela da tese). None se não houver.
    Cada vigência do benefício vai em sua própria coluna, sob o cabeçalho mesclado "Vigências do FAP".
    `indices_padrao`: texto da coluna Índices quando a tabela da tese não a traz (60 dias); `None` =
    sem a coluna (a menos que a petição a traga), `''` = coluna presente e em branco.
    `datas`: acrescenta DIB e DCB (custo cessado)."""
    if not beneficios:
        return None
    com_tipo = any(b.especie for b in beneficios)     # tabela de NTP sem coluna "Tipo": sem a coluna no pedido
    com_indices = regra_60_dias or indices_padrao is not None or any(r['indices'] for b in beneficios for r in b.linhas)
    vigs = [_unicos(v for r in b.linhas for v in r['vigs']) for b in beneficios]
    n_vig = max([len(v) for v in vigs] + [1])
    linhas = []
    for k, (b, vg) in enumerate(zip(beneficios, vigs), 1):
        if regra_60_dias and vg:
            por_ano = indices_por_vigencia([a for a in vg if re.fullmatch(r'\d{4}', a)], b.vigs_anteriores)
            iguais = len({i for _, i in por_ano}) <= 1
            grupos = [(vg, por_ano[0][1] if por_ano else '')] if iguais else [([a], i) for a, i in por_ano]
        else:
            grupos = [(vg, next((r['indices'] for r in b.linhas if r['indices']), indices_padrao or ''))]
        for g, (anos, indices) in enumerate(grupos):   # índices diferentes entre as vigências: uma linha por ano
            linha = [str(k)] + _celulas_vigencia(anos, n_vig) + [_juntar(r['cnpj'] for r in b.linhas)]
            if com_tipo:
                linha.append(b.especie)
            if ntp:                               # coluna NTP entre Tipo e Benefício, como nos pedidos reais
                linha.append('NTP' if b.ntp else '-')
            linha.append(b.numero)
            if g:                                 # 2ª linha em diante do mesmo item: Item/CNPJ/Tipo/NTP/Benefício mesclados
                for j in [0] + list(range(1 + n_vig, len(linha))):
                    linha[j] = ACIMA
            if com_indices:
                linha.append(indices)
            if datas:
                linha += [b.dib or '', b.dcb or '']
            linhas.append(linha)
    resto = ['CNPJ'] + (['Tipo'] if com_tipo else []) + (['NTP'] if ntp else []) + [rotulo_beneficio] + (['Índices'] if com_indices else []) + \
            (['DIB', 'DCB'] if datas else [])
    return _montar(n_vig, resto, linhas)


def tabela_por_vigencia(secao):
    """Teses sem benefícios: Item | Vigência(s) do FAP | CNPJ [| Competências], da tabela da seção.

    Nas teses de correção (massa salarial, vínculos) a seção tem DUAS tabelas: a matriz de dados por
    mês ("Ano do insumo ...", uma linha por mês) e a tabela-resumo "Item | Vigência | CNPJ |
    Competências", cujo texto ("Todas as competências do ano de 2023", "De 01/2023 a 12/2023"...) é o
    que o pedido leva. A matriz NUNCA é usada como fonte."""
    candidatas = []
    for t in secao.tabelas:
        cab = [norm(c) for c in t.cabecalho]
        if ('item' in cab and 'cnpj' in cab and 'beneficio' not in cab and 'tipo' not in cab
                and any(c.startswith('vigenc') for c in cab) and not _eh_matriz(cab)):
            candidatas.append((t, cab))
    if not candidatas:
        return None
    com_competencias = [(t, cab) for t, cab in candidatas if any(c.startswith('competencias') for c in cab)]
    fontes = com_competencias or candidatas[:1]
    dados = []        # (cnpj, [anos], texto_da_competencia | None)
    for t, cab in fontes:
        i_vigs = [i for i, c in enumerate(cab) if c.startswith('vigenc')]
        i_cnpj = cab.index('cnpj')
        i_comp = next((i for i, c in enumerate(cab) if c.startswith('competencias')), None) if com_competencias else None
        for l in t.linhas[1:]:
            if len(l) == len(cab):
                dados.append((l[i_cnpj].strip(), _unicos(a for i in i_vigs for a in anos_da_celula(l[i])),
                              _normalizar_competencia(l[i_comp]) if i_comp is not None else None))
    if not dados:
        return None
    n_vig = max([len(v) for _, v, _ in dados] + [1])
    linhas = []
    for cnpj, vg, comp in dados:
        linha = [str(len(linhas) + 1)] + _celulas_vigencia(vg, n_vig) + [cnpj]
        if comp is not None:
            linha.append(comp)
        linhas.append(linha)
    return _montar(n_vig, ['CNPJ'] + (['Competências'] if com_competencias else []), linhas,
                   varias_vigencias=len({a for _, vg, _ in dados for a in vg}) > 1)


def _eh_matriz(cab):
    """Tabela de dados por mês ("Ano do insumo: 2023 ..."): não é a tabela-resumo do pedido."""
    return any(c.startswith('ano do insumo') for c in cab)


def _normalizar_competencia(texto):
    """"Competências de 01/2023 a 12/2023" -> "De 01/2023 a 12/2023" (como nos pedidos)."""
    texto = unicodedata.normalize('NFC', texto).replace('\xa0', ' ').strip()
    return re.sub(r'^Compet[êe]ncias\s+de\s+', 'De ', texto, flags=re.IGNORECASE)


def tabela_do_pedido(p):
    """Tabela do PedidoProposto (ou None). Recalculada a partir dos dados atuais do pedido."""
    if getattr(p, 'tabela_base', None) is not None:
        return p.tabela_base
    chave = p.dados['tese_key']
    return tabela_beneficios(
        p.beneficios, ntp=bool(p.dados.get('excluir_ntp')),
        indices_padrao=PADRAO_INDICES_60_DIAS if chave == 'restabelecimento_beneficio_anterior' else None,
        datas=chave == 'custo_cessado', regra_60_dias=chave == 'restabelecimento_beneficio_anterior',
        rotulo_beneficio=ROTULO_NTP_DO_BENEFICIO if chave in ('cat_nao_vinculada', 'ntp_duplicado') else 'Benefício')


def n_beneficios_na_tabela(tabela):
    """Quantidade de benefícios distintos na tabela (pela coluna Benefício), ou None."""
    rot = [t for t, s in tabela.cabecalho for _ in range(s)]
    rotulo = next((r for r in ('Benefício', ROTULO_NTP_DO_BENEFICIO) if r in rot), None)
    if rotulo is None:
        return None
    j = rot.index(rotulo)
    return len({l[j] for l in tabela.linhas if l[j] and l[j] != ACIMA})
