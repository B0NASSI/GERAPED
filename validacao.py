# Regras de negócio do formulário de pedidos - sem qualquer dependência de Tkinter, para
# poderem ser testadas isoladamente (ver TESTES/test_validacao.py) e reaproveitadas tanto
# pelos handlers interativos da UI (feedback imediato) quanto na validação final antes de
# gerar o documento (garantia, para o caso de o estado da UI escapar das restrições
# interativas - ex: registro restaurado, ordem de eventos inesperada etc.).

from teses import TESES


def validar_quantidade(texto):
    """Converte e valida o texto do campo "Quantidade de benefícios"."""
    if not texto.isdigit() or int(texto) < 1:
        raise ValueError('Informe uma quantidade válida de benefícios (número inteiro maior que zero).')
    return int(texto)


def limite_especies_excedido(quantidade, especies):
    """Não faz sentido citar mais espécies do que a quantidade de benefícios (ex: "2
    benefícios de espécies B91, B92 e B93" exigiria pelo menos 3 benefícios)."""
    return quantidade is not None and len(especies) > quantidade


def limitar_especies(especies_marcadas, quantidade):
    """Trunca a lista de espécies marcadas para caber no limite da quantidade, preservando
    a ordem em que foram marcadas. Usado para reagir a mudanças de quantidade na UI."""
    if quantidade is None:
        return list(especies_marcadas)
    return list(especies_marcadas[:quantidade])


def validar_especies(tese_key, especies, quantidade):
    if TESES[tese_key].get('ignora_especie'):
        return
    if not especies:
        raise ValueError('Selecione ao menos uma espécie do benefício.')
    if limite_especies_excedido(quantidade, especies):
        raise ValueError(f'Com quantidade {quantidade}, selecione no máximo {quantidade} espécie(s) de benefício.')


def validar_itens_duplicados(itens_peticao):
    """itens_peticao: lista do item da petição de cada pedido PRINCIPAL, na ordem da tela
    (pedidos subsidiários ficam de fora dessa checagem - é comum retomarem o mesmo item).
    Lança ValueError apontando os dois pedidos (1-indexados) que colidem."""
    itens_vistos = {}
    for i, item in enumerate(itens_peticao, start=1):
        if item in itens_vistos:
            raise ValueError(
                f'O item "{item}" já foi usado no Pedido {itens_vistos[item]} e no Pedido {i}. '
                'Cada pedido principal deve ter um item da petição inicial diferente.'
            )
        itens_vistos[item] = i


def especie_unica_travada(especies_marcadas, especies_validas_subsidiaria):
    """Se a tese principal citar uma só espécie (e ela valer para as teses subsidiárias),
    retorna essa espécie, para travar a escolha nas teses subsidiárias. Caso contrário,
    None (escolha livre)."""
    if len(especies_marcadas) == 1 and especies_marcadas[0] in especies_validas_subsidiaria:
        return especies_marcadas[0]
    return None


def beneficio_subsidiario_pode_herdar_do_principal(quantidade_principal):
    """Uma tese subsidiária sem benefícios próprios informados só pode herdar "todos os
    benefícios do pedido principal" quando a quantidade principal for maior que 1 (com
    quantidade 1 o benefício já é o próprio, então precisa ser informado)."""
    return bool(quantidade_principal and quantidade_principal > 1)


def validar_beneficios_subsidiaria(numeros_com_especie, quantidade_principal):
    """numeros_com_especie: lista de (especie, numero_ou_None) informados em UMA tese
    subsidiária. Duas regras, isoladas por tese subsidiária (repetir o mesmo benefício em
    teses subsidiárias diferentes é permitido - representa alternativas para o mesmo
    benefício):

    - Com mais de um benefício informado, o número de cada um é obrigatório (senão o texto
      gerado repete a mesma espécie várias vezes sem identificar qual benefício é qual,
      ex: "dos benefícios B91, B91 e B91").
    - Uma tese subsidiária, isoladamente, não pode citar mais benefícios do que a
      quantidade do pedido principal (não existem mais benefícios do que isso)."""
    if len(numeros_com_especie) > 1 and any(numero is None for _, numero in numeros_com_especie):
        raise ValueError('com mais de um benefício, informe o número de cada um deles.')
    if quantidade_principal is not None and len(numeros_com_especie) > quantidade_principal:
        raise ValueError(
            f'informou {len(numeros_com_especie)} benefícios, mas o pedido principal tem '
            f'apenas {quantidade_principal}.'
        )
