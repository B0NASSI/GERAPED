"""Extrai, do texto da seção "Pedidos" de uma petição já pronta, os pares (item, tese).

Serve só para MEDIR o detector: as petições do escritório já trazem os pedidos no formato do
GERAPED, então o texto do motivo (motivo_singular/plural de teses.py) revela a tese de cada item.
Teses de texto idêntico formam um grupo de equivalência (não dá para distingui-las pelo pedido).
"""
import re
import unicodedata

from .gerapedvendor import TESES, gerador_pedido


def norm(s):
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', s.lower()).strip()


def _padrao(texto):
    return re.escape(norm(texto)).replace(r'\{outro_beneficio\}', '.+?').replace('\\ ', ' ')


def _construir_padroes():
    pads = []   # (tese_key, regex)
    for key, t in TESES.items():
        frases = []
        for campo in ('motivo_singular', 'motivo_plural', 'motivo_fixo',
                      'texto_principal'):
            if campo in t:
                frases.append(t[campo])
        if t.get('tipo_clausula') == 'fixo':
            frases.append('bloqueio por taxa de rotatividade')
        if t.get('tipo_clausula') == 'custo_cessado':
            frases += list(gerador_pedido.CUSTO_CESSADO_MOTIVO.values())
        for f in frases:
            pads.append((key, re.compile(_padrao(f))))
    # As petições reais variam a redação dos motivos em relação ao teses.py atual (versões
    # antigas do modelo): padrões frouxos, restritos ao trecho do motivo do pedido.
    for key, rx in _VARIANTES:
        pads.append((key, re.compile(rx)))
    return pads


_VARIANTES = [
    ('ausencia_nexo_causal_concausalidade', r'nexo causal e (?:o )?(?:de )?concausalidade'),
    ('ausencia_nexo_causal_concausalidade', r'ausencia de nexo causal'),
    ('concomitancia_outro_beneficio', r'usufruia de (?:outro )?beneficio'),
    ('dib_igual_dcb', r'mesma data de inicio \(dib\) e cessacao \(dcb\)'),
    ('natureza_previdenciaria', r'natureza previdenciaria'),
    ('acidente_sem_relacao_empresa', r'nao (?:sao |tem )?(?:relacionad\w+|relacao) (?:com )?a empresa autora'),
    ('acidente_outro_estabelecimento', r'ocorridos? em outros? estabelecimentos?'),
    ('acidente_anterior_2007', r'(?:anteriores? a|antes de) abril de 2007'),
    ('restabelecimento_beneficio_anterior', r'restabelecimentos? de beneficios? anteriores?'),
    ('acidente_trajeto', r'acidentes? de trajeto'),
    ('beneficio_cancelado_revogado', r'revogacao'),
    ('sobreposicao_concomitancia_beneficios', r'sobreposicao'),
]

_PADROES = _construir_padroes()

# teses que o texto do pedido não distingue entre si
GRUPOS_EQUIV = [
    {'convertido', 'natureza_previdenciaria'},
    {'ntp_duplicado', 'cat_nao_vinculada'},
]


def equivalentes(key):
    for g in GRUPOS_EQUIV:
        if key in g:
            return set(g)
    return {key}


_RE_ITEM = re.compile(r'item\s+[“"]?(\d+(?:\.\d+)*)[”"]?\s+da\s+peti[cç][aã]o\s+inicial', re.I)


def classificar_segmento(texto):
    """tese(s) cujo motivo aparece no trecho; devolve o conjunto de equivalentes da mais longa."""
    t = norm(texto)
    melhor = None
    for key, rx in _PADROES:
        m = None
        for m in rx.finditer(t):
            pass
        if m and (melhor is None or (m.end() - m.start()) > melhor[1]):
            melhor = (key, m.end() - m.start())
    return equivalentes(melhor[0]) if melhor else None


def extrair_gabarito(peticao):
    """Lista de dicts: {'item', 'teses': set, 'papel': 'principal'|'subsidiaria'}."""
    achados = []
    secoes = peticao.secoes
    idx = next((i for i, s in enumerate(secoes) if norm(s.titulo) == 'pedidos'), None)
    if idx is None:
        return achados
    for s in secoes[idx:]:
        for par in s.paragrafos:
            texto = par.texto
            if norm(texto).startswith('para comprovar'):
                continue                       # pedido de prova documental, não de exclusão
            marcas = list(_RE_ITEM.finditer(texto))
            if not marcas:
                continue
            pos_sub = norm(texto).find('subsidiariamente')
            inicio = 0
            for m in marcas:
                seg = texto[inicio:m.start()]
                inicio = m.end()
                teses = classificar_segmento(seg)
                papel = 'subsidiaria' if pos_sub != -1 and len(norm(texto[:m.start()])) > pos_sub else 'principal'
                achados.append({'item': m.group(1), 'teses': teses, 'papel': papel, **_detalhes(seg)})
    return achados


_RX_QTD = re.compile(r'exclusao de (\d+) \(')
_RX_ESPECIES = re.compile(r'especies? (b\d\d(?:(?:, | e )b\d\d)*)')
_RX_NUMERADO = re.compile(r'\bb(\d\d) no (\d+)')


def _detalhes(seg):
    """quantidade/espécies (pedido principal) e benefícios numerados (subsidiário) do trecho."""
    t = norm(seg)
    q = _RX_QTD.search(t)
    e = _RX_ESPECIES.search(t)
    return {
        'quantidade': int(q.group(1)) if q else None,
        'especies': [x.upper() for x in re.findall(r'b\d\d', e.group(1))] if e else None,
        'numeros': [('B' + a, n) for a, n in _RX_NUMERADO.findall(t)],
        'indice_singular': ('base de calculo do indice do fap' in t) if 'base de calculo d' in t else None,
    }
