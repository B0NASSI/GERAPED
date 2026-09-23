"""Testes de geração de texto - cobrem cada tipo de cláusula (exclusão padrão, fixo,
correção com vigência, custo cessado) e as variações de singular/plural, para pegar
regressões de texto sem precisar rodar a UI manualmente."""

from gerador_pedido import gerar_documento


def texto(pedido):
    doc = gerar_documento([pedido])
    return doc.paragraphs[0].text


def pedido_base(**overrides):
    dados = {
        'quantidade': 1,
        'especies': ['B91'],
        'tese_key': 'acidente_trajeto',
        'item_peticao': '5.1',
        'grupos_subsidiarios': [],
    }
    dados.update(overrides)
    return dados


def grupo_subsidiario(**overrides):
    dados = {
        'tese_subsidiaria_key': 'acidente_trajeto',
        'item_peticao': '3.1',
        'numeros_com_especie': [],
        'parametro_valor': None,
        'todos_beneficios_principal': False,
        'especies_principal': None,
        'quantidade_principal': None,
    }
    dados.update(overrides)
    return dados


class TestExclusaoBeneficioPadrao:
    def test_singular_uma_especie(self):
        t = texto(pedido_base(quantidade=1, especies=['B91'], tese_key='acidente_trajeto', item_peticao='5.1'))
        assert t == (
            'Determinar a exclusão de 1 (um) benefício de auxílio por incapacidade temporária por '
            'acidente de trabalho, espécie B91, abaixo arrolado, da base de cálculo do índice do FAP, '
            'decorrente de acidente de trajeto – item 5.1 da petição inicial.'
        )

    def test_plural_multiplas_especies(self):
        t = texto(pedido_base(quantidade=3, especies=['B91', 'B92'], tese_key='acidente_trajeto'))
        assert '3 (três) benefícios acidentários, espécies B91 e B92' in t
        assert 'dos índices do FAP' in t
        assert 'decorrentes de acidentes de trajeto' in t

    def test_plural_multiplas_especies_previdenciarias(self):
        # B31/B36 são previdenciários, não acidentários (bug real: o texto sempre dizia
        # "acidentários", mesmo quando as espécies escolhidas eram só B31/B36)
        t = texto(pedido_base(quantidade=2, especies=['B31', 'B36'], tese_key='convertido'))
        assert '2 (dois) benefícios previdenciários, espécies B31 e B36' in t

    def test_verbo_sempre_plural_em_nexo_afastado(self):
        # motivo_singular e motivo_plural são iguais nessa tese (sujeito composto) mesmo
        # com um só benefício - ver comentário em teses.py
        t = texto(pedido_base(quantidade=1, tese_key='ausencia_nexo_causal_concausalidade'))
        assert 'tendo em vista que o nexo causal e de concausalidade foram afastados por decisão judicial' in t

    def test_dib_igual_dcb_usa_indice_singular_e_plural(self):
        t = texto(pedido_base(tese_key='dib_igual_dcb', quantidade=1))
        assert 'da base de cálculo do índice do FAP,' in t

        t_plural = texto(pedido_base(tese_key='dib_igual_dcb', quantidade=3, especies=['B91', 'B92']))
        assert 'da base de cálculo dos índices do FAP,' in t_plural

    def test_cat_nao_vinculada_usa_substantivo_fixo_e_ignora_especie(self):
        t = texto(pedido_base(quantidade=2, tese_key='cat_nao_vinculada', especies=[]))
        assert 'Nexos Técnicos Previdenciários (NTP)' in t
        assert 'B91' not in t

    def test_cat_nao_vinculada_singular_usa_substantivo_singular(self):
        t = texto(pedido_base(quantidade=1, tese_key='cat_nao_vinculada', especies=[]))
        assert 'Nexo Técnico Previdenciário (NTP) sem Comunicação de Acidente de Trabalho (CAT) vinculada ao benefício' in t

    def test_parametro_concomitancia_preenche_placeholder(self):
        t = texto(pedido_base(tese_key='concomitancia_outro_beneficio', parametro_valor='aposentadoria'))
        assert 'concedido enquanto o segurado já usufruía de outro benefício de aposentadoria' in t


class TestRotatividade:
    def test_singular_quantidade_1(self):
        t = texto(pedido_base(tese_key='rotatividade', quantidade=1, especies=[]))
        assert 'recálculo do índice do FAP em relação ao estabelecimento e à vigência abaixo arrolados' in t

    def test_plural_quantidade_2_ou_mais(self):
        t = texto(pedido_base(tese_key='rotatividade', quantidade=2, especies=[]))
        assert 'recálculo dos índices do FAP em relação aos estabelecimentos e à vigência abaixo arrolados' in t

        t5 = texto(pedido_base(tese_key='rotatividade', quantidade=5, especies=[]))
        assert 'recálculo dos índices do FAP em relação aos estabelecimentos e à vigência abaixo arrolados' in t5

    def test_vigencia_nao_varia_com_a_quantidade(self):
        # mesmo no plural, "vigência" continua no singular (pedido explícito do usuário)
        t = texto(pedido_base(tese_key='rotatividade', quantidade=3, especies=[]))
        assert 'vigências' not in t
        assert 'à vigência abaixo arrolados' in t


