import os
import re
import sys

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from teses import TESES, TIPO_BENEFICIO_POR_ESPECIE, PARAMETROS_TESE
from utilitarios import numero_e_extenso

FONTE_NOME = 'Segoe UI'
FONTE_TAMANHO = Pt(11)
COR_ITEM_PETICAO = RGBColor(0x00, 0x70, 0xC0)

ESTILO_PEDIDO = 'Lista de Pedidos'
# Numeração (numId/ilvl) usada pelos itens de pedido no modelo oficial - produz a
# lista com letras "a., b., c...". numId=0 desliga a numeração (usado nas linhas em
# branco que separam os itens, replicando o espaçamento visual do modelo).
NUMPR_ITEM = (1, 6)
NUMPR_SEM_NUMERO = (0, 0)


def _caminho_recurso(nome):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nome)


CAMINHO_MODELO = _caminho_recurso(os.path.join('Modelo', 'PEDIDOS.docx'))


def _limpar_corpo(doc):
    """Remove todo o conteúdo do documento-modelo, preservando estilos, numeração
    e propriedades de seção (margens etc.) definidos nele."""
    body = doc.element.body
    for filho in list(body):
        if filho.tag != qn('w:sectPr'):
            body.remove(filho)


def _definir_numeracao(paragrafo, ilvl, num_id):
    pPr = paragrafo._p.get_or_add_pPr()
    numPr = OxmlElement('w:numPr')
    el_ilvl = OxmlElement('w:ilvl')
    el_ilvl.set(qn('w:val'), str(ilvl))
    numPr.append(el_ilvl)
    el_numid = OxmlElement('w:numId')
    el_numid.set(qn('w:val'), str(num_id))
    numPr.append(el_numid)
    pPr.append(numPr)


def _nome_tipo_beneficio(especie):
    return TIPO_BENEFICIO_POR_ESPECIE.get(especie, f"benefício espécie {especie}")


def _add_run(paragrafo, texto, bold=False, italic=False, cor=None):
    run = paragrafo.add_run(texto)
    run.bold = bold
    run.italic = italic
    if cor is not None:
        run.font.color.rgb = cor
    run.font.name = FONTE_NOME
    run.font.size = FONTE_TAMANHO
    return run


def _add_item_referencia(paragrafo, item_peticao):
    """Adiciona ' – item X da petição inicial' (sem ponto final - quem chama decide)."""
    _add_run(paragrafo, ' – ')
    _add_run(paragrafo, f'item {item_peticao} da petição inicial', bold=True, italic=True, cor=COR_ITEM_PETICAO)


def _motivo(tese, singular, parametro_valor=None):
    # Custo cessado não tem motivo_singular/motivo_plural - a frase inteira depende do tipo
    # de cessação escolhido (ver CUSTO_CESSADO_MOTIVO, definido mais abaixo neste módulo).
    if tese.get('tipo_clausula') == 'custo_cessado':
        return CUSTO_CESSADO_MOTIVO[parametro_valor]

    texto = tese['motivo_singular'] if singular else tese['motivo_plural']
    parametro_id = tese.get('parametro')
    if parametro_id:
        opcoes = PARAMETROS_TESE[parametro_id]['opcoes']
        texto = texto.format(**{parametro_id: opcoes[parametro_valor]})
    return texto


def _descricao_beneficios(especies, singular):
    substantivo = 'benefício' if singular else 'benefícios'

    if len(especies) == 1:
        tipo_nome = _nome_tipo_beneficio(especies[0])
        return f'{substantivo} de {tipo_nome}, espécie {especies[0]}'

    lista = ', '.join(especies[:-1]) + f' e {especies[-1]}'
    sufixo = 'acidentário' if singular else 'acidentários'
    return f'{substantivo} {sufixo}, espécies {lista}'


def _descricao_item(tese, especies, singular):
    """Descreve o que está sendo excluído. Teses com 'substantivo_singular'/'substantivo_plural'
    (ex: NTP em vez de benefício de espécie X) usam texto fixo em vez do padrão por espécie."""
    if 'substantivo_singular' in tese:
        return tese['substantivo_singular'] if singular else tese['substantivo_plural']
    return _descricao_beneficios(especies, singular)


