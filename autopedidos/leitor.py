"""Leitura de petição inicial (.docx) -> estrutura: seções numeradas, parágrafos e tabelas.

Pontos de Word tratados aqui (ver tests/test_leitor.py):
  * numeração automática (numPr direto ou herdado do estilo): o número "5.1" é CALCULADO a
    partir de numbering.xml, pois não está no texto;
  * tabelas com células mescladas (gridSpan/vMerge), aninhadas e continuadas em outra tabela
    com o cabeçalho repetido;
  * caixas de texto, cabeçalho/rodapé, notas de rodapé e controle de alterações (lê o texto
    "como exibido": inserções entram, exclusões não; avisa se houver revisões pendentes);
  * runs quebrados: o texto de um parágrafo é sempre a concatenação de todos os runs.

Somente .docx. Nenhum conteúdo sai do computador.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from typing import Optional

import docx
from docx.oxml.ns import qn

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
MC = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
_FALLBACK = f'{{{MC}}}Fallback'


# ───────────────────────────── estruturas ─────────────────────────────

@dataclass
class Paragrafo:
    texto: str
    estilo: str = ''
    rotulo: Optional[str] = None      # numeração automática da lista, ex.: "a.", "5.1."
    caixa_de_texto: bool = False      # veio de uma caixa de texto


@dataclass
class Tabela:
    linhas: list                      # list[list[str]]; mescladas repetem o valor nas colunas cobertas
    continuada: bool = False          # juntou outra(s) tabela(s) com o mesmo cabeçalho

    @property
    def cabecalho(self):
        return self.linhas[0] if self.linhas else []

    @property
    def n_linhas(self):
        return len(self.linhas)

    @property
    def n_colunas(self):
        return max((len(l) for l in self.linhas), default=0)


@dataclass
class Secao:
    numero: Optional[str]             # "5", "5.1" (None = sem numeração / preâmbulo)
    nivel: int                        # 1 = título principal; 0 = preâmbulo
    titulo: str
    estilo: str = ''
    origem_numero: str = ''           # 'auto' | 'digitada' | ''
    blocos: list = field(default_factory=list)   # Paragrafo | Tabela, na ordem do documento

    @property
    def paragrafos(self):
        return [b for b in self.blocos if isinstance(b, Paragrafo)]

    @property
    def tabelas(self):
        return [b for b in self.blocos if isinstance(b, Tabela)]

    @property
    def texto(self):
        return '\n'.join(p.texto for p in self.paragrafos if p.texto)


@dataclass
class Peticao:
    secoes: list
    sumario: list                     # parágrafos de sumário (TOC), fora das seções
    cabecalhos_rodapes: list
    notas_rodape: list
    avisos: list

    def secao_por_numero(self, numero):
        return next((s for s in self.secoes if s.numero == numero), None)

    @property
    def tabelas(self):
        return [t for s in self.secoes for t in s.tabelas]


# ───────────────────────────── numeração ─────────────────────────────

def _romano(n):
    pares = [(1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'), (90, 'XC'),
             (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')]
    out = ''
    for v, s in pares:
        while n >= v:
            out += s
            n -= v
    return out


def _letras(n):
    out = ''
    while n > 0:
        n, r = divmod(n - 1, 26)
        out = chr(97 + r) + out
    return out


def _formatar(valor, fmt):
    if fmt == 'decimal':
        return str(valor)
    if fmt == 'decimalZero':
        return f'{valor:02d}'
    if fmt == 'lowerLetter':
        return _letras(valor)
    if fmt == 'upperLetter':
        return _letras(valor).upper()
    if fmt == 'lowerRoman':
        return _romano(valor).lower()
    if fmt == 'upperRoman':
        return _romano(valor)
    if fmt in ('bullet', 'none'):
        return ''
    return str(valor)


def _val(el, tag, default=None):
    if el is None:
        return default
    f = el.find(qn(tag))
    return f.get(qn('w:val')) if f is not None else default


class _Numeracao:
    """Calcula o rótulo de cada parágrafo numerado, em ordem de documento."""

    def __init__(self, numbering_el):
        self.niveis = {}     # abstractNumId -> {ilvl: (start, fmt, lvlText)}
        self.num_abs = {}    # numId -> abstractNumId
        self.num_start = {}  # (numId, ilvl) -> startOverride
        self.contadores = {}
        if numbering_el is None:
            return
        for a in numbering_el.findall(qn('w:abstractNum')):
            aid = a.get(qn('w:abstractNumId'))
            lv = {}
            for l in a.findall(qn('w:lvl')):
                lv[int(l.get(qn('w:ilvl')))] = (
                    int(_val(l, 'w:start', '1')), _val(l, 'w:numFmt', 'decimal'), _val(l, 'w:lvlText', ''))
            self.niveis[aid] = lv
        for n in numbering_el.findall(qn('w:num')):
            nid = n.get(qn('w:numId'))
            self.num_abs[nid] = _val(n, 'w:abstractNumId')
            for o in n.findall(qn('w:lvlOverride')):
                s = o.find(qn('w:startOverride'))
                if s is not None:
                    self.num_start[(nid, int(o.get(qn('w:ilvl'))))] = int(s.get(qn('w:val')))

    def proximo(self, num_id, ilvl):
        """Avança o contador e devolve (rotulo, numero_completo_sem_pontuacao_final)."""
        if num_id in (None, '0'):
            return None
        aid = self.num_abs.get(num_id)
        lv = self.niveis.get(aid)
        if not lv or ilvl not in lv:
            return None
        chave = aid
        cont = self.contadores.setdefault(chave, {})
        inicio = lambda i: self.num_start.get((num_id, i), lv.get(i, (1,))[0])
        cont[ilvl] = (inicio(ilvl) - 1 if ilvl not in cont else cont[ilvl]) + 1
        for i in [k for k in cont if k > ilvl]:
            del cont[i]
        _, fmt, texto = lv[ilvl]
        if fmt in ('bullet', 'none') or not texto:
            return None

        def sub(m):
            i = int(m.group(1)) - 1
            if i not in lv:
                return ''
            v = cont.get(i, inicio(i))
            return _formatar(v, lv[i][1])
        return re.sub(r'%(\d)', sub, texto)


# ───────────────────────────── estilos ─────────────────────────────

class _Estilos:
    def __init__(self, styles_el):
        self.por_id = {}
        if styles_el is None:
            return
        for s in styles_el.findall(qn('w:style')):
            self.por_id[s.get(qn('w:styleId'))] = s

    def nome(self, sid):
        s = self.por_id.get(sid)
        return _val(s, 'w:name', sid or '') if s is not None else (sid or '')

    def _cadeia(self, sid):
        vistos = set()
        while sid and sid not in vistos and sid in self.por_id:
            vistos.add(sid)
            yield self.por_id[sid]
            sid = _val(self.por_id[sid], 'w:basedOn')

    def numpr(self, sid):
        """(numId, ilvl) herdado do estilo (percorrendo basedOn)."""
        num_id = ilvl = None
        for s in self._cadeia(sid):
            ppr = s.find(qn('w:pPr'))
            np_ = ppr.find(qn('w:numPr')) if ppr is not None else None
            if np_ is not None:
                if num_id is None:
                    num_id = _val(np_, 'w:numId')
                if ilvl is None:
                    ilvl = _val(np_, 'w:ilvl')
        return num_id, ilvl

    def outline(self, sid):
        for s in self._cadeia(sid):
            ppr = s.find(qn('w:pPr'))
            v = _val(ppr, 'w:outlineLvl') if ppr is not None else None
            if v is not None:
                return int(v)
        return None


_RE_NOME_TITULO = re.compile(r'^(?:heading|t[ií]tulo)\s*(\d)$', re.I)
_RE_NUM_DIGITADO = re.compile(r'^\s*(\d+(?:\.\d+)*)\s*[.)\-–]?\s+(?=\S)')


# ───────────────────────────── leitura de texto ─────────────────────────────

def _texto_e_caixas(p):
    """Texto exibido de um w:p (concatena todos os runs) + textos de caixas de texto."""
    partes, caixas = [], []

    def visita(el):
        for filho in el:
            tag = filho.tag
            if tag in (qn('w:del'), qn('w:moveFrom'), _FALLBACK):
                continue
            if tag == qn('w:txbxContent'):
                for pp in filho.iter(qn('w:p')):
                    t, _ = _texto_e_caixas(pp)
                    if t.strip():
                        caixas.append(t)
                continue
            if tag == qn('w:t'):
                partes.append(filho.text or '')
            elif tag == qn('w:tab'):
                partes.append('\t')
            elif tag in (qn('w:br'), qn('w:cr')):
                partes.append('\n')
            elif tag == qn('w:noBreakHyphen'):
                partes.append('-')
            elif tag == qn('w:p') and el is not p:
                continue
            else:
                visita(filho)
    visita(p)
    return ''.join(partes), caixas


def _texto_celula(tc):
    textos = []
    for p in tc.iter(qn('w:p')):
        t, _ = _texto_e_caixas(p)
        textos.append(t.strip())
    return '\n'.join(t for t in textos if t)


def _ler_tabela(tbl):
    """Grade de texto: gridSpan repete o valor nas colunas cobertas; vMerge herda o de cima."""
    linhas = []
    for tr in tbl.findall(qn('w:tr')):
        linha = []
        for tc in tr.findall(qn('w:tc')):
            tcpr = tc.find(qn('w:tcPr'))
            span = int(_val(tcpr, 'w:gridSpan', '1')) if tcpr is not None else 1
            vm = tcpr.find(qn('w:vMerge')) if tcpr is not None else None
            if vm is not None and vm.get(qn('w:val')) in (None, 'continue'):
                col = len(linha)
                texto = linhas[-1][col] if linhas and col < len(linhas[-1]) else ''
            else:
                texto = _texto_celula(tc)
            linha.extend([texto] * span)
        linhas.append(linha)
    return linhas


def _norm_linha(linha):
    return [re.sub(r'\s+', ' ', c).strip().lower() for c in linha]


_RX_ESPECIE_CELULA = re.compile(r'^[Bb]\s?\d{2}$')


def _continuacao_sem_cabecalho(anterior, linhas):
    """True se `linhas` é a continuação de `anterior` sem cabeçalho repetido: a 1ª linha já é um benefício
    (célula com espécie "B91") e o "Item" dela segue o da última linha da tabela anterior."""
    if not linhas or len(anterior.linhas) < 2:
        return False
    if not any(_RX_ESPECIE_CELULA.match(c.strip()) for c in linhas[0]):
        return False
    ult, nova = anterior.linhas[-1][0].strip(), linhas[0][0].strip()
    return ult.isdigit() and nova.isdigit() and int(nova) == int(ult) + 1


def _remove_cabecalhos_repetidos(linhas):
    if len(linhas) < 2:
        return linhas, False
    cab = _norm_linha(linhas[0])
    saida, removeu = [linhas[0]], False
    for l in linhas[1:]:
        if _norm_linha(l) == cab and any(cab):
            removeu = True
            continue
        saida.append(l)
    return saida, removeu


# ───────────────────────────── leitor principal ─────────────────────────────

def _partes_xml(caminho):
    """notas de rodapé e revisões não dependem do python-docx: lê direto do zip."""
    with zipfile.ZipFile(caminho) as z:
        nomes = z.namelist()
        return {n: z.read(n) for n in nomes
                if n.startswith('word/') and n.endswith('.xml') and ('footnotes' in n or 'endnotes' in n)}


def ler_peticao(caminho) -> Peticao:
    d = docx.Document(caminho)
    body = d.element.body
    estilos = _Estilos(d.styles.element)
    try:
        numbering_el = d.part.numbering_part.element
    except Exception:
        numbering_el = None
    numeracao = _Numeracao(numbering_el)

    avisos = []
    n_ins = len(body.findall(f'.//{qn("w:ins")}'))
    n_del = len(body.findall(f'.//{qn("w:del")}')) + len(body.findall(f'.//{qn("w:moveFrom")}'))
    if n_ins or n_del:
        avisos.append(f'Há revisões pendentes (controle de alterações): {n_ins} inserções, {n_del} exclusões. '
                      'O texto foi lido como exibido (inserções incluídas, exclusões ignoradas).')

    secoes = [Secao(numero=None, nivel=0, titulo='')]
    sumario = []
    ultima_tabela_idx = {'sec': None, 'bloco': None, 'vazios': True}

    def info_paragrafo(p):
        ppr = p.find(qn('w:pPr'))
        sid = _val(ppr, 'w:pStyle') if ppr is not None else None
        nome = estilos.nome(sid) if sid else 'Normal'
        np_ = ppr.find(qn('w:numPr')) if ppr is not None else None
        num_id = ilvl = None
        if np_ is not None:
            num_id, ilvl = _val(np_, 'w:numId'), _val(np_, 'w:ilvl')
        e_num, e_ilvl = estilos.numpr(sid) if sid else (None, None)
        num_id = num_id if num_id is not None else e_num
        ilvl = ilvl if ilvl is not None else e_ilvl
        outline = _val(ppr, 'w:outlineLvl') if ppr is not None else None
        outline = int(outline) if outline is not None else (estilos.outline(sid) if sid else None)
        if outline is None:
            m = _RE_NOME_TITULO.match(nome)
            if m:
                outline = int(m.group(1)) - 1
        return nome, num_id, int(ilvl or 0), outline

    def processa_paragrafo(p):
        nome, num_id, ilvl, outline = info_paragrafo(p)
        rotulo = numeracao.proximo(num_id, ilvl) if num_id else None
        texto, caixas = _texto_e_caixas(p)
        texto = texto.strip()

        if nome.lower().startswith(('toc', 'sumário', 'sumario', 'table of')):
            if texto:
                sumario.append(texto)
            return
        e_titulo = outline is not None and outline <= 8 and texto
        if e_titulo:
            numero, origem = None, ''
            if rotulo:
                numero, origem = rotulo.strip().rstrip('.)').strip(), 'auto'
            else:
                m = _RE_NUM_DIGITADO.match(texto)
                if m:
                    numero, origem = m.group(1), 'digitada'
                    texto = texto[m.end():].strip()
            secoes.append(Secao(numero=numero, nivel=outline + 1, titulo=texto, estilo=nome, origem_numero=origem))
            ultima_tabela_idx['vazios'] = False
        elif texto:
            secoes[-1].blocos.append(Paragrafo(texto=texto, estilo=nome, rotulo=rotulo))
            ultima_tabela_idx['vazios'] = False
        for c in caixas:
            secoes[-1].blocos.append(Paragrafo(texto=c.strip(), estilo='(caixa de texto)', caixa_de_texto=True))
            ultima_tabela_idx['vazios'] = False

    def processa_tabela(tbl):
        linhas = _ler_tabela(tbl)
        linhas, _ = _remove_cabecalhos_repetidos(linhas)
        sec = secoes[-1]
        # continuação: tabela imediatamente após outra (sem texto no meio) com o mesmo cabeçalho
        if (ultima_tabela_idx['vazios'] and ultima_tabela_idx['sec'] is sec and sec.blocos
                and isinstance(sec.blocos[-1], Tabela) and linhas
                and _norm_linha(linhas[0]) == _norm_linha(sec.blocos[-1].cabecalho) and any(_norm_linha(linhas[0]))):
            sec.blocos[-1].linhas.extend(linhas[1:])
            sec.blocos[-1].continuada = True
        elif (ultima_tabela_idx['vazios'] and ultima_tabela_idx['sec'] is sec and sec.blocos
                and isinstance(sec.blocos[-1], Tabela) and _continuacao_sem_cabecalho(sec.blocos[-1], linhas)):
            # a tabela continua na página seguinte SEM repetir o cabeçalho: a 1ª linha já é um benefício
            sec.blocos[-1].linhas.extend(linhas)
            sec.blocos[-1].continuada = True
        else:
            sec.blocos.append(Tabela(linhas=linhas))
        ultima_tabela_idx['sec'] = sec
        ultima_tabela_idx['vazios'] = True

    def percorre(container):
        for el in container:
            if el.tag == qn('w:p'):
                processa_paragrafo(el)
            elif el.tag == qn('w:tbl'):
                processa_tabela(el)
            elif el.tag == qn('w:sdt'):
                c = el.find(qn('w:sdtContent'))
                if c is not None:
                    percorre(c)
    percorre(body)

    # cabeçalhos/rodapés (texto único)
    vistos, hf = set(), []
    for s in d.sections:
        for parte in (s.header, s.first_page_header, s.even_page_header,
                      s.footer, s.first_page_footer, s.even_page_footer):
            try:
                for p in parte.paragraphs:
                    t = p.text.strip()
                    if t and t not in vistos:
                        vistos.add(t)
                        hf.append(t)
            except Exception:
                pass

    # notas de rodapé / fim
    from lxml import etree
    notas = []
    for xml in _partes_xml(caminho).values():
        raiz = etree.fromstring(xml)
        for fn in list(raiz.findall(qn('w:footnote'))) + list(raiz.findall(qn('w:endnote'))):
            if fn.get(qn('w:type')) in ('separator', 'continuationSeparator', 'continuationNotice'):
                continue
            t = ' '.join(_texto_e_caixas(p)[0] for p in fn.iter(qn('w:p'))).strip()
            if t:
                notas.append(t)

    if not any(s.nivel > 0 for s in secoes):
        avisos.append('Nenhum título (Heading/outline) encontrado: não foi possível dividir em seções.')
    return Peticao(secoes=secoes, sumario=sumario, cabecalhos_rodapes=hf, notas_rodape=notas, avisos=avisos)
