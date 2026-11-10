"""Monta os pedidos (formato do GERAPED v1.3.1) a partir das teses detectadas + tabelas de benefícios.

Regra de ouro: caso ambíguo vira PENDÊNCIA explícita, não palpite. Todo pedido proposto é
rodado em `validacao.py` do vendor e em `gerar_documento`; falhas viram pendências.

Estrutura observada nas petições do escritório (ver relatório): cada seção de tese que tem
tabela de benefícios gera um pedido PRINCIPAL com todos os benefícios dela; e uma seção que
repete benefícios de uma seção ANTERIOR entra também como tese SUBSIDIÁRIA do pedido daquela
(o principal vem sempre antes no documento). Isso é uma inferência: vai em `notas`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .beneficios import _data_ordenavel, eh_tabela_de_beneficios, ler_beneficios, vigencias_e_cnpjs_da_tabela
from .detector import ALTA, ResultadoDeteccao
from .gabarito import norm
from .gerapedvendor import PARAMETROS_TESE, TESES, gerador_pedido, teses as _teses, validacao
from .leitor import Peticao, Secao
from .tabelas import TESES_POR_VIGENCIA, n_beneficios_na_tabela, tabela_do_pedido, tabela_por_vigencia

ORDEM_ESPECIES = list(_teses.TIPO_BENEFICIO_POR_ESPECIE)       # B91 B92 B93 B94 B31 B36
# teses cuja tabela lista, para cada caso, DOIS benefícios (o anterior/outro e o excluído)
TESES_DE_PAR = {'restabelecimento_beneficio_anterior', 'concomitancia_outro_beneficio',
                'sobreposicao_concomitancia_beneficios'}


# teses em que o pedido exclui o NTP do benefício (não o benefício): sem espécie no texto nem na tabela
TESES_DE_NTP = {'cat_nao_vinculada', 'ntp_duplicado'}


@dataclass
class PedidoProposto:
    dados: dict                      # exatamente o formato de BlocoPedido.obter_dados (GERAPED)
    secao_numero: str
    tese_nome: str
    confianca: str
    evidencia: str
    beneficios: list = field(default_factory=list)
    pendencias: list = field(default_factory=list)   # exigem decisão/conferência do usuário
    notas: list = field(default_factory=list)        # inferências informativas
    valido: bool = True              # passou em validacao.py + gerar_documento
    incluir_tabela: bool = True      # tabela do pedido (ver tabelas.py) logo após o texto
    tabela_base: object = None       # TabelaPedido fixa (teses por vigência); senão sai dos benefícios
    logica: list = field(default_factory=list)       # passo a passo do porquê de cada decisão (log de análise)


@dataclass
class Proposta:
    pedidos: list
    pendencias_globais: list = field(default_factory=list)


# ───────────────────────────── utilitários ─────────────────────────────

def _ordenar_especies(especies):
    # B31 vem antes das demais ("espécies B31 e B91"); o resto segue ORDEM_ESPECIES
    chave = lambda e: (-1 if e == 'B31' else ORDEM_ESPECIES.index(e) if e in ORDEM_ESPECIES else 99, e)
    return sorted(set(especies), key=chave)


def _formatar_vigencias(anos):
    anos = sorted(set(anos))
    if len(anos) <= 1:
        return anos[0] if anos else ''
    return ', '.join(anos[:-1]) + f' e {anos[-1]}'


def _texto_norm(sec: Secao, n=12):
    return norm(sec.titulo + ' ' + ' '.join(p.texto for p in sec.paragrafos[:n]))


_OUTRO_POR_ESPECIE = {'B31': 'auxilio_incapacidade', 'B91': 'auxilio_incapacidade',
                      'B36': 'auxilio_acidente', 'B94': 'auxilio_acidente'}


def _parametro(tese_key, sec: Secao, anteriores=()):
    """parametro_valor (outro benefício / tipo de custo cessado) ou None se indeterminado."""
    titulo = norm(sec.titulo)
    corpo = _texto_norm(sec)
    if tese_key == 'concomitancia_outro_beneficio' and anteriores:
        # espécie do benefício anterior na tabela: B4x/B32/B57... = aposentadoria
        esp = anteriores[0]
        return _OUTRO_POR_ESPECIE.get(esp, 'aposentadoria' if esp not in ORDEM_ESPECIES or esp == 'B32' else None)
    if tese_key == 'concomitancia_outro_beneficio':
        for texto in (titulo, corpo):
            m = re.search(r'(?:usufruia de|concomitante de .*?com|com) (?:outro )?(?:beneficio de )?'
                          r'(aposentadoria|auxilio.acidente|auxilio por incapacidade|auxilio.doenca)', texto)
            if m:
                g = m.group(1)
                if g.startswith('aposentadoria'):
                    return 'aposentadoria'
                if 'acidente' in g:
                    return 'auxilio_acidente'
                return 'auxilio_incapacidade'
        return None
    if tese_key == 'custo_cessado':
        if 'obito' in titulo or ('obito' in corpo and 'aposentadoria' not in corpo):
            return 'obito'
        if 'aposentadoria' in titulo or 'aposentadoria' in corpo:
            return 'aposentadoria'
        return None
    return None


def _anos_fap_anteriores(anteriores):
    """Anos de FAP já consumidos pelos benefícios anteriores do mesmo segurado. Só vale o que a tabela
    mostra: traço "-" = o benefício não está no FAP (B31 nunca está) e conta zero vigência."""
    anos = set()
    for b in anteriores:
        if b.especie in ORDEM_ESPECIES and b.especie not in ('B31', 'B32'):
            anos |= {a for r in b.linhas for v in r['vigs'] for a in re.findall(r'(?:19|20)\d{2}', v)}
    return sorted(anos)


def _beneficios_excluidos(tese_key, lista):
    """Filtra a lista da tabela para o que o pedido realmente exclui. Devolve (lista, notas)."""
    notas = []
    # B32 (aposentadoria) só é benefício excluível na tese CONVERTIDO; nas demais continua sendo o "outro benefício"
    excluiveis = [e for e in ORDEM_ESPECIES if e != 'B32' or tese_key == 'convertido']
    conhecidos = [b for b in lista if b.especie in excluiveis]
    outros = [b for b in lista if b.especie not in excluiveis]
    completa = list(lista)
    if conhecidos and outros:
        notas.append(f'{len(outros)} benefício(s) de espécie fora de B91-B94/B31/B36 (ex.: aposentadoria) '
                     'tratado(s) como o "outro benefício", não excluído(s).')
        lista = conhecidos
    anteriores = [b.especie for b in outros]
    for b in outros:
        b.decisao = f'não excluído: espécie {b.especie} é tratada como "outro benefício"'
    if tese_key in TESES_DE_PAR:
        # benefícios do mesmo segurado (NIT; sem NIT, mesmo "Item"): o mais antigo é o benefício
        # anterior/"outro benefício" e fica; os posteriores são os excluídos. O "outro benefício"
        # (ex.: aposentadoria) entra na ordenação do segurado: se ele é o mais antigo, ele é o anterior
        # e TODOS os benefícios excluíveis do segurado ficam no pedido.
        ids = {id(b) for b in lista}
        grupos = {}
        for b in completa:
            grupos.setdefault(b.nit or f'item:{b.item}', []).append(b)
        if any(sum(id(b) in ids for b in g) > 1 for g in grupos.values()):
            escolhidos = []
            for g in grupos.values():
                membros = [b for b in g if id(b) in ids]
                if len(membros) <= 1:
                    for b in membros:
                        b.decisao = 'excluído: único benefício excluível do segurado na tabela'
                    escolhidos += membros
                    continue
                # DIB depois da própria DCB = data errada na planilha: não dá pra confiar na ordenação
                # por data, então vale a ordem em que os benefícios aparecem na tabela
                datas_incoerentes = [b for b in g if b.dib and b.dcb and _data_ordenavel(b.dib) > _data_ordenavel(b.dcb)]
                if datas_incoerentes:
                    notas.append('Planilha com DIB posterior à DCB no NB ' +
                                 ', '.join(b.numero for b in datas_incoerentes) +
                                 ': a ordem do benefício anterior seguiu a ordem da tabela. Confira as datas.')
                ordenados = (sorted(g, key=lambda b: _data_ordenavel(b.dib))
                             if all(b.dib for b in g) and not datas_incoerentes
                             else sorted(g, key=lambda b: b.ordem))
                criterio = ('ordem da tabela (DIB posterior à DCB em algum benefício)' if datas_incoerentes else
                            'menor DIB' if all(b.dib for b in g) else 'ordem da tabela (faltam datas na planilha)')
                # Marcação explícita da planilha: "-" na coluna Item = benefício anterior (fica), número =
                # excluído. Vale sobre qualquer data; sem esse padrão, vale a ordenação acima.
                tracos = [b for b in g if b.item.strip() == '-']
                numerados = [b for b in g if b.item.strip() != '-']
                anterior_de = {id(b): ordenados[0] for b in ordenados[1:]}
                if tracos and numerados and all(b.item.strip().isdigit() for b in numerados):
                    if len(tracos) == 1:
                        if ordenados[0] is not tracos[0] and not datas_incoerentes and all(b.dib for b in g):
                            notas.append(f'As datas da planilha indicam o NB {ordenados[0].numero} como o mais antigo, '
                                         f'mas a planilha marca o NB {tracos[0].numero} como o benefício anterior '
                                         '("-" na coluna Item): vale a marcação. Confira as datas.')
                        ordenados = tracos + [b for b in ordenados if b is not tracos[0]]
                        anterior_de = {id(b): tracos[0] for b in numerados}
                    else:
                        # vários "-" no mesmo segurado (ex.: dois pares B31 -> B91): todo "-" é um anterior
                        # e fica; cada numerado é o restabelecimento do "-" logo acima dele na tabela
                        ordenados = sorted(g, key=lambda b: b.ordem)
                        ultimo, anterior_de = min(tracos, key=lambda b: b.ordem), {}
                        for b in ordenados:
                            if b.item.strip() == '-':
                                ultimo = b
                            else:
                                anterior_de[id(b)] = ultimo
                    criterio = 'marcação "-" na coluna Item da planilha'
                for i, b in enumerate(ordenados):
                    if id(b) not in anterior_de:
                        b.decisao = f'benefício anterior (não excluído): critério {criterio}'
                        if id(b) in ids:
                            anteriores.append(b.especie)
                    else:
                        b.vigs_anteriores = _anos_fap_anteriores(ordenados[:i])
                        if id(b) in ids:
                            b.decisao = f'excluído: posterior ao NB {anterior_de[id(b)].numero} (critério {criterio})'
                escolhidos += [b for b in ordenados if id(b) in anterior_de and id(b) in ids]
            notas.append('Vários benefícios do mesmo segurado: o mais antigo foi tratado como o benefício '
                         'anterior (não excluído) e os posteriores como os excluídos.')
            lista = escolhidos
    return lista, notas, anteriores


# ───────────────────────────── montagem ─────────────────────────────

def montar_pedidos(peticao: Peticao, resultado: ResultadoDeteccao) -> Proposta:
    det = {d.secao_numero: d for d in resultado.deteccoes if d.secao_numero}
    secoes = {s.numero: s for s in peticao.secoes if s.numero}
    ordem = [n for n in (s.numero for s in peticao.secoes) if n in det]

    ben, notas_ben, anterior_esp = {}, {}, {}
    for n in ordem:
        lst = {}
        # teses que excluem NTP (não o benefício): a espécie não importa; cada número da tabela é um NTP
        so_ntp = det[n].tese_key in TESES_DE_NTP
        for t in secoes[n].tabelas:
            if eh_tabela_de_beneficios(t, sem_especie=so_ntp):
                for b in ler_beneficios(t, sem_especie=so_ntp):
                    lst.setdefault(b.numero, b)
        if so_ntp:
            filtrada, notas, anteriores = list(lst.values()), [], []
        else:
            filtrada, notas, anteriores = _beneficios_excluidos(det[n].tese_key, list(lst.values()))
        ben[n] = {b.numero: b for b in filtrada}
        notas_ben[n] = notas
        anterior_esp[n] = anteriores

    def descendentes(n):
        return [m for m in ordem if m.startswith(n + '.')]

    # unidades de pedido: seção com tabela própria que não seja só um resumo dos filhos;
    # seção sem tabela em lugar nenhum vira pedido com pendência
    unidades = []
    for n in ordem:
        desc = descendentes(n)
        uniao_desc = set().union(*[set(ben[m]) for m in desc]) if desc else set()
        if secoes[n].tabelas:
            if ben[n] and desc and set(ben[n]) <= uniao_desc:
                continue
            unidades.append(n)
        elif not [m for m in desc if secoes[m].tabelas]:
            unidades.append(n)

    propostos = {n: _montar_principal(n, det[n], secoes[n], ben[n], notas_ben[n], anterior_esp[n])
                 for n in unidades}

    # 1º tópico em que cada NB aparece: é só nele que as teses subsidiária/alternativa do NB constam; nos demais
    # tópicos o NB é pedido principal normalmente, sem menção às outras teses.
    primeira = {}
    for n in unidades:
        for nb in ben[n]:
            primeira.setdefault(nb, n)

    # tese subsidiária: seção que repete benefícios de unidade ANTERIOR
    for k, s in enumerate(unidades):
        for p in unidades[:k]:
            comuns = [b for num, b in ben[s].items() if num in ben[p] and primeira[num] == p]
            if not comuns:
                continue
            pp, tg, tp = propostos[p], TESES[det[s].tese_key], TESES[det[p].tese_key]
            if not validacao.tese_permite_subsidiario(det[p].tese_key) or tg.get('tipo_clausula') not in (None, 'custo_cessado'):
                continue
            todos = {b.numero for b in comuns} >= set(ben[p])
            pp.dados['grupos_subsidiarios'].append({
                'tese_subsidiaria_key': det[s].tese_key,
                'item_peticao': s,
                'numeros_com_especie': [] if todos else [(b.especie, b.numero) for b in comuns],
                'parametro_valor': _parametro(det[s].tese_key, secoes[s], anterior_esp[s]),
                'todos_beneficios_principal': todos,
                'especies_principal': pp.dados['especies'] if todos else None,
                'quantidade_principal': pp.dados['quantidade'] if todos else None,
            })
            pp.notas.append(f'Seção {s} ({tg["nome"]}) repete benefícios deste pedido: incluída como tese subsidiária.')
            if det[s].confianca != ALTA:
                pp.pendencias.append(f'Confira a tese subsidiária do item {s}: confiança {det[s].confianca}.')

    pedidos = [propostos[n] for n in unidades]
    validar_pedidos(pedidos, remover_invalidas=True)
    return Proposta(pedidos=pedidos)


def _montar_principal(n, d, sec, beneficios, notas, anteriores=()):
    tese = TESES[d.tese_key]
    pend = []
    tipo = tese.get('tipo_clausula', 'exclusao_beneficio')
    lista = list(beneficios.values())
    anos, cnpjs = set(), set()
    for t in sec.tabelas:
        a, c = vigencias_e_cnpjs_da_tabela(t)
        anos |= a
        cnpjs |= c
    quantidade, especies, campo_texto = len(lista), _ordenar_especies(b.especie for b in lista), None
    varios = False

    if tipo in ('fixo_com_vigencia', 'correcao_com_vigencia'):
        quantidade, especies = 1, []
        campo_texto = _formatar_vigencias(anos)
        if not campo_texto:
            pend.append('Vigências não encontradas na tabela: preencher o campo de vigência.')
        varios = len(cnpjs) > 1 and tipo == 'correcao_com_vigencia'
    elif tipo == 'fixo':                                   # rotatividade
        quantidade, especies = max(1, len(cnpjs)), []
        if not cnpjs:
            pend.append('Nenhum CNPJ encontrado na tabela: quantidade de estabelecimentos assumida como 1.')
    else:
        if tese.get('ignora_quantidade'):
            quantidade = 1
        if tese.get('ignora_especie'):
            especies = []
        if not lista and not tese.get('ignora_quantidade'):
            pend.append('Tabela de benefícios não encontrada (ou sem benefício excluível) nesta seção: '
                        'informe quantidade e espécies.')
            quantidade = 0

    # (parâmetro indeterminado: o aviso sai da validação, mais abaixo, uma única vez)
    parametro = _parametro(d.tese_key, sec, anteriores) if tese.get('parametro') else None

    if d.confianca != ALTA:
        pend.append(f'Confira a tese: confiança {d.confianca} ({d.evidencia}).')
    pts = [p for _, p in (d.candidatas or [])]
    if len(pts) > 1 and pts[0] == pts[1]:
        pend.append('Mais de uma tese com a mesma pontuação: confirme a tese.')

    # Regra do escritório (definida pelo usuário): 1 vigência em 1 estabelecimento => "do índice do
    # FAP" (singular), mesmo com 2+ benefícios; mais de uma vigência e/ou mais de um
    # estabelecimento => "dos índices do FAP" (plural). (Nas petições antigas o plural aparece
    # em 27 de 38 casos de mesma vigência/estabelecimento; vale a regra atual do escritório.)
    indice_singular = False
    if quantidade > 1 and lista and validacao.tese_permite_indice_singular(d.tese_key):
        vig = {v for b in lista for v in b.vigencias}
        cn = {v for b in lista for v in b.cnpjs}
        indice_singular = len(vig) == 1 and len(cn) == 1
    # 1 benefício em mais de uma vigência ou em mais de um CNPJ: sempre "dos índices do FAP" (plural),
    # mesmo com quantidade 1 (singular só com 1 vigência e 1 CNPJ)
    indice_plural = (quantidade == 1 and len(lista) == 1
                     and (len(lista[0].vigencias) > 1 or len(lista[0].cnpjs) > 1)
                     and validacao.tese_permite_indice_singular(d.tese_key))

    # NTP: a tabela da tese traz a coluna "NTP" ("NTP" / "-") por benefício. Há benefício com NTP =>
    # o pedido também exclui o NTP; singular se só 1 benefício tem NTP, plural se 2+ (regra das
    # petições reais: 6 de 6 pedidos). Sem a coluna, só avisa quando a vigência vai até 2017.
    excluir_ntp = ntp_singular = False
    notas = list(notas)
    if validacao.tese_permite_exclusao_ntp(d.tese_key):
        flags = [b.ntp for b in lista if b.ntp is not None]
        com_ntp = sum(1 for f in flags if f)
        if com_ntp:
            excluir_ntp, ntp_singular = True, com_ntp == 1
            notas.append(f'{com_ntp} benefício(s) com NTP na tabela da tese: exclusão do NTP incluída no pedido '
                         f'e na tabela (coluna NTP).')
        elif not flags:
            anos_ntp = [int(a) for a in anos | {v for b in lista for v in b.vigencias}]
            if anos_ntp and min(anos_ntp) <= validacao.ULTIMA_VIGENCIA_COM_NTP:
                pend.append('Vigência até 2017: verifique se cabe excluir também o NTP.')

    dados = {
        'quantidade': quantidade, 'especies': especies, 'tese_key': d.tese_key, 'item_peticao': n,
        'parametro_valor': parametro, 'campo_texto_valor': campo_texto,
        'indice_singular': indice_singular, 'indice_plural': indice_plural, 'excluir_ntp': excluir_ntp, 'ntp_singular': ntp_singular,
        'varios_estabelecimentos': varios, 'grupos_subsidiarios': [],
    }
    base = None
    if tipo in TESES_POR_VIGENCIA:
        base = tabela_por_vigencia(sec)
        if base is None:
            pend.append('Tabela do pedido: não encontrei a tabela de vigências/CNPJ na seção.')
    logica = [
        f'Tese {tese["nome"]} ({d.tese_key}): detectada por {d.origem}, confiança {d.confianca}; evidência: {d.evidencia!r}.',
    ]
    if d.candidatas:
        logica.append('Teses candidatas (pontos): ' + ', '.join(f'{k}={p}' for k, p in d.candidatas) + '.')
    logica.append(f'Tipo de cláusula: {tipo}.')
    if tipo in ('fixo_com_vigencia', 'correcao_com_vigencia'):
        logica.append(f'Pedido por vigência: vigências lidas da tabela = {campo_texto or "nenhuma"}; CNPJs distintos = '
                      f'{len(cnpjs)} -> plural ("mais de um estabelecimento"/"mais de uma vigência") = {varios}.')
    elif tipo == 'fixo':
        logica.append(f'Quantidade = nº de CNPJs distintos na tabela ({len(cnpjs)}).')
    else:
        logica.append(f'Quantidade = {quantidade} benefício(s) na tabela da seção (depois dos filtros da tese); '
                      f'espécies tiradas da coluna Tipo da planilha: {", ".join(especies) or "(nenhuma / a tese ignora espécie)"}.')
        if tese.get('ignora_especie') or tese.get('ignora_quantidade'):
            logica.append('A tese ignora espécie e/ou quantidade no texto do pedido.')
    if lista:
        vig = sorted({v for b in lista for v in b.vigencias})
        cn = sorted({v for b in lista for v in b.cnpjs})
        logica.append(f'Índice do FAP: vigências distintas = {len(vig)} ({", ".join(vig) or "-"}), CNPJs distintos = {len(cn)}; '
                      f'singular só com 1 vigência e 1 CNPJ -> indice_singular={indice_singular}, indice_plural={indice_plural}.')
    logica.append(f'Exclusão de NTP: {excluir_ntp} (singular={ntp_singular}).')
    if parametro is not None:
        logica.append(f'Parâmetro da tese deduzido da petição: {parametro!r}.')
    return PedidoProposto(dados=dados, secao_numero=n, tese_nome=tese['nome'], confianca=d.confianca,
                          evidencia=d.evidencia, beneficios=lista, pendencias=pend, notas=list(notas),
                          tabela_base=base, logica=logica)


def validar_pedidos(pedidos, remover_invalidas=False):
    """Roda validacao.py e gerar_documento em cada pedido; falhas viram pendências
    "Validação: ..." e `valido=False`. `remover_invalidas`: descarta subsidiárias inválidas
    (proposta automática); na revisão manual elas ficam, para o usuário corrigir."""
    for p in pedidos:     # revalidação: limpa o resultado da rodada anterior
        p.pendencias = [t for t in p.pendencias if not t.startswith(('Validação:', 'Tabela:'))]
        if p.incluir_tabela and p.tabela_base is None:       # tabela de benefícios x quantidade do pedido
            tab = tabela_do_pedido(p)
            n = n_beneficios_na_tabela(tab) if tab else None
            if tab is not None and n is not None and n != p.dados['quantidade']:
                p.pendencias.append(f'Tabela: a tabela do pedido tem {n} benefício(s) e o pedido diz '
                                    f'{p.dados["quantidade"]}; ajuste a tabela no Word ou desligue "Incluir tabela".')
    erro_itens = None
    try:
        validacao.validar_itens_duplicados([p.dados['item_peticao'] for p in pedidos])
    except ValueError as e:
        erro_itens = str(e)
    for p in pedidos:
        dd = p.dados
        erros = [erro_itens] if erro_itens else []
        try:
            if dd['quantidade'] < 1:
                raise ValueError('Informe uma quantidade válida de benefícios (número inteiro maior que zero).')
            if not dd['item_peticao'].strip():
                raise ValueError('Informe o item do pedido na petição inicial.')
            validacao.validar_especies(dd['tese_key'], dd['especies'], dd['quantidade'])
        except ValueError as e:
            erros.append(str(e))
        if dd['grupos_subsidiarios'] and not validacao.tese_permite_subsidiario(dd['tese_key']):
            erros.append('Esta tese não admite benefício subsidiário.')
        for g in list(dd['grupos_subsidiarios']):
            try:
                tg = TESES[g['tese_subsidiaria_key']]
                if tg.get('tipo_clausula') not in (None, 'custo_cessado'):
                    raise ValueError(f'a tese {tg["nome"]} não pode ser subsidiária.')
                if tg.get('parametro') and g['parametro_valor'] is None:
                    raise ValueError(f'tese subsidiária {tg["nome"]} sem o parâmetro (ex.: outro benefício).')
                if not g['item_peticao'].strip():
                    raise ValueError('informe o item da petição inicial.')
                if g['numeros_com_especie']:
                    validacao.validar_beneficios_subsidiaria(g['numeros_com_especie'], dd['quantidade'])
                elif not validacao.beneficio_subsidiario_pode_herdar_do_principal(dd['quantidade']):
                    raise ValueError('informe ao menos um benefício.')
            except ValueError as e:
                erros.append(f'Subsidiária (item {g["item_peticao"]}): {e}')
                if remover_invalidas:
                    dd['grupos_subsidiarios'].remove(g)
        if TESES[dd['tese_key']].get('parametro') and dd['parametro_valor'] is None:
            rotulo = PARAMETROS_TESE[TESES[dd['tese_key']]['parametro']]['label'].rstrip(':')
            erros.append(f'Escolha "{rotulo}" no pedido: não consegui descobrir pela petição.')
        if not erros:
            try:
                gerador_pedido.gerar_documento([dd])
            except Exception as e:      # noqa: BLE001 - qualquer falha de geração é pendência
                erros.append(f'Geração do texto falhou: {type(e).__name__}: {e}')
        for e in erros:
            p.pendencias.append(f'Validação: {e}')
        p.valido = not erros