def montar_clausula_principal(paragrafo, quantidade, especies, tese_key, item_peticao, parametro_valor=None):
    tese = TESES[tese_key]
    singular = quantidade == 1
    # Teses cujo substantivo excluído é gramaticalmente feminino (ex: Comunicação de
    # Acidente de Trabalho) precisam de "uma"/"duzentas"/"abaixo arrolada(s)" em vez do
    # masculino padrão - ver 'genero' em teses.py.
    feminino = tese.get('genero') == 'feminino'

    _add_run(paragrafo, 'Determinar ')
    # Algumas teses (ex: CAT DUPLICADA) omitem o artigo: "Determinar exclusão de..." em vez
    # de "Determinar a exclusão de...", conforme o texto oficial - ver 'omitir_artigo_exclusao'.
    if not tese.get('omitir_artigo_exclusao'):
        _add_run(paragrafo, 'a ')
    _add_run(paragrafo, 'exclusão', bold=True)
    _add_run(paragrafo, ' de ')

    if singular:
        contagem = '1 (uma)' if feminino else '1 (um)'
    else:
        contagem = numero_e_extenso(quantidade, feminino=feminino)
    _add_run(paragrafo, contagem, bold=True)
    _add_run(paragrafo, ' ')
    _add_run(paragrafo, _descricao_item(tese, especies, singular), bold=True)
    if feminino:
        arrolado = 'abaixo arrolada' if singular else 'abaixo arroladas'
    else:
        arrolado = 'abaixo arrolado' if singular else 'abaixo arrolados'
    # 'base_calculo' sobrescreve a frase padrão para teses cujo modelo oficial não segue a
    # regra "índice do FAP" (singular) / "índices do FAP" (plural) - ex: DIB=DCB usa
    # "da base de cálculo do FAP" sem menção a índice, e CAT não vinculada usa "índice" sempre
    # no singular independente da quantidade.
    base_calculo = tese.get('base_calculo')
    if base_calculo is None:
        indice = 'do índice do FAP' if singular else 'dos índices do FAP'
        base_calculo = f'da base de cálculo {indice}'
    _add_run(paragrafo, f', {arrolado}, {base_calculo}, ')
    _add_run(paragrafo, _motivo(tese, singular, parametro_valor), bold=True)

    _add_item_referencia(paragrafo, item_peticao)


# Frases específicas de cada tipo de custo cessado - a redação muda de estrutura
# gramatical entre uma opção e outra, então não dá para usar o mecanismo genérico de
# {parametro}.format() usado em outras teses.
CUSTO_CESSADO_MOTIVO = {
    'aposentadoria': 'sendo este o dia imediatamente anterior à concessão da aposentadoria',
    'obito': 'esta correspondente ao dia imediatamente anterior ao óbito',
}

# Preenche {indice}/{estabelecimento} em TESES['rotatividade']['clausula_fixa'] conforme a
# quantidade informada (1 = singular, 2+ = plural).
ROTATIVIDADE_VARIACAO = {
    True: {'indice': 'do índice do FAP', 'estabelecimento': 'ao estabelecimento'},
    False: {'indice': 'dos índices do FAP', 'estabelecimento': 'aos estabelecimentos'},
}


def montar_clausula_custo_cessado(paragrafo, quantidade, especies, item_peticao, parametro_valor):
    singular = quantidade == 1

    _add_run(paragrafo, 'Determinar a ')
    _add_run(paragrafo, 'correção', bold=True)
    _add_run(paragrafo, ' do índice de custo de ')

    contagem = '1 (um)' if singular else numero_e_extenso(quantidade)
    _add_run(paragrafo, contagem, bold=True)
    _add_run(paragrafo, ' ')
    _add_run(paragrafo, _descricao_beneficios(especies, singular), bold=True)
    arrolado = 'abaixo arrolado' if singular else 'abaixo arrolados'
    _add_run(paragrafo, f', {arrolado}, limitando a apuração do valor ao período compreendido entre a DIB e a DCB, ')
    _add_run(paragrafo, CUSTO_CESSADO_MOTIVO[parametro_valor], bold=True)
    _add_run(paragrafo, ', devendo ser considerado o novo valor para o campo "TOTAL PAGO" do sistema FAP')

    _add_item_referencia(paragrafo, item_peticao)


def montar_clausula_correcao_com_vigencia(paragrafo, tese, item_peticao, vigencias):
    _add_run(paragrafo, 'Determinar a ')
    _add_run(paragrafo, 'correção', bold=True)
    _add_run(paragrafo, ' ')
    _add_run(paragrafo, tese['texto_principal'], bold=True)
    _add_run(paragrafo, ', nas competências do estabelecimento e vigências indicadas na tabela abaixo')

    _add_item_referencia(paragrafo, item_peticao)

    _add_run(paragrafo, '. ')
    _add_run(paragrafo, tese['texto_subsidiario'].format(vigencias=vigencias or 'xxxx'))


def _vigencia_no_plural(vigencia):
    """True se o texto livre de vigência citar mais de uma (separadas por vírgula ou "e"),
    ex: "2023, 2024" ou "2023 e 2024" - para declinar "vigência"/"vigências" corretamente."""
    if not vigencia:
        return False
    partes = [p for p in re.split(r',| e ', vigencia) if p.strip()]
    return len(partes) > 1


def montar_clausula_fixo_com_vigencia(paragrafo, tese, item_peticao, vigencia):
    plural = _vigencia_no_plural(vigencia)
    preposicao = 'às vigências de' if plural else 'à vigência de'

    _add_run(paragrafo, 'Declarar a ')
    _add_run(paragrafo, 'inexistência', bold=True)
    _add_run(
        paragrafo,
        ' de prescrição do direito da empresa Autora de corrigir os erros cometidos na base de '
        f'cálculo do FAP e reaver (compensar) seus créditos em relação {preposicao} ',
    )
    _add_run(paragrafo, vigencia or 'xxxx')
    _add_run(paragrafo, f", {tese['motivo_fixo']}")

    _add_item_referencia(paragrafo, item_peticao)


