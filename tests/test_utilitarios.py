from utilitarios import numero_extenso, numero_e_extenso


class TestNumeroExtensoMasculino:
    def test_um(self):
        assert numero_extenso(1) == 'um'

    def test_dois(self):
        assert numero_extenso(2) == 'dois'

    def test_tres_nao_varia_por_genero(self):
        assert numero_extenso(3) == 'três'

    def test_vinte_e_um(self):
        assert numero_extenso(21) == 'vinte e um'

    def test_duzentos(self):
        assert numero_extenso(200) == 'duzentos'

    def test_duzentos_e_um(self):
        assert numero_extenso(201) == 'duzentos e um'


class TestNumeroExtensoFeminino:
    def test_uma(self):
        assert numero_extenso(1, feminino=True) == 'uma'

    def test_duas(self):
        assert numero_extenso(2, feminino=True) == 'duas'

    def test_tres_igual_no_feminino(self):
        assert numero_extenso(3, feminino=True) == 'três'

    def test_vinte_e_uma(self):
        assert numero_extenso(21, feminino=True) == 'vinte e uma'

    def test_duzentas(self):
        assert numero_extenso(200, feminino=True) == 'duzentas'

    def test_duzentas_e_uma(self):
        assert numero_extenso(201, feminino=True) == 'duzentas e uma'

    def test_cem_nao_varia(self):
        # "cem" e "cento" não têm forma feminina em português
        assert numero_extenso(100, feminino=True) == 'cem'
        assert numero_extenso(101, feminino=True) == 'cento e uma'


class TestNumeroEExtenso:
    def test_formato_masculino(self):
        assert numero_e_extenso(3) == '3 (três)'

    def test_formato_feminino(self):
        assert numero_e_extenso(1, feminino=True) == '1 (uma)'
