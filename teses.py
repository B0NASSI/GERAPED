# Registro central de teses disponíveis. Para adicionar uma nova tese, basta
# incluir uma entrada nova aqui (chave -> nome de exibição + motivo no singular/plural).
# Nada mais no resto do programa precisa mudar.
#
# Fonte de verdade: "ATUALIZADO - Petição inicial - Estrutura (3).docx" (template oficial
# do escritório, com placeholders "x"/"xxxx" no lugar dos números reais). Onde só um dos
# dois números (singular/plural) aparece no template, o outro foi inferido por simetria
# gramatical e está marcado com comentário - ajustar se aparecer um caso real divergente.

TIPO_BENEFICIO_POR_ESPECIE = {
    'B91': 'auxílio por incapacidade temporária por acidente de trabalho',
    'B92': 'aposentadoria por incapacidade permanente por acidente de trabalho',
    'B93': 'pensão por morte acidentária',
    'B94': 'auxílio-acidente por acidente de trabalho',
    'B31': 'auxílio por incapacidade temporária previdenciária',
    'B36': 'auxílio-acidente previdenciário',
}

TESES = {
    'acidente_trajeto': {
        'nome': 'TRAJETO',
        'motivo_singular': 'decorrente de acidente de trajeto',
        'motivo_plural': 'decorrentes de acidentes de trajeto',
    },
    'restabelecimento_beneficio_anterior': {
        'nome': '60 DIAS',
        'motivo_singular': 'por se tratar de restabelecimento de benefício anterior',
        'motivo_plural': 'por se tratar de restabelecimentos de benefícios anteriores',
    },
    'acidente_outro_estabelecimento': {
        'nome': 'OUTRO ESTABELECIMENTO',
        'motivo_singular': 'decorrente de acidente ocorrido em outro estabelecimento',
        # plural inferido (template só mostra o singular) - ajustar se aparecer um caso real
        'motivo_plural': 'decorrentes de acidentes ocorridos em outro estabelecimento',
    },
    'ausencia_nexo_causal_concausalidade': {
        'nome': 'NEXO AFASTADO',
        # o verbo concorda com "o nexo causal E a concausalidade" (sujeito composto), não com a
        # quantidade de benefícios - por isso é sempre plural ("foram"), confirmado no template
        # mesmo em grupos com 1 só benefício.
        'motivo_singular': 'tendo em vista que o nexo causal e de concausalidade foram afastados por decisão judicial',
        'motivo_plural': 'tendo em vista que o nexo causal e de concausalidade foram afastados por decisão judicial',
    },
    'acidente_sem_relacao_empresa': {
        'nome': 'OUTRA EMPRESA',
        'motivo_singular': 'considerando que o acidente de trabalho não tem relação com a empresa Autora',
        'motivo_plural': 'considerando que os acidentes de trabalho não têm relação com a empresa Autora',
    },
    'natureza_previdenciaria': {
        'nome': 'BENEFÍCIO PREVIDENCIÁRIO',
        # singular inferido (template só mostra o plural) - ajustar se aparecer um caso real
        'motivo_singular': 'por se tratar de benefício de natureza previdenciária',
        'motivo_plural': 'por se tratar de benefícios de natureza previdenciária',
    },
    'concomitancia_outro_beneficio': {
        'nome': 'CONCOMITANTE',
        # {outro_beneficio} é preenchido a partir do seletor extra (ver PARAMETROS_TESE) -
        # substitui os 9 combos B91/B92/B94 x aposentadoria/auxílio-incapacidade/auxílio-acidente
        # por uma única tese + escolha do outro benefício concomitante.
        'motivo_singular': 'concedido enquanto o segurado já usufruía de outro benefício de {outro_beneficio}',
        'motivo_plural': 'concedidos enquanto os segurados já usufruíam de outro benefício de {outro_beneficio}',
        'parametro': 'outro_beneficio',
    },
    'acidente_anterior_2007': {
        'nome': 'PRÉ-FAP',
        'motivo_singular': 'decorrente de acidente anterior a abril de 2007',
        # plural inferido (template só mostra o singular) - ajustar se aparecer um caso real
        'motivo_plural': 'decorrentes de acidentes anteriores a abril de 2007',
    },
    'sobreposicao_concomitancia_beneficios': {
        'nome': 'SOBREPOSIÇÃO',
        'motivo_singular': 'tendo em vista a sobreposição e concomitância de benefícios',
        'motivo_plural': 'tendo em vista a sobreposição e concomitância de benefícios',
    },
    'dib_igual_dcb': {
        'nome': 'DIB=DCB',
        'motivo_plural': 'por se tratar de benefícios concedidos com a mesma data de início (DIB) e cessação (DCB)',
        # singular inferido (template só mostra o plural) - ajustar se aparecer um caso real
        'motivo_singular': 'por se tratar de benefício concedido com a mesma data de início (DIB) e cessação (DCB)',
    },
    'beneficio_cancelado_revogado': {
        'nome': 'BENEFÍCIO CANCELADO/REVOGADO',
        'motivo_plural': 'tendo em vista a revogação das decisões que concederam os benefícios',
        # singular inferido (template só mostra o plural) - ajustar se aparecer um caso real
        'motivo_singular': 'tendo em vista a revogação da decisão que concedeu o benefício',
    },
    'cat_nao_vinculada': {
        'nome': 'CAT NÃO VINCULADA',
        'motivo_plural': 'por se tratar de eventos acidentários considerados em duplicidade',
        # singular inferido (template só mostra o plural) - ajustar se aparecer um caso real
        'motivo_singular': 'por se tratar de evento acidentário considerado em duplicidade',
        # aqui o que é excluído não é "benefício de espécie X", e sim o NTP em si
        'substantivo_plural': 'Nexos Técnicos Previdenciários (NTP) sem Comunicação de Acidente de Trabalho (CAT) vinculada aos benefícios',
        'substantivo_singular': 'Nexo Técnico Previdenciário (NTP) sem Comunicação de Acidente de Trabalho (CAT) vinculada ao benefício',
        # o modelo oficial usa "índice" sempre no singular, mesmo com vários NTPs
        'base_calculo': 'da base de cálculo do índice do FAP',
        # o texto não menciona espécie de benefício (é sempre "NTP") - campo desabilitado na UI
        'ignora_especie': True,
    },
    'erro_implantacao': {
        'nome': 'ERRO DE IMPLANTAÇÃO',
        'motivo_plural': 'implantados de forma equivocada pelo INSS',
        # singular inferido (template só mostra o plural) - ajustar se aparecer um caso real
        'motivo_singular': 'implantado de forma equivocada pelo INSS',
        'base_calculo': 'da base de cálculo do índice do FAP',
    },
    # ── Teses com estrutura de cláusula própria (ver 'tipo_clausula' em gerador_pedido.py) ──
    'rotatividade': {
        'nome': 'ROTATIVIDADE',
        'tipo_clausula': 'fixo',
        # {indice} e {estabelecimento} variam no singular/plural conforme a quantidade
        # informada (1 ou 2+) - ver ROTATIVIDADE_VARIACAO em gerador_pedido.py. O resto do
        # texto, incluindo "vigência" (sempre singular), não muda com a quantidade.
        'clausula_fixa': (
            'Declarar a ilegalidade da restrição à bonificação denominada "bloqueio por taxa de rotatividade", '
            'imposta pelas Resoluções CNPS nºs 1.316/2010, 1.329/2017 e 1.347/2021, bem como determinar o '
            'recálculo {indice} em relação {estabelecimento} e à vigência abaixo arrolados, conforme '
            'as disposições constantes da Lei nº 10.666/2003 e dos Decretos nºs 3.048/1999, 6.042/2007 e '
            '6.957/2009, ou seja, sem a aplicação da trava do "bloqueio de rotatividade"'
        ),
        # texto fixo não menciona benefícios por espécie - campo desabilitado na UI
        'ignora_especie': True,
    },
    'erro_massa_salarial': {
        'nome': 'ERRO DE MASSA SALARIAL',
        'tipo_clausula': 'correcao_com_vigencia',
        'texto_principal': 'do valor da massa salarial',
        'campo_texto': {
            'label': 'Vigências para correção:',
        },
        'texto_subsidiario': (
            'Subsidiariamente, entendendo V. Exa. que as massas salariais indicadas no FAP nas vigências '
            'de {vigencias} estão corretas, requer-se a declaração expressa para que a empresa Autora possa, em '
            'processo autônomo, utilizar essas massas salariais para repetir todos os tributos pagos a maior '
            'no período em que foram apurados sobre tais bases de cálculo'
        ),
        # trata de massa salarial do estabelecimento, não de benefícios por espécie/quantidade
        'ignora_especie': True,
        'ignora_quantidade': True,
    },
    'erro_vinculos': {
        'nome': 'ERRO DE VÍNCULOS',
        'tipo_clausula': 'correcao_com_vigencia',
        'texto_principal': 'do número médio de vínculos',
        'campo_texto': {
            'label': 'Vigências para correção:',
        },
        'texto_subsidiario': (
            'Subsidiariamente, caso V. Exa. entenda que os números médios de vínculos indicados no FAP nas '
            'vigências de {vigencias} estão corretos, requer-se a declaração expressa para que a empresa Autora '
            'possa, em processo autônomo, utilizar esses números médios de vínculos para repetir todos os '
            'tributos pagos a maior no período em que foram apurados com base nessas informações'
        ),
        # trata de número médio de vínculos do estabelecimento, não de benefícios por espécie/quantidade
        'ignora_especie': True,
        'ignora_quantidade': True,
    },
    'custo_cessado': {
        'nome': 'CUSTO CESSADO',
        'tipo_clausula': 'custo_cessado',
        'parametro': 'tipo_custo_cessado',
    },
    # Estrutura igual à de 'rotatividade': texto fixo (com 'inexistência' em negrito) que só
    # varia a vigência (texto livre) e o motivo final - por isso o mesmo 'tipo_clausula'
    # ('fixo_com_vigencia') serve às duas.
    'prescricao_quinquenal': {
        'nome': 'PRESCRIÇÃO QUINQUENAL',
        'tipo_clausula': 'fixo_com_vigencia',
        'motivo_fixo': 'em razão da prescrição quinquenal, nos termos da fundamentação',
        'campo_texto': {
            'label': 'Vigência:',
        },
        'ignora_especie': True,
        'ignora_quantidade': True,
    },
    'contestacao_administrativa': {
        'nome': 'CONTESTAÇÃO ADMINISTRATIVA',
        'tipo_clausula': 'fixo_com_vigencia',
        'motivo_fixo': 'em razão do efeito suspensivo atribuído à contestação administrativa',
        'campo_texto': {
            'label': 'Vigência:',
        },
        'ignora_especie': True,
        'ignora_quantidade': True,
    },
}