class TestCorrecaoComVigencia:
    def test_erro_massa_salarial_com_vigencias_informadas(self):
        t = texto(pedido_base(tese_key='erro_massa_salarial', especies=[], campo_texto_valor='jan/2020 a dez/2020'))
        assert 'correção do valor da massa salarial' in t
        assert 'jan/2020 a dez/2020' in t

    def test_erro_vinculos_sem_vigencias_usa_placeholder(self):
        t = texto(pedido_base(tese_key='erro_vinculos', especies=[], campo_texto_valor=None))
        assert 'vigências de xxxx estão corretos' in t


class TestFixoComVigencia:
    def test_prescricao_quinquenal(self):
        t = texto(pedido_base(tese_key='prescricao_quinquenal', especies=[], campo_texto_valor='2021', item_peticao='3'))
        assert t == (
            'Declarar a inexistência de prescrição do direito da empresa Autora de corrigir os erros '
            'cometidos na base de cálculo do FAP e reaver (compensar) seus créditos em relação à '
            'vigência de 2021, em razão da prescrição quinquenal, nos termos da fundamentação – item 3 '
            'da petição inicial.'
        )

    def test_contestacao_administrativa(self):
        t = texto(pedido_base(tese_key='contestacao_administrativa', especies=[], campo_texto_valor='2020', item_peticao='3'))
        assert t == (
            'Declarar a inexistência de prescrição do direito da empresa Autora de corrigir os erros '
            'cometidos na base de cálculo do FAP e reaver (compensar) seus créditos em relação à '
            'vigência de 2020, em razão do efeito suspensivo atribuído à contestação administrativa – '
            'item 3 da petição inicial.'
        )

    def test_sem_vigencia_informada_usa_placeholder(self):
        t = texto(pedido_base(tese_key='prescricao_quinquenal', especies=[], campo_texto_valor=None))
        assert 'em relação à vigência de xxxx, em razão' in t

    def test_mais_de_uma_vigencia_com_virgula_fica_no_plural(self):
        t = texto(pedido_base(tese_key='contestacao_administrativa', especies=[], campo_texto_valor='2023, 2024'))
        assert 'em relação às vigências de 2023, 2024, em razão' in t

    def test_mais_de_uma_vigencia_com_e_fica_no_plural(self):
        t = texto(pedido_base(tese_key='contestacao_administrativa', especies=[], campo_texto_valor='2023 e 2024'))
        assert 'em relação às vigências de 2023 e 2024, em razão' in t

    def test_uma_so_vigencia_fica_no_singular(self):
        t = texto(pedido_base(tese_key='contestacao_administrativa', especies=[], campo_texto_valor='2023'))
        assert 'em relação à vigência de 2023, em razão' in t

    def test_inexistencia_fica_em_negrito(self):
        doc = gerar_documento([pedido_base(tese_key='prescricao_quinquenal', especies=[], campo_texto_valor='2021')])
        runs_em_negrito = [r.text for r in doc.paragraphs[0].runs if r.bold]
        assert 'inexistência' in runs_em_negrito


class TestCustoCessado:
    def test_motivo_aposentadoria(self):
        t = texto(pedido_base(tese_key='custo_cessado', parametro_valor='aposentadoria'))
        assert 'correção do índice de custo' in t
        assert 'sendo este o dia imediatamente anterior à concessão da aposentadoria' in t

    def test_motivo_obito(self):
        t = texto(pedido_base(tese_key='custo_cessado', parametro_valor='obito'))
        assert 'esta correspondente ao dia imediatamente anterior ao óbito' in t


class TestNtpDuplicado:
    def test_singular(self):
        t = texto(pedido_base(tese_key='ntp_duplicado', especies=[], item_peticao='16'))
        assert t == (
            'Determinar a exclusão de 1 (um) Nexo Técnico Previdenciário (NTP) sem '
            'Comunicação de Acidente de Trabalho (CAT) vinculada ao benefício, abaixo '
            'arrolado, da base de cálculo do índice do FAP, por se tratar de evento '
            'acidentário considerado em duplicidade – item 16 da petição inicial.'
        )

    def test_plural(self):
        t = texto(pedido_base(tese_key='ntp_duplicado', quantidade=2, especies=[], item_peticao='16'))
        assert t == (
            'Determinar a exclusão de 2 (dois) Nexos Técnicos Previdenciário (NTP) sem '
            'Comunicação de Acidente de Trabalho (CAT) vinculadas aos benefícios, abaixo '
            'arrolados, da base de cálculo dos índices do FAP, por se tratar de eventos '
            'acidentários considerados em duplicidade – item 16 da petição inicial.'
        )


