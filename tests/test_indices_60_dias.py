"""Pedido de 60 dias: o benefício fica no FAP por no máximo 2 vigências (somadas as do anterior);
da 3ª em diante o pedido também exclui o custo."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autopedidos.tabelas import FREQ_GRAV as FG, FREQ_GRAV_CUSTO as FGC, indices_por_vigencia  # noqa: E402


def test_anterior_ja_usou_as_duas_vigencias():          # exemplo 1: anterior 2019-2020
    assert indices_por_vigencia(['2021', '2022'], ['2019', '2020']) == [('2021', FGC), ('2022', FGC)]


def test_anterior_sobrepoe_uma_vigencia():              # exemplo 2: anterior 2020-2021
    assert indices_por_vigencia(['2021', '2022'], ['2020', '2021']) == [('2021', FG), ('2022', FGC)]


def test_anterior_fora_do_fap_conta_zero():             # "-" na tabela (B31 ou B91 raro)
    assert indices_por_vigencia(['2021', '2022'], []) == [('2021', FG), ('2022', FG)]


def test_anterior_com_uma_vigencia():
    assert indices_por_vigencia(['2021', '2022'], ['2020']) == [('2021', FG), ('2022', FGC)]
