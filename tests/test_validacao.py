import pytest

from validacao import (
    validar_quantidade, validar_especies, limite_especies_excedido, limitar_especies,
    validar_itens_duplicados, especie_unica_travada, beneficio_subsidiario_pode_herdar_do_principal,
    validar_beneficios_subsidiaria,
)


class TestValidarQuantidade:
    def test_aceita_numero_valido(self):
        assert validar_quantidade('3') == 3

    @pytest.mark.parametrize('texto', ['0', '-1', '', 'abc', '1.5'])
    def test_rejeita_valores_invalidos(self, texto):
        with pytest.raises(ValueError):
            validar_quantidade(texto)


class TestLimiteEspecies:
    def test_nao_excede_quando_cabe(self):
        assert limite_especies_excedido(2, ['B91', 'B92']) is False

    def test_excede_quando_mais_especies_que_quantidade(self):
        assert limite_especies_excedido(2, ['B91', 'B92', 'B93']) is True

    def test_sem_quantidade_definida_nunca_excede(self):
        assert limite_especies_excedido(None, ['B91', 'B92', 'B93', 'B94', 'B31']) is False

    def test_limitar_trunca_preservando_ordem(self):
        assert limitar_especies(['B92', 'B91', 'B94'], 2) == ['B92', 'B91']

    def test_limitar_sem_quantidade_nao_trunca(self):
        assert limitar_especies(['B92', 'B91', 'B94'], None) == ['B92', 'B91', 'B94']


class TestValidarEspecies:
    def test_exige_ao_menos_uma_especie(self):
        with pytest.raises(ValueError):
            validar_especies('acidente_trajeto', [], quantidade=1)

    def test_bloqueia_mais_especies_que_quantidade(self):
        with pytest.raises(ValueError):
            validar_especies('acidente_trajeto', ['B91', 'B92', 'B93'], quantidade=2)

    def test_aceita_dentro_do_limite(self):
        validar_especies('acidente_trajeto', ['B91', 'B92'], quantidade=2)

    def test_tese_que_ignora_especie_nao_exige_nada(self):
        # rotatividade tem 'ignora_especie': True em teses.py
        validar_especies('rotatividade', [], quantidade=1)


class TestItensDuplicados:
    def test_sem_duplicata_nao_lanca(self):
        validar_itens_duplicados(['5.1', '5.2', '6'])

    def test_detecta_duplicata_e_aponta_os_pedidos(self):
        with pytest.raises(ValueError, match='Pedido 1.*Pedido 3'):
            validar_itens_duplicados(['5.1', '5.2', '5.1'])


class TestEspecieUnicaTravada:
    def test_retorna_a_especie_quando_uma_so_valida(self):
        assert especie_unica_travada(['B91'], ['B91', 'B92', 'B93', 'B94']) == 'B91'

    def test_none_quando_mais_de_uma(self):
        assert especie_unica_travada(['B91', 'B92'], ['B91', 'B92', 'B93', 'B94']) is None

    def test_none_quando_especie_nao_e_valida_para_subsidiaria(self):
        # B31 não é uma espécie válida para teses subsidiárias
        assert especie_unica_travada(['B31'], ['B91', 'B92', 'B93', 'B94']) is None


class TestHerancaBeneficioSubsidiario:
    def test_pode_herdar_com_quantidade_maior_que_1(self):
        assert beneficio_subsidiario_pode_herdar_do_principal(2) is True

    def test_nao_pode_herdar_com_quantidade_1(self):
        assert beneficio_subsidiario_pode_herdar_do_principal(1) is False

    def test_nao_pode_herdar_sem_quantidade(self):
        assert beneficio_subsidiario_pode_herdar_do_principal(None) is False


class TestValidarBeneficiosSubsidiaria:
    def test_nenhum_beneficio_e_permitido(self):
        # caminho normal para "todos os benefícios desta tese subsidiária"
        validar_beneficios_subsidiaria([], quantidade_principal=3)

    def test_um_so_beneficio_sem_numero_e_bloqueado(self):
        with pytest.raises(ValueError, match='número'):
            validar_beneficios_subsidiaria([('B91', None)], quantidade_principal=3)

    def test_mais_de_um_beneficio_sem_numero_e_bloqueado(self):
        # exatamente o caso relatado: 7 linhas de B91 sem número, virando "B91, B91, ..."
        with pytest.raises(ValueError, match='número'):
            validar_beneficios_subsidiaria([('B91', None)] * 7, quantidade_principal=3)

    def test_mais_de_um_beneficio_com_numero_em_cada_e_permitido(self):
        validar_beneficios_subsidiaria([('B91', '1'), ('B91', '2')], quantidade_principal=3)

    def test_um_beneficio_faltando_numero_entre_varios_e_bloqueado(self):
        with pytest.raises(ValueError, match='número'):
            validar_beneficios_subsidiaria([('B91', '1'), ('B91', None)], quantidade_principal=3)

    def test_nao_pode_exceder_quantidade_do_pedido_principal(self):
        with pytest.raises(ValueError, match='apenas 3'):
            validar_beneficios_subsidiaria(
                [('B91', '1'), ('B91', '2'), ('B91', '3'), ('B91', '4')], quantidade_principal=3,
            )

    def test_dentro_do_limite_e_permitido(self):
        validar_beneficios_subsidiaria([('B91', '1'), ('B91', '2'), ('B91', '3')], quantidade_principal=3)

    def test_sem_quantidade_principal_nao_bloqueia_por_limite(self):
        validar_beneficios_subsidiaria([('B91', '1'), ('B91', '2')], quantidade_principal=None)