class TestCatDuplicada:
    def test_singular_no_feminino_e_sem_artigo(self):
        t = texto(pedido_base(tese_key='cat_duplicada', especies=[], item_peticao='11'))
        assert t == (
            'Determinar exclusão de 1 (uma) Comunicação de Acidente de Trabalho (CAT), '
            'abaixo arrolada, da base de cálculo do índice do FAP, por se tratar de '
            'comunicação acidentária em duplicidade para o mesmo acidente – item 11 da '
            'petição inicial.'
        )

    def test_plural_no_feminino_e_sem_artigo(self):
        t = texto(pedido_base(tese_key='cat_duplicada', quantidade=3, especies=[], item_peticao='11'))
        assert t == (
            'Determinar exclusão de 3 (três) Comunicações de Acidente de Trabalho (CATs), '
            'abaixo arroladas, da base de cálculo dos índices do FAP, por se tratar de '
            'comunicações acidentárias em duplicidade para os mesmos acidentes – item 11 '
            'da petição inicial.'
        )


class TestTeseSubsidiaria:
    def test_beneficio_unico_com_numero_fica_no_singular(self):
        pedido = pedido_base(grupos_subsidiarios=[
            grupo_subsidiario(numeros_com_especie=[('B91', '123456')]),
        ])
        t = texto(pedido)
        assert 'requer-se a exclusão do benefício B91 nº 123456, decorrente de acidente de trajeto' in t
        assert 'item 3.1 da petição inicial' in t

    def test_multiplos_beneficios_ficam_no_plural(self):
        pedido = pedido_base(grupos_subsidiarios=[
            grupo_subsidiario(numeros_com_especie=[('B91', '1'), ('B92', None)]),
        ])
        t = texto(pedido)
        assert 'requer-se a exclusão dos benefícios B91 nº 1 e B92, decorrentes de acidentes de trajeto' in t

    def test_heranca_dos_beneficios_do_principal_quando_sem_numeros(self):
        # Exemplo de regressão relatado pelo usuário: grupo sem benefícios próprios e
        # quantidade principal > 1 -> herda a espécie do principal, sempre no plural.
        pedido = pedido_base(
            quantidade=3, especies=['B91'], tese_key='acidente_sem_relacao_empresa', item_peticao='2',
            grupos_subsidiarios=[grupo_subsidiario(
                tese_subsidiaria_key='acidente_trajeto', item_peticao='3.1',
                todos_beneficios_principal=True, especies_principal=['B91'],
            )],
        )
        t = texto(pedido)
        assert t == (
            'Determinar a exclusão de 3 (três) benefícios de auxílio por incapacidade temporária por '
            'acidente de trabalho, espécie B91, abaixo arrolados, da base de cálculo dos índices do FAP, '
            'considerando que os acidentes de trabalho não têm relação com a empresa Autora – item 2 da '
            'petição inicial. Subsidiariamente, não sendo esse o entendimento de V. Exa., requer-se a '
            'exclusão dos benefícios B91, decorrentes de acidentes de trajeto – item 3.1 da petição inicial.'
        )

    def test_heranca_do_beneficio_do_principal_com_quantidade_1_fica_no_singular(self):
        # Com quantidade principal 1, só existe um benefício possível - não faz sentido
        # exigir que o número dele seja repetido na tese subsidiária, nem falar no plural.
        pedido = pedido_base(
            quantidade=1, especies=['B91'], tese_key='acidente_sem_relacao_empresa', item_peticao='2',
            grupos_subsidiarios=[grupo_subsidiario(
                tese_subsidiaria_key='acidente_trajeto', item_peticao='3.1',
                todos_beneficios_principal=True, especies_principal=['B91'], quantidade_principal=1,
            )],
        )
        t = texto(pedido)
        assert 'requer-se a exclusão do benefício B91, decorrente de acidente de trajeto' in t

    def test_multiplos_grupos_encadeados_com_separador(self):
        pedido = pedido_base(grupos_subsidiarios=[
            grupo_subsidiario(
                tese_subsidiaria_key='acidente_sem_relacao_empresa', item_peticao='2',
                numeros_com_especie=[('B91', '1'), ('B91', '2')],
            ),
            grupo_subsidiario(
                tese_subsidiaria_key='restabelecimento_beneficio_anterior', item_peticao='18',
                numeros_com_especie=[('B91', '3')],
            ),
        ])
        t = texto(pedido)
        assert (
            'item 2 da petição inicial –, e do benefício B91 nº 3, por se tratar de restabelecimento '
            'de benefício anterior – item 18 da petição inicial.'
        ) in t

    def test_grupo_com_parametro_proprio(self):
        pedido = pedido_base(grupos_subsidiarios=[
            grupo_subsidiario(
                tese_subsidiaria_key='custo_cessado', parametro_valor='obito',
                numeros_com_especie=[('B91', '1')],
            ),
        ])
        t = texto(pedido)
        assert 'esta correspondente ao dia imediatamente anterior ao óbito' in t
