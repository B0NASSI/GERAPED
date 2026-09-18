import unicodedata


def normalizar(texto):
    sem_acento = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    return sem_acento.strip().lower()


def numero_extenso(n):
    unidades = ['zero', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove']
    dez_a_dezenove = ['dez', 'onze', 'doze', 'treze', 'quatorze', 'quinze', 'dezesseis', 'dezessete', 'dezoito', 'dezenove']
    dezenas = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa']
    centenas = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos']

    if n < 0 or n >= 1000:
        return str(n)
    if n < 10:
        return unidades[n]
    if n < 20:
        return dez_a_dezenove[n - 10]
    if n < 100:
        dezena, unidade = divmod(n, 10)
        if unidade == 0:
            return dezenas[dezena]
        return f"{dezenas[dezena]} e {unidades[unidade]}"
    if n == 100:
        return 'cem'
    centena, resto = divmod(n, 100)
    if resto == 0:
        return centenas[centena]
    return f"{centenas[centena]} e {numero_extenso(resto)}"


def numero_e_extenso(n):
    return f"{n} ({numero_extenso(n)})"
