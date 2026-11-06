"""Ponto único de importação da lógica do GERAPED usada pelo motor de leitura da petição.

Nesta pasta (GERAPED-Integrado) teses.py, validacao.py e gerador_pedido.py são os do PRÓPRIO app,
na raiz - não há mais cópia em vendor/."""
import gerador_pedido   # noqa: F401
import teses            # noqa: F401
import validacao        # noqa: F401

TESES = teses.TESES
PARAMETROS_TESE = teses.PARAMETROS_TESE