# Teses com 'parametro' pedem uma escolha extra na interface (ver PARAMETROS_TESE).
# Texto de "aposentadoria" e "auxílio-acidente" inferido por simetria com o caso confirmado
# no template (auxílio por incapacidade temporária) - ajustar se o usuário enviar o texto oficial.
PARAMETROS_TESE = {
    'outro_beneficio': {
        'label': 'Outro benefício já em vigor:',
        'opcoes': {
            'auxilio_incapacidade': 'auxílio por incapacidade temporária',
            'aposentadoria': 'aposentadoria',
            'auxilio_acidente': 'auxílio-acidente',
        },
    },
    'tipo_custo_cessado': {
        'label': 'Motivo da cessação:',
        # rótulos curtos para o combobox - o texto completo de cada opção fica em
        # gerador_pedido.CUSTO_CESSADO_MOTIVO, pois a frase muda de estrutura gramatical
        # entre uma opção e outra (não é uma simples troca de palavra)
        'opcoes': {
            'aposentadoria': 'Aposentadoria',
            'obito': 'Óbito',
        },
    },
}


def nome_para_chave(nome_exibicao):
    for chave, tese in TESES.items():
        if tese['nome'] == nome_exibicao:
            return chave
    return None


def chave_para_opcao_parametro(parametro_id, nome_exibicao):
    for chave, nome in PARAMETROS_TESE[parametro_id]['opcoes'].items():
        if nome == nome_exibicao:
            return chave
    return None