def montar_clausula(paragrafo, pedido):
    """Ponto único de entrada: decide qual estrutura de cláusula usar conforme
    tese['tipo_clausula'] (padrão: exclusão de benefício(s) da base de cálculo do FAP)."""
    tese = TESES[pedido['tese_key']]
    tipo = tese.get('tipo_clausula', 'exclusao_beneficio')

    if tipo == 'fixo':
        singular = pedido['quantidade'] == 1
        _add_run(paragrafo, tese['clausula_fixa'].format(**ROTATIVIDADE_VARIACAO[singular]))
        _add_item_referencia(paragrafo, pedido['item_peticao'])
        return

    if tipo == 'fixo_com_vigencia':
        montar_clausula_fixo_com_vigencia(
            paragrafo, tese, pedido['item_peticao'], pedido.get('campo_texto_valor'),
        )
        return

    if tipo == 'correcao_com_vigencia':
        montar_clausula_correcao_com_vigencia(
            paragrafo, tese, pedido['item_peticao'], pedido.get('campo_texto_valor'),
        )
        return

    if tipo == 'custo_cessado':
        montar_clausula_custo_cessado(
            paragrafo, pedido['quantidade'], pedido['especies'], pedido['item_peticao'],
            pedido.get('parametro_valor'),
        )
        return

    montar_clausula_principal(
        paragrafo, pedido['quantidade'], pedido['especies'], pedido['tese_key'], pedido['item_peticao'],
        parametro_valor=pedido.get('parametro_valor'),
    )


def _formatar_lista_beneficios(numeros_com_especie):
    return [f'{especie} nº {numero}' if numero else especie for especie, numero in numeros_com_especie]


def _formatar_lista_especies(especies):
    if len(especies) == 1:
        return especies[0]
    return ', '.join(especies[:-1]) + f' e {especies[-1]}'


def montar_grupo_subsidiario(paragrafo, grupo, primeiro, ultimo):
    if not primeiro:
        separador = ' –, e ' if ultimo else ' –, '
        _add_run(paragrafo, separador)

    tese = TESES[grupo['tese_subsidiaria_key']]
    parametro_valor = grupo.get('parametro_valor')

    if grupo.get('todos_beneficios_principal'):
        # Nenhum benefício informado neste grupo - subsidiário se aplica a todos os
        # benefícios do pedido principal (quantidade > 1), por isso sempre no plural.
        lista = _formatar_lista_especies(grupo['especies_principal'])
        _add_run(paragrafo, f'dos benefícios {lista}, ')
        _add_run(paragrafo, _motivo(tese, singular=False, parametro_valor=parametro_valor), bold=True)
    else:
        partes = _formatar_lista_beneficios(grupo['numeros_com_especie'])
        if len(partes) == 1:
            _add_run(paragrafo, f'do benefício {partes[0]}, ')
            _add_run(paragrafo, _motivo(tese, singular=True, parametro_valor=parametro_valor), bold=True)
        else:
            lista = ', '.join(partes[:-1]) + f' e {partes[-1]}'
            _add_run(paragrafo, f'dos benefícios {lista}, ')
            _add_run(paragrafo, _motivo(tese, singular=False, parametro_valor=parametro_valor), bold=True)

    _add_item_referencia(paragrafo, grupo['item_peticao'])


def adicionar_clausula_subsidiaria(paragrafo, grupos_subsidiarios):
    _add_run(paragrafo, 'Subsidiariamente, não sendo esse o entendimento de V. Exa., requer-se a ')
    _add_run(paragrafo, 'exclusão ', bold=True)
    total = len(grupos_subsidiarios)
    for i, grupo in enumerate(grupos_subsidiarios):
        montar_grupo_subsidiario(paragrafo, grupo, primeiro=(i == 0), ultimo=(i == total - 1))


def gerar_documento(pedidos):
    doc = docx.Document(CAMINHO_MODELO)
    _limpar_corpo(doc)

    for pedido in pedidos:
        paragrafo = doc.add_paragraph(style=ESTILO_PEDIDO)
        paragrafo.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _definir_numeracao(paragrafo, *NUMPR_ITEM)

        montar_clausula(paragrafo, pedido)

        grupos_subsidiarios = pedido.get('grupos_subsidiarios') or []
        if grupos_subsidiarios:
            _add_run(paragrafo, '. ')
            adicionar_clausula_subsidiaria(paragrafo, grupos_subsidiarios)

        _add_run(paragrafo, '.')

        espacador = doc.add_paragraph(style=ESTILO_PEDIDO)
        _definir_numeracao(espacador, *NUMPR_SEM_NUMERO)

    return doc
