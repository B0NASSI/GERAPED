"""Detecção de teses por seção — 100% local (regras/heurísticas), sem rede.

`Detector` é a interface: qualquer outro método (futuro) só precisa implementar
`detectar(peticao) -> ResultadoDeteccao`. Nada é enviado a serviços externos.

Princípio: nunca inventar certeza. Cada detecção traz confiança (alta/média/baixa) e a
evidência (o trecho curto que casou); o que não casa vai para "não classificadas", e teses
com palavras-chave no texto mas sem seção própria vão para "possíveis não detectadas".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Protocol

from .gabarito import norm
from .leitor import Peticao, Secao

ALTA, MEDIA, BAIXA = 'alta', 'media', 'baixa'

# (tese_key, regex no TÍTULO normalizado, peso).  Títulos reais do escritório são formulaicos.
REGRAS_TITULO = [
    ('acidente_trajeto', r'acidentes? de trajeto', 3),
    ('restabelecimento_beneficio_anterior', r'menos de \d+ dias entre a data da cessacao', 3),
    ('restabelecimento_beneficio_anterior', r'restabelecimentos? de beneficios?', 3),
    ('acidente_outro_estabelecimento', r'sem vinculo com os estabelecimentos', 3),
    ('acidente_outro_estabelecimento', r'(?:ocorridos?|ocorrencia) em outros? estabelecimentos?', 3),
    ('acidente_outro_estabelecimento', r'sem vinculo com .{0,40}na data d\w+ acidentes?', 4),
    ('ausencia_nexo_causal_concausalidade', r'ausencia de nexo causal', 3),
    ('ausencia_nexo_causal_concausalidade', r'atribuicao indevida de nexo tecnico', 3),
    ('ausencia_nexo_causal_concausalidade', r'concausalidade', 2),
    ('acidente_sem_relacao_empresa', r'nao relacionad\w+ (?:a|com) (?:a )?empresa autora', 4),
    ('natureza_previdenciaria', r'erro ao atribuir a natureza acidentaria', 4),
    ('natureza_previdenciaria', r'natureza previdenciaria', 3),
    ('convertido', r'incapacidade temporaria previdenciari[oa]', 3),
    ('natureza_previdenciaria', r'auxilio.acidente previdenciari[oa]', 3),
    ('cat_nao_vinculada', r'\bntp\b', 2),
    ('convertido', r'convertid[oa]s?', 3),
    ('concomitancia_outro_beneficio', r'concomitante', 3),
    ('concomitancia_outro_beneficio', r'usufruia de (?:outro )?beneficio', 3),
    ('acidente_anterior_2007', r'(?:antes de|anteriores? a) abril de 2007', 3),
    ('sobreposicao_concomitancia_beneficios', r'sobreposicao', 4),
    ('ntp_duplicado', r'\bntp\b.*(?:duplicidade|duplicad)', 3),
    ('ntp_duplicado', r'nexos? tecnicos?(?: previdenciari\w+)?.*duplicad', 4),
    ('cat_nao_vinculada', r'nexos? tecnicos? contabilizados? de forma indevida', 4),
    ('computado_duas_vezes', r'computad\w+ duas vezes', 4),
    ('cat_duplicada', r'\bcat\b.*duplicidade|comunicacoes? de acidente.*duplicidade', 3),
    ('cat_nao_vinculada', r'(?:cat nao vinculada|sem (?:comunicacao de acidente|cat) vinculada)', 3),
    ('dib_igual_dcb', r'dib\s*=\s*dcb', 4),
    ('dib_igual_dcb', r'mesma data de inicio \(dib\) e cessacao', 3),
    ('beneficio_cancelado_revogado', r'revogad\w+|revogacao|cancelad\w+', 2),
    ('erro_implantacao', r'(?:erro (?:de|na) implantacao|implantad\w+ de forma equivocada|'
                         r'divergencia.*implantado)', 3),
    ('rotatividade', r'rotatividade', 4),
    ('erro_massa_salarial', r'massa salarial', 4),
    ('erro_vinculos', r'numero medio de vinculos', 4),
    ('custo_cessado', r'(?:apuracao do indice de custo|custo cessado|indice de custo)', 4),
    ('prescricao_quinquenal', r'prescricao quinquenal', 4),
    ('contestacao_administrativa', r'contestacao administrativa', 4),
]

# Palavras-chave no CORPO (fraco: só gera média/baixa, nunca alta).
REGRAS_CORPO = [
    ('acidente_trajeto', r'acidentes? de trajeto|in itinere'),
    ('restabelecimento_beneficio_anterior', r'menos de (?:60|sessenta) dias|restabelecimento'),
    ('acidente_outro_estabelecimento', r'outros? estabelecimentos?'),
    ('ausencia_nexo_causal_concausalidade', r'nexo causal'),
    ('ausencia_nexo_causal_concausalidade', r'concausalidade'),
    ('acidente_sem_relacao_empresa', r'nao (?:tem|possui) relacao com a empresa|nao relacionad\w+ a empresa autora'),
    ('natureza_previdenciaria', r'natureza previdenciaria|natureza acidentaria'),
    ('convertido', r'convertid\w+|\bb31\b'),
    ('concomitancia_outro_beneficio', r'concomitan\w+|usufruia'),
    ('acidente_anterior_2007', r'abril de 2007|pre-?fap'),
    ('sobreposicao_concomitancia_beneficios', r'sobreposicao'),
    ('dib_igual_dcb', r'\bdib\b.*\bdcb\b.*(?:mesma|igual)|dib\s*=\s*dcb'),
    ('beneficio_cancelado_revogado', r'revogacao|revogad\w+'),
    ('erro_implantacao', r'implantad\w+ de forma equivocada|erro de implantacao'),
    ('rotatividade', r'rotatividade'),
    ('erro_massa_salarial', r'massa salarial'),
    ('erro_vinculos', r'numero medio de vinculos'),
    ('custo_cessado', r'indice de custo|custo cessado'),
    ('prescricao_quinquenal', r'prescricao quinquenal|quinquenio'),
    ('contestacao_administrativa', r'contestacao administrativa|efeito suspensivo'),
]

# Seções estruturais fixas (não argumentam tese; ignoradas na lista de "não classificadas").
TITULOS_ESTRUTURAIS = {
    'objeto da acao', 'sintese fatica', 'utilizacao da via judicial', 'comprovacao das alegacoes',
    'repeticao do indebito', 'sigilo dos autos', 'pedidos',
}


@dataclass
class Deteccao:
    secao_numero: Optional[str]
    secao_titulo: str
    tese_key: str
    confianca: str                       # alta | media | baixa
    evidencia: str                       # trecho curto que casou (nunca a seção inteira)
    origem: str                          # 'titulo' | 'corpo' | 'herdada'
    candidatas: list = field(default_factory=list)   # [(tese_key, pontos)] em ordem


@dataclass
class ResultadoDeteccao:
    deteccoes: list
    nao_classificadas: list              # [(numero, titulo)] seções que não são estruturais e não casaram
    possiveis_nao_detectadas: list       # [(tese_key, n_ocorrencias, evidencia)]
    estruturais: list


class Detector(Protocol):
    def detectar(self, peticao: Peticao) -> ResultadoDeteccao: ...


def _trecho(texto, m, largura=70):
    ini = max(0, m.start() - 10)
    return re.sub(r'\s+', ' ', texto[ini:m.end() + 10]).strip()[:largura]


def _pontuar(regras, texto, com_peso):
    pontos, evid = {}, {}
    for regra in regras:
        key, rx = regra[0], regra[1]
        peso = regra[2] if com_peso else 1
        m = re.search(rx, texto)
        if m:
            pontos[key] = pontos.get(key, 0) + peso
            evid.setdefault(key, m)
    return pontos, evid


class DetectorRegras:
    """Detector por regras de título e palavras-chave (implementa `Detector`)."""

    def __init__(self, max_paragrafos_corpo=25):
        self.max_paragrafos = max_paragrafos_corpo

    # -- por seção --
    def _classificar_secao(self, sec: Secao):
        titulo = norm(sec.titulo)
        pontos, evid = _pontuar(REGRAS_TITULO, titulo, True)
        if pontos:
            ordem = sorted(pontos.items(), key=lambda kv: -kv[1])
            melhor, p1 = ordem[0]
            empate = len(ordem) > 1 and ordem[1][1] == p1
            conf = MEDIA if empate or p1 < 3 else ALTA
            m = evid[melhor]
            return melhor, conf, f'título: "{_trecho(titulo, m)}"', 'titulo', ordem
        corpo = norm(' '.join(p.texto for p in sec.paragrafos[:self.max_paragrafos]))
        pontos, evid = _pontuar(REGRAS_CORPO, corpo, False)
        if pontos:
            ordem = sorted(pontos.items(), key=lambda kv: -kv[1])
            melhor, p1 = ordem[0]
            empate = len(ordem) > 1 and ordem[1][1] == p1
            conf = MEDIA if p1 >= 2 and not empate else BAIXA
            return melhor, conf, f'corpo: "{_trecho(corpo, evid[melhor])}"', 'corpo', ordem
        return None

    def detectar(self, peticao: Peticao) -> ResultadoDeteccao:
        deteccoes, nao_class, estrut = [], [], []
        por_numero = {}
        for sec in peticao.secoes:
            if sec.nivel == 0:
                continue
            if norm(sec.titulo) in TITULOS_ESTRUTURAIS:
                estrut.append((sec.numero, sec.titulo))
                continue
            r = self._classificar_secao(sec)
            if r is None and sec.numero and '.' in sec.numero:
                pai = sec.numero.rsplit('.', 1)[0]
                if pai in por_numero:
                    d = por_numero[pai]
                    r = (d.tese_key, MEDIA, f'herdada da seção {pai}', 'herdada', [(d.tese_key, 0)])
            if r is None:
                nao_class.append((sec.numero, sec.titulo))
                continue
            tese, conf, evid, origem, ordem = r
            d = Deteccao(sec.numero, sec.titulo, tese, conf, evid, origem, ordem)
            deteccoes.append(d)
            if sec.numero:
                por_numero[sec.numero] = d

        # teses com palavras-chave no documento, mas sem nenhuma seção detectada
        achadas = {d.tese_key for d in deteccoes}
        corpo_todo = norm(' '.join(p.texto for s in peticao.secoes
                                   if norm(s.titulo) not in TITULOS_ESTRUTURAIS and s.nivel > 0
                                   for p in s.paragrafos))
        possiveis = []
        for key, rx in REGRAS_CORPO:
            if key in achadas or any(k == key for k, *_ in possiveis):
                continue
            ms = list(re.finditer(rx, corpo_todo))
            if ms:
                possiveis.append((key, len(ms), _trecho(corpo_todo, ms[0])))
        return ResultadoDeteccao(deteccoes, nao_class, possiveis, estrut)
